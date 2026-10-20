"""Test helper: certificates with chosen validity dates, made with the openssl command line.

No Python crypto dependency is needed. Tests that use it skip themselves when openssl is not installed.
"""

from __future__ import annotations

import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

OPENSSL = shutil.which("openssl")


def stamp(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y%m%d%H%M%SZ")


def make_cert(directory: Path, name: str, host: str, *, days_from: int, days_to: int) -> tuple[Path, Path]:
    """A self-signed certificate for `host` valid from now+days_from to now+days_to (days may be negative)."""
    assert OPENSSL is not None
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "index.txt").write_text("")
    (directory / "serial").write_text("01\n")
    (directory / "newcerts").mkdir(exist_ok=True)
    (directory / "ca.cnf").write_text(
        f"""[ca]
default_ca = CA_default
[CA_default]
dir = {directory}
database = {directory}/index.txt
new_certs_dir = {directory}/newcerts
serial = {directory}/serial
default_md = sha256
policy = policy_any
unique_subject = no
[policy_any]
commonName = supplied
[ext]
subjectAltName = DNS:{host}
basicConstraints = critical,CA:TRUE
keyUsage = critical,digitalSignature,keyCertSign
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid
"""
    )

    def run(*args: str) -> None:
        subprocess.run(args, check=True, capture_output=True)

    key, csr, cert = directory / f"{name}.key", directory / f"{name}.csr", directory / f"{name}.pem"
    run(
        "openssl",
        "req",
        "-new",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-keyout",
        str(key),
        "-out",
        str(csr),
        "-subj",
        f"/CN={host}",
    )
    now = datetime.now(UTC)
    run(
        "openssl", "ca", "-batch", "-config", str(directory / "ca.cnf"), "-selfsign", "-keyfile", str(key),
        "-in", str(csr), "-out", str(cert), "-startdate", stamp(now + timedelta(days=days_from)),
        "-enddate", stamp(now + timedelta(days=days_to)), "-extensions", "ext", "-notext",
    )  # fmt: skip
    return cert, key
