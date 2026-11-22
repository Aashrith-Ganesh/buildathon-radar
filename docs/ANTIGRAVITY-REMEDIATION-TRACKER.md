# Freebuff remediation tracker

**Local login update.** At the owner's request, HTTP Basic login was removed after remediation. The tracker trusts localhost callers and still enforces same-origin browser writes and signed event actions. Authentication findings below record the original remediation.


The Full Audit and Functional QA reuse F-IDs for different findings. Both mappings are listed. VERIFIED indicates that the corrected behavior was exercised. IN PROGRESS indicates remaining acceptance work.

## Full Application Audit

| ID | Finding and root cause | Affected code and correction | Verification | Status |
|---|---|---|---|---|
| F-01 | Fixtures and network fallbacks masqueraded as live discovery | discovery/adapters, engine, tracker_store. Remove fixture paths and quarantine legacy rows | All 27 adapter contracts and repeated scan tests | VERIFIED |
| F-02 | LinkedIn-labelled Google News headlines became events | discovery/adapters/social.py. Disable unsupported feed | No output or health success from this source | VERIFIED |
| F-03 | Dashboard rendered completed events | discovery/integrity.py, tracker_store. Use lifecycle views | Historical listing excluded in count and render assertions | VERIFIED |
| F-04 | Headline and filters counted different populations | tracker_store, tracker_service. Use one set of views | Count and rendered-row regression test | VERIFIED |
| F-05 | Search fabricated dates. Adapter assertions also influenced eligibility | discovery/adapters/search_engine.py, rule_engine. Remove headline ingestion and require eligibility rules | Disabled-adapter and contradictory-evidence tests | VERIFIED |
| F-06 | Format and city were conflated, scores saturated, and the hero ignored preferences | rule_engine, tracker_store. Correct geography, normalize scoring, constrain spotlight | Online geography and local spotlight regressions. Visual factor rendering checked on detail | VERIFIED |
| F-07 | Title and nearby dates over-merged events and lineage was dropped at write time | discovery/deduplicator.py, engine, tracker_store. Add corroboration and persist source references | Different locations, years, hosts, undated pairs, repeat scan and cross-source lineage tests | VERIFIED |
| F-08 | Conflict count was labelled as calendar size | tracker_service, tracker_store. Distinguish event conflicts, rules and unique days | Chromium calendar and exact row comparison with backup | VERIFIED |

## Functional QA

| ID | Finding and root cause | Affected code and correction | Verification | Status |
|---|---|---|---|---|
| F-01 | Literal event feeds presented as real | discovery/adapters, engine. Remove seeded results and label unsupported feeds | Mocked contract tests, live scan and history separation | VERIFIED |
| F-02 | LinkedIn-labelled headline ingestion | discovery/adapters/social.py. Remove pseudo-discovery | Disabled-adapter and history-exclusion tests | VERIFIED |
| F-03 | Search supplied fallback dates and eligibility | discovery/adapters/search_engine.py. Remove search from the event pipeline | Unsupported adapter test | VERIFIED |
| F-04 | Expired records appeared under open events | discovery/integrity.py, tracker_store, tracker_service. Compute lifecycle separately from user state | Active and history regression tests | VERIFIED |
| F-05 | Expected fields were absent or misinterpreted, and unknown deadlines read as open | discovery/adapters/dedicated.py, base_adapter.py, tracker_service. Map observed fields, parse timestamps, show unknowns | Controlled live responses and ISO conversion test. Some sources still omit dates | VERIFIED |
| F-06 | Adapter value was an eligibility input and generic words could trigger inclusion | rule_engine, tracker_store. Require independent rule evaluation and store evidence | Explicit school and all-student rules, adult-only, undergraduate-only and contradictory evidence tests | VERIFIED |
| F-07 | Online Bengaluru text triggered local venue score | rule_engine.py. Score online before location | Online score regression | VERIFIED |
| F-08 | Score was capped despite a 115-point total | rule_engine, tracker_service. Normalize the total and show factors | Rule-engine tests and event detail render | VERIFIED |
| F-09 | Generic titles merged across unrelated events | discovery/deduplicator.py, engine and tracker_store. Guard dates, places and organizers | Distinct-city, year, missing dates and lineage regressions | VERIFIED |
| F-10 | A successful function return counted as healthy, including fixture and fallback paths | engine, tracker_store, tracker_service. Store feed-level status and current scan counts | Timeout, rollback and real HackerEarth rejection | VERIFIED |
| F-11 | Different filters and metrics used different eligibility, date and location criteria | tracker_store, tracker_service. Derive them from the same rows | Test covers All Open, Bengaluru, closing soon and exclusion of historical records | VERIFIED |
| F-12 | Search only hid existing rows client-side | tracker_service.py. Search before pagination, add result count and recovery links | Chromium search and empty state | VERIFIED |
| F-13 | Event detail left lineage and score logic opaque | tracker_service, tracker_store. Show source links, retrieval times, factors and eligibility evidence | Lineage and per-sighting scan IDs tested, factor bars added to detail | VERIFIED |
| F-14 | Root used a JavaScript redirect | tracker_service.py. Use 307 and explicit health endpoint | Automated and live HTTP checks | VERIFIED |
| F-15 | Disabled email checked credentials first and fatal-failure email ignored the switch | deliver.py and main.py. Hard-disable both paths and return skipped after local archive | Unit tests spy on both SMTP constructors. Reminders and test-send commands deferred by owner instruction | VERIFIED |
| F-16 | Historical audit recorded no loaded jobs | scheduler/launchd, engine, tracker_service. Update refresh command and display freshness | Tracker job loaded and restarted. Weekly job remains inactive. Manual refresh completed | IN PROGRESS |

## Security Audit

| ID | Finding and root cause | Affected code and correction | Verification | Status |
|---|---|---|---|---|
| S-01 | Loopback routes had no authentication | local_security.py, tracker_service.py. Require admin Basic auth, enforce loopback Host | Unauthenticated and authenticated behavior tested against live tracker | VERIFIED |
| S-02 | Cross-origin mutations had no boundary checks | local_security.py and tracker_service. Require custom header and same-origin browser parameters | Reject foreign origin, missing header and invalid host | VERIFIED |
| S-03 | Blackout values were interpolated into an inline handler | tracker_service.py. Use escaped data attributes, listeners and safe form values | Automated literal-text assertion and Chromium apostrophe edit on database copy | VERIFIED |
| S-04 | Responses lacked CSP and framing controls | local_security.py. Add per-response script nonces, frame protection, no-store and other headers | Header tests and Chromium console verification | VERIFIED |
| S-05 | Optional signed mutation token and GET state changes | tracker_service.py. Require token and authenticated POST. GET shows confirmation | Verify no state write on GET, reject missing and invalid tokens | VERIFIED |
| S-06 | FastAPI published internal API docs | tracker_service.py and local_security.py. Disable docs/schema | HTTP 404 checks | VERIFIED |
| S-07 | Environment credentials and SQLite were group/world readable | Restrict local files to 0600, secure backup, retain Git ignore policy | Mode, Git and backup checks. Revoke SMTP app password if prior file accessibility exposed it | VERIFIED |
| S-08 | Dependency versions floated | requirements.txt, requirements.lock and dependency-audit workflow. Pin versions and automate advisory checks | pip check and pip-audit run locally. Workflow awaits first CI execution | VERIFIED |
| S-09 | Personal calendar and tracker records were publicly readable on loopback | local_security.py and tracker_service. Authenticate reads, restrict opportunity API to live listings | Unauthenticated API returns 401 | VERIFIED |

## UX and accessibility audit

| ID | Finding and root cause | Affected code and correction | Verification | Status |
|---|---|---|---|---|
| U-01 | Pages used incompatible navigation and control classes | tracker_service.py. Shared navigation, theme, control and table styles | Six pages exercised in Chromium in both themes | VERIFIED |
| U-02 | Hardcoded white headings in light theme | tracker_service.py. Semantic foreground and surface colors | Computed headings and backgrounds in both themes. Full component contrast scan remains | IN PROGRESS |
| U-03 | Fixed-width navigation clipped on phones | tracker_service.py. Wrap nav and filters and constrain table overflow | 1440, 1280, 768, 390 and 320 px Chromium measurements | VERIFIED |
| U-04 | Promotional metrics substituted for telemetry | tracker_service, tracker_store and engine. Remove percentage claims, use actual status and counts | Browser and live scan stats | VERIFIED |
| U-05 | Stale headlines filled primary ranking | discovery/adapters, tracker_store. Remove fabricated inputs and separate legacy history | Discovery and dashboard regression tests | VERIFIED |
| U-06 | Zero matches left blank results | tracker_service.py. Server-filter results and show empty state | Chromium search | VERIFIED |
| U-07 | Pipe-joined reasons were the only visible score explanation | rule_engine, tracker_store, tracker_service. Store and show relevance factors | Detail rendering verified. Per-row factors remain | IN PROGRESS |
| U-08 | Source and calendar destination labels used conflicting terminology | tracker_service.py. Shared Calendar, Exam conflicts and Sources labels | Page and navigation checks | VERIFIED |
| U-09 | Emoji and symbol-only labels were inconsistent | tracker_service.py. Simplify navigation, action and copy labels | Mixed iconography remains elsewhere | IN PROGRESS |
| U-10 | Overlay layout clipped controls and lacked native modal focus behavior | tracker_service.py. Use a bounded native dialog and contained table scrolling | Chromium dialog fit and Save workflow, including 320 px | VERIFIED |
| U-11 | Unknown event page had no recovery | tracker_service.py. Shared navigation and dashboard link | Chromium and HTTP 404 checks | VERIFIED |
| A-01 | Heading contrast failed in light theme | tracker_service.py. Use dark foreground on light surface | Chromium computed color pairs. Full contrast CI remains | IN PROGRESS |
| A-02 | Copy, view and toggle controls lacked accessible names or state | tracker_service.py. Add names and pressed states | Browser view toggle check. Whole-app automated accessibility pass remains | IN PROGRESS |
| A-03 | Mobile navigation extended beyond the viewport | tracker_service.py. Wrap items and drop mobile sticky layout | Exact-width Chromium check | VERIFIED |
| A-04 | Some labels were too small and dense | tracker_service.py. Increase shared control size and allow table scrolling | Some metadata and source table text remain small | IN PROGRESS |
| A-05 | Invisible focus on custom toggles | tracker_service.py. Shared focus styling and native dialog | Code and functional browser checks. Full keyboard walkthrough remains | IN PROGRESS |
| A-06 | Decorative emoji could be announced | tracker_service.py. Remove emoji from main nav and key action labels | Remaining inline emoji need accessibility review | IN PROGRESS |

## Roadmap acceptance

| ID | Task and underlying finding | Affected code and correction | Verification | Status |
|---|---|---|---|---|
| R-01 | Fabricated and news events polluted discovery | adapters, engine, store, service. Remove this ingestion and quarantine history | Registry and browser checks | VERIFIED |
| R-02 | No expiry filter | integrity, store, service. Dynamic lifecycle and explicit History view | Expired and open regression | VERIFIED |
| R-03 | Guessed fields and self-certified eligibility | adapters, base adapter, rule engine and store. Preserve unknowns and evidence | Mocked, network and eligibility checks | VERIFIED |
| R-04 | Open mutation endpoints | local_security and service. Admin auth, origin controls and signed POST | Automated and live HTTP checks | VERIFIED |
| R-05 | Inaccurate source success counters | engine, store, service. Store recent feed results and failure details | Live non-hackathon rejection, error tests and per-feed stale-status logic | VERIFIED |
| R-06 | Unsafe merging | deduplicator, engine, store. Tighten comparison, preserve lineage | Automated dedup checks and merge log. Sources includes recent merge review | VERIFIED |
| R-07 | Misleading scores and recommendations | rule_engine, store, service. Normalize score and constrain eligibility and spotlight | Automated rules and browser detail | VERIFIED |
| R-08 | Unsafe inline JS, headers absent, permissive local files | local_security, service, environment and database. Harden boundaries | CSP, HTTP checks, file permissions and calendar tests | VERIFIED |
| R-09 | Delivery ambiguity and missing reminders | deliver and main. Report skipped and keep archive path running | No-SMTP tests. Test delivery and reminders deferred by owner instruction | VERIFIED |
| R-10 | Inconsistent page shell and clipped dialog | tracker_service. Shared navigation/styles and native dialog | Browser major routes and CRUD | VERIFIED |
| R-11 | Low-contrast light theme | tracker_service. Semantic text color tokens and light surfaces | Computed heading contrast at all widths. Whole-app contrast CI remains | IN PROGRESS |
| R-12 | Clipped responsive nav | tracker_service. Responsive wrap and contained tables | Chromium measurements at five widths | VERIFIED |
| R-13 | Accessible names, keyboard and focus gaps | tracker_service. Label primary controls and add focus styling | Chromium interaction checks. Dedicated axe and screen-reader passes remain | IN PROGRESS |
| R-14 | Weak search, lineage and browsing workflow | tracker_service and store. Search, pagination, counts and source links | Chromium search and pagination shell checked. Date grouping and scan links are present | FIXED |
| R-15 | Stale data and inactive schedule | engine, tracker_service, scheduler. Freshness and revised local refresh command | Existing tracker restarted. Weekly agent remains inactive | IN PROGRESS |
| R-16 | Tests rewarded fixtures and dependencies floated | tests, requirements and audit workflow. Verify provenance and pin dependencies | Full pytest suite and local dependency checks. Contrast CI remains | IN PROGRESS |

## Feature expansion follow-up

The original Freebuff statuses above remain historical remediation records. The expansion adds a SQLite tracker with notes and history, stable event pages, a local write unlock, richer source diagnostics, enrichment and safe thumbnails. These additions do not close unresolved audit items. The hourly launchd agent is now loaded and was verified separately during the expansion. See [Feature expansion report](FEATURE-EXPANSION-REPORT.md) for the implementation and its limitations.
