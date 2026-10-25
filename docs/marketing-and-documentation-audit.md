# Public website and documentation audit

Date: 25 Oct 2026. Phase 10 of the product-quality brief. The live home page was read in the built-in browser on 25 Oct (signed out) and compared with the code in `Landing.tsx`, the legal pages and the scanner source before anything was changed. **No claim was added that the code does not back, and no legal fact was invented.**

## Result

| Visitor question | Before | After |
|---|---|---|
| Who is it for? | Implied by the hero only | Own FAQ entry, first in the list |
| What does it check? | Clear (nine check areas, sample report) | Unchanged |
| What does it not check? | In the FAQ and in every report | Unchanged; FAQ also names the well-known path requests (such as `/.env`) |
| How does ownership verification work? | Explained in "how it works" | Unchanged; the "someone else's site" answer no longer overstates it (see below) |
| What does a report look like? | Sample report page and PDF | Unchanged |
| Why is scheduled monitoring useful? | Only appeared inside plan lists | Own FAQ entry: what it does, daily or weekly, an email only for something new or a 5-point drop, not on sale yet |
| What do plans include? | Pricing table, Free "Available now", paid "Coming soon" | Unchanged |
| How do I get started? | "Create free account" | Unchanged. The "4 steps" tile was next to a five-step list; it now reads "steps from sign-up to your first scan" |
| Where is the documentation? | **No public link** | Still no public documentation page (see gaps) |
| How do I contact support? | **Addresses only inside Impressum, privacy and terms** | Footer "Help and legal" column with the support address |
| How do I report a security issue? | **Only reachable through `security.txt` if you knew the URL** | Footer link "Report a security issue" to `/.well-known/security.txt` (contact `security@getsecurescope.com`) |

## Claims review

Everything the page says was compared with the code or the legal text.

| Claim | Basis | Verdict |
|---|---|---|
| Page contents are not stored | `scanner/checks.py`, `fetcher.py`: findings keep evidence snippets about headers, cookies and file presence, not page bodies | Backed by code |
| Free plan available now; Professional €19 and Agency €49 "Coming soon" | `billing/plans.py`; no checkout exists | Accurate |
| Scan history kept 30 / 90 / 365 days | Retention loop and `DATA_RETENTION.md` | Accurate |
| "A clean result does not mean a site is secure" | FAQ and every report | Accurate and prominent |
| "Can't be pointed at someone else's website" | **Stronger than the Terms**, which say verification shows technical control only (a person with a file or DNS record on a site is not necessarily its owner or authorised) | **Softened**: verification proves technical control, and permission from the owner is still needed |
| Scheduled monitoring emails | Scheduler and alert rules in code | Accurate, and marked not on sale |

Checked for and not found (also enforced by `landing.test.tsx`): "guarantee", "completely / fully / 100% secure", "unhackable", "bank-grade", "military-grade", a penetration-test service, "certified", "trusted by", customer or user counts, testimonials. There are no logos, reviews, statistics or compliance badges on the page.

## Changes made

- `frontend/src/pages/Landing.tsx`: the two new FAQ entries, the two reworded answers, the corrected tile label and the footer column "Help and legal" with Support and Report a security issue.
- `frontend/src/test/landing.test.tsx` (new, 4 tests): footer support and security links exist; the new FAQ entries exist; paid plans still say "Coming soon"; the forbidden-claims list above does not appear in the page text.
- Frontend: lint, typecheck and format clean; 226 tests pass (222 before); build passes. The end-to-end test (`landing.e2e.ts`) uses the sign-in and create-account links and the Menu button, none of which moved; it runs only in CI.

## Gaps left open (not changed, on purpose)

1. **No public documentation page.** `docs/API.md` and the developer guides live in the repository only. A public page should wait until the API surface is declared stable and the docs have been reviewed; publishing the file as it is would expose internal wording. Queued under "public API docs".
2. **Search and sharing.** The app uses hash routes, so the pages have no distinct addresses for search engines; there are no canonical or Open Graph tags and no sitemap. Fixing this means pre-rendering or path routing, which is a larger change than copy.
3. **No pricing detail on billing terms** (refunds, renewal, cancellation notice). Correct for now because nothing can be bought; it must be written with the Paddle terms.
4. **A signed-out visit logs one expected 401** from `/auth/me` in the browser console. Harmless; it can be silenced later.

## Facts only the owner can supply (none were invented)

- Whether the Kleinunternehmer rule applies, and the VAT ID if there is one. The pricing shows euro amounts without a tax statement.
- Business registration details beyond what the Impressum already shows, and any trade-register or chamber entry.
- The result of the lawyer review of the privacy notice and Terms.
- **The privacy notice does not mention Cloudflare's leaked-credential check**, which now runs on traffic to the site at the edge (the owner kept it on 25 Oct). Cloudflare is already named as the network provider, but the notice should say what this feature does before a public launch.
- The provider arrangements (data-processing agreements with Render, Neon, Cloudflare and Brevo). The notice states what is processed; the agreements themselves are for the owner to confirm.

## Statuses for this phase

- Local development: READY.
- Owned or authorised sites: READY WITH CONDITIONS.
- Controlled external pilot (free plans): READY WITH CONDITIONS. The page is honest about scope, limits and plan status, and now shows support and security contacts.
- Public commercial launch: NOT READY (public documentation, search-friendly addresses, tax statement, lawyer review, billing terms).
