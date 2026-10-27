"""Redaction rules for App Scanning: no part of a secret may survive, and ordinary text must be left alone."""

from __future__ import annotations

import logging
import time

import pytest

from app.appscan import redaction as r
from app.tests.canary import all_text, assert_no_canary, capture_logs, make_canary

# Built from pieces so this source file holds no string that looks like a credential.
SAMPLES = {
    "aws-access-key-id": "AK" + "IA" + "Q7ZP4M2XK9WD3LRT",
    "github-token": "gh" + "p_" + "aB3dE5fG7hJ9kL1mN3pQ5rS7tU9vW1xY3zA5",
    "slack-token": "xo" + "xb-" + "1234567890-abcdefghij",
    "google-api-key": "AI" + "za" + "SyA1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q",
    "npm-token": "np" + "m_" + "aB3dE5fG7hJ9kL1mN3pQ5rS7tU9vW1xY3zA",
    "provider-secret-key": "sk" + "_live_" + "aB3dE5fG7hJ9kL1mN3pQ5",
    "securescope-token": "ss" + "k_" + "aB3dE5fG7hJ9kL1mN3pQ5rS7tU9vW1xY3zA5bC7dE9fG",
    "json-web-token": "ey"
    + "JhbGciOiJIUzI1NiJ9."
    + "ey"
    + "JzdWIiOiIxMjM0NTY3ODkwIn0."
    + "dBjftJeZ4CVPmB92K27uhbUJU1p1r",
    "bearer-credential": "Bear" + "er " + "aB3dE5fG7hJ9kL1mN3pQ5rS7",
    "url-with-credentials": "postgres" + "://admin:" + "S3cr3tPw0rd" + "@db.example.net/app",
}


def _assert_gone(secret: str, output: str) -> None:
    assert secret not in output
    # No tail or head of the secret may survive either (a mask that keeps the last four characters is a leak).
    assert secret[-6:] not in output
    assert secret[:6] not in output or secret[:6] in {"Bearer", "postgr"}


@pytest.mark.parametrize(("rule", "secret"), SAMPLES.items())
def test_known_shapes_are_removed_completely(rule: str, secret: str) -> None:
    text = f"found in config: {secret} (line 4)"
    out = r.redact_text(text)
    _assert_gone(secret.split(" ")[-1] if rule == "bearer-credential" else secret, out)
    assert "[REDACTED:" in out
    assert out.startswith("found in config: ")
    assert r.contains_secret(text)


def test_private_key_block_is_removed_whole() -> None:
    body = "MIIEvQIBADANBgkqhkiG9w0BAQEFAASC" + "KcwggSjAgEAAoIBAQDXYZ"
    text = "-----BEGIN " + "PRIVATE KEY-----\n" + body + "\n-----END " + "PRIVATE KEY-----\nafter"
    out = r.redact_text(text)
    assert body not in out
    assert out.endswith("after")


def test_assignment_keeps_name_and_drops_value() -> None:
    out = r.redact_text('DB_PASSWORD = "hunter2hunter2"\napi_key: abcd1234efgh')
    assert "hunter2" not in out and "abcd1234efgh" not in out
    assert "DB_PASSWORD" in out and "api_key" in out


@pytest.mark.parametrize(
    "text",
    [
        "password = <your-password>",
        "token = ${GITHUB_TOKEN}",
        "secret: changeme",
        "api_key = xxxxxxxx",
        "Use a strong password for the admin account.",
        "src/components/authentication/handlers/loginHandler.ts line 42",
        "sha256 " + "a" * 64,
        "commit " + "0123456789abcdef" * 2 + "01234567",
        "lodash 4.17.20 is affected by CVE-2021-23337 (prototype pollution)",
        "Upgrade express from 4.16.0 to 4.19.2",
        "https://github.com/advisories/GHSA-xxxx-yyyy-zzzz",
    ],
)
def test_ordinary_text_is_left_alone(text: str) -> None:
    assert r.redact_text(text) == text
    assert not r.contains_secret(text)


def test_high_entropy_string_is_removed() -> None:
    token = "Zk8qP2vXr7LmN4tYb9WcD3sFh6JgA1eU"
    out = r.redact_text(f"value {token} end")
    assert token not in out and "[REDACTED:high-entropy-string]" in out


def test_redaction_is_idempotent() -> None:
    text = f"x {SAMPLES['github-token']} y password=hunter2hunter2"
    once = r.redact_text(text)
    assert r.redact_text(once) == once


def test_nested_values_and_keys_are_redacted() -> None:
    canary = make_canary()
    data = {"title": f"leaked {canary}", "list": [{"evidence": canary}, 5, None], canary: "key"}
    out = r.redact_value(data)
    assert_no_canary(canary, out)
    assert out["list"][1] == 5 and out["list"][2] is None


def test_nesting_depth_is_limited() -> None:
    deep: object = "x"
    for _ in range(r.MAX_DEPTH + 3):
        deep = [deep]
    with pytest.raises(ValueError, match="nested too deeply"):
        r.redact_value(deep)
    with pytest.raises(ValueError, match="nested too deeply"):
        r.reject_if_secret(deep)


def test_rejection_message_never_echoes_content() -> None:
    canary = make_canary()
    with pytest.raises(r.SecretRejected) as caught:
        r.reject_if_secret({"findings": [{"evidence": f"token {canary}"}]})
    assert_no_canary(canary, str(caught.value), repr(caught.value), caught.value.args)
    assert str(caught.value) == r.REJECTION_MESSAGE


def test_clean_submission_is_accepted() -> None:
    r.reject_if_secret({"rule": "python.lang.eval", "path": "src/app.py", "line": 12, "title": "Use of eval"})


def test_oversized_text_is_not_assumed_clean() -> None:
    tail_canary = make_canary()
    text = "a " * (r.MAX_TEXT_CHARS // 2 + 10) + tail_canary
    assert r.contains_secret(text)
    out = r.redact_text(text)
    assert_no_canary(tail_canary, out)
    assert out.endswith("[truncated]")


def test_pathological_input_is_fast() -> None:
    """Regression: an earlier assignment pattern took over a second on 5,000 dotted characters (quadratic)."""
    n = r.MAX_TEXT_CHARS
    cases = [
        "a" * n,
        "a." * (n // 2),
        "a:" * (n // 2),
        "a/" * (n // 2),
        "http://a:" * (n // 9),
        "Bearer " * (n // 7),
        "token = " * (n // 8),
        "password=" * (n // 9),
        "aB1_" * (n // 4),
        "A1" * (n // 2),
        ("-----BEGIN " + "PRIVATE KEY-----") * (n // 27),
    ]
    for text in cases:
        start = time.perf_counter()
        r.redact_text(text)
        r.contains_secret(text)
        assert time.perf_counter() - start < 1.5, text[:20]


def test_matches_hold_no_part_of_the_value() -> None:
    secret = SAMPLES["github-token"]
    matches = r.find_secrets(f"a {secret} b")
    assert matches and all(not hasattr(m, "value") for m in matches)
    assert secret not in repr(matches)
    assert matches[0].length == len(secret)


@pytest.mark.parametrize(
    ("length", "expected"),
    [
        (0, "under 8 characters"),
        (7, "under 8 characters"),
        (8, "8 to 19 characters"),
        (19, "8 to 19 characters"),
        (20, "20 to 39 characters"),
        (39, "20 to 39 characters"),
        (40, "40 to 99 characters"),
        (99, "40 to 99 characters"),
        (100, "100 characters or more"),
    ],
)
def test_length_class_never_reports_exact_length(length: int, expected: str) -> None:
    assert r.length_class(length) == expected


def test_fingerprint_is_keyed_stable_and_hides_the_value() -> None:
    secret = make_canary()
    key = b"k" * 32
    first = r.secret_fingerprint(key, secret)
    assert first == r.secret_fingerprint(key, secret)
    assert first != r.secret_fingerprint(b"j" * 32, secret)
    assert first != r.secret_fingerprint(key, secret + "x")
    assert len(first) == 32
    assert_no_canary(secret, first)
    with pytest.raises(ValueError, match="too short"):
        r.secret_fingerprint(b"short", secret)


def test_canary_harness_detects_a_leak_and_captures_logs() -> None:
    canary = make_canary()
    assert canary != make_canary()
    with pytest.raises(AssertionError):
        assert_no_canary(canary, f"prefix {canary[:10]} suffix")  # a partial leak is still a leak
    assert_no_canary(canary, "clean", b"clean bytes")

    handler, lines = capture_logs()
    log = logging.getLogger("appscan-canary-test")
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    try:
        log.info("scan %s finished with %d findings", "abc123", 3)
    finally:
        log.removeHandler(handler)
    assert_no_canary(canary, all_text(lines))
