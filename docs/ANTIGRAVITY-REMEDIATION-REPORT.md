# Buildathon Radar remediation report

**Local login update.** At the owner's request, HTTP Basic login was removed after remediation. The tracker trusts localhost callers and still enforces same-origin browser writes and signed event actions. Authentication findings below record the original remediation.


## Result

The local tracker on port 8015 now requires authentication and uses provenance-aware discovery. Email is disabled for both digest and failure notifications. The five original Freebuff reports match their pre-remediation copies byte for byte. The [remediation tracker](ANTIGRAVITY-REMEDIATION-TRACKER.md) maps the findings and roadmap IDs to changes and verification.

Work is on the local `remediation/freebuff` branch, based on `adapt-antigravity`. The backup is under `~/.local/state/buildathon-radar/pre-remediation-jtixi51g`. The directory is owner-only and contains a SQLite online backup, configuration, audit documents and the local environment file. No changes were pushed or deployed publicly.

## Baseline and audit corrections

- Original suite on this machine had 398 passing tests. The dashboard returned HTTP 200 and the database contained 116 events. Many tests accepted fixtures as expected discovery output.
- Freebuff correctly identified fabricated source output, historical headlines recast as opportunities, unreliable counts, open administrative routes, a calendar interpolation bug, and display problems. Several network adapters also contained fallback fixtures.
- The audits reuse F-IDs inconsistently. The tracker carries both the Full Audit and Functional QA mappings. The bare string `ELIGIBLE` alone did not match an inclusion rule in the old implementation. The real issue was that asserted or incidental text could influence a rules decision without explicit participation evidence.
- The tracker launchd agent was already loaded when remediation began. The weekly job was inactive. The tracker was restarted and its authenticated HTTP routes were tested.
- In the backup, the calendar had 29 rules and 54 unique enabled days. At final verification, the live database had 46 rules and 69 unique enabled days. A row-by-row comparison confirmed that all 29 baseline rows, including their original IDs, values and timestamps, remain exact. Seventeen additional rows appeared during the run. A concurrent edit to `config/profile.json` was also detected and preserved.

## Database and calendar

- `buildathon_radar/tracker_store.py` adds SQLite migration version 1. It records live or legacy provenance, registration state, factor scores, eligibility evidence and its input rules, date provenance and recent feed-level telemetry. Existing event rows default to legacy provenance, so they remain available in history and retain their user action state.
- Discovery event, source health and scan-history writes commit together. A scan-log failure test verifies rollback. Repeating the same controlled production scan added zero duplicate rows.
- Calendar writes and conflict recomputation run in one transaction. The inclusive overlap formula is retained. SQL toggles are atomic, and an intentionally empty calendar after deletion remains empty.
- SQLite `integrity_check` returned `ok`. The original 116 rows remain, and the live scan added 32 source listings. Both `.env` and `tracker.db` are mode `0600`.

## Security and email

- `local_security.py` protects local pages and APIs with HTTP Basic authentication for `admin` using the owner-held `TRACKER_SECRET`. The service binds to loopback and rejects unexpected Host headers. Browser writes require same-origin request metadata and a custom header. Signed event links render a confirmation page, while the authenticated POST applies a valid signed action.
- CSP is nonce-based for scripts, with script attributes disabled. Responses include frame denial, MIME sniffing protection, a no-referrer policy and no-store caching. Calendar data travels in escaped attributes and is read through the DOM. Public API docs and schema routes are disabled. The status-only `/health` route is available for local supervision.
- The deployment assumes the owner controls the local machine and the loopback port. The OWASP ASVS 5.0.0 reference informed review of request authentication, cross-origin mutations, encoding and browser response controls. This work did not assess the full standard.
- No Git history blob matched the current configured credential values in a local comparison that emitted counts only. Exact filenames for the live environment and database were absent from tracked history. A prior group/world-readable SMTP credential may already have been accessible to other local accounts. Revoke that credential if it was exposed.
- `deliver.py` hard-disables SMTP with an application gate, and the local environment also sets `ENABLE_EMAIL=false`. Local archive generation continues without email credentials. Tests verified both SMTP constructors remain uncalled in the disabled paths. No SMTP connection, test send, digest send or reminder was attempted.

## Discovery and source verification

| Configured feed | Network verification and current limits |
|---|---|
| Devpost | 9 listing records returned and accepted. The feed exposes a submission period. It is not used as an event or registration date. |
| Devfolio | 8 listings returned and accepted. Event times and application windows are mapped from the observed listing schema. Eligibility stays unknown without explicit school participation rules. |
| Unstop | 15 listings returned and accepted. Canonical listing URLs and explicit registration-window fields are mapped. The registration end time does not establish the event date. |
| HackerEarth | 3 records returned. All were monthly challenges and were rejected. A responding endpoint did not count as successful hackathon discovery in this scan. |

All other registry entries are unavailable in the opportunity pipeline. Nineteen previously returned fixtures: AllEvents, AWS Community, CNCF, DoraHacks, ETHGlobal, Eventbrite, FOSS United, GDG, GitHub Community, Hack2skill, Hackathon.com, Indian Colleges, Meetup, Microsoft Reactor, NVIDIA Developer, Tech Companies, TenTimes, Townscript and X/Twitter. The old MLH adapter fetched a page and supplied a fixture, Reddit substituted a fixture after failure, LinkedIn attributed news headlines to LinkedIn, and Search turned news into events. All four now report an unsupported feed.

The retained endpoints were exercised with their robots checks and size and timeout bounds. These public listing interfaces may change. Feed reachability and syntactic link validity were verified separately from organizer confirmation, comprehensive platform terms review and registration-link usability. There was no blanket verification of organizer rules or registration access. The live listing records remain unverified. At the first live post-migration check the app showed zero open, dated, conflict-free opportunities, four upcoming listings and four exam conflicts. A live check matched seven filter totals against rendered rows, including pagination of the 28 needs-verification listings. An honest empty open view is expected when the evidence is insufficient.

## Frontend and tests

- `tracker_service.py` now shares navigation, theme and core controls across dashboard, calendar, sources, list, detail and the event 404. The calendar uses a native dialog. Server-side search, unified view counts, pagination and date groups replaced the original client-only list filtering. Event details display evidence, scoring factors and source references with scan IDs from new ingestions.
- Dedicated tests cover unsupported feeds, real-schema mocked listings, invalid responses and URLs, timeout behavior, lifecycle filtering, conflicting eligibility rules, duplicate guards and lineage, scan rollback, authentication, origin enforcement, inert calendar values and disabled email.
- Final Python suite recorded 421 passing tests. `git diff --check`, `pip check` and the two launchd plist syntax checks passed. The locally run `pip-audit` reported no known vulnerabilities for the pinned dependency set. The new dependency workflow has not run on GitHub.
- Real Chromium exercised six routes at 1440, 1280, 768, 390 and 320 px in both themes. It exercised search, filtering, list/grid selection, shortlisting, calendar create/edit/toggle and deletion, and a scan against a disposable database copy. No unexpected JavaScript exceptions or HTTP errors were observed during that run. The 404 route was expected. Live runtime HTTP checks independently covered authentication, the health endpoint, mutation-origin rejection and major pages.

## Remaining work

- The weekly refresh agent remains inactive. The repository plist now invokes the provenance-aware engine without email. The installed weekly plist was not updated or loaded. The equivalent manual refresh ran successfully and the UI shows the last refresh or a stale indicator. The original manual digest command remains available for local reports and does not promote its legacy rows into the opportunity feed.
- A full component contrast scan, axe and screen-reader verification, further removal of decorative emoji, and keyboard-only testing remain open. The measured heading contrast and exact-width navigation checks cover the specific reported failures.
- Sources includes recent merge review and warns when a previously successful feed has gone 14 days without a successful scan. An organizer confirmation workflow and reminder ledger remain open or deferred. Reminders and test-send paths are deferred while email is intentionally disabled.
- Cross-source merging was verified with deterministic test records. The observed live sample contained no confirmed duplicate pair. Sparse registration and eligibility evidence limits the current student spotlight. No manual subscription, fee payment or registration was performed.
