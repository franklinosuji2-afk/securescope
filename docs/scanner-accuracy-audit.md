# Scanner accuracy audit

Scope: the 40 rules in `frontend/src/guidance.json`, how well tests pin each one, and what the scanner can and cannot be trusted to say. Labels: **Verified** (checked by running code or tests), **Risk**, **Recommendation**, **Not tested**.

## Verified

- **Every rule is produced by at least one test.** A recorder wrapped `Finding.__init__` during the full backend run; none of the 40 rules is uncovered. The per-rule table is in [scanner-test-matrix.md](scanner-test-matrix.md), regenerated with `scripts/gen_scanner_matrix.py`.
- **Edge cases are pinned** in `test_scanner_edge_cases.py` and `test_wider_checks.py`:
  - CORS: a lone `*` is not reported; `*` with credentials (any letter case) is; `null` is; an empty header is not; evidence never includes other headers such as cookies.
  - robots/sitemap: sensitive words match whole path parts only (`/badminton` no, `/admin` yes); addresses on other hosts, error responses and comments are ignored; long lists are cut to five but counted in full.
  - SPF/DMARC: record tags are case-insensitive; other TXT records are ignored; a DNS error is not "no record"; the DMARC *domain* policy is read, not the subdomain policy (`sp=none; p=reject` is clean); `v=DMARC2` is not a DMARC record.
  - Mixed content: see the fix below.
- No scanner rule was found to report a false positive in these probes.

## Defect found and fixed

- **False negative: images listed only in `srcset`.** `<img srcset="http://...">` was not checked for mixed content. The scanner now checks `src` and every `srcset` candidate (skipping `data:` URLs) for img/audio/video/source/track. Three tests cover it, including the case where https candidates must not be reported.

## Known limits (not defects, now written down)

- **Risk:** mixed content in inline CSS (`url(http://...)`) and `<meta http-equiv=refresh>` is not checked, so a clean result does not rule it out.
- **Risk:** the missing-integrity rule treats any other hostname as another site, so `cdn.example.com` on `example.com` is asked for SRI. This errs on the side of reporting.
- **Risk:** an SPF record with neither `all` nor `redirect` produces no finding.
- **Risk:** a DMARC record that omits the `;` after `v=DMARC1` is treated as no record.
- **Risk:** `<link rel=preload>` to an http URL is classed as passive mixed content (LOW).
- **Recommendation:** decide for each whether to fix or to list under "what this scan does not check" in the report. None is a security regression.

## Coverage quality

- Two rules are produced fewer than three times by the whole suite: SS-DNS-SPF-003 and SS-MIX-002. Both have a positive and a negative test; they are the first to extend when those checks change.
- Six rules are built from a dynamic id (the six `SS-TLS-CERT-*` certificate rules), so the generator cannot read their severity from source and lists them as "varies". **Recommendation:** pin their severities in a test.
- **Not tested:** behaviour against real third-party sites. All tests use fixtures; accuracy against live sites (CDNs, SPAs, WAF-blocked responses) has not been measured and no accuracy percentage is claimed anywhere.
