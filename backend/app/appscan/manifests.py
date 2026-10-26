"""Reads dependency lists from manifest files. It only parses text: nothing is installed, imported, executed or
fetched, nothing is written to disk, and no network is used. Lifecycle scripts, `postinstall` hooks and the like
are ignored as plain data.

Supported (v1): `package-lock.json` (lockfile v1, v2, v3), `package.json` (exact versions only) and
`requirements.txt` (pinned `==` versions only). Anything else is reported as unsupported, never guessed.

Raw lines and values are never copied into results, so a token pasted into a requirements line cannot be stored."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any

MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_PACKAGES = 20_000
MAX_FILES_PER_SCAN = 5
MAX_JSON_DEPTH = 64
MAX_NAME_LENGTH = 214
MAX_UNSUPPORTED = 200
SUPPORTED_FILES = ("package-lock.json", "package.json", "requirements.txt")
# Leading bytes of common archive and binary formats. Archives are refused in v1.
_BINARY_MAGIC = (
    b"PK\x03\x04",
    b"\x1f\x8b",
    b"7z\xbc\xaf",
    b"Rar!",
    b"\x7fELF",
    b"MZ",
    b"%PDF",
    b"\x89PNG",
    b"BZh",
)

_NPM_NAME = re.compile(r"^(?:@[a-z0-9][a-z0-9._~-]*/)?[a-z0-9][a-z0-9._~-]*$")
_NPM_EXACT = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
_PY_NAME = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$")
_PY_PIN = re.compile(
    r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[A-Za-z0-9,._\s-]*\])?\s*==\s*(?P<version>[A-Za-z0-9][A-Za-z0-9.!+_-]*)\s*(?:;.*)?$"
)


class ManifestError(ValueError):
    """The file cannot be read as a manifest. `code` is stable; the message is fixed text that never contains the
    file's content."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class Package:
    ecosystem: str  # "npm" or "PyPI"
    name: str
    version: str
    source_file: str
    dev: bool = False


@dataclass(frozen=True, slots=True)
class Unsupported:
    """Something the parser saw but cannot check. The reason is fixed text; no input text is copied."""

    source_file: str
    reason: str
    name: str | None = None


@dataclass(slots=True)
class ParseResult:
    file_name: str
    size: int
    sha256: str
    packages: list[Package] = field(default_factory=list)
    unsupported: list[Unsupported] = field(default_factory=list)
    unsupported_truncated: bool = False


def _skip(result: ParseResult, reason: str, name: str | None = None) -> None:
    if len(result.unsupported) >= MAX_UNSUPPORTED:
        result.unsupported_truncated = True
        return
    result.unsupported.append(Unsupported(result.file_name, reason, name))


def _add(result: ParseResult, seen: set[tuple[str, str]], package: Package) -> None:
    key = (package.name, package.version)
    if key in seen:
        return
    if len(result.packages) >= MAX_PACKAGES:
        raise ManifestError("too_many_packages", f"The file lists more than {MAX_PACKAGES} packages.")
    seen.add(key)
    result.packages.append(package)


def _check_json_depth(text: str) -> None:
    """Rejects deeply nested JSON before the parser sees it (a hostile file can otherwise exhaust the stack)."""
    depth = 0
    in_string = False
    escaped = False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char in "[{":
            depth += 1
            if depth > MAX_JSON_DEPTH:
                raise ManifestError("too_deep", "The file is nested too deeply to read.")
        elif char in "]}":
            depth -= 1


def _decode(file_name: str, data: bytes) -> str:
    if file_name not in SUPPORTED_FILES:
        raise ManifestError(
            "unsupported_format",
            "This file type is not supported. Use package-lock.json, package.json or requirements.txt.",
        )
    if len(data) > MAX_FILE_BYTES:
        raise ManifestError("too_large", f"The file is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB.")
    if not data.strip():
        raise ManifestError("empty", "The file is empty.")
    if data.startswith(_BINARY_MAGIC) or b"\x00" in data:
        raise ManifestError("not_text", "The file is binary or an archive. Upload the manifest file itself.")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ManifestError("not_text", "The file is not valid UTF-8 text.") from exc


def _load_json(text: str) -> dict[str, Any]:
    _check_json_depth(text)
    try:
        value = json.loads(text)
    except (json.JSONDecodeError, RecursionError) as exc:
        raise ManifestError("malformed", "The file is not valid JSON.") from exc
    if not isinstance(value, dict):
        raise ManifestError("malformed", "The file does not have the expected structure.")
    return value


def _npm_name_from_path(path: str) -> str | None:
    marker = "node_modules/"
    index = path.rfind(marker)
    return path[index + len(marker) :] if index != -1 else None


def _valid_npm(name: object, version: object) -> bool:
    return (
        isinstance(name, str)
        and isinstance(version, str)
        and len(name) <= MAX_NAME_LENGTH
        and bool(_NPM_NAME.match(name))
        and bool(_NPM_EXACT.match(version))
    )


def _parse_package_lock(result: ParseResult, text: str) -> None:
    data = _load_json(text)
    seen: set[tuple[str, str]] = set()
    packages = data.get("packages")
    if isinstance(packages, dict):  # lockfile v2 and v3
        for path, entry in packages.items():
            if path == "" or not isinstance(entry, dict) or not isinstance(path, str):
                continue
            name = entry.get("name") if isinstance(entry.get("name"), str) else _npm_name_from_path(path)
            version = entry.get("version")
            if entry.get("link") or entry.get("inBundle") and not version:
                _skip(
                    result,
                    "A linked or bundled package has no registry version.",
                    name if isinstance(name, str) else None,
                )
                continue
            if not _valid_npm(name, version):
                _skip(result, "A package entry has no valid registry name and exact version.")
                continue
            resolved = entry.get("resolved")
            if isinstance(resolved, str) and not resolved.startswith(("https://", "http://")):
                _skip(result, "A package is not installed from a registry address.", name)
                continue
            _add(
                result,
                seen,
                Package("npm", str(name), str(version), result.file_name, bool(entry.get("dev"))),
            )
        return
    legacy = data.get("dependencies")
    if isinstance(legacy, dict) and data.get("lockfileVersion") in (1, None):
        _walk_legacy(result, legacy, seen, 0)
        return
    raise ManifestError(
        "malformed", "No package list was found. Is this a package-lock.json from npm 5 or later?"
    )


def _walk_legacy(result: ParseResult, deps: dict[str, Any], seen: set[tuple[str, str]], depth: int) -> None:
    if depth > MAX_JSON_DEPTH:
        raise ManifestError("too_deep", "The file is nested too deeply to read.")
    for name, entry in deps.items():
        if not isinstance(entry, dict):
            continue
        version = entry.get("version")
        if _valid_npm(name, version):
            _add(result, seen, Package("npm", name, str(version), result.file_name, bool(entry.get("dev"))))
        else:
            _skip(result, "A package entry has no valid registry name and exact version.")
        nested = entry.get("dependencies")
        if isinstance(nested, dict):
            _walk_legacy(result, nested, seen, depth + 1)


def _parse_package_json(result: ParseResult, text: str) -> None:
    data = _load_json(text)
    seen: set[tuple[str, str]] = set()
    found_section = False
    for section, dev in (("dependencies", False), ("devDependencies", True), ("optionalDependencies", False)):
        deps = data.get(section)
        if not isinstance(deps, dict):
            continue
        found_section = True
        for name, spec in deps.items():
            if (
                not isinstance(spec, str)
                or not isinstance(name, str)
                or not _NPM_NAME.match(name)
                or len(name) > MAX_NAME_LENGTH
            ):
                _skip(result, "A dependency entry is not a valid package name and version.")
            elif _NPM_EXACT.match(spec):
                _add(result, seen, Package("npm", name, spec, result.file_name, dev))
            else:
                _skip(
                    result,
                    "The version is a range or an address, not an exact version. Use package-lock.json for exact versions.",
                    name,
                )
    if not found_section:
        raise ManifestError("malformed", "No dependency list was found in package.json.")


def _logical_lines(text: str) -> list[str]:
    lines: list[str] = []
    buffer = ""
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.endswith("\\"):
            buffer += line[:-1] + " "
            continue
        lines.append(buffer + line)
        buffer = ""
    if buffer:
        lines.append(buffer)
    return lines


def _parse_requirements(result: ParseResult, text: str) -> None:
    seen: set[tuple[str, str]] = set()
    saw_requirement = False
    for line in _logical_lines(text):
        stripped = re.sub(r"(^|\s)#.*$", "", line).strip()
        if not stripped:
            continue
        if stripped.startswith("-"):
            _skip(result, "An option line (such as -r, -e or an index setting) is not followed or checked.")
            continue
        saw_requirement = True
        if (
            "://" in stripped
            or stripped.startswith(("git+", ".", "/", "file:"))
            or "@" in stripped.split(";")[0]
        ):
            _skip(result, "A requirement from an address or a local path has no registry version.")
            continue
        # Hashes follow the version on the same logical line.
        requirement = re.split(r"\s--hash=", stripped)[0].strip()
        match = _PY_PIN.match(requirement)
        if not match:
            _skip(result, "The version is not pinned with == so it cannot be checked exactly.")
            continue
        name = re.sub(r"[-_.]+", "-", match.group("name")).lower()
        if len(name) > MAX_NAME_LENGTH or not _PY_NAME.match(name):
            _skip(result, "A requirement name is not valid.")
            continue
        _add(result, seen, Package("PyPI", name, match.group("version"), result.file_name))
    if not saw_requirement:
        raise ManifestError("malformed", "No requirements were found in the file.")


def parse_manifest(file_name: str, data: bytes) -> ParseResult:
    """Parses one manifest. Raises ManifestError for anything that cannot be read; never executes anything."""
    text = _decode(file_name, data)
    result = ParseResult(file_name=file_name, size=len(data), sha256=hashlib.sha256(data).hexdigest())
    if file_name == "package-lock.json":
        _parse_package_lock(result, text)
    elif file_name == "package.json":
        _parse_package_json(result, text)
    else:
        _parse_requirements(result, text)
    return result
