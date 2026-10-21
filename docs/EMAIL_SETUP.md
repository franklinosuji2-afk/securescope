# Email setup

SecureScope uses email in two separate ways. Keep them apart when something goes wrong.

| Direction | Purpose | Provider | Where it is configured |
|---|---|---|---|
| Incoming | Public contact addresses (`hello@`, `support@`, `privacy@`, `security@`) | Cloudflare Email Routing (free) | Cloudflare dashboard, Email Routing |
| Outgoing | Service email: confirmation links, password resets | Brevo HTTPS API | Render environment variables, Brevo account |

The public addresses are defined once in `frontend/src/contact.ts`. The legal pages and `security.txt` use them. Nothing else in the frontend contains a mailbox, and no key or secret belongs in the frontend.

## Incoming: Cloudflare Email Routing

State as configured on 2026-10-21:

- Email Routing is enabled for `getsecurescope.com`. Cloudflare manages the three MX records (`route1`, `route2`, `route3` on `mx.cloudflare.net`).
- One routing rule per address: `hello@`, `support@`, `privacy@`, `security@`. Each forwards to a single destination mailbox that the operator controls and has verified in Cloudflare (Email Routing, Destination addresses).
- The catch-all rule is set to **Drop**, so addresses that were never created do not reach the inbox.
- A test message to all four addresses was forwarded (Cloudflare Activity log showed one "Forwarded" entry per address).

To add or change an address: Cloudflare, Email Routing, Routing rules, Create routing rule. The destination must already be verified, otherwise Cloudflare does not forward.

Email Routing only receives mail. It cannot send as these addresses.

## Outgoing: Brevo

The API sends plain-text service mail through Brevo (`docs/DEPLOY_FREE.md`, section 2). Environment variables on the API host:

| Variable | Meaning | Secret |
|---|---|---|
| `SECURESCOPE_MAIL_PROVIDER` | `brevo` (or `resend`; `log` writes to the log only) | no |
| `SECURESCOPE_MAIL_API_KEY` | provider API key | **yes**, host environment only |
| `SECURESCOPE_MAIL_FROM_EMAIL` | sender address verified with the provider | no |
| `SECURESCOPE_MAIL_FROM_NAME` | display name, default `SecureScope` | no |
| `SECURESCOPE_MAIL_REPLY_TO` | optional; where replies go, for example `support@getsecurescope.com` | no |

`SECURESCOPE_MAIL_REPLY_TO` is optional. When it is unset, no reply-to header is sent. Set it on the API host (Render, Environment) for it to take effect.

## DNS records

Do not copy values from this file. Each provider shows the exact records for the account, and values differ per account. Records present on the domain now, by name and purpose:

| Name | Type | Purpose |
|---|---|---|
| `getsecurescope.com` (three) | MX | Cloudflare Email Routing |
| `getsecurescope.com` | TXT | one SPF record that includes Cloudflare's SPF |
| `cf2024-1._domainkey` | TXT | Brevo DKIM key |
| `getsecurescope.com` | TXT | Brevo domain verification code |
| `_dmarc` | TXT | DMARC policy; aggregate reports go to Brevo |

Rules to keep:

1. **Exactly one SPF record per domain.** Two `v=spf1` records make SPF fail. If a provider ever asks for an SPF include, add its `include:` to the existing record instead of creating a second one.
2. **DKIM** comes from the sending provider. Copy it from that provider's dashboard and never write it by hand.
3. **DMARC** starts at `p=none` (monitor only). Tighten to `quarantine` and then `reject` only after reports show that all legitimate mail passes. Check the current policy with `dig TXT _dmarc.getsecurescope.com`.

## Verifying after a change

1. Send a test message from an outside mailbox to each public address and confirm it arrives (check spam as well). Cloudflare, Email Routing, Activity log shows one entry per address.
2. Register a new account and confirm that the verification email arrives and the link works.
3. In the received service email, open "Show original" and confirm SPF, DKIM and DMARC show PASS.
4. Platform Health (signed in as the operator) shows the mail provider, the sent and failed counts and the last success.

## Limitations

- Replying *as* `support@` or `hello@` from a normal mail client is not set up. Replies come from the operator's own mailbox. Sending as these addresses would need an SMTP login from the outgoing provider; it is not configured and nothing here depends on it.
- Forwarding to one personal mailbox means the operator's inbox is the single point of contact. Nobody monitors these addresses around the clock and no response time is promised.
- If the destination mailbox is deleted or unverified, Cloudflare stops forwarding without telling visitors.
- Service email depends on the provider's free plan limits.

## Manual steps that stay with the operator

- Keep the destination mailbox verified in Cloudflare.
- Review DMARC reports and tighten the policy later.
- Rotate the Brevo API key by the reminder date, and update it in the host environment only.
