# App Scanning Worker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move App Scanning's CPU-heavy work out of the website's API process into a separate private worker, so a large scan no longer slows every page, without storing anything that is not stored today.

**Architecture:** A _remote executor_, not a queue. The API keeps accounting, permissions and every database write. The CPU-bound steps (reading the JSON body, parsing manifests, the secret check, building the result, dependency lookups) move behind an `AppScanExecutor` interface. It has two implementations: `InlineExecutor` (today's behaviour, the default) and `RemoteExecutor`, which streams the request body over Render's private network to a worker service and awaits the answer. The worker has no database access and holds content only in memory, so the "file contents are never stored" and "a refused submission is never stored" guarantees hold unchanged. The request stays synchronous, so the page's progress and result messages don't change.

**Tech Stack:** Python 3.13, FastAPI, httpx (async client, `ASGITransport` in tests), pytest, Alembic (no migration needed), Docker, Render.

**Spec:** `docs/load-test-results.md`, section "App Scanning (31 Oct 2026)", and the decisions below.

## Decisions for the owner (before Task 4 is deployed; Tasks 1–3 need none)

| #    | Decision           | Recommendation                                                                                                                                                                                                                                                                                                                                                                |
| ---- | ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| D-W1 | **Hosting (paid)** | A Render **Private Service** (reachable only on Render's private network), on a paid instance, in the same region as the API. Free Render web services sleep when idle and share 750 free hours a month, so a second always-on free service is not viable, and a public worker would need its own internet-facing protection. Check the current Render price before deciding. |
| D-W2 | Worker unreachable | Refuse with 503 "The scanning service is not available right now. Try again shortly." and count nothing. Do **not** fall back to inline, which would bring back the slowdown the worker exists to remove. Inline stays only when no worker is configured.                                                                                                                     |
| D-W3 | Worker size        | Start at the smallest paid instance (0.5 CPU on Render's Starter, to be confirmed). Task 5's load test confirms whether the 5 000-finding maximum fits the 20 s check limit there.                                                                                                                                                                                            |

## Global Constraints

- Nothing new is stored: no table holds uploaded file contents or submission documents, temporarily or otherwise.
- The worker has **no database URL and no database connection**. The API alone reads and writes the database.
- Default behaviour is unchanged. With `SECURESCOPE_APP_WORKER_URL` unset, every route behaves exactly as today, and all existing tests pass unmodified.
- Existing limits keep their values and meaning: `MAX_REQUEST_BYTES` (6 MB), `MAX_DOCUMENT_BYTES` (4 MB), `CHECK_WAIT_SECONDS` 10, `CHECK_RUN_SECONDS` 20, `SCAN_BUDGET_SECONDS` 20, `SCAN_HARD_SECONDS` 60, `BODY_READ_SECONDS` 30.
- Accounting rules don't move: a run is accepted and counted only in the API (`_accept`). A request refused before acceptance is never counted. A run that fails after acceptance ends Failed or Interrupted and is not counted.
- Error text from the worker is never passed on. The API maps errors to the fixed messages that exist today (`ManifestError` code and message, `SubmissionRejected` code and message, or a fixed 503 text).
- Worker authentication: `Authorization: Bearer <SECURESCOPE_APP_WORKER_SECRET>`, compared with `app.security.tokens.constant_time_equal`. A missing or wrong secret gets the same 401.
- No `render.yaml` change in this plan. Adding a service there could create a paid service on the next Blueprint sync, so the deployment steps go in `docs/DEPLOYMENT.md` for the owner to apply.

## Review Focus

- **The worker restarts mid-request.** Expected: a browser scan that was already accepted ends Failed ("The scan could not be completed."), is not counted, and the page shows the failure reason. Covered in Task 4 (`test_a_worker_that_drops_the_connection_ends_the_run_failed_not_counted`).
- **The worker is slow but alive** (longer than the hard limit). Expected: the same 60 s hard stop as inline, and the run ends Failed and not counted. Covered in Task 4 (`test_a_worker_past_the_hard_limit_ends_the_run_failed`).
- **The worker returns something malformed** (wrong shape, extra fields, oversized). Expected: treated as worker failure; never trusted or stored. Covered in Task 3 (`test_wire_rejects_unknown_fields_and_wrong_types`) and Task 4 (`test_a_malformed_worker_reply_is_a_failure_not_a_result`).
- **Someone on the private network calls the worker without the secret.** Expected: 401, no work done. Covered in Task 4 (`test_worker_refuses_without_the_secret_and_does_no_work`).
- **A slow client trickles a large upload.** Expected: the API still enforces `BODY_READ_SECONDS` before anything is forwarded, so a slow sender can't tie up the worker. Covered in Task 4 (`test_a_slow_upload_is_refused_before_the_worker_is_called`).

---

### Task 1: Find out where the CPU goes, and keep the event loop free (inline mode)

The load test measured CPU per run but not per step, and browser uploads parse JSON on the event loop. That blocks every request during a large upload, even with a worker in place. This task records the split and fixes the blocking. It's useful on its own and needs no decision.

**Files:**

- Create: `scripts/profile_appscan.py`
- Modify: `backend/app/api/v1/app_scans.py` (`_read_limited_json` and `AppScanCreate.model_validate` in `create_scan`)
- Modify: `docs/load-test-results.md` (a "Where the CPU goes" table under "App Scanning")
- Test: `backend/app/tests/test_appscan_routes.py`

**Interfaces:**

- Produces: `profile_steps(packages: int, findings: int) -> dict[str, float]` in `scripts/profile_appscan.py`, returning CPU seconds for the keys `json_upload`, `validate_upload`, `parse_manifest`, `scan`, `json_ci`, `check_document`, `store_result_ci`.

- [ ] **Step 1:** Write `scripts/profile_appscan.py`. It reuses `lockfile()` and `ci_document()` from `scripts/loadtest_appscan.py`, times each step with `time.process_time()` against an in-memory SQLite database (`make_settings`-style `Settings(database_url="sqlite:///:memory:")` and Alembic `upgrade`), and prints one JSON line for (8 367 packages, 0 findings) and (0 packages, 5 000 findings).
- [ ] **Step 2:** Run `backend/.venv/Scripts/python scripts/profile_appscan.py` and add its numbers to `docs/load-test-results.md` as "Where the CPU goes" (one row per key). If `store_result_ci` is more than a third of the 5 000-finding total, note that inserts need batching, as a follow-up outside this plan.
- [ ] **Step 3: Write the failing test** `test_health_answers_while_a_large_upload_is_being_read` in `test_appscan_routes.py`:

```python
def test_health_answers_while_a_large_upload_is_being_read(app_on, monkeypatch):
    real = app_scans._parse_json
    monkeypatch.setattr(app_scans, "_parse_json", lambda raw: (time.sleep(1.5), real(raw))[1])
    pid = project(app_on)
    worker = threading.Thread(target=lambda: scan(app_on, pid))
    worker.start()
    time.sleep(0.3)
    started = time.perf_counter()
    # The same client, so the same event loop: a second TestClient would have its own loop and never block.
    assert app_on.get("/api/v1/health").status_code == 200
    assert time.perf_counter() - started < 0.5   # the event loop was not blocked by the 1.5 s parse
    worker.join()
```

- [ ] **Step 4:** Run `pytest app/tests/test_appscan_routes.py::test_health_answers_while_a_large_upload_is_being_read -v`. Expected: FAIL (the health check waits about 1.2 s).
- [ ] **Step 5:** In `create_scan`, replace `await _read_limited_json(request)` and `AppScanCreate.model_validate(raw)` with one `await asyncio.to_thread(_read_upload, raw_bytes)`. Define `_read_upload(raw: bytes) -> AppScanCreate` to raise the same `HTTPException` details as today (400 not JSON; 422 "The request is not valid: check the project, files and checks.").
- [ ] **Step 6:** Run `pytest app/tests -k appscan -q`. Expected: all pass, including the new test.
- [ ] **Step 7: Commit** `git commit -m "App Scanning: read uploads off the event loop; record where the CPU goes"`

### Task 2: An executor interface, with today's behaviour behind it

**Files:**

- Create: `backend/app/appscan/executor.py`
- Modify: `backend/app/api/v1/app_scans.py` (routes call `state.app_executor`), `backend/app/api/deps.py` (`AppState.app_executor = InlineExecutor(...)`)
- Test: `backend/app/tests/test_appscan_executor.py`

**Interfaces:**

- Produces, in `app/appscan/executor.py`:
  - `class PreparedUpload(NamedTuple): body: AppScanCreate; parsed: list[manifests.ParseResult]`
  - `class CheckedDocument(NamedTuple): submission: Submission; outcome: ScanOutcome`
  - `class ExecutorBusy(Exception)` (maps to today's 503 "Busy. Try again shortly." with `Retry-After: 30`)
  - `class ExecutorUnavailable(Exception)` (maps to 503 with the text in D-W2)
  - `class ExecutorTimeout(Exception)` (replaces `SlotTimeout` at call sites)
  - `class AppScanExecutor(Protocol)`:
    - `async def prepare_upload(self, raw: bytes) -> PreparedUpload`. Raises `HTTPException` for invalid JSON or body (same details as today) and `manifests.ManifestError`.
    - `async def scan(self, project_id: str, parsed: list[manifests.ParseResult], on_start: Callable[[], bool]) -> ScanOutcome | None`. Calls `on_start()` at the moment the work really begins: inside the processing slot for inline, just before sending for remote. If it returns `False` (the run was already ended), it returns `None` without scanning, exactly as `_scan_job` does today. Never raises for scanner errors; returns a Failed outcome as `_scan_job` does. Raises `ExecutorTimeout` past `SCAN_HARD_SECONDS`.
    - `async def check_document(self, raw: bytes) -> CheckedDocument`. Raises `SubmissionRejected`, `ExecutorBusy`, `ExecutorTimeout`, or `CheckFailed`.
  - `class InlineExecutor` implementing it with today's code (`_run_exclusive`, the semaphore, `_scan_job` minus the DB `start_run`, `_check_document`), constructed as `InlineExecutor(source: VulnerabilitySource, semaphore: asyncio.Semaphore)`.
- Consumes: Task 1's `_read_upload`.

- [ ] **Step 1: Write the failing tests** in `test_appscan_executor.py`:
  - `test_inline_prepare_upload_returns_parsed_manifests`: a two-package lockfile gives `len(parsed[0].packages) == 2`.
  - `test_inline_prepare_upload_raises_manifest_error_with_code`: invalid JSON content gives a `ManifestError` with `.code == "not_json"`.
  - `test_inline_check_document_refuses_a_secret`: a submission containing an `ssk_`-shaped token raises `SubmissionRejected`.
  - `test_inline_scan_returns_failed_outcome_for_a_broken_source`: a source that raises `RuntimeError` gives `status == AppScanStatus.FAILED` and `error == "The scan could not be completed."`.
- [ ] **Step 2:** Run `pytest app/tests/test_appscan_executor.py -v`. Expected: FAIL (module missing).
- [ ] **Step 3:** Implement `executor.py`. In `app_scans.py`, `create_scan` and `submit_ci_results` call the executor. Database work stays in the route. `create_scan` passes `on_start=lambda: state.app_scans.start_run(org, scan_id)`, which runs in the worker thread inline, as today. `store_result` is called after the executor returns. `test_appscan_browser_slots.py` (a run cancelled while waiting for its slot is never started) must still pass unmodified.
- [ ] **Step 4:** Run `pytest app/tests -k "appscan or action_app" -q`. Expected: all existing tests pass **unmodified**, plus the four new ones.
- [ ] **Step 5: Commit** `git commit -m "App Scanning: put the CPU-bound steps behind an executor (no behaviour change)"`

### Task 3: A strict wire format for executor results

**Files:**

- Create: `backend/app/appscan/wire.py`
- Test: `backend/app/tests/test_appscan_wire.py`

**Interfaces:**

- Produces: `dump_parse_results(list[ParseResult]) -> dict`, `load_parse_results(dict) -> list[ParseResult]`, `dump_outcome(ScanOutcome) -> dict`, `load_outcome(dict) -> ScanOutcome`, `dump_checked(CheckedDocument) -> dict`, `load_checked(dict) -> CheckedDocument`, and `class WireError(ValueError)`. Loading uses Pydantic models with `extra="forbid"` and the same length caps as the stored columns (`AppFindingRow`: `rule_id` 128, `path` 255, `package_name` 214, `package_version` 64, `category` 64) and `MAX_FINDINGS` (5 000).
- Consumes: Task 2's `CheckedDocument`.

- [ ] **Step 1: Write the failing tests:**
  - `test_round_trip_keeps_every_field` (parametrized over a `DependencyFinding` outcome, a `CodeFinding` outcome with `line=None`, and a Failed outcome with `error`): `load_outcome(dump_outcome(x)) == x`.
  - `test_wire_rejects_unknown_fields_and_wrong_types`: an extra key, a string `line`, a 129-character `rule_id` and 5 001 findings each raise `WireError`.
  - `test_parse_results_never_carry_raw_lines`: the dumped dict of a parsed `requirements.txt` with a token-shaped line contains no substring of that line (the parser already drops raw lines; the wire must not reintroduce them).
- [ ] **Step 2:** Run `pytest app/tests/test_appscan_wire.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement `wire.py`. Severity and confidence go over the wire as their `.value` strings and back as the enums.
- [ ] **Step 4:** Run `pytest app/tests/test_appscan_wire.py -v`. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "App Scanning: strict wire format for executor results"`

### Task 4: The worker service and the remote executor

**Files:**

- Create: `backend/app/worker/__init__.py`, `backend/app/worker/main.py`
- Modify: `backend/app/appscan/executor.py` (add `RemoteExecutor`), `backend/app/core/config.py`, `backend/app/api/deps.py`, `docker-compose.yml` (an `appscan-worker` service for local use only), `docs/DEPLOYMENT.md`, `docs/app-scanning-stage-1-runbook.md`
- Test: `backend/app/tests/test_appscan_worker.py`

**Interfaces:**

- Produces:
  - `create_worker_app(settings: WorkerSettings) -> FastAPI` in `app/worker/main.py`, with routes `POST /internal/v1/prepare-upload`, `POST /internal/v1/scan` and `POST /internal/v1/check-document`. Request bodies are raw bytes (prepare, check) or `{"project_id": str, "parsed": <wire>}` (scan). Replies are wire dicts; refusals are `422 {"code": str, "message": str, "file": str | None}`.
  - `class WorkerSettings(BaseSettings)` with the prefix `SECURESCOPE_` and **only** `app_worker_secret: SecretStr` and `app_osv_enabled: bool = False`. It has no `database_url`, so the worker cannot connect.
  - `class RemoteExecutor(AppScanExecutor)` with `__init__(self, base_url: str, secret: str, transport: httpx.AsyncBaseTransport | None = None)`. Timeouts: connect 5 s; read `CHECK_WAIT_SECONDS + CHECK_RUN_SECONDS` for check-document and `SCAN_HARD_SECONDS` for scan. A connection error or 5xx raises `ExecutorUnavailable`; a read timeout raises `ExecutorTimeout`; a malformed reply raises `ExecutorUnavailable`.
  - Settings: `app_worker_url: str | None = None`, `app_worker_secret: SecretStr | None = None`. A validator refuses a URL without a secret, and refuses a URL that is neither `http://` on a private or `localhost` host nor `https://`.
- Consumes: Task 2's executor interface and exceptions, and Task 3's wire functions.

- [ ] **Step 1: Write the failing tests.** Each route test runs against the API with `RemoteExecutor(transport=httpx.ASGITransport(create_worker_app(...)))`:
  - `test_worker_refuses_without_the_secret_and_does_no_work`: no header and a wrong secret both give 401 with the same body, and `parse_manifest` is never called (monkeypatched to fail if called).
  - `test_remote_upload_gives_the_same_result_as_inline`: for the `LOCK` fixture with `Fake({"lodash": [ADV]})` injected into the worker, the response JSON matches the inline response field for field (except `id` and the timestamps).
  - `test_remote_ci_submission_refuses_a_secret_and_stores_nothing`: 422 with the existing secret code; `app_scans` and `app_findings` are empty afterwards.
  - `test_worker_unreachable_refuses_before_counting`: a transport raising `httpx.ConnectError` gives 503 with the D-W2 text, and the usage `runs_used` is unchanged.
  - `test_a_worker_that_drops_the_connection_ends_the_run_failed_not_counted`: prepare succeeds, then scan raises `httpx.RemoteProtocolError`. Result `scanner_error`; usage unchanged.
  - `test_a_worker_past_the_hard_limit_ends_the_run_failed`: scan sleeps past a monkeypatched `SCAN_HARD_SECONDS = 0.2`. Result `scanner_error`, error "The scan took too long and was stopped."
  - `test_a_malformed_worker_reply_is_a_failure_not_a_result`: the worker replies `{"status": "completed", "findings": [{"evil": 1}]}`. Nothing is stored as a finding, and the run is Failed.
  - `test_a_slow_upload_is_refused_before_the_worker_is_called`: with `BODY_READ_SECONDS = 0.2` and a body sent in delayed chunks, the result is 408 and the worker transport is never called.
  - `test_the_worker_has_no_database_setting`: `"database_url" not in WorkerSettings.model_fields`.
  - `test_inline_is_used_when_no_worker_is_configured`: `isinstance(state.app_executor, InlineExecutor)` with default settings.
- [ ] **Step 2:** Run `pytest app/tests/test_appscan_worker.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement the worker app (reusing `InlineExecutor` inside it, with its own semaphore of `max_concurrent_app_scans`), `RemoteExecutor`, and the settings and wiring in `deps.py` (`RemoteExecutor` when `app_worker_url` is set). The worker logs only route, status and duration, never bodies.
- [ ] **Step 4:** Run `pytest app/tests -k "appscan or action_app" -q`, then `ruff check .` and `mypy app`. Expected: all pass.
- [ ] **Step 5:** Add the `appscan-worker` service to `docker-compose.yml`: same image, command `uvicorn app.worker.main:create_worker_app --factory --host 0.0.0.0 --port 8001`, no ports published, no database environment variables, and `read_only`, `cap_drop` and `no-new-privileges` as the backend has. Then document the Render steps (Private Service, same region, `SECURESCOPE_APP_WORKER_SECRET` on both services, `SECURESCOPE_APP_WORKER_URL=http://<private host>:8001` on the API) in `docs/DEPLOYMENT.md`, and the kill switch (unset the URL to return to inline) in the runbook.
- [ ] **Step 6: Commit** `git commit -m "App Scanning: private worker service and remote executor (off unless configured)"`

### Task 5: Prove it under load, and update the privacy record

**Files:**

- Modify: `scripts/loadtest_appscan.py` (`--worker-container` option for memory and CPU of the worker), `docs/load-test-results.md`, `docs/app-scanning-v1-privacy-and-licensing.md` (section 4c facts table), `docs/app-scanning-v1-plan-entitlements.md` (section 9)

**Interfaces:**

- Consumes: Task 4's worker container and settings.

- [ ] **Step 1:** Run the API at one core and the worker at the D-W3 size with `docker compose` (both local), then `python scripts/loadtest_appscan.py --base http://127.0.0.1:8092 --container <api> --worker-container <worker> --db-container <db>`.
- [ ] **Step 2:** Record in `docs/load-test-results.md`, under "App Scanning with the worker":
  - the API's CPU per run (expected: under 0.05 s for every size, since only reading, accounting and inserts remain)
  - the worker's CPU per run
  - the signed-in page p95 during both bursts (target: within 2× the idle value)
  - whether a 5 000-finding submission completes within 20 s at the worker's size
- [ ] **Step 3:** Add a row to the 4c facts table in the privacy record: "With the worker on, request bodies pass in memory from the API to a private worker on the same hosting provider's private network; the worker has no database access and stores nothing." Add the measured numbers to the entitlements record, section 9.
- [ ] **Step 4: Commit** `git commit -m "App Scanning worker: load test and records"`
