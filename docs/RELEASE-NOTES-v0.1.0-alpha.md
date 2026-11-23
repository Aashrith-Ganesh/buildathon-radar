# Release Notes — Buildathon Radar v0.1.0-alpha

- **Release Version:** `v0.1.0-alpha`
- **Release Codename:** Student Opportunity Intelligence & Blackout Protection
- **Release Date:** November 23, 2026
- **Target Audience:** High-School Students (Class 11/12, The Amaatra Academy, Bengaluru) & Mentors
- **Git Tag:** `v0.1.0-alpha`

---

## Executive Summary

Buildathon Radar `v0.1.0-alpha` marks the first official, stabilized release of the student-first hackathon discovery and opportunity intelligence platform. Originally derived from upstream open-source work by Jcube101 and inspired by SEPURI-SAI-KRISHNA, this release culminates an extensive multi-phase initiative: resolving all critical findings from the Freebuff application audit, implementing transparent rule-based eligibility filtering without metered LLM costs, and providing automated academic blackout protection specifically calibrated for Indian high-school curriculums.

---

## Key Highlights & Feature Deliverables

### 1. Freebuff Audit Remediation & Integrity Engine
- **Elimination of Pseudo-Discovery:** Completely removed mocked fixtures, fallback network data, and Google News RSS headline scraping that previously masqueraded as live hackathon events.
- **Accurate Lifecycle States:** Refactored event lifecycle filtering into distinct states (`seen`, `tracked`, `applied`, `rejected`, `over`). Completed and expired hackathons are cleanly segregated from open opportunities.
- **Robust Canonical Deduplication:** Multi-factor entity resolution prevents over-merging while preserving cross-source lineage and per-sighting metadata.

### 2. Academic Blackout Calendar (46 Rules / 69 Days)
- **Zero Academic Compromise:** Preserves a comprehensive calendar of 46 distinct academic blackout rules covering 69 unique examination days (spanning term examinations, pre-boards, CBSE board testing periods, and national entrance exams).
- **Interactive Visual Monthly Grid:** Added a monthly calendar interface at `/calendar` with day badges and interactive hover tooltips that detail the specific examination, organizing school/board, reason, and active conflict status.
- **Automated Conflict Tagging:** Events clashing with exam days are clearly labeled and downgraded in recommendation priorities.

### 3. Student Affiliation & Personal Tracker
- **Affiliation Update:** Updated student affiliation to **The Amaatra Academy** (Bengaluru, Karnataka) in `config/profile.json` and web templates.
- **Unlocked Loopback Tracker:** The personal tracker (`/tracker` and `/api/tracker`) is fully unlocked for seamless loopback usage (`127.0.0.1`), allowing immediate note-taking and state tracking without authentication friction.
- **Curated Real Opportunities:** Added verified hackathons, including **HackFusion 4.0** (`hackfusion-4-sggs-nanded`), directly into the verified SQLite database.

### 4. Transparent 0–100 Student Relevance Rubric
- **Zero LLM API Key Requirement:** Evaluates theme relevance (AI/ML, Agents, Robotics, Systems Software), geographic accessibility (Bengaluru in-person bonus, other India, online), team size (3–5 members preferred), and host prestige deterministically.
- **Explainable Scores:** Clear factor breakdowns visible on every event detail page (`/h/{slug}`).

### 5. Repository Hygiene & Release Gallery
- **Standardized Screenshots:** Captured and organized clean, high-resolution snapshots in `docs/screenshots/` (Dark Dashboard, Light Dashboard, Mobile Views, Monthly Calendar Grid, Personal Tracker, Sources Console, Event Detail).
- **Zero Secret Exposure:** Verified `.env` and `*.db` are strictly excluded from version control; provided safe `.env.example`.
- **Packaging & Test Cleanliness:** Verified all 444 automated tests pass in ~1.08s with zero broken dependencies (`pip check` clean, LaunchAgent plists validated).

---

## Detailed Changelog

### Added
- `docs/screenshots/calendar-month-grid.png`: High-resolution capture of the interactive monthly examination calendar.
- `docs/screenshots/`: Consolidated screenshot gallery for all core views.
- `docs/RELEASE-NOTES-v0.1.0-alpha.md`: Formal release documentation.
- `docs/RELEASE-READINESS-REPORT.md`: Comprehensive release readiness audit sign-off.
- Interactive hover tooltips in `/calendar` with rich exam, school, reason, and conflict badges.
- HackFusion 4.0 event registration in SQLite database.

### Changed
- `README.md`: Completely rewritten to include all 21 comprehensive sections with architecture diagrams, scoring rubric, and verified test results.
- `config/profile.json`: Updated school affiliation to The Amaatra Academy.
- `buildathon_radar/tracker_service.py`: Updated school branding, unlocked `/tracker` and `/api/tracker` for loopback use, and enriched calendar hover mechanics.
- `.gitignore`: Enhanced to strictly ignore `.DS_Store`, `*.db`, `*.db-wal`, `*.db-shm`, `*.bak`, and `.env.*`.

### Fixed
- Fixed calendar hover and detail display to surface specific academic blackout rules.
- Fixed personal tracker access to eliminate unnecessary password barriers on local loopback.
- Cleaned whitespace and untracked files across the repository.

---

## Verification & Test Results

```
============================= test session starts ==============================
collected 444 items

tests/test_agent.py .......................                              [  5%]
tests/test_blackout_calendar_and_redesign.py ..........                  [  7%]
tests/test_deliver.py ..............                                     [ 10%]
tests/test_digest.py ..............................................      [ 20%]
tests/test_feature_expansion.py .............                            [ 23%]
tests/test_fetcher.py .................................................. [ 35%]
.........................................................                [ 47%]
tests/test_guard.py .........                                            [ 50%]
tests/test_local_security.py ....                                        [ 50%]
tests/test_main.py .......                                               [ 52%]
tests/test_multi_platform_discovery.py ................................. [ 59%]
....................................                                     [ 68%]
tests/test_student_radar.py ...................                          [ 72%]
tests/test_tracker_service.py ....................                       [ 76%]
tests/test_tracker_store.py ..............................               [ 83%]
tests/test_triage.py .............................................       [ 93%]
tests/test_watchlist.py ............................                     [100%]

============================= 444 passed in 1.08s ==============================
```

- **Launchd Plist Validation:** `scheduler/launchd/*.plist: OK`
- **Dependency Status:** `pip check: No broken requirements found`
- **Git Tree Status:** Clean working tree, no tracked secrets or local databases.

---

## Operating Instructions

```bash
# Activate environment
source venv/bin/activate

# Start local tracker service
uvicorn buildathon_radar.tracker_service:app --host 127.0.0.1 --port 8015

# Access dashboard
open http://127.0.0.1:8015/dashboard
```
