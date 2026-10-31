# App Scanning v1: privacy and licensing review

Date: 26 Oct 2026. **This is a record of what is known, unknown and blocked. It is not legal advice and contains no legal conclusions.** The official OSV documentation, data pages and terms could not be fetched from this session (the hosts were outside the session's allowed list), so every statement about OSV below is from general knowledge and is marked UNVERIFIED. Nothing may ship on the basis of this file. **Update 31 Oct 2026:** the official pages were read; section 2 now records what they say, with sources.

## 1. The data flow, exactly (built 31 Oct 2026, switched off: `SECURESCOPE_APP_OSV_ENABLED`)

If SecureScope's server performs the lookup (decision D-A, option 1):

| Sent to the dependency database                                    | Not sent                                                                                                                                                                                                            |
| ------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Ecosystem (for example `npm`, `PyPI`), package name, exact version | File names, project name, workspace or organisation name, user identity, repository URL, source code, secrets, tokens, any other manifest content, our API keys (none exist for OSV as far as is known: UNVERIFIED) |

Transport: HTTPS to one fixed host stored as a constant; no redirects; request and response size caps; timeouts; batch size cap. The IP address of the SecureScope server is visible to the service as for any request. The user's IP is not sent.

Package names can be private (internal packages). A private package name sent to a public service is a disclosure. Proposed mitigations to decide: let the user mark a project "private packages" so unrecognised scoped names are skipped and reported as skipped; document the behaviour.

## 2. Items to verify before release

Read on 31 Oct 2026 from the official documentation: https://google.github.io/osv.dev/api/, `/post-v1-query/`, `/post-v1-querybatch/`, `/get-v1-vulns/`, `/faq/`, `/data/`, and https://ossf.github.io/osv-schema/ (schema 1.9.2). "Not stated" means the pages read say nothing about it; it is not a conclusion that something is allowed.

| #   | Item                                                                                 | Status (31 Oct 2026)                                                                                                                                                                                                                                                                                                                                |
| --- | ------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| V1  | Endpoints and request/response fields (query, batch query, record fetch, pagination) | **Verified.** `POST https://api.osv.dev/v1/querybatch` takes `{"queries": [{"package": {"name", "ecosystem"}, "version"}]}` and answers in the same order with only `id` and `modified` per advisory; `GET /v1/vulns/{id}` returns the full record. A batch result paginates (`next_page_token`) above 1,000 advisories for one query or 3,000 in total. Ecosystem names are case-sensitive (`npm`, `PyPI`). |
| V2  | Request, batch and response size limits                                              | **Partly.** Responses are capped at 32 MiB over HTTP/1.1. Maximum queries per batch, request size and client timeouts: not stated. SecureScope sends at most 500 queries per batch and caps replies at 8 MiB (batch) and 1 MiB (record).                                                                                                         |
| V3  | Rate limits, fair-use or service terms, commercial-use position for the hosted API   | **Partly.** "Currently there are no limits on the API" (API page and FAQ). No API key is mentioned. Terms of service and a commercial-use position: **not stated** on the pages read. Open.                                                                                                                                                    |
| V4  | Licence of the data, and of the aggregated sources inside it, attribution duties     | **Partly.** Per source (data page): GitHub Advisory Database CC-BY 4.0, PyPI Advisory Database CC-BY 4.0 (the two sources for npm and PyPI); others vary, including Chainguard/Wolfi CC-BY-NC-ND 4.0, which SecureScope does not query. OSV's own licence for the aggregate and any attribution rule: not stated. Results show an attribution line naming OSV.dev and the CC-BY 4.0 sources. |
| V5  | Whether caching or storing records and redistributing them in reports is permitted   | **Not stated.** Bulk downloads are documented (`gs://osv-vulnerabilities`). SecureScope keeps fetched records in memory only (up to 2,000, lost on restart) and stores the derived finding text with the run. Open.                                                                                                                            |
| V6  | Whether the service logs or retains requests, and for how long                       | **Not stated.** No privacy policy is linked from the pages read. Open; needed for the privacy notice (section 4, item 5).                                                                                                                                                                                                                       |
| V7  | How severity and fixed versions are represented in real responses                    | **Verified** (schema and one live lookup of public packages on 31 Oct 2026). `severity[]` holds CVSS vector strings (`CVSS_V3`, `CVSS_V4`); GitHub records also carry `database_specific.severity` (`HIGH`, `MODERATE`, ...). Fixed versions are `fixed` events in `affected[].ranges[].events`. A CVSS v3 vector is converted to its base score; a CVSS v4-only record shows Medium with "no severity given". |

## 3. Component licence register

Every scanner, rule set, database, bundled dependency and container image needs a row filled with a reviewed licence before release. Rows start empty on purpose.

| Component                               | Version | Licence      | Commercial use | Redistribution | Attribution  | Rule or data licence | Status                                                                   |
| --------------------------------------- | ------- | ------------ | -------------- | -------------- | ------------ | -------------------- | ------------------------------------------------------------------------ |
| Dependency vulnerability database (OSV) | n/a     | not reviewed | not reviewed   | not reviewed   | not reviewed | not reviewed         | **BLOCKED FOR RELEASE**                                                  |
| Secret scanner (candidate not chosen)   |         |              |                |                |              |                      | **BLOCKED FOR RELEASE** (no choice made)                                 |
| SAST engine (candidate not chosen)      |         |              |                |                |              |                      | **BLOCKED FOR RELEASE**                                                  |
| SAST rule set                           |         |              |                |                |              |                      | **BLOCKED FOR RELEASE** (rule licences often differ from the engine's)   |
| Container image for the Action, if any  |         |              |                |                |              |                      | **BLOCKED FOR RELEASE**                                                  |
| New Python or JavaScript dependencies   |         |              |                |                |              |                      | To be added per dependency; `pip-audit` and `npm audit` run at that time |

Rule: if a row is not reviewed, the component is not bundled, shipped or redistributed. The Action should invoke tools the customer installs themselves wherever possible, which reduces what SecureScope redistributes; this still needs review.

## 4. Privacy notice changes required (draft requirements, not wording)

Added only when the feature is enabled, and only to match the implementation:

1. Name the dependency database as a recipient of package ecosystem, name and version, for the purpose of checking known vulnerabilities (if D-A option 1).
2. State what is not sent (list in section 1) and that source code never reaches SecureScope in v1.
3. State what SecureScope stores: findings, file names, line numbers, package coordinates, digests, scan metadata; never file contents or secret values.
4. State retention (follows the plan's history period) and deletion with the project or account.
5. Transfer mechanism and the recipient's location: depends on V6 and counsel's view. **Owner / lawyer item.**
6. Update `docs/PRIVACY.md`, `docs/DATA_RETENTION.md` and the Privacy page together. A generic sentence that does not match the data flow must not be published.

## 4a. Provisional privacy wording (owner direction, 26 Oct 2026). NOT APPROVED, NOT FOR PUBLICATION. Superseded by the draft in 4c

The owner approved this draft as a **direction** only. Publication is blocked until the actual data flow and the OSV terms are verified (gates G1 and G3). It is not in `docs/PRIVACY.md`, not on the Privacy page and must not be added to either yet. If the implementation differs from it, the text changes, not the implementation's description.

> **Application dependency vulnerability checks**
>
> When dependency vulnerability scanning is performed, SecureScope may transmit package names, versions and ecosystem information to the OSV vulnerability information service to retrieve information about known vulnerabilities. This information may reveal aspects of the technology stack used by an application.
>
> SecureScope does not intentionally transmit application source code or application secrets as part of these vulnerability lookups. Lookup failures may result in an incomplete assessment.
>
> The processing details, applicable third-party terms and relevant data-handling information will be described in this notice before the functionality is enabled.

Before the final paragraph may be written, verify and record (with date and source) in section 2: the precise endpoint and fields transmitted (V1); whether requests carry any other identifying information (the server's IP address is visible to any recipient; confirm nothing else); the applicable terms and privacy documentation (V3, V4); logging, caching and retention behaviour on the recipient's side (V5, V6); and whether `docs/PRIVACY.md`, `docs/DATA_RETENTION.md` and any data-protection documentation need updating. State of the implementation (31 Oct 2026): the lookup exists but is off unless `SECURESCOPE_APP_OSV_ENABLED` is set; the default source is still "unavailable". The outbound payload test (security model T10) exists: `test_only_ecosystem_name_and_version_are_sent_to_the_fixed_host`.

Note on the wording "does not intentionally transmit": the implementation design sends only ecosystem, name and version (section 1). That is a statement about a future client, to be proven by a test of the outbound payload when the client exists (security model T10). Until then it describes intent, not behaviour.

## 4b. Review status of the Stage 1 questions (26 Oct 2026)

| Question | Status | Evidence collected so far |
|---|---|---|
| OSV API terms, permitted use, request limits | **BLOCKED, not reviewed** | None. The official pages were unreachable from the build environment |
| Caching and redistribution restrictions | **BLOCKED** | None |
| Attribution requirements | **BLOCKED** | None |
| Licence of the vulnerability data and of its aggregated sources | **BLOCKED** | None |
| Licence of any bundled scanner, rule set or dataset | **BLOCKED FOR RELEASE** | Nothing is bundled in Stage 1; no scanner is chosen |
| Privacy and data-processing implications | **BLOCKED** | Draft direction in section 4a only; no legal conclusion is recorded here |

Nothing in this file is a legal conclusion and nothing is marked approved.

## 4c. Draft privacy notice text for App Scanning (31 Oct 2026). NOT APPROVED, NOT FOR PUBLICATION

Written from the code on `main` at `4eb2346`, to describe what the build does today, not what is planned. It replaces the direction in 4a once approved. It is not on the Privacy page and must not be added there until the owner (and a lawyer where needed) approves it, which closes gate G3. Points marked **[Decision]** or **[Lawyer]** are open; the text must change if the answer changes the facts.

### Facts it is based on (with where to check them)

| Fact | Source |
| --- | --- |
| Browser uploads are read in memory; file contents are never stored. A run stores file name, size and SHA-256 digest only | `api/v1/app_scans.py` (`inputs`), `models/app_scan.py` |
| Package names are stored only inside findings (package, version, advisory id, severity, text, fixed versions, links). Packages without a finding are not stored | `appscan/pipeline.py`, `AppFindingRow` |
| CI submissions carry per finding: rule id, severity, file path, line, and for static analysis a rule title and message; plus tool name and version, project id, branch and first 12 characters of the commit. Secret findings carry no message and no value; the server refuses a document that looks like it contains a secret | `action/app-scanning/README.md`, `appscan/submission.py` |
| Each run records who started it (or which API token sent it) and when; audit events `app_project.created`, `app_project.archived`, `app_scan.created`, `app_scan.submitted`, `app_scan.finished` | `api/v1/app_scans.py` |
| No package information leaves SecureScope while `SECURESCOPE_APP_OSV_ENABLED` is off (production: off on 31 Oct 2026, checked through `lookups_available`) | `api/deps.py`, `services/osv.py` |
| Runs and findings are deleted by the hourly maintenance job once older than the plan's history period (Free 30 days, Professional 90, Agency 365), the same rule as website scans, except that runs from the current usage month are never deleted and queued or running runs are never touched. Projects stay until the workspace is deleted (or the account, for a workspace with no other member); archiving a project deletes nothing (added 31 Oct 2026) | `repositories/appscans.py` `delete_expired_history`, `main.py` maintenance loop, `test_appscan_retention.py` |
| The account data export (Account page) does not include App Scanning data, as it does not include website scan data | `repositories/accounts.py` `export_personal_data` |

### Draft text (to sit under "What we store and why", after "Scan data")

> **App Scanning (Early Access, pilot workspaces only):** App Scanning checks the dependencies and code of an application. It is open only to workspaces we have invited to the pilot.
>
> *Files you upload.* When you upload a dependency file (package-lock.json, package.json or requirements.txt), it is read in memory to list the packages and exact versions it declares, and is not stored. For each run we keep the file name, its size and a fingerprint (SHA-256 digest), which checks ran or could not run and why, when the run started and ended, and who started it. For each finding we keep the package name, version and ecosystem, the advisory identifier, its title, severity and description, the fixed versions and links to the advisory. We do not keep the list of packages that had no finding.
>
> *Results your CI pipeline sends.* If you use the SecureScope GitHub Action, the analysis tools run in your own pipeline and only their results are sent to us: for each finding the rule identifier, severity, file path and line number, and for code analysis the rule's title and message; the names and versions of the tools; the project; the branch name and the first 12 characters of the commit identifier. Your source code is not sent, and the value of a detected secret is never sent or stored. We refuse a submission that looks like it contains a secret. Check that your analysis rules do not copy code into their messages, because a rule's message is sent as written.
>
> *What leaves SecureScope.* At present nothing from App Scanning is sent to anyone else: the vulnerability database is not connected, so dependency checks end as "failed" and are not counted. **[Decision: publish this sentence now; replace it with the OSV paragraph below only on the day lookups are switched on.]**
>
> Needed to provide the feature you use (Art. 6(1)(b) GDPR). **[Lawyer: confirm the legal basis for pilot use.]**
>
> *How long we keep it.* App Scanning results (runs and their findings) are deleted automatically after the history period of your plan, as for website scans (30 days on Free, 90 days on Professional, 365 days on Agency), but never during the calendar month in which they count towards your allowance. Projects are kept until you delete the workspace, or your account if no one else is a member of the workspace; archiving a project does not delete it. Deleting the workspace deletes everything in it at once.

### Paragraph to add only when `SECURESCOPE_APP_OSV_ENABLED` is switched on

> *Vulnerability lookups.* To check whether a package version has a known vulnerability, our server sends the package ecosystem (for example npm or PyPI), the package name and the exact version to OSV.dev, a public vulnerability database **[Lawyer/owner: name the operator and its location after verifying them; not stated in the OSV documentation read on 31 Oct 2026]**. Nothing else is sent: not the file, its name, your project, your workspace or who you are. OSV.dev sees our server's address, not yours. A package name can reveal part of how your application is built; if you use private packages, their names are sent too. If OSV.dev cannot be reached, the run is marked incomplete or failed, never clean.

Before that paragraph may be published, the open items in section 2 must be closed: V3 (terms of service and commercial use), V5 (caching and display of records) and V6 (whether OSV logs or keeps requests, and for how long), plus a decision on private package names (section 1).

### Other places that change with it

- `docs/PRIVACY.md` and `docs/DATA_RETENTION.md`: add the same facts.
- Privacy page "Service providers": no change while lookups are off (App Scanning uses the same hosting and database providers). With lookups on, OSV.dev is added with its role. **[Lawyer: processor or independent recipient?]**
- Early Access page, card "Not yet decided": keep as is until the notice is published.

## 5. Gates

| Gate | Condition                                                                                    | State |
| ---- | -------------------------------------------------------------------------------------------- | ----- |
| G1   | V1 to V7 verified from the official sources and recorded here with the date                  | Partly (31 Oct 2026): V1, V7 verified; V2, V4 partly; V3 terms, V5, V6 not stated |
| G2   | Every component row above reviewed                                                           | Open  |
| G3   | Privacy notice text approved by the owner (and a lawyer where needed) and matching the build | Open. Draft written 31 Oct 2026 (section 4c), awaiting review |
| G4   | Owner decision D-A                                                                           | Closed 31 Oct 2026: option 1 (the server looks packages up), built behind `SECURESCOPE_APP_OSV_ENABLED`, off by default |

No lookup to an external service is enabled until G1, G3 and G4 are closed. The client exists since 31 Oct 2026 (`app/services/osv.py`) but runs only when `SECURESCOPE_APP_OSV_ENABLED` is set; no deployment sets it. Its outbound payload (ecosystem, name, version only) is asserted in `test_appscan_osv.py`; all tests use mocked responses.
