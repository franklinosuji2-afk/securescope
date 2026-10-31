# App Scanning v1: privacy and licensing review

Date: 26 Oct 2026. **This is a record of what is known, unknown and blocked. It is not legal advice and contains no legal conclusions.** The official OSV documentation, data pages and terms could not be fetched from this session (the hosts were outside the session's allowed list), so every statement about OSV below is from general knowledge and is marked UNVERIFIED. Nothing may ship on the basis of this file. **Update 31 Oct 2026:** the official pages were read; section 2 now records what they say, with sources.

## 1. The data flow, exactly (proposed; nothing is implemented)

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

## 4a. Provisional privacy wording (owner direction, 26 Oct 2026). NOT APPROVED, NOT FOR PUBLICATION

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

## 5. Gates

| Gate | Condition                                                                                    | State |
| ---- | -------------------------------------------------------------------------------------------- | ----- |
| G1   | V1 to V7 verified from the official sources and recorded here with the date                  | Partly (31 Oct 2026): V1, V7 verified; V2, V4 partly; V3 terms, V5, V6 not stated |
| G2   | Every component row above reviewed                                                           | Open  |
| G3   | Privacy notice text approved by the owner (and a lawyer where needed) and matching the build | Open  |
| G4   | Owner decision D-A                                                                           | Closed 31 Oct 2026: option 1 (the server looks packages up), built behind `SECURESCOPE_APP_OSV_ENABLED`, off by default |

No lookup to an external service is enabled until G1, G3 and G4 are closed. The client exists since 31 Oct 2026 (`app/services/osv.py`) but runs only when `SECURESCOPE_APP_OSV_ENABLED` is set; no deployment sets it. Its outbound payload (ecosystem, name, version only) is asserted in `test_appscan_osv.py`; all tests use mocked responses.
