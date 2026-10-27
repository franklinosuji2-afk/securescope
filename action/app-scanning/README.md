# SecureScope App Scanning GitHub Action

Sends the results of tools you already run in your pipeline to SecureScope App Scanning, and fails the job when
findings of the severity you choose are present. **Pilot, off by default:** it needs the App Scanning feature to be
switched on for your workspace, a plan that includes App Scanning CI, and an `app` API token.

## What is sent, and what is not

- A secret finding is always at least **high**, whatever level the tool gives it (Gitleaks gives none).
- Sent: for each finding the rule id, severity, file path, line number and (static analysis only) a short message
  and rule title; the name and version of each tool; your project id; the branch name and the first 12 characters
  of the commit id.
- **Never sent:** the SARIF snippet (Semgrep puts the matched source lines there) and, for secret findings, not even
  the message. Only the rule, the file and the line leave your runner. The server also refuses any document that
  looks like it contains a secret.
- **One exception to know about:** a static-analysis rule's own message is sent. If a rule interpolates matched code
  into its message (Semgrep metavariables such as `$X` can), that fragment is sent too. Check your rules' messages.
- SecureScope cannot check that a tool really ran or that its results are complete. Results are labelled as
  reported by you, and a check you did not run is shown as skipped. The job then fails ("incomplete"), whatever
  `fail-on` says.

## Use

1. In SecureScope create an App Scanning project and an API token with scope **app** (Integrations). Store the token
   as the repository secret `SECURESCOPE_APP_TOKEN`. Tokens expire after 90 days (pilot value).
2. Run your tools and write SARIF files, then call the action:

```yaml
jobs:
  appscan:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@v4
      - run: pipx run semgrep --config auto --sarif --output semgrep.sarif .
      # Install and run gitleaks the way your team already does (pinned version, checked download), writing SARIF:
      #   gitleaks detect --report-format sarif --report-path gitleaks.sarif --exit-code 0
      - uses: <owner>/securescope/action/app-scanning@<full commit sha>
        with:
          api-key: ${{ secrets.SECURESCOPE_APP_TOKEN }}
          project-id: <your project id>
          sast-sarif: semgrep.sarif
          secrets-sarif: gitleaks.sarif
          fail-on: high
```

Pin the action to a full commit sha, not a branch or tag. Pull requests from forks do not receive secrets, so run
this on `push` and on pull requests from the same repository.

## Rules

| Input | Meaning |
|---|---|
| `fail-on` | `critical`, `high` (default), `medium`, `low` or `none`. A finding at or above it fails the job (exit 1). |
| `sast-sarif`, `secrets-sarif` | At least one is required. A path with no file counts as a skipped check. |
| `api-url` | Must start with `https://` (or point to localhost for tests), with no user name, password, query or fragment. A host other than the default prints a warning. Requests are never redirected. |

Exit codes: `0` rules met; `1` rules not met, a check did not run, or the run did not complete; `2` nothing could be
submitted or the answer could not be trusted (bad token or settings, a SARIF file that cannot be read, project not
found, plan limit, results refused, an empty or unexpected answer, server not reachable after eight attempts, or an
unexpected error). Only a clearly completed run can pass; an unknown or error-like answer fails the job.

A scanner that crashed and wrote no file, or a SARIF without a run, or a tool that reports it did not finish, is sent as
a **skipped** check: the run is *incomplete* and the job fails (exit 1) whatever `fail-on` says. An incomplete run is
still an accepted run and **counts** toward the monthly allowance. Results the tool marked as suppressed are left out
and noted in the log.

A retry of the same pipeline run and attempt with the same results sends the same `Idempotency-Key`, returns the
earlier run and is not counted twice. A changed result is a new run. Limits (pilot values, may change): 4 MiB per
submission, 5,000 findings, 30 submissions per token per hour.

## Not done yet

- The action does not install or run the tools; you choose, pin and run them.
- Findings are stored and counted; the SecureScope page does not show code and secret findings yet.
- Linux and macOS runners only (needs `bash` and `python3`).
- Tested with genuine Semgrep OSS 1.182.1 and Gitleaks 8.18.4 SARIF; other tools and versions are not tested.
- Not tested on a real GitHub runner: only the script, against the real API over a local socket.
