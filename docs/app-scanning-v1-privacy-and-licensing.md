# App Scanning v1: privacy and licensing review

Date: 26 Oct 2026. **This is a record of what is known, unknown and blocked. It is not legal advice and contains no legal conclusions.** The official OSV documentation, data pages and terms could not be fetched from this session (the hosts were outside the session's allowed list), so every statement about OSV below is from general knowledge and is marked UNVERIFIED. Nothing may ship on the basis of this file.

## 1. The data flow, exactly (proposed; nothing is implemented)

If SecureScope's server performs the lookup (decision D-A, option 1):

| Sent to the dependency database                                    | Not sent                                                                                                                                                                                                            |
| ------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Ecosystem (for example `npm`, `PyPI`), package name, exact version | File names, project name, workspace or organisation name, user identity, repository URL, source code, secrets, tokens, any other manifest content, our API keys (none exist for OSV as far as is known: UNVERIFIED) |

Transport: HTTPS to one fixed host stored as a constant; no redirects; request and response size caps; timeouts; batch size cap. The IP address of the SecureScope server is visible to the service as for any request. The user's IP is not sent.

Package names can be private (internal packages). A private package name sent to a public service is a disclosure. Proposed mitigations to decide: let the user mark a project "private packages" so unrecognised scoped names are skipped and reported as skipped; document the behaviour.

## 2. Items to verify before release (all UNVERIFIED)

| #   | Item                                                                                 | Status                                                                      |
| --- | ------------------------------------------------------------------------------------ | --------------------------------------------------------------------------- |
| V1  | Endpoints and request/response fields (query, batch query, record fetch, pagination) | UNVERIFIED                                                                  |
| V2  | Request, batch and response size limits                                              | UNVERIFIED                                                                  |
| V3  | Rate limits, fair-use or service terms, commercial-use position for the hosted API   | UNVERIFIED                                                                  |
| V4  | Licence of the data, and of the aggregated sources inside it, attribution duties     | UNVERIFIED                                                                  |
| V5  | Whether caching or storing records and redistributing them in reports is permitted   | UNVERIFIED                                                                  |
| V6  | Whether the service logs or retains requests, and for how long                       | UNVERIFIED                                                                  |
| V7  | How severity and fixed versions are represented in real responses                    | UNVERIFIED (to be checked against live responses in a test with permission) |

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

## 5. Gates

| Gate | Condition                                                                                    | State |
| ---- | -------------------------------------------------------------------------------------------- | ----- |
| G1   | V1 to V7 verified from the official sources and recorded here with the date                  | Open  |
| G2   | Every component row above reviewed                                                           | Open  |
| G3   | Privacy notice text approved by the owner (and a lawyer where needed) and matching the build | Open  |
| G4   | Owner decision D-A                                                                           | Open  |

No lookup to an external service is enabled until G1, G3 and G4 are closed. Tests use mocked responses only.
