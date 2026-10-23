#!/usr/bin/env bash
# SecureScope scan for CI. Needs bash, curl and jq (all present on GitHub-hosted runners).
#
# Exit codes: 0 the rules you set were met; 1 they were not; 2 the scan could not be run or finished.
#
# Safety: the token is read from the environment, masked and never printed. Text that comes from the scanned
# site (finding titles can contain a cookie name, for example) is cleaned before it is written to the log, so it
# cannot start a workflow command ("::...") or inject Markdown into the job summary.
set -euo pipefail
set +x

API_KEY="${SS_API_KEY:-}"
URL="${SS_URL:-}"
MIN_SCORE="${SS_MIN_SCORE:-}"
FAIL_ON="${SS_FAIL_ON:-high}"
TIMEOUT_MIN="${SS_TIMEOUT_MINUTES:-10}"
API_URL="${SS_API_URL:-https://getsecurescope.com/api/v1}"
OUT="${GITHUB_OUTPUT:-/dev/null}"
SUMMARY="${GITHUB_STEP_SUMMARY:-/dev/null}"
POLL_SECONDS="${SS_POLL_SECONDS:-5}"
RETRY_SECONDS="${SS_RETRY_SECONDS:-15}"

fail() { echo "::error::SecureScope: $*"; exit 2; }

[ -n "$API_KEY" ] || fail "no API token was given (input api-key)."
echo "::add-mask::$API_KEY"
[ -n "$URL" ] || fail "no address was given (input url)."
case "$URL" in https://*|http://*) ;; *) fail "the url must start with https:// or http://." ;; esac
case "$API_URL" in
  https://*|http://127.0.0.1*|http://localhost*) ;;
  *) fail "the api-url must start with https://." ;;
esac
API_URL="${API_URL%/}"
if [ -n "$MIN_SCORE" ]; then
  [[ "$MIN_SCORE" =~ ^[0-9]{1,3}$ ]] && [ "$MIN_SCORE" -le 100 ] || fail "min-score must be a number from 0 to 100."
fi
case "$FAIL_ON" in critical|high|medium|low|none) ;; *) fail "fail-on must be critical, high, medium, low or none." ;; esac
[[ "$TIMEOUT_MIN" =~ ^[0-9]{1,2}$ ]] && [ "$TIMEOUT_MIN" -ge 1 ] && [ "$TIMEOUT_MIN" -le 60 ] \
  || fail "timeout-minutes must be a number from 1 to 60."

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# One request. Prints the HTTP status; the body goes to $TMP/body. The token goes through a config file on
# stdin so it never appears in the process list.
call() {
  local method="$1" path="$2" data="${3:-}"
  local args=(-sS -o "$TMP/body" -w '%{http_code}' --max-time 60 -X "$method" --config -)
  if [ -n "$data" ]; then args+=(-H 'Content-Type: application/json' --data "$data"); fi
  printf 'header = "Authorization: Bearer %s"\n' "$API_KEY" | curl "${args[@]}" "$API_URL$path" 2>"$TMP/err" || echo "000"
}

# A sleeping free-tier backend needs about a minute to wake, so connection errors and 502-504 are retried.
call_retry() {
  local code tries=0
  while :; do
    code="$(call "$@")"
    case "$code" in
      000|502|503|504)
        tries=$((tries + 1))
        if [ "$tries" -ge 8 ]; then echo "$code"; return; fi
        echo "SecureScope did not answer yet (attempt $tries). Waiting for it to wake up..." >&2
        sleep "$RETRY_SECONDS"
        ;;
      *) echo "$code"; return ;;
    esac
  done
}

clean() { tr -d '\000-\010\013-\037\177' | sed 's/::/: :/g' | cut -c1-300; }
detail() { jq -r '.detail // empty | if type=="string" then . else "request rejected" end' "$TMP/body" 2>/dev/null | clean || true; }

body="$(jq -cn --arg url "$URL" '{url: $url}')"
code="$(call_retry POST /ci/scans "$body")"
case "$code" in
  202|200) ;;
  401) fail "the API token is not valid, or it has been removed." ;;
  403) fail "the scan was refused: $(detail)" ;;
  429) fail "too many requests: $(detail)" ;;
  000) fail "SecureScope could not be reached." ;;
  *) fail "the scan could not be started (HTTP $code). $(detail)" ;;
esac
SCAN_ID="$(jq -r '.id // empty' "$TMP/body")"
[[ "$SCAN_ID" =~ ^[A-Za-z0-9]{8,64}$ ]] || fail "SecureScope answered with an unexpected scan id."
echo "Scan $SCAN_ID started for $(printf '%s' "$URL" | clean)"

deadline=$(( $(date +%s) + TIMEOUT_MIN * 60 ))
status="queued"
while :; do
  code="$(call_retry GET "/ci/scans/$SCAN_ID")"
  [ "$code" = "200" ] || fail "the scan could not be read (HTTP $code). $(detail)"
  status="$(jq -r '.status' "$TMP/body")"
  case "$status" in completed|failed|cancelled) break ;; esac
  if [ "$(date +%s)" -ge "$deadline" ]; then fail "the scan did not finish within $TIMEOUT_MIN minutes."; fi
  sleep "$POLL_SECONDS"
done

if [ "$status" != "completed" ]; then
  reason="$(jq -r '.error // empty' "$TMP/body" | clean)"
  fail "the scan $status. ${reason:-No reason was given.} A scan that did not complete is not a clean result."
fi

SCORE="$(jq -r '.score // empty' "$TMP/body")"
GRADE="$(jq -r '.grade // empty' "$TMP/body")"
HOST="$(jq -r '.host' "$TMP/body" | clean)"
LINK="$(jq -r '.link' "$TMP/body" | clean)"
[[ "$SCORE" =~ ^[0-9]{1,3}$ ]] || fail "the scan finished without a score."
[[ "$GRADE" =~ ^[A-F]$ ]] || fail "the scan finished without a grade."

case "$FAIL_ON" in
  critical) bad='["critical"]' ;;
  high) bad='["critical","high"]' ;;
  medium) bad='["critical","high","medium"]' ;;
  low) bad='["critical","high","medium","low"]' ;;
  none) bad='[]' ;;
esac
blocking="$(jq --argjson bad "$bad" '[.findings[] | select(.severity as $s | $bad | index($s))] | length' "$TMP/body")"
reasons=()
if [ -n "$MIN_SCORE" ] && [ "$SCORE" -lt "$MIN_SCORE" ]; then reasons+=("the score $SCORE is below the minimum of $MIN_SCORE"); fi
if [ "$blocking" -gt 0 ]; then reasons+=("$blocking finding(s) of severity $FAIL_ON or higher"); fi
PASSED=true
[ "${#reasons[@]}" -eq 0 ] || PASSED=false

echo "SecureScope result for $HOST: score $SCORE/100, grade $GRADE"
jq -r '.findings[] | "  [\(.severity)] \(.id) \(.title)"' "$TMP/body" | clean
echo "Details: $LINK"
echo "This is a passive, heuristic check. A good result is not proof that a site is secure."

{
  echo "scan-id=$SCAN_ID"
  echo "score=$SCORE"
  echo "grade=$GRADE"
  echo "passed=$PASSED"
} >>"$OUT"

{
  echo "### SecureScope: $HOST"
  echo
  echo "**Score $SCORE/100, grade $GRADE.** $([ "$PASSED" = true ] && echo 'The rules you set were met.' || echo 'The rules you set were not met.')"
  echo
  count="$(jq '.findings | length' "$TMP/body")"
  if [ "$count" -gt 0 ]; then
    echo "| Severity | Finding |"
    echo "| --- | --- |"
    jq -r '.findings[] | "| \(.severity) | \(.id): \(.title) |"' "$TMP/body" | clean \
      | sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g; s/`/\&#96;/g; s/\[/\&#91;/g'
    echo
  else
    echo "No findings."
    echo
  fi
  echo "A passive, heuristic check. A good result is not proof that a site is secure."
} >>"$SUMMARY"

if [ "$PASSED" = false ]; then
  for r in "${reasons[@]}"; do echo "::error::SecureScope: $r."; done
  exit 1
fi
