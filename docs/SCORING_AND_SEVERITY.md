# Scoring and severity

SecureScope reports passive observations. This page says how a finding gets its severity, how the score is worked out,
and what neither of them can tell you. The score numbers below are checked against the code by a test
(`backend/app/tests/test_score_method.py`), so this page cannot drift from the product.

## What the score is

A heuristic summary of one scan. It starts at 100 and each scored finding takes points off by severity. Informational
notes take off nothing. The same findings always give the same score, whatever order they were found in.

| Severity | Points off |
| --- | --- |
| critical | 40 |
| high | 20 |
| medium | 10 |
| low | 4 |
| info | 0 |

| Grade | Score from |
| --- | --- |
| A | 90 |
| B | 80 |
| C | 65 |
| D | 50 |
| F | below 50 |

Reading it correctly:

- 100/100 means none of the checks that ran reported a scored finding. It does not mean the site is secure, and
  informational notes can still be listed next to a 100.
- The score only reflects checks that ran. A check that could not run is listed as "Not checked" and never counts as a
  pass. A failed scan has no score.
- It is not a penetration test and says nothing about application code, logins, business logic, servers or anything
  the passive checks do not look at.
- Scores are not comparable with other tools, and nothing is adjusted to encourage a purchase.

## How severity is decided

Each rule is judged on its own, on what was actually observed, not on how common the condition is.

1. **Observed condition and impact.** What the response shows, and what that realistically allows an attacker to do.
2. **Exposure.** Whether the problem is reachable by any visitor (an exposed `.env`, an expired certificate) or only
   weakens a defence in depth (a missing optional header).
3. **Confidence.** `high` means directly observed. `medium` means a heuristic or a cause the scanner cannot fully
   attribute. A finding with less certainty is not given a higher severity to compensate.
4. **Kind of finding.** A weakness (something wrong now), a hardening gap (a missing control that reduces damage), or an
   informational observation (worth knowing, no direct weakness).

Rough bands: **high** is a direct, observable exposure or a failure visitors will hit (plain HTTP, exposed secrets
files, failed certificate checks). **medium** is a clear weakness with a plausible path to harm (missing HSTS or CSP,
cookies without `Secure`, mixed content). **low** is a hardening gap (version disclosure, missing `nosniff`,
no DMARC record). **info** is a note or a control whose absence is not itself a weakness.

Deliberate distinctions that are easy to get wrong:

- **DNSSEC** missing is `info`. It is optional, depends on the registrar and DNS host, and its absence does not mean a
  domain can be spoofed.
- **CAA** missing is `info`. It restricts which authorities may issue certificates; a domain without it is not
  compromised.
- **DMARC** with no record is `low`; a record with `p=none` is `info`. Monitoring is a legitimate first step, and the
  right policy depends on which senders legitimately send mail for the domain.
- **Uncertain certificate failures** (`not yet valid`, which can be the scanner's own clock, and `could not be
  verified`, whose cause is not classified) are `medium` with `medium` confidence. Expired, mismatched and untrusted
  certificates are `high` with `high` confidence.

A severity is changed only with a reason that is written here and a test that fails if it changes by accident.

## Severity of every reviewed rule

| Rule | Severity |
| --- | --- |
| SS-TLS-001 | high |
| SS-TLS-002 | info |
| SS-HDR-HSTS-001 | medium |
| SS-HDR-HSTS-002 | low |
| SS-HDR-CSP-001 | medium |
| SS-HDR-CSP-002 | low |
| SS-HDR-XCTO-001 | low |
| SS-HDR-REF-001 | low |
| SS-HDR-PERM-001 | info |
| SS-DISC-SRV-001 | low |
| SS-DISC-SRV-002 | info |
| SS-DISC-XPB-001 | low |
| SS-COOKIE-SECURE-001 | medium |
| SS-COOKIE-HTTPONLY-001 | low |
| SS-COOKIE-SAMESITE-001 | low |
| SS-DIR-001 | medium |
| SS-SCOPE-001 | info |
| SS-EXPOSE-GIT-001 | high |
| SS-EXPOSE-ENV-001 | high |
| SS-DISC-SEC-001 | info |
| SS-TLS-CERT-001 | medium or high (high at 14 days or fewer) |
| SS-TLS-CERT-002 | high |
| SS-TLS-CERT-003 | high |
| SS-TLS-CERT-004 | high |
| SS-TLS-CERT-005 | medium |
| SS-TLS-CERT-006 | medium |
| SS-MIX-001 | medium |
| SS-MIX-002 | low |
| SS-SRI-001 | low |
| SS-CORS-001 | medium |
| SS-CORS-002 | medium |
| SS-DISC-ROBOTS-001 | info |
| SS-DISC-SITEMAP-001 | info |
| SS-DNS-SPF-001 | low |
| SS-DNS-SPF-002 | medium |
| SS-DNS-SPF-003 | low |
| SS-DNS-DMARC-001 | low |
| SS-DNS-DMARC-002 | info |
| SS-DNS-CAA-001 | info |
| SS-DNS-DNSSEC-001 | info |

Each rule's fix examples, verification steps and limits are in `backend/app/reporting/guidance.json`.

## Scope

A report separates what was checked and passed, what was found, what could not be checked and why, and what the scan
does not cover at all (its "Limits"). A scan that fails technically is shown as failed, never as clean.
