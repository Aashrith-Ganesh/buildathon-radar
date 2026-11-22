# Antigravity Integration Guide: Buildathon Radar

This document defines the integration between **Antigravity** and **Buildathon Radar**.

Antigravity serves as the **optional, on-demand AI analysis and decision-making layer**. The core application functions completely without Antigravity (discovering events, applying rule-based scoring, updating the SQLite database, and serving the local dashboard).

No paid external LLM API (such as Anthropic or OpenAI) is required.

---

## Architecture Overview

```
                      +---------------------------------------+
                      |             EVENT SOURCES             |
                      | Devpost, Devfolio, Luma, Unstop, MLH  |
                      +-------------------+-------------------+
                                          |
                                          v
                      +---------------------------------------+
                      |           DISCOVERY ENGINE            |
                      | Fetching, Normalization, Dedup        |
                      +-------------------+-------------------+
                                          |
                                          v
                      +---------------------------------------+
                      |      RULE-BASED FILTERING ENGINE      |
                      | Class 11/12 High School Eligibility   |
                      | Scoring (0-100), Priority Tiers       |
                      +-------------------+-------------------+
                                          |
                                          v
                      +---------------------------------------+
                      |            SQLITE DATABASE            |
                      |              (tracker.db)             |
                      +-------+-----------------------+-------+
                              |                       |
                              v                       v
               +----------------------+      +----------------------+
               |    LOCAL TRACKER     |      |     ANTIGRAVITY      |
               |  FastAPI Dashboard   |      |  AI Reasoning Layer  |
               |   (localhost:8015)   |      |  (On-Demand CLI/SQL) |
               +----------------------+      +----------------------+
```

---

## 1. SQLite Database Schema (`tracker.db`)

All data is stored locally in `tracker.db` in SQLite WAL mode. Antigravity can query it directly via SQL or via the CLI.

### Table: `events`

| Column | Type | Description |
|---|---|---|
| `event_id` | TEXT PRIMARY KEY | Composite slug: `host-title-startdate` |
| `title` | TEXT NOT NULL | Event name |
| `url` | TEXT NOT NULL | Canonical registration / event URL |
| `host` | TEXT | Organiser / sponsoring organization |
| `source` | TEXT | Source platform (`Devpost`, `Devfolio`, `Luma`, `Unstop`, `MLH`, `Watchlist`) |
| `summary` | TEXT | Event blurb / description (trimmed) |
| `category` | TEXT | Category (`Hackathon`, `Meetup`, `Showcase`, `Competition`) |
| `location` | TEXT | Location string (e.g. `Bengaluru, Karnataka`, `Online`) |
| `mode` | TEXT | `in-person`, `online`, `hybrid`, or `unknown` |
| `event_start` | TEXT | ISO start date `YYYY-MM-DD` |
| `event_end` | TEXT | ISO end date `YYYY-MM-DD` |
| `registration_deadline` | TEXT | ISO registration deadline `YYYY-MM-DD` |
| `team_size` | TEXT | Team size restrictions (e.g. `3-5 members`, `1-4`) |
| `eligibility` | TEXT | `ELIGIBLE`, `UNKNOWN`, `INELIGIBLE` |
| `age_restrictions` | TEXT | Explicit age restrictions (e.g. `Open to school students`, `18+ only`, `None specified`) |
| `prize` | TEXT | Prize information |
| `priority` | TEXT | `HIGH PRIORITY`, `MEDIUM PRIORITY`, `LOW PRIORITY`, `INELIGIBLE` |
| `score` | INTEGER | Rule-based score from 0 to 100 |
| `why` | TEXT | Explainable justification for score and tiering |
| `state` | TEXT | Lifecycle: `seen`, `tracked` (shortlisted), `applied`, `rejected`, `over` |
| `first_seen` | TEXT | ISO timestamp when first discovered |
| `last_verified` | TEXT | ISO timestamp of last verification |
| `tracked_at` | TEXT | ISO timestamp when shortlisted |
| `applied_at` | TEXT | ISO timestamp when marked applied |
| `rejected_at` | TEXT | ISO timestamp when rejected |
| `updated_at` | TEXT | ISO timestamp of last update |

### Table: `action_log`

Audit trail recording user actions (`track`, `applied`, `reject`) and outcomes (`ok`, `noop`, `bad_token`, `unknown_event`).

---

## 2. Antigravity CLI Commands

Antigravity can invoke these commands directly:

### Inspect Database
```bash
venv/bin/python antigravity_cli.py inspect --priority "HIGH PRIORITY"
venv/bin/python antigravity_cli.py inspect --eligibility "UNKNOWN"
venv/bin/python antigravity_cli.py inspect --search "Agent" --json
```

### Database Summary
```bash
venv/bin/python antigravity_cli.py summary
```

### Deep Event Analysis
```bash
venv/bin/python antigravity_cli.py analyze <event_id>
```

### Class 11 Eligibility Check
```bash
venv/bin/python antigravity_cli.py eligibility <event_id>
```

### Upcoming Registration Deadlines
```bash
venv/bin/python antigravity_cli.py deadlines --limit 10
```

### Overlapping Event Dates
```bash
venv/bin/python antigravity_cli.py overlaps
```

### Side-by-Side Comparison
```bash
venv/bin/python antigravity_cli.py compare <event_id_1> <event_id_2>
```

### Top Recommendations
```bash
venv/bin/python antigravity_cli.py recommend --limit 8
```

### Generate Personalized Markdown Report
```bash
venv/bin/python antigravity_cli.py report --output archive/opportunity_report.md
```

### Scan Incomplete or Suspicious Listings
```bash
venv/bin/python antigravity_cli.py verify
```

### Backup Database
```bash
venv/bin/python antigravity_cli.py backup
```

---

## 3. Recommended Antigravity Workflow

When the user asks Antigravity for hackathon guidance:

1. **Check Status & Summary:**
   Run `antigravity_cli.py summary` to see the current opportunity landscape.
2. **Review High-Priority Events:**
   Run `antigravity_cli.py inspect --priority "HIGH PRIORITY"` to find verified, student-eligible competitions.
3. **Resolve Unknown Eligibility:**
   Run `antigravity_cli.py inspect --eligibility "UNKNOWN"` to identify promising events where the student needs to check the rules.
4. **Schedule Planning:**
   Run `antigravity_cli.py deadlines` and `antigravity_cli.py overlaps` to ensure the student doesn't miss deadlines or register for conflicting dates.
5. **Report Generation:**
   Generate a custom opportunity brief with `antigravity_cli.py report`.
