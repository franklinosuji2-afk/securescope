# CI and badge integrations

## GitHub Action

`action/` is a composite GitHub Action that starts a passive SecureScope scan of a verified site and fails the job when
the result is below the bar you set. It needs bash, curl and jq, which GitHub-hosted runners have.

```yaml
- uses: franklinosuji2-afk/securescope/action@v1
  with:
    api-key: ${{ secrets.SECURESCOPE_TOKEN }}
    url: https://example.com
    min-score: 70 # optional
    fail-on: high # critical, high, medium, low or none
```

Outputs: `scan-id`, `score`, `grade`, `passed`. Exit code 1 means the rules you set were not met; exit code 2 means the
scan could not be run or finished (bad token, plan, rate limit, timeout). A scan that did not complete is never a pass.
A pass is not proof that a site is secure: the checks are passive and heuristic.

Notes

- Release: the `@v1` tag must exist in the repository (`git tag v1 && git push origin v1`). If the repository is
  private, other repositories can only use the Action after access is granted under Settings > Actions > General.
- Cold starts: on the free hosting tier the backend sleeps and needs up to a minute to wake. The script retries
  connection errors and 502, 503 and 504 for about two minutes. Raise `timeout-minutes` for slow sites.
- Findings your team marked as a false positive or accepted risk are not listed and do not count toward `fail-on`. The score is worked out when the scan runs and is not changed by those decisions, so `min-score` still sees the original score.
- The host of `url` must be a site your workspace has verified. A scan counts toward the monthly allowance.
- Text that comes from the scanned site (finding titles) is cleaned before it reaches the job log or summary, so it
  cannot start a workflow command or inject Markdown.

## API tokens

Integrations > API tokens for CI (owners and admins; Professional and Agency plans). A token looks like `ssk_...`, is shown
once, and only its SHA-256 digest and a short prefix are stored. At most 5 per workspace.

A token can only call `POST /api/v1/ci/scans` and `GET /api/v1/ci/scans/{id}` with `Authorization: Bearer <token>`.
The answer holds the scan id, host, status, score, grade, counts, up to 100 findings (id, severity, title) and a link.
No evidence or remediation text is included. A token acts as the person who made it, in one workspace, and is rechecked
on every use: it stops working when that person is deactivated, removed from the workspace, or loses the right to scan.
Failed token attempts are rate limited per client; each token is rate limited too.

Revoke a token from the same page. Audit events: `api_token.created`, `api_token.revoked`.

## Score badges

Integrations > Score badge (all plans; switching on or off needs the right to manage sites). A badge is off until switched
on. The address is `/api/v1/badges/<random token>.svg`: a link, not a credential, and public. It shows only the latest
completed scan's score and grade and the date, never findings or hostnames. "New address" makes the old one stop
working. Unknown or switched-off addresses answer 404 with a neutral "unavailable" image. Responses are cached for five
minutes and sent with `Content-Security-Policy: default-src 'none'`. Audit event: `badge.updated`.

The badge is a heuristic from passive checks, not a certificate of security, and its title text says so.

## Slack alerts

Integrations > Webhook alerts > "Send alerts to: A Slack channel" (Professional and Agency; the same limit of three addresses
as webhook addresses). In Slack, create an incoming webhook for a channel and paste its address
(`https://hooks.slack.com/services/T…/B…/…`). No other address is accepted for Slack. SecureScope sends a short text
message on the same triggers as the alert email: the site's host name, why the alert was raised, the titles of new
findings, the score and a link to the scan. No evidence and no page content are sent. The address contains a secret, so
it is shown only as `https://hooks.slack.com/…` after saving; remove and re-add it to change it. Slack does not sign
messages, so there is no signing secret. "Send test message" and "Recent deliveries" work as for webhook addresses.
Anyone who knows the address can post to that channel: treat it like a password and revoke it in Slack if it leaks.
