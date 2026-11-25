# CLI and Database Reference: Buildathon Radar

This document provides a comprehensive technical reference for the local SQLite database schema and the opportunity intelligence command-line interface.

The core application functions completely offline without external services (discovering events, applying rule-based scoring, updating the SQLite database, and serving the local dashboard).

---

## 1. SQLite Database Schema (`tracker.db`)

All data is stored locally in `tracker.db` in SQLite WAL (Write-Ahead Logging) mode. It can be queried directly via standard SQL or through the project CLI.

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

## 2. CLI Commands Reference

The command-line interface (`python -m buildathon_radar.cli` or `./radar_cli.py`, with `./antigravity_cli.py` retained as an alias) provides rapid terminal access to opportunity inspection and query tools:

### Inspect Database
```bash
venv/bin/python radar_cli.py inspect --priority "HIGH PRIORITY"
venv/bin/python radar_cli.py inspect --eligibility "UNKNOWN"
venv/bin/python radar_cli.py inspect --search "Agent" --json
```

### Database Summary
```bash
venv/bin/python radar_cli.py summary
```

### Deep Event Analysis
```bash
venv/bin/python radar_cli.py analyze <event_id>
```

### Student Eligibility Evaluation
```bash
venv/bin/python radar_cli.py eligibility <event_id>
```

### Upcoming Registration Deadlines
```bash
venv/bin/python radar_cli.py deadlines --limit 10
```

### Overlapping Event Dates
```bash
venv/bin/python radar_cli.py overlaps
```

### Side-by-Side Comparison
```bash
venv/bin/python radar_cli.py compare <event_id_1> <event_id_2>
```

### Top Recommendations
```bash
venv/bin/python radar_cli.py recommend --limit 8
```

### Generate Opportunity Report
```bash
venv/bin/python radar_cli.py report --output archive/opportunity_report.md
```

### Scan Incomplete or Suspicious Listings
```bash
venv/bin/python radar_cli.py verify
```

### Backup Database
```bash
venv/bin/python radar_cli.py backup
```
