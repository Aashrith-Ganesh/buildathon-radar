# Buildathon Radar — Full Application Audit

**Audit date:** 2026-11-22
**Target:** `/Users/aashrith/Projects/buildathon-radar` (adapted project, not the upstream repository)
**Application:** FastAPI + SQLite + server-rendered HTML dashboard, live at `http://127.0.0.1:8015`
**Auditor role:** Independent adversarial review; no application code, database rows, blackout dates, or configuration were changed.
**Reports:** `FREEBUFF-FULL-AUDIT.md` (this file), `FREEBUFF-SECURITY-AUDIT.md`, `FREEBUFF-UX-AI-SLOP-AUDIT.md`, `FREEBUFF-FUNCTIONAL-QA.md`, `FREEBUFF-REMEDIATION-ROADMAP.md`.

---

## 1. Verdict in one page

**Buildathon Radar is not ready for real student use in its current state.**

The shell of a serious product exists: a real FastAPI app, a persistent SQLite store, a working blackout calendar engine, a functioning dashboard shell, and 398 passing tests. But the central promise — *"find hackathons that a Bengaluru Class 11/12 student can actually attend"* — is not met, because most of the discovery layer is fabricated rather than discovered.

The decisive findings:

| # | Finding | Severity | Evidence class |
|---|---|---|---|
| F-01 | 19 of 27 "discovery adapters" are hardcoded event literals; several report success and "verified" while making no network request. | Critical | Command-verified + code review |
| F-02 | LinkedIn discovery is a Google News RSS search. It ingests news articles and obituaries of hackathons as live opportunities and assigns many of them 73–100/100. | Critical | DB + browser |
| F-03 | 16 expired events (some from 2014, 2022, 2025) remain in the dashboard; 13 of them are `HIGH PRIORITY`. | High | DB + browser |
| F-04 | Headline and filter counts do not match the rendered rows: "100 open now" renders 63 events; "Bengaluru (30)" renders 9; "closing soon (3)" renders 33. | High | Browser + HTML parse |
| F-05 | `SearchDiscoveryAdapter` invents dates (`2027-01-23` etc.) and marks results `ELIGIBLE`/`verified` when the source is a news headline. | High | Code review + DB |
| U-01 | The Calendar, Sources and Event Detail pages are visually unstyled relative to the dashboard: default browser buttons/links, broken header, clipped modal. | High | Browser + screenshots |
| U-02 | Light theme is unusable: H1 contrast measured at **1.04:1** (white on near-white). | High | Browser measurement |
| U-03 | Mobile layout overflows horizontally (758 px content in a 390 px viewport) and the primary navigation is clipped with no menu alternative. | High | Browser measurement + screenshot |
| S-01 | No authentication or authorization on any route, including mutating `POST/PUT/DELETE` endpoints and `/api/scan`. | High (local-only mitigations) | Command-verified |
| S-02 | No CSRF/origin protection; a cross-origin page can POST to the local API (verified with `Origin: http://evil.example`). | Medium–High | Command-verified |

**Overall score: 3.5 / 10.** The architecture is coherent; the data trust layer and front-end consistency are not.

---

## 2. What was verified vs. claimed

### 2.1 Architecture claims

| Claim | Result | Notes |
|---|---|---|
| Backend is Python FastAPI | **Confirmed** | `buildathon_radar/tracker_service.py`, FastAPI 0.165.0, Uvicorn 0.54.0 |
| Database is SQLite | **Confirmed** | `tracker.db`, WAL-capable `connect()`; tables `events`, `blackout_dates`, `discovery_sources`, `discovery_scans`, `action_log` |
| Frontend is a local web dashboard | **Confirmed** | Server-rendered HTML/CSS/JS, no separate SPA build |
| 27 discovery adapters | **Confirmed as a count** | 27 classes in `ADAPTER_REGISTRY`; only 8 touch the network and only 4 return genuine event listings |
| Adapters distributed across six tiers | **Partly false** | Seven categories are used: Dedicated Platforms (9), Professional/Social (3), Event Platforms (5), Communities (7), Indian Colleges (1), Companies (1), Search Pipeline (1) |
| Deterministic 0–100 scoring, no paid LLM required | **Confirmed** | `rule_engine.py`; scoring does not call an LLM |
| macOS launchd scheduling | **Code present, not active** | Plists valid and installed under `scheduler/launchd`, but `launchctl list` shows no `com.buildathon.*` jobs loaded |
| Email via SMTP | **Configured** | `.env` has `ENABLE_EMAIL=true` and credentials; no email was sent during the audit |
| Automated Python test suite | **Confirmed** | `398 passed in 5.03s`; README still says 343 |
| 29 blackout rules / 54 days | **Confirmed** | 29 rows in `blackout_dates`; 54 unique enabled dates |
| Runs without external paid LLM API | **Confirmed** | Anthropic/TypeSafe are optional and unset for core scoring |

### 2.2 Runtime state at audit time

- App reachable: `GET /dashboard` → `200`.
- Events in DB: **116**. Upcoming (end/start ≥ 2026-11-22): **100**. Expired: **16**.
- Conflicts flagged: **53**.
- Verified events: **98**; no start date: **13**; no end date: **10**; no registration deadline: **23**.
- Discovery sources reporting success: **27/27**, failures **0**.
- Latest scan: 1.15 s, 27/27 healthy, +68 new, per `/sources`.
- Multi-source merged events: **0 of 116** (lineage exists in JSON but no merge has occurred in production data).
- Browser: 1440×900 desktop and 390×844 mobile, dark and light themes.

---

## 3. Top findings (summary)

Full reproduction steps, expected/actual, and evidence are in `FREEBUFF-FUNCTIONAL-QA.md`, `FREEBUFF-SECURITY-AUDIT.md` and `FREEBUFF-UX-AI-SLOP-AUDIT.md`. Every ID below is identical across reports.

### F-01 — Most "sources" are fixture data, not discovery (Critical)

Of 27 adapters, 19 return a Python list literal with no network call and complete in ~0.0 s:

`allevents, aws_community, cncf, dorahacks, ethglobal, eventbrite, foss_united, gdg, github_community, hack2skill, hackathon_com, indian_colleges, meetup, microsoft_reactor, nvidia_dev, tech_companies, tentimes, townscript, twitter`

Each hardcodes `verification_status: "verified"`, `confidence: "High"`, `eligibility: "ELIGIBLE"`, prize amounts, venue addresses and registration URLs. Sample URLs checked:

| Event | URL | HTTP result |
|---|---|---|
| PES Hack-A-Trisha 2027 | `https://aatmatrisha.pes.edu/hackathon` | **404** |
| Bangalore MedTech & Health AI 2027 | `https://healthai-bangalore.org/hackathon-2027` | **no DNS / 000** |
| Karnataka Student Cyber Security Sprint 2027 | `https://cybersecurity-karnataka.org/sprint-2027` | **no DNS / 000** |
| AWS Bedrock Buildathon 2027 | `https://awsugblr.in/buildathon-2027` | **no DNS / 000** |
| Razorpay FTX Hackathon 2027 | `https://ftx.razorpay.com/hackathon` | **no DNS / 000** |
| RVCE 8th Mile | `https://rvce.edu.in/8thmile/hackathon` | 403 (may exist, bot-blocked) |
| Cashfree DevFlow 2027 | `https://www.cashfree.com/hackathon-2027` | 403 (may exist, bot-blocked) |

The Sources page nonetheless shows "27/27 healthy", "100% FAULT ISOLATED", and each fixture source has `success_count=1, fail_count=0`. The health metric measures "did the function return a list", not "did the source produce a real event".

**Correction direction:** Delete fixture-only adapters or gate them behind an explicit `DEMO_SOURCES` flag that is off by default and excluded from "open now" counts. Health must distinguish `live`, `cached`, `fixture`, and `failed`.

### F-02 — LinkedIn and search "discovery" ingest news, not events (Critical)

The LinkedIn adapter queries `news.google.com/rss/search?q=site:linkedin.com/posts/...` and treats every returned item as a hackathon. In the live database all 10 LinkedIn rows are expired and all are `HIGH PRIORITY`; several are clearly not events:

- "Proud uncle moment… my niece… winner of the Goldman Sachs India Hackathon 2026" — score **73**.
- "A special moment from our journey at the Singapore-India Hackathon 2026…" — score **73**.
- "One of the most interesting questions we asked participants in the Paytm AI Hackathon…" — score **96**.
- "MSME Idea Hackathon 6.0 … aged over 18 years" — still shown as a student opportunity.

`SearchDiscoveryAdapter` does the same with Google News, then fabricates `event_start/event_end/registration_deadline` from `pubDate` or defaults to `2027-01-23`, and sets `eligibility: "ELIGIBLE"`. Result: "IIMB hosts Policy Hackathon 2014" and "Oakridge Codefest 2022" appear as upcoming 2027 events with score 84.

### F-03 — Expired events remain visible and prioritised (High)

`get_all_events()` has no date floor and is used for the default dashboard view. Measured:

- Default dashboard renders **63 event rows**, of which **16 are in the past**.
- `All Open (100)` is computed from upcoming stats, but the list is not filtered to upcoming.
- Expired rows include 13 `HIGH PRIORITY` items, e.g. Paytm Build for India (2026-10-24) at 100/100.

This is the single clearest usability failure for a student: the top of the list is stale.

### F-04 — Counts lie (High)

| UI label | Rendered rows (browser/HTML) |
|---|---|
| "100 hackathons are open right now" | 63 |
| "All Open (100)" | 63 |
| "Bengaluru (30)" | 9 |
| "Student Eligible (8)" | 8 (this one matches) |
| "3 closing soon" | 33 |
| "Blackouts (53)" | 53 (conflict count, not rule count) |

Causes are different queries and different definitions: stats count all upcoming rows; `filter=bengaluru` uses a SQL `LIKE '%bengaluru%'` that misses "Bangalore"; `closing_soon` calls `get_upcoming_deadlines(limit=50)` which returns anything with a future deadline or start, not only ≤7 days; `free_weekend` filters on the `why` string.

### F-05 — Eligibility is self-certified (High)

`assess_eligibility()` builds its text corpus from `item["eligibility"]`. Most adapters pre-set `eligibility: "ELIGIBLE"`. Therefore the engine "confirms" eligibility using the value it was handed. Genuine exclusions only work when exclusion words appear in title/summary/host. The profile's stated intent — exclude undergraduate-only events, retain ambiguous ones — is not reliably implemented.

### F-06 — Scores are opaque and sometimes wrong (Medium)

- `score_geography()` returns 30/"In-person in Bengaluru" for an **online** event whose location string contains "Bengaluru". Synthetic test confirmed score 55 and that label.
- Component maxima sum to 115 (35+30+20+10+5+15) and are clamped at 100, so several distinct events tie at 100.
- The detail page shows a pipe-separated `why` string but no per-component breakdown, so a student cannot see why an event scored 79 while "Low software/AI alignment" is one of its reasons.
- `only_in_person` and `target_city_only` in `config/profile.json` are never enforced; the "Next Eligible Hackathon" hero is a Chandigarh in-person event while the profile says Bengaluru-only.

### F-07 — Deduplication over-merges and never merges in practice (Medium)

Synthetic tests against `are_duplicates()`:

| Case | Result |
|---|---|
| Two different "AI Hackathon" events, adjacent days, different city and host | **True (wrongly merged)** |
| Two different "Code Sprint" events with no dates | **True (wrongly merged)** |
| Same title four days apart | False (correct) |
| Cross-source same event (Paytm + Luma) | True (correct) |

Merging uses title+date only; city, host and URL are not considered. `merge_event_records()` can set `host` to `None` when the higher-priority record lacks a host. In the live database **0 of 116** events have more than one source, so the lineage UI/behaviour is effectively unexercised.

### F-08 — Blackout engine works; count labels confuse (Positive + Low)

Directly tested on a disposable copy of `tracker.db`:

- add → persisted and recomputed conflicts (3 events on 2027-01-23 became `CONFLICT`);
- toggle → conflict cleared and priority restored from score;
- update → dates/title changed and recomputed;
- delete → rule removed, conflict list recalculated.

Boundary math is correct and inclusive: 2026-11-25 is free; 2026-11-30 conflicts (range 26–30); multi-day 25–27 conflicts; missing end date uses start date. Time zones are not a practical issue because all event dates are date-only strings.

However the dashboard label "Blackouts (53)" means *53 conflicted events*, not 53 rules; the calendar has 29 rules / 54 days. That ambiguity will mislead the user.

---

## 4. Requirements coverage matrix

| Requirement | Status | Where documented |
|---|---|---|
| Discovery engine, 27 adapters, real outputs | **Failed** — 19 fixtures, 8 network, 4 genuine event sources | FUNCTIONAL F-01, F-02 |
| Dates parsed correctly | **Partly** — 13 no-start, 10 no-end; news dates fabricated | FUNCTIONAL F-05 |
| Registration URLs work | **Mixed** — live Devpost/Devfolio/Unstop URLs return 200; fixtures point to non-existent hosts | FUNCTIONAL F-01 |
| Expired events removed/flagged | **Failed** — 16 expired, 13 high priority | FUNCTIONAL F-03 |
| Duplicates identified | **Risky** — over-merges generic titles; 0 real merges | FUNCTIONAL F-07 |
| Failed sources reported | **Failed** — all 27 report success, including Reddit which returns 403 and substitutes fixtures | FUNCTIONAL F-02 |
| Dashboard reflects discovery | **Failed** — counts and content contradict the DB | FUNCTIONAL F-04 |
| High-school eligibility rules | **Failed** — self-certified eligibility | FUNCTIONAL F-05 |
| Deterministic 0–100 scoring | **Confirmed, but incorrect in places** | FUNCTIONAL F-06 |
| 29 blackout rules / 54 days | **Confirmed** | FUNCTIONAL F-08 |
| Conflict formula and boundaries | **Confirmed** | FUNCTIONAL F-08 |
| Calendar editing/deleting/persistence | **Confirmed on DB copy** | FUNCTIONAL F-08 |
| Multi-source lineage | **Stored, never exercised** | FUNCTIONAL F-07 |
| Frontend pages and navigation | **All routes respond; several pages visually broken** | UX U-01…U-10 |
| Search/filters/themes | **Search works; filters and light theme broken** | UX U-02, U-06 |
| Email SMTP | **Configured; disabled path and bad-auth path tested without sending** | FUNCTIONAL F-11 |
| Weekly digest / reminders / dedupe | **Weekly digest exists; deadline reminders do not** | FUNCTIONAL F-12 |
| Local web dashboard on 8015 | **Confirmed** | — |
| No paid LLM required | **Confirmed** | — |
| Security boundaries | **No auth, no CSRF, stored XSS vector, no headers** | SECURITY S-01…S-08 |

---

## 5. What is genuinely good

1. **Blackout conflict engine is correct and transactional.** The inclusive overlap logic and recomputation on CRUD are solid, and the 54-day calendar is preserved exactly as configured.
2. **The database schema is sensible** and the code uses parameterised SQL throughout; no SQL injection was found.
3. **The live adapters that are real are good.** Devpost, Devfolio, Unstop and HackerEarth return live data with working URLs (sampled 200s). The APIs are undocumented but the parsing works today.
4. **The dashboard's dark visual language is coherent on the main page** and the row design is readable at desktop width.
5. **The test suite runs fast and passes**, and network calls are mocked.
6. **The app fails closed on missing `TRACKER_SECRET`** at service start.

These strengths make remediation feasible: the UI shell, DB and blackout logic can be kept; the discovery/trust layer needs replacement.

---

## 6. Method and evidence

- **Code reconnaissance:** read `main.py`, `tracker_service.py`, `tracker_store.py`, `rule_engine.py`, `discovery/*`, `deliver.py`, `config/profile.json`, scheduler plists, README/CLAUDE docs.
- **Runtime:** app already running on `127.0.0.1:8015`; health check 200. No restart or configuration change.
- **Database:** read-only `sqlite3` queries; write tests performed on a **copy** at `/tmp/audit_tracker.db`, which was deleted.
- **Adapters:** invoked each class directly with an 8 s timeout; no DB writes; 27 results recorded.
- **Scoring/dedup:** synthetic inputs through the real functions; no DB writes.
- **Browser:** Chromium via preview tools at 1440×900 and 390×844; screenshots in `docs/audit-assets/`.
- **Security:** unauthenticated and cross-origin HTTP probes with non-destructive payloads; no data created, modified or deleted; no emails sent.
- **Tests:** `venv/bin/python -m pytest -q` → 398 passed.

### Screenshot index

| File | What it shows |
|---|---|
| `audit-assets/dashboard-dark.png` | Dark dashboard, hero, inflated counts, stale "Paytm … Luma" row |
| `audit-assets/dashboard-light.png` | Light theme: invisible H1 and metric, dark card on light canvas |
| `audit-assets/dashboard-mobile.png` | 390 px viewport: clipped nav, horizontal overflow |
| `audit-assets/calendar-desktop.png` | Calendar page: unstyled header/buttons, cramped table |
| `audit-assets/calendar-add-modal.png` | Add-blackout modal clipped off the right edge |
| `audit-assets/sources-desktop.png` | Sources page: broken header, "100% fault isolated" metric |
| `audit-assets/event-detail.png` | Event detail: default browser link styling, no navigation |

---

## 7. Limitations and untested areas

- **No email was sent.** SMTP credentials exist and are valid-looking; I exercised only the disabled path and a deliberately wrong password. I did not authenticate against Gmail or send to the configured recipient.
- **No discovery scan was triggered through the UI**, to avoid writing new rows/logs. Adapters were probed directly and existing scan data was read.
- **No shortlist/applied/reject action was performed on real events**, to avoid changing user state. The API path was probed with a non-existent event ID (404).
- **Blackout UI create/edit/delete was not committed to the live DB**; modal opening and rendering were tested in the browser, CRUD semantics on a disposable DB copy.
- **Launchd scheduling is not active**, so the weekly run was not observed in a live scheduled context.
- **Accessibility was spot-checked**, not audited with axe/WAVE; contrast, accessible names and layout overflow were measured directly.
- **Performance was measured on 116 rows only**; no load or concurrency testing.

---

## 8. Adversarial verdict

```markdown
## Adversarial verdict
Claims reviewed: 27 live discovery sources; student eligibility; deterministic scoring;
54-day blackout calendar; deduplication; dashboard accuracy; SMTP notifications; tests.
Evidence: 27-file code read; 398 passing tests (exit 0); live DB queries; direct adapter
probe (27 adapters); browser snapshots/screenshots at 2 viewports; contrast measurement;
unauthenticated/cross-origin HTTP probes; disposable DB CRUD tests.
Confirmed: FastAPI/SQLite/blackout engine/scoring exist; 29 rules/54 days correct;
conflict math correct; 398 tests pass; live Devpost/Devfolio/Unstop URLs resolve.
Refuted / gaps: "27 live sources" (19 fixtures, 4 genuine event sources); "100 open now"
(63 rendered, 16 expired); "student eligible" (self-certified); "100% fault isolated"
(no fault detection); multi-source dedup (0 merges, over-merges synthetic pairs);
"next eligible hackathon" ignores Bengaluru-only preference.
Risk: high for data trust; medium for local-only security; high for UI consistency.
Decision: fix-required. Do not present this as a reliable student opportunity feed
until F-01..F-05 and S-01/S-02 are resolved.
```
