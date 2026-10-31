"""CVSS v3.0 / v3.1 base score from a vector string, as the FIRST specification defines it. Advisory sources often
give only the vector (for example "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"), not the number. Pure arithmetic:
anything that is not a complete, valid v3 base vector gives None, never a guessed score."""

from __future__ import annotations

import math

_AV = {"N": 0.85, "A": 0.62, "L": 0.55, "P": 0.2}
_AC = {"L": 0.77, "H": 0.44}
_PR_UNCHANGED = {"N": 0.85, "L": 0.62, "H": 0.27}
_PR_CHANGED = {"N": 0.85, "L": 0.68, "H": 0.5}
_UI = {"N": 0.85, "R": 0.62}
_CIA = {"H": 0.56, "L": 0.22, "N": 0.0}
_BASE = ("AV", "AC", "PR", "UI", "S", "C", "I", "A")


def _roundup(value: float) -> float:
    """The CVSS v3.1 Roundup: the smallest number with one decimal that is equal to or higher than the input,
    computed on integers so floating-point noise cannot push 4.0 to 4.1."""
    whole = round(value * 100_000)
    if whole % 10_000 == 0:
        return whole / 100_000
    return (math.floor(whole / 10_000) + 1) / 10.0


def base_score(vector: str) -> float | None:
    parts = vector.strip().split("/")
    if not parts or parts[0] not in ("CVSS:3.0", "CVSS:3.1"):
        return None
    metrics: dict[str, str] = {}
    for part in parts[1:]:
        key, sep, value = part.partition(":")
        if not sep or key in metrics:
            return None
        metrics[key] = value
    if any(k not in metrics for k in _BASE):
        return None
    try:
        changed = {"U": False, "C": True}[metrics["S"]]
        av, ac, ui = _AV[metrics["AV"]], _AC[metrics["AC"]], _UI[metrics["UI"]]
        pr = (_PR_CHANGED if changed else _PR_UNCHANGED)[metrics["PR"]]
        c, i, a = _CIA[metrics["C"]], _CIA[metrics["I"]], _CIA[metrics["A"]]
    except KeyError:
        return None
    iss = 1 - (1 - c) * (1 - i) * (1 - a)
    impact = 7.52 * (iss - 0.029) - 3.25 * (iss - 0.02) ** 15 if changed else 6.42 * iss
    if impact <= 0:
        return 0.0
    exploitability = 8.22 * av * ac * pr * ui
    total = (impact + exploitability) * (1.08 if changed else 1.0)
    return _roundup(min(total, 10.0))
