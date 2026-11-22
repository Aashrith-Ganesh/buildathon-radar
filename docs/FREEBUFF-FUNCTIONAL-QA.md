# Buildathon Radar — Functional QA

**Date:** 2026-11-22
**Scope:** Discovery, eligibility, scoring, deduplication, blackout engine, dashboard, filters, search, event detail, source health, email, scheduling.
**Legend:** `Confirmed` = reproduced with evidence · `Potential` = code path indicates risk but not triggered · `Observation` = code review only · `Untested` = explicitly not run.

---

## 1. Test environment

| Item | Value |
|---|---|
| URL | `http://127.0.0.1:8015` (already running; PID 39383, loopback-only) |
| DB | `tracker.db` (read-only during audit; write tests on `/tmp/audit_tracker.db`, deleted after) |
| Events | 116 total · 100 upcoming · 16 expired |
| Blackouts | 29 rules · 54 unique days · 53 conflicted events |
| Tests | `venv/bin/python -m pytest -q` → **398 passed** in 5.03 s |
| Browser | Chromium, 1440×900 and 390×844, dark/light |

---

## 2. Discovery adapters — source-by-source

Direct invocation of every adapter (`fetch()` with 8 s timeout, no DB writes):

| # | source_key | Type | Duration | Items | Error | Verdict |
|---|---|---|---|---|---|---|
| 1 | devpost | Live API | 0.41 s | 9 | None | **Genuine** |
| 2 | unstop | Live API | 0.28 s | 15 | None | **Genuine** (dates partly null) |
| 3 | devfolio | Live API | 0.30 s | 8 | None | **Genuine** (dates null) |
| 4 | hackerearth | Live API | 0.20 s | 3 | None | **Genuine** (dates null) |
| 5 | mlh | Fetches HTML, ignores it | 0.39 s | 1 | None | **Fake output** — one hardcoded "Global Hack Week" |
| 6 | linkedin | Google News RSS | 0.47 s | 10 | None | **News, not events** |
| 7 | reddit | Live JSON | 0.39 s | 1 | 403 logged, not returned | **Fails open to fixture, reports success** |
| 8 | search_discovery | Google News RSS | 0.64 s | 7 | None | **News, fabricated dates** |
| 9 | gdg | Fixture | 0.0 s | 2 | None | Hardcoded |
| 10 | microsoft_reactor | Fixture | 0.0 s | 1 | None | Hardcoded |
| 11 | aws_community | Fixture | 0.0 s | 1 | None | Hardcoded, dead URL |
| 12 | github_community | Fixture | 0.0 s | 1 | None | Hardcoded |
| 13 | nvidia_dev | Fixture | 0.0 s | 1 | None | Hardcoded |
| 14 | foss_united | Fixture | 0.0 s | 1 | None | Hardcoded |
| 15 | cncf | Fixture | 0.0 s | 1 | None | Hardcoded |
| 16 | indian_colleges | Fixture | 0.0 s | 4 | None | Hardcoded, one URL 404 |
| 17 | tech_companies | Fixture | 0.0 s | 4 | None | Hardcoded, dead URLs |
| 18 | hack2skill | Fixture | 0.0 s | 1 | None | Hardcoded |
| 19 | dorahacks | Fixture | 0.0 s | 1 | None | Hardcoded |
| 20 | ethglobal | Fixture | 0.0 s | 1 | None | Hardcoded |
| 21 | hackathon_com | Fixture | 0.0 s | 1 | None | Hardcoded |
| 22 | meetup | Fixture | 0.0 s | 2 | None | Hardcoded |
| 23 | eventbrite | Fixture | 0.0 s | 1 | None | Hardcoded |
| 24 | townscript | Fixture | 0.0 s | 1 | None | Hardcoded |
| 25 | allevents | Fixture | 0.0 s | 1 | None | Hardcoded |
| 26 | tentimes | Fixture | 0.0 s | 1 | None | Hardcoded |
| 27 | twitter | Fixture | 0.0 s | 2 | None | Hardcoded |

**Totals:** 19 fixture-only, 8 network, 4 genuine event listings, 1 failing source (Reddit 403) that still reports success.

### F-01 — Fixture-only adapters present fabricated events as verified discoveries

- **Severity:** Critical
- **Component:** `buildathon_radar/discovery/adapters/{communities,event_platforms,colleges,companies,dedicated,social}.py`
- **Status:** Confirmed (command + code review)
- **Description:** Nineteen adapters return literal lists. They never call `make_request()`, yet set `verification_status="verified"`, `confidence="High"`, `eligibility="ELIGIBLE"` and detailed prizes/venues.
- **Reproduction:**
  1. Run each adapter directly (see table).
  2. Inspect `communities.py`, `event_platforms.py`, `colleges.py`, `companies.py`: `fetch()` has no network branch.
  3. Open `http://127.0.0.1:8015/sources` → all show `✓ 1 / ✗ 0`, "27 active", "100% fault isolated".
  4. Request fixture URLs (`aatmatrisha.pes.edu/hackathon`, `healthai-bangalore.org/hackathon-2027`, `awsugblr.in/buildathon-2027`, `ftx.razorpay.com/hackathon`).
- **Expected:** Sources without a live endpoint are disabled, labelled `fixture`, and excluded from opportunity counts and "open now".
- **Actual:** They populate the dashboard as high-priority, verified, free, in-person opportunities; 404/NXDOMAIN links are presented as official pages.
- **Evidence:** Adapter table above; `/sources` snapshot; URL probe results; source code.
- **Recommended correction:** Remove fixture adapters or gate them behind `DEMO_MODE=1` with a visible banner. Add a `source_kind` column (`live|cached|fixture|curated`) and make health count only `live`/`cached`. Re-verify every seeded URL before showing it.
- **Confidence:** High

### F-02 — LinkedIn source ingests news articles as hackathons

- **Severity:** Critical
- **Component:** `adapters/social.py::LinkedInAdapter`, `tracker.db.events`
- **Status:** Confirmed (DB + browser)
- **Description:** The adapter queries Google News RSS for `site:linkedin.com/posts/`. Google News does not return LinkedIn post bodies; it returns syndicated articles/headlines. Every item becomes a hackathon with `event_start=pubDate`, `mode=hybrid`, `eligibility=ELIGIBLE`.
- **Reproduction:**
  1. Open `/dashboard`; observe LinkedIn-sourced rows: "Proud uncle moment…", "A special moment from our journey…", "One of the most interesting questions we asked participants…".
  2. Query the DB: all 10 LinkedIn events are expired and `HIGH PRIORITY`.
  3. Inspect `LinkedInAdapter.fetch()` — no filtering on event language, registration, or future date.
- **Expected:** Social/news sources either extract structured event data and validate it, or are labelled `news` and never enter the ranked event list.
- **Actual:** Obituaries/recaps/winners' posts are scored 73–100 and shown as opportunities.
- **Evidence:** `audit-assets/dashboard-dark.png`; DB query in section 5.
- **Recommended correction:** Remove LinkedIn/X/news adapters from the opportunity pipeline until an event-extraction + validation step exists (requires registration URL, future date, event schema). A headline is not an event.
- **Confidence:** High

### F-03 — Search pipeline fabricates dates and eligibility

- **Severity:** High
- **Component:** `adapters/search_engine.py`
- **Status:** Confirmed (code + DB)
- **Description:** If RSS returns items, `event_start` is `pub_date`; if absent, it defaults to `"2027-01-23"`, `event_end` to `"2027-01-24"`, deadline `"2027-01-18"`. `eligibility` is hardcoded `"ELIGIBLE"`. If RSS fails, two invented events are returned with `verification_status="verified"`.
- **Reproduction:** read `SearchDiscoveryAdapter.fetch()`; observe `IIMB hosts Policy Hackathon 2014` displayed with dates `Jan 23, 2027` and score 84.
- **Expected:** No date should be invented; unknown dates must remain `None`/`date_status=uncertain`; eligibility must not be asserted from a headline.
- **Actual:** Historical news is re-dated into the future and prioritised.
- **Evidence:** browser rows; DB rows for `search_discovery`; code lines in `search_engine.py`.
- **Recommended correction:** Delete default dates and default eligibility. Require a parseable event date from the article body or drop the item. Add a `date_source` field (`listing|article|inferred`) and never call inferred dates "verified".
- **Confidence:** High

### F-04 — Expired events are not removed or flagged

- **Severity:** High
- **Component:** `tracker_store.get_all_events`, `/dashboard`
- **Status:** Confirmed (DB + browser)
- **Description:** `get_all_events()` has no `min_date`; the default dashboard passes only `include_conflicts=False`. Sixteen expired events (2014–2026) remain, 13 of them `HIGH PRIORITY`.
- **Reproduction:** `GET /dashboard`; count rows with `data-start < 2026-11-22` → 16 events. SQL in section 5.
- **Expected:** Expired events are excluded from "open now" or clearly marked `Expired` and sorted last.
- **Actual:** They sit in the main ranked list, some at the top (Paytm 100/100).
- **Evidence:** DB query; `audit-assets/dashboard-dark.png`.
- **Recommended correction:** Add `min_date=today` to the default list; introduce `state='over'`/`verification_status='expired'`; run a daily prune (the CLI already has `prune`).
- **Confidence:** High

### F-05 — Missing dates are widespread

- **Severity:** Medium
- **Component:** Devfolio, Unstop, HackerEarth adapters; event schema
- **Status:** Confirmed (DB)
- **Description:** 13 events have no `event_start`, 10 no `event_end`, 23 no `registration_deadline`. Devfolio returns 8/8 with `first=None`; Unstop partly null.
- **Reproduction:** `select count(*) ... where event_start is null` → 13. Devfolio rows show `TBD` / `Closes: Open`.
- **Expected:** Date parsing handles ISO timestamps (`starts_at`, `ends_at`, `start_date`) and records uncertainty explicitly.
- **Actual:** `parse_date_safe()` only matches `YYYY-MM-DD` or named month + year; timestamp formats and epoch values are lost. Missing deadlines render as "Open", which reads as "still open" rather than "unknown".
- **Evidence:** DB aggregates; adapter probe.
- **Recommended correction:** Parse ISO 8601 with `datetime.fromisoformat`, accept epoch ms, and render `Unknown` rather than `Open`. Add `date_status=uncertain` for missing dates.
- **Confidence:** High

### F-06 — Eligibility engine is self-certifying and can be gamed

- **Severity:** High
- **Component:** `rule_engine.assess_eligibility`, all adapters
- **Status:** Confirmed (synthetic + code)
- **Description:** The corpus includes `item["eligibility"]`. Adapters set it to `ELIGIBLE`. The engine then matches its own assertion. 98 events are `verified`; only 8 are actually `ELIGIBLE` per the dashboard, but many hardcoded `ELIGIBLE` values are unsupported.
- **Reproduction:**
  - Synthetic event with `eligibility="ELIGIBLE"` and no supporting text → `UNKNOWN` (corpus has no inclusion keyword), but live adapters ship `eligibility` plus words like "students" in summaries, producing `ELIGIBLE`.
  - Synthetic `summary="18+ only event for university students only"` → `INELIGIBLE` (correct).
  - `PES Hack-A-Trisha` (college fest) → `UNKNOWN` (correct); `IIT Bombay Physical AI Hackathon` (college) → `ELIGIBLE` in DB (unsupported).
- **Expected:** Eligibility derives from listing text and explicit evidence; the adapter's own claim is never an input.
- **Actual:** Self-certification; college-only events can be labelled eligible.
- **Evidence:** `rule_engine.py` lines building `text_corpus`; DB `eligibility` counts; detail page showing `HIGH PRIORITY` with `UNKNOWN` eligibility (contradictory but at least honest).
- **Recommended correction:** Remove `item["eligibility"]` from the corpus. Require a quoted evidence snippet for every `ELIGIBLE` decision and store it. Default to `UNKNOWN`. Add a manual verification workflow.
- **Confidence:** High

### F-07 — Geography scoring contradicts the event format

- **Severity:** Medium
- **Component:** `rule_engine.score_geography`
- **Status:** Confirmed (synthetic)
- **Description:** Any location containing "Bengaluru/Bangalore/Karnataka" returns 30 with reason "In-person in Bengaluru", even when `mode="online"`.
- **Reproduction:** synthetic event `{mode:"online", location:"Bengaluru / Online"}` → `geo=30`, reason "In-person in Bengaluru (Top local priority)", total 55.
- **Expected:** Online events cannot score as in-person local; geography and format are separate dimensions.
- **Actual:** Online events receive the maximum geography score; the explanation is false.
- **Evidence:** synthetic output in section 5.
- **Recommended correction:** Check `mode` first. If online, cap geography at the online tier (14) regardless of location string. Split the reason text from the score.
- **Confidence:** High

### F-08 — Scoring components exceed the advertised 0–100 scale

- **Severity:** Medium
- **Component:** `rule_engine.classify_and_score_event`
- **Status:** Confirmed (code)
- **Description:** Maxima are 35 theme + 30 geo + 20 host + 10 format + 5 team + 15 timing = 115, clamped to 100. Several different events tie at 100.
- **Reproduction:** code inspection; dashboard shows multiple 100s (LinkedIn news, Meetup fixture).
- **Expected:** Components sum to 100, or the UI explains that 100 is a cap.
- **Actual:** Score inflation; top of the list is dominated by the same cap.
- **Evidence:** scoring weights in `config/profile.json`; dashboard.
- **Recommended correction:** Normalize to 100 or reduce the timing bonus; publish the component breakdown in the detail view.
- **Confidence:** High

### F-09 — Deduplication over-merges unrelated events

- **Severity:** Medium
- **Component:** `discovery/deduplicator.py`
- **Status:** Confirmed (synthetic)
- **Description:** Title similarity + date proximity only; city, host and URL are ignored. Missing dates are treated as compatible.
- **Reproduction:**
  - `are_duplicates({"title":"AI Hackathon","event_start":"2027-01-16"}, {"title":"AI Hackathon","event_start":"2027-01-17","location":"Delhi","host":"Different Org"})` → **True**.
  - Two `"Code Sprint"` events with no dates → **True**.
  - `Deduplicator().deduplicate([...])` merges them, sets `host=None`.
- **Expected:** Same event requires URL match, or title similarity plus compatible date plus compatible city/host.
- **Actual:** Generic titles collapse across cities and organisers.
- **Evidence:** synthetic output; 0 real merges in DB.
- **Recommended correction:** Add location/host guards; require at least one non-generic token; lower title threshold for short titles; never overwrite a non-null host with null.
- **Confidence:** High

### F-10 — Source health is binary and misleading

- **Severity:** High
- **Component:** `discovery/engine.py`, `/sources`, `discovery_sources`
- **Status:** Confirmed (DB + browser)
- **Description:** `err is None` → success. Fixtures and fallbacks always return `err=None`. Reddit logs a 403 and returns fixture data, so it counts as healthy. `events_discovered` is cumulative and not tied to real events.
- **Reproduction:** `/sources` shows 27/27, `100% fault isolated`; DB shows every source `fail_count=0`; Reddit stderr shows 403.
- **Expected:** Health reflects real reachability and data freshness; fixture/fallback states are visible.
- **Actual:** A perfect health dashboard while 19 sources do nothing and 1 is blocked.
- **Evidence:** `/sources` snapshot; adapter probe; `logs` stderr.
- **Recommended correction:** Persist `last_success_at`, `last_status` (`ok|empty|blocked|fixture|error`), and `consecutive_failures`. Show "0 live events" distinctly from "healthy".
- **Confidence:** High

### F-11 — Counts and filters are inconsistent

- **Severity:** High
- **Component:** `_dashboard_page`, `tracker_store.get_dashboard_stats`, dashboard filters
- **Status:** Confirmed (browser + HTML parse)
- **Description:** Labels are computed from different datasets than the rendered list.

| Control | Label | Rendered |
|---|---|---|
| Headline | "100 hackathons are open right now" | 63 rows |
| All Open | 100 | 63 |
| Bengaluru | 30 | 9 |
| Student Eligible | 8 | 8 |
| Closing soon | 3 | 33 |
| Blackouts | 53 | 53 conflicts (not rules) |

- **Reproduction:** `GET /dashboard?filter=...`; count `data-start` attributes; compare with pill text.
- **Expected:** Each label equals the number of rows it produces, from the same query.
- **Actual:** Different queries/definitions; "Bengaluru" misses "Bangalore"; "closing soon" is not limited to 7 days.
- **Evidence:** measured table above.
- **Recommended correction:** Compute counts from the same filtered query; use one canonical location matcher; define "closing soon" in SQL and reuse it.
- **Confidence:** High

### F-12 — Search has no empty state and only filters rendered rows

- **Severity:** Medium
- **Component:** dashboard `filterEvents()`
- **Status:** Confirmed (browser)
- **Description:** Client-side search matches `innerText`; when nothing matches, the page is blank with no "no results" message. It never searches the server, so events excluded by the active filter or past events are unreachable.
- **Reproduction:** on `?filter=bengaluru`, type `quantum` → visible rows 0, no message, no reset hint.
- **Expected:** "No hackathons match 'quantum' in Bengaluru" plus a clear-filters action; search should query the API/DB.
- **Actual:** Silent blank list.
- **Evidence:** browser evaluation `visibleRows: 0`, `bodyText` without "No hackathons".
- **Recommended correction:** Add an empty state; use `/api/events?search=` and re-render server-side.
- **Confidence:** High

### F-13 — Event detail omits source lineage and score breakdown

- **Severity:** Medium
- **Component:** `/event/{event_id}`
- **Status:** Confirmed (browser + code)
- **Description:** The detail page shows "Source: X" and a `why` string, but not `discovery_sources`, component scores, or the registration deadline's provenance. There is no link to the source or scan that found it.
- **Reproduction:** open `/event/pes-aatmatrisha-hack-2027-01-23`.
- **Expected:** A "Discovered by" block with every source + announcement URL; per-factor score bars; "why this score" explanation.
- **Actual:** A single source label and a pipe-separated sentence.
- **Evidence:** `audit-assets/event-detail.png`.
- **Recommended correction:** Render `discovery_sources` and `scoring` from the stored JSON; link to `/sources` and the scan log.
- **Confidence:** High

### F-14 — Root route hides the health page

- **Severity:** Low
- **Component:** `GET /`
- **Status:** Confirmed (command)
- **Description:** `/` returns the health page but immediately redirects via JavaScript to `/dashboard` unless the query contains `health`.
- **Reproduction:** `curl /` → 200 with `<script>window.location.href="/dashboard"</script>`.
- **Expected:** A proper redirect (`307`) or an explicit `/health` endpoint.
- **Actual:** JS redirect; non-JS clients see an unrelated page; health checks are awkward.
- **Evidence:** response body.
- **Recommended correction:** Serve `/health` as JSON and redirect `/` with a 307.
- **Confidence:** High

### F-15 — Email: configured, but semantics and reminders are weak

- **Severity:** Medium
- **Component:** `deliver.py`, `main.py`
- **Status:** Confirmed for disabled/auth paths; **Untested for successful send**
- **Description:** `ENABLE_EMAIL=true` and credentials are present. When disabled, `send_digest()` returns `True` (indistinguishable from "sent"). A wrong password produced a generic `SMTP error, Connection unexpectedly closed`, not the dedicated authentication message. No deadline-reminder job exists; only the weekly digest.
- **Reproduction:**
  - `ENABLE_EMAIL=false` + `send_digest(...)` → prints "skipping" and returns `True`.
  - `EMAIL_PASSWORD=<wrong>` + `send_digest(...)` → prints generic SMTP error, returns `False`.
- **Expected:** Disabled returns a distinct status (`skipped`), not success. Authentication failures map to `SMTPAuthenticationError`.
- **Actual:** Misleading success; generic failure classification; no reminder feature.
- **Evidence:** command output; `deliver.py`; `digest.py` has no deadline-reminder builder.
- **Recommended correction:** Return an enum (`sent|skipped|failed`); add a `--test-email` command restricted to a configured test recipient; add an explicit deadline-reminder job with a notification ledger to prevent duplicates.
- **Confidence:** High for tested paths; **not verified** that real delivery works.

### F-16 — Scheduling is installed but inactive

- **Severity:** Low
- **Component:** `scheduler/launchd`, `scripts/manage_launchd.sh`
- **Status:** Confirmed (command)
- **Description:** Plists are valid and point at the correct venv, but `launchctl list` reports no `com.buildathon.tracker` or `com.buildathon.radar` jobs. The running server was started outside launchd.
- **Reproduction:** `launchctl list | grep -i radar` → no output.
- **Expected:** Services loaded and a weekly run observed.
- **Actual:** No scheduled job; the dashboard will go stale when the current process ends.
- **Evidence:** command output; plist files.
- **Recommended correction:** Load the agents or document a supervisor; add a freshness indicator ("data last updated X hours ago") so staleness is visible.
- **Confidence:** High

---

## 4. Blackout calendar — detailed test results

Tested on `/tmp/audit_tracker.db` (copy), then deleted.

| Test | Input | Expected | Actual | Verdict |
|---|---|---|---|---|
| Rule count | DB | 29 | 29 | Pass |
| Unique days | union | 54 | 54 | Pass |
| Overlap start boundary | event 2026-11-25 | no conflict | no conflict | Pass |
| Overlap end boundary | event 2026-11-30 | conflict (26–30) | conflict | Pass |
| Multi-day straddle | 2026-11-25 → 27 | conflict | conflict | Pass |
| No end date | 2026-11-28, null end | conflict | conflict | Pass |
| Add rule | 2027-01-23/24 | persisted, conflicts recomputed | persisted; 3 events flagged | Pass |
| Toggle rule | disable | conflicts cleared, priority restored | cleared, `MEDIUM PRIORITY` | Pass |
| Update rule | move to 2027-02-10 | persisted, recomputed | yes | Pass |
| Delete rule | remove | 29 rules remain, recomputed | yes | Pass |
| Calendar display | `/calendar` | readable, consistent | unstyled, clipped table | **Fail (UX U-01)** |
| Conflict labels | dashboard | clear | "Blackouts (53)" ambiguous | Partial |

**Time zone:** all dates are stored as date-only strings; no timezone conversion is applied or needed for date spans. No defect found, but the system would need explicit handling if timed sessions are added.

---

## 5. Commands and raw evidence

```text
$ venv/bin/python -m pytest -q
398 passed in 5.03s

$ sqlite3 tracker.db "select count(*) from events;"
116
$ sqlite3 tracker.db "... where coalesce(event_end,event_start) < '2026-11-22'"
16  (13 HIGH PRIORITY, 3 MEDIUM)
$ sqlite3 tracker.db "... no_start/no_end/no_deadline/verified"
13 / 10 / 23 / 98
$ sqlite3 tracker.db "select count(*), sum(...) from blackout_dates"
29 rules / 54 unique enabled days / 53 conflicts

$ curl -s -o /dev/null -w "%{time_total}" /dashboard
0.040 s (376 KB)

HTTP security headers: none present.
/docs -> 200, /openapi.json -> 200.
```

Synthetic scoring results:

```text
adult-only ("18+ only ... university students only") -> score 0, INELIGIBLE (correct)
online + location "Bengaluru / Online"               -> score 55, geo reason "In-person in Bengaluru" (wrong)
multi-day 2026-11-25..27                             -> CONFLICT (correct)
boundary 2026-11-25                                  -> 98, HIGH PRIORITY (correct)
boundary 2026-11-30                                  -> CONFLICT (correct)
missing end date 2026-11-28                          -> CONFLICT (correct)
generic title + Mumbai + no prize                    -> 35 (CONFLICT via Jan-17 test date)
```

Dedup results:

```text
generic same-day different city -> True (wrong)
no-date generic titles          -> True (wrong)
same title 4 days apart         -> False (correct)
cross-source same event         -> True (correct)
merged result                   -> 1 event, 2 sources, host=None
```

---

## 6. Route matrix

| Route | Method | Status | Notes |
|---|---|---|---|
| `/` | GET | 200 → JS redirect | Health page hidden (F-14) |
| `/dashboard` | GET | 200 | 63 rendered; counts wrong (F-11) |
| `/dashboard?filter=bengaluru` | GET | 200 | 9 rows vs 30 |
| `/dashboard?filter=eligible` | GET | 200 | 8 rows |
| `/dashboard?filter=closing_soon` | GET | 200 | 33 rows vs 3 |
| `/dashboard?filter=free_weekend` | GET | 200 | 22 rows |
| `/dashboard?filter=excluded` | GET | 200 | 53 rows |
| `/calendar` | GET | 200 | Broken styling (U-01) |
| `/sources` | GET | 200 | Broken header, fake health (F-10) |
| `/list` | GET | 200 | Read-only list |
| `/event/{id}` | GET | 200/404 | Works; lacks lineage (F-13) |
| `/api/events` | GET | 200 | 116 rows incl. 16 expired |
| `/api/deadlines` | GET | 200 | Upcoming only |
| `/api/dashboard-stats` | GET | 200 | Source of the 100 count |
| `/api/blackouts` | GET/POST | 200/422 | CRUD works; unauthenticated |
| `/api/blackouts/{id}` | PUT/DELETE | 200/404 | Recomputes conflicts |
| `/api/blackouts/{id}/toggle` | POST | 200/404 | Works |
| `/api/action` | POST | 200/400/403/404 | Token optional (S-05) |
| `/api/sources` | GET | 200 | 27 sources |
| `/api/sources/{key}/toggle` | POST | 200/404 | Unauthenticated |
| `/api/scan` | POST | 200/500 | Unauthenticated, triggers writes |
| `/api/scans` | GET | 200 | Scan log |
| `/track`, `/applied`, `/reject` | GET | 200/400/403 | Signed-token actions |

---

## 7. Untested / cannot confirm

- Successful SMTP delivery (no email sent).
- Real discovery scan through the UI (avoided DB writes).
- Shortlist/Applied/Reject state changes on real events (avoided user-state changes).
- Blackout create/edit/delete through the modal (CRUD tested on DB copy; modal rendering tested only).
- Scheduled weekly run under launchd (jobs not loaded).
- Concurrent access/WAL behavior under load.
- Behaviour when external APIs change or rate-limit.
