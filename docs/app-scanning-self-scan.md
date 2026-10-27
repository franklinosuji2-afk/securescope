# App Scanning self-scan (owner pilot)

`.github/workflows/app-scanning-self-scan.yml` runs SecureScope's own App Scanning Action on this repository. It is
**manual only** (Actions, "App Scanning self-scan", Run workflow): it never runs on push or on pull requests, so
it cannot be triggered by a fork or by a contributor without write access. It proves the one App Scanning path that
works today (SARIF from tools run in CI) against production, in the owner's allow-listed workspace.

## What it does

1. Checks out the full history (the secret scan reads it) without keeping the Git credentials.
2. Runs Semgrep 1.182.1 (`p/default`, metrics off) and writes `semgrep.sarif`.
3. Downloads Gitleaks 8.18.4, **verifies its sha256** against the value published with the release, and writes
   `gitleaks.sarif` with secret values redacted.
4. Calls `./action/app-scanning` (the Action at the same commit, not an external reference), which sends only rule,
   severity, file path and line number (plus a static-analysis rule's own message) to `https://getsecurescope.com/api/v1`.

`fail-on` defaults to `none` for the first runs so that the evidence can be read without a red build. An incomplete
run (a tool that did not run) fails the job whatever `fail-on` says. Set `fail-on` to `high` once the findings are
understood.

## One-time setup (owner)

1. In SecureScope, App Scanning page: add a project, for example `securescope-repo`. Note its id.
2. In SecureScope, Integrations: create an API token with scope **app** (Professional, Agency or Internal plan).
   Copy it once; it is not shown again. Tokens expire after 90 days (pilot value).
3. In the GitHub repository, Settings, Secrets and variables, Actions:
   - Secret `SECURESCOPE_APP_TOKEN`: the token.
   - Variable `SECURESCOPE_APP_PROJECT_ID`: the project id (not secret).
     With the GitHub CLI: `gh secret set SECURESCOPE_APP_TOKEN` (paste at the prompt) and
     `gh variable set SECURESCOPE_APP_PROJECT_ID --body <id>`.
4. Run the workflow and read the Action's summary line (`scan-id`, `result`).

## Expected results and known noise

- **Gitleaks reports 4 findings today**, all `generic-api-key` in test files whose strings are made up (a wrong
  password in `test_log_secrets.py`, sample inputs for the redaction tests in `test_appscan_redaction.py`, a test
  idempotency key in `test_idempotency.py`). I read the flagged lines; none is a real credential. A secret finding
  is always at least **high**, so with `fail-on: high` the job fails until these are reviewed. They are not
  suppressed here on purpose: allow-listing them (a `.gitleaks.toml` allowlist or an inline `gitleaks:allow`) is an
  owner decision.
- The SecureScope page does not show code and secret findings yet; the run is visible in the run history and counts
  as an App Scanning run for the workspace.
- Semgrep rules are fetched from the Semgrep registry at run time, so the rule set can change between runs.

## Remove or revoke

Delete the workflow file and the secret, and revoke the token in SecureScope (Integrations). The project and its
runs can stay.
