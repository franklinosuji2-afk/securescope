# SecureScope pre-launch checklist

Date: 24 October 2026. Status of the product: **in development**. The site is reachable at getsecurescope.com, but it is
not launched and the operator has **not formally registered a business**. This list is engineering support, not legal
advice. Nothing is marked Done without evidence; "Open" means unverified.

How to read it: **Blocks launch** = must be resolved before the site is publicly promoted or takes payment. **Owner** =
Operator (only you know the fact), Lawyer/Tax adviser (needs a professional), Engineering (code or configuration).
Sources for the evidence column are in `docs/legal-audit.md`.

## Private development versus public launch

- The Impressum duty (§ 5 DDG) applies to any commercially-oriented, publicly reachable site. The site is reachable now, so
  the Impressum and privacy notice are kept live and accurate. Being "not launched" does not remove them.
- Payment, invoicing, tax and consumer-contract rules start only when paid plans are sold. They are launch blockers for
  payments, not for the free plan.

## 1. Business registration

| Item | What to verify | Why | Blocks launch | Owner | Status |
| --- | --- | --- | --- | --- | --- |
| Business classification | Whether selling subscriptions needs a Gewerbeanmeldung (trade registration) and Finanzamt registration; whether activity is freiberuflich or gewerblich | Determines tax, registers, Impressum content | Yes, for paid plans | Operator + Tax adviser | Open |
| Register entries | Whether any Handelsregister, trade or chamber number exists | Impressum must list them only if they exist; none may be invented | Yes | Operator | Open. Pages claim none; they say "not a registered company" |

## 2. Tax and VAT

| Item | What to verify | Why | Blocks launch | Owner | Status |
| --- | --- | --- | --- | --- | --- |
| Kleinunternehmerregelung (§ 19 UStG) | Whether you qualify and elect it | Decides whether €19 and €49 are gross prices without VAT, or need VAT added | Yes, for paid plans | Tax adviser | Open. No tax claim is published |
| VAT ID | Whether a USt-IdNr. exists or is needed | Impressum lists it only if issued; B2B invoices and EU rules may need it | Yes, for paid plans | Operator / Finanzamt | Open. The Impressum no longer says "none issued" because that was unconfirmed |
| Invoice content | Required invoice fields, small-business wording if applicable | Invalid invoices are a tax risk | Yes, for paid plans | Tax adviser | Open |

## 3. Subscription pricing and billing

| Item | What to verify | Why | Blocks launch | Owner | Status |
| --- | --- | --- | --- | --- | --- |
| Paddle seller approval | Account approved; whether Paddle acts as merchant of record | Paddle then handles VAT and invoices, which changes what you must do | Yes, for paid plans | Operator | In progress: Paddle dashboard (screenshot, 24 Oct 2026) shows website approval for `getsecurescope.com` **In review**. Seller-account approval not yet seen. Paddle reviews the pricing, terms and privacy pages, and expects refund and cancellation terms; the Terms say payment terms will be added, so a refund policy is an Operator decision before approval |
| Price display | Gross/net statement matches the tax outcome | German price-display rules | Yes, for paid plans | Tax adviser + Lawyer | Open |
| Billing code | Checkout, webhooks, plan changes, cancellation | None exists yet | Yes, for paid plans | Engineering | Not built |
| Withdrawal and cancellation terms | Consumer withdrawal right, cancel button (§ 312k BGB) | Required for consumer subscriptions | Yes, for paid plans | Lawyer | Open |

## 4. Impressum

| Item | What to verify | Why | Blocks launch | Owner | Status |
| --- | --- | --- | --- | --- | --- |
| Name, postal address, email | Present and correct | § 5 DDG | Yes | Operator | Done: present on the page (`Legal.tsx`) |
| Telephone | Not required when email gives fast contact | Avoid publishing more than needed | No | Lawyer to confirm | Open |
| Business statements | Only "individual, not a registered company"; no register, VAT or professional data | No invented data | Yes | Operator | Done in code; confirm the sentence stays true after registration, then update |
| § 18 Abs. 2 MStV block | Needed only for journalistic-editorial content | Probably not needed; harmless | No | Lawyer | Open |
| Consumer dispute notice (§ 36 VSBG) | Needed above the staff threshold only. Do not add the EU ODR link | Avoid wrong statements | No | Lawyer | Open |

## 5. Privacy notice

| Item | What to verify | Why | Blocks launch | Owner | Status |
| --- | --- | --- | --- | --- | --- |
| Data categories and purposes | Match the code | Art. 13 GDPR accuracy | Yes | Engineering | Done: checked against code on 24 Oct (see audit section 2) |
| Legal bases | Art. 6(1)(b)/(f) per item | Legal review | Yes | Lawyer | Open |
| Retention periods | Audit log has no cleanup job | Notice says "until the workspace is deleted" | No, but decide | Operator + Engineering | Open |
| Data export | No self-service export | Art. 20 GDPR is handled by email today | No | Engineering | Open |

## 6. Terms of use

| Item | What to verify | Why | Blocks launch | Owner | Status |
| --- | --- | --- | --- | --- | --- |
| Development-stage wording | Terms say the service is in development and no payment terms exist | Must not describe unfinished features as available | Yes | Engineering | Done |
| Liability clause, governing law, suspension | Legal review | Standard terms are legally sensitive | Yes, for paid plans | Lawyer | Open |
| Payment terms | Add before any plan is sold | None exist | Yes, for paid plans | Lawyer | Not written |

## 7. Hosting region

| Item | What to verify | Why | Blocks launch | Owner | Status |
| --- | --- | --- | --- | --- | --- |
| Render region | Region of the web service in the Render dashboard | EU hosting must not be assumed | Yes | Operator | Done: Render dashboard screenshot (24 Oct 2026) shows `securescope-api` in **Oregon (USA)**. The privacy notice now says so. Decision open: move to Frankfurt (new service, same settings) to keep data in the EU and cut database latency |
| Neon region | Dashboard shows the project region | Notice says Frankfurt | Yes | Operator | Done: Neon dashboard screenshot (24 Oct 2026) shows project `securescope`, region AWS Europe Central 1 (Frankfurt), Free plan, restore history 6 hours, no IP restrictions, Postgres 18 |
| Cloudflare | Edge network, logs, processing locations | Notice mentions routing only | No | Operator | Open |

## 8. Data-processing agreements and transfers

| Item | What to verify | Why | Blocks launch | Owner | Status |
| --- | --- | --- | --- | --- | --- |
| Cloudflare, Render, Neon, Brevo | Art. 28 DPA accepted in each dashboard; which transfer mechanism applies (DPF or SCCs) | Required for processors; the notice must not assert unverified mechanisms | Yes | Operator | Operator states on 24 Oct 2026 that all DPAs are accepted (no document seen by engineering). Transfer mechanism for the US-hosted Render server still to confirm from Render's DPA |
| Brevo entity | Contracting entity and country | Notice names Brevo (Sendinblue SAS), France | No | Operator | Open |
| Provider logs | Retention in each dashboard | Notice gives no period | No | Operator | Open |

## 9. Cookies and analytics

| Item | What to verify | Why | Blocks launch | Owner | Status |
| --- | --- | --- | --- | --- | --- |
| Cookies | Only `ss_session`, `ss_csrf`, `ss_oauth` | TDDDG § 25 | Yes | Engineering | Done: checked in code |
| Browser storage | Theme, selected workspace, pending invitation; disclosed | Same | Yes | Engineering | Done: disclosed, tested (`legal.test.tsx`) |
| Visit statistics | No cookie, no stored IP, DNT and GPC honoured | Consent-free analytics claim | Yes | Engineering + Lawyer | Code verified; legal view open |
| Live check | Inspect cookies and storage in the live site | Evidence from production | Yes | Engineering with you | Open (joint site check) |

## 10. Account deletion and data retention

| Item | What to verify | Why | Blocks launch | Owner | Status |
| --- | --- | --- | --- | --- | --- |
| Deletion removes all account data | Every table covered | Art. 17 GDPR | Yes | Engineering | Done: `test_account_deletion_data.py` |
| Scan history retention | 30/90/365 days by plan | Notice promise | Yes | Engineering | Done: hourly cleanup loop in code; confirm on the live database after a day |
| Backups | Neon restore window, dump handling | Deleted data lives in backups for a time | No | Operator | Open |

## 11. Security and authorisation controls

| Item | What to verify | Why | Blocks launch | Owner | Status |
| --- | --- | --- | --- | --- | --- |
| Verified-only scanning | Enforced on every scan path | Prevents scanning third parties | Yes | Engineering | Done: scans, CI, scheduler (code) |
| Auth, CSRF, SSRF, ownership | Reviewed and tested | Standing security rules | Yes | Engineering | Done for current code; reviewed 24 Oct |
| Public docs and internal routes | `/api/docs` off; internal route not reachable by encoded path | Reduce exposure | Yes | Engineering | Done and live (404 confirmed) |
| Edge rate limit on sign-in | Cloudflare rule | Brute-force protection | No | Operator | Open |
| Secret rotation and backups | Written procedure, scheduled backup | Recovery | No | Engineering | In progress |

## 12. Payment and subscription testing

| Item | What to verify | Why | Blocks launch | Owner | Status |
| --- | --- | --- | --- | --- | --- |
| Paddle sandbox | Checkout, success, failure, cancel, refund, webhook signature | Money handling | Yes, for paid plans | Engineering | Not started (no billing code) |
| Plan limits | Upgrade and downgrade change limits correctly | Entitlements | Yes, for paid plans | Engineering | Open |

## 13. Production deployment checks

| Item | What to verify | Why | Blocks launch | Owner | Status |
| --- | --- | --- | --- | --- | --- |
| CI and deploy | GitHub Actions green, Render Live, migrations applied | Release evidence | Yes | Engineering | Done for `740c399` backend; frontend live. Recheck after each push |
| Health and headers | `/api/v1/health`, `/api/v1/ready`, HSTS, CSP | Basic readiness | Yes | Engineering | Done 24 Oct |
| Scheduled scans | Second run confirmed | Cron path | Yes | Engineering | Done: run on 23 Oct, score 100 |
| Email delivery | First real alert email and webhook | Features work end to end | Yes | Operator + Engineering | Open |
| DNS hardening | CAA, DNSSEC, DMARC for getsecurescope.com | Domain trust | No | Operator | Open |

## Outstanding before public launch (short list)

1. Business registration and tax status (sections 1 and 2).
2. Hosting regions and processor agreements (7 and 8).
3. Lawyer review of the three legal pages (4 to 6).
4. Everything under "for paid plans" before any plan is sold (2, 3, 6, 12).
