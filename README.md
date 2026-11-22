# Buildathon Radar (Indian High-School Student Edition)

An automated hackathon and buildathon discovery service tailored for an Indian high-school student (Class 11/12) based in Bengaluru, Karnataka. It continuously monitors top competition platforms, filters events using transparent, rule-based scoring without requiring external paid LLM APIs, persists structured event data in SQLite, serves an interactive local dashboard, and provides a native reasoning and query interface for **Antigravity**.

---

## Architecture Overview

```
                      +------------------------------------------+
                      |              EVENT SOURCES               |
                      | Devpost · Devfolio · Luma · Unstop · MLH |
                      | Watchlist (Top AI Companies & Contests)  |
                      +--------------------+---------------------+
                                           |
                                           v
                      +------------------------------------------+
                      |             DISCOVERY ENGINE             |
                      |  HTTP APIs · Canonical URL Dedup · Cache |
                      +--------------------+---------------------+
                                           |
                                           v
                      +------------------------------------------+
                      |     RULE-BASED STUDENT ELIGIBILITY       |
                      |  Class 11/12 High School Eligibility     |
                      |  Transparent Scoring (0-100) & Tiers     |
                      |  (Zero External Paid LLM Dependency)     |
                      +--------------------+---------------------+
                                           |
                                           v
                      +------------------------------------------+
                      |             SQLITE DATABASE              |
                      |      (tracker.db in WAL concurrency)     |
                      +----------+--------------------+----------+
                                 |                    |
                                 v                    v
               +-------------------------+   +-------------------------+
               |     LOCAL TRACKER       |   |       ANTIGRAVITY       |
               |    FastAPI Dashboard    |   |    AI Reasoning Layer   |
               |  (http://127.0.0.1:8015)|   |  (On-Demand CLI / SQL)  |
               +-------------------------+   +-------------------------+
                                 |
                                 v
               +-----------------------------------------+
               |         PERSISTENT LOCAL REPORTS        |
               |  Markdown & HTML in archive/            |
               |  (Optional Email Digest if configured)  |
               +-----------------------------------------+
```

---

## Key Adaptations in this Edition

1. **Student & High-School Focus (Class 11 & Class 12)**:
   - Prioritizes hackathons open to high-school students, school students, and minors.
   - Preserves college-organised competitions that permit external school participants (marked `UNKNOWN` for manual verification rather than auto-dropped).
   - Automatically excludes competitions that strictly prohibit minors or require enrolled university undergraduates (e.g. `18+ only`, `enrolled university students only`).
2. **Geographic Priorities**:
   - **Tier 1:** Bengaluru, Karnataka (In-person buildathons, tech showcases, and hackathons).
   - **Tier 2:** Other Indian cities (Delhi NCR, Mumbai, Hyderabad, Pune, Chennai).
   - **Tier 3:** Global online competitions.
3. **Transparent Rule-Based Engine (No Paid LLM Required)**:
   - Completely removes mandatory dependency on `ANTHROPIC_API_KEY` or paid LLM APIs.
   - Evaluates theme fit (AI/ML, GenAI, Agents, Fintech, Robotics, Quantum), location, team size (3-5 preferred), host prestige, and format.
   - Assigns explainable priorities: `HIGH PRIORITY`, `MEDIUM PRIORITY`, `LOW PRIORITY`, `INELIGIBLE`.
4. **Antigravity On-Demand Intelligence Layer**:
   - Ready-to-use CLI and Python interface for Antigravity to inspect, analyze, and compare events, verify Class 11 eligibility, track deadlines, and generate customized reports.
5. **Native macOS `launchd` Scheduling**:
   - Replaced Linux systemd with native macOS `launchd` plist templates for background weekly execution (Sundays at 5:00 PM IST) and tracker service management.
6. **Local Tracker Dashboard**:
   - FastAPI web service running locally on `http://127.0.0.1:8015`. No Cloudflare Tunnel required.

---

## Installation

### Prerequisites
- macOS 12+ (Apple Silicon or Intel)
- Python 3.11+ (Python 3.13 recommended)

### Step 1: Clone and Setup Virtual Environment
```bash
cd ~/Projects/buildathon-radar
python3 -m venv venv
venv/bin/pip install --upgrade pip
venv/bin/pip install -r requirements.txt
```

### Step 2: Configure Environment
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
*Note:* No API keys are required for discovery and local dashboard operation. `TRACKER_SECRET` will be auto-generated securely if left blank.

---

## Operating Commands

### 1. Manual Discovery & Runs
```bash
# Dry run: fetches live events, runs rule-based filter, displays digest, does not alter database or cache
venv/bin/python main.py --dry-run

# Full run: fetches live, filters, updates SQLite tracker.db and cache.json, archives reports
venv/bin/python main.py
```

### 2. Antigravity & CLI Intelligence Interface
```bash
# Overview statistics of discovered hackathons
venv/bin/python antigravity_cli.py summary

# Inspect high-priority opportunities
venv/bin/python antigravity_cli.py inspect --priority "HIGH PRIORITY"

# Search for specific themes or keywords (e.g. agents)
venv/bin/python antigravity_cli.py inspect --search "Agent"

# In-depth analysis of a specific event
venv/bin/python antigravity_cli.py analyze <event_id>

# Check Class 11 student eligibility and action steps
venv/bin/python antigravity_cli.py eligibility <event_id>

# Upcoming registration deadlines chronologically
venv/bin/python antigravity_cli.py deadlines

# Check for date conflicts and overlapping events
venv/bin/python antigravity_cli.py overlaps

# Generate a personalized Markdown opportunity report
venv/bin/python antigravity_cli.py report --output archive/student_report.md

# Scan for incomplete or suspicious listings
venv/bin/python antigravity_cli.py verify

# Create a timestamped backup of the database
venv/bin/python antigravity_cli.py backup
```

### 3. Local Tracker Service (Web Dashboard)
```bash
# Run tracker locally
venv/bin/uvicorn buildathon_radar.tracker_service:app --host 127.0.0.1 --port 8015

# Open Dashboard in your browser:
# http://127.0.0.1:8015/dashboard
# Open Read-Only List:
# http://127.0.0.1:8015/list
# JSON API:
# http://127.0.0.1:8015/api/events
```

### 4. macOS Scheduling with `launchd`
Use the provided management script `scripts/manage_launchd.sh`:
```bash
# Validate plist syntax
./scripts/manage_launchd.sh validate

# Install plist files to ~/Library/LaunchAgents/
./scripts/manage_launchd.sh install

# Start services (only after confirmation)
./scripts/manage_launchd.sh start-tracker
./scripts/manage_launchd.sh start-radar

# Check service status
./scripts/manage_launchd.sh status

# View persistent service logs
./scripts/manage_launchd.sh logs

# Stop services
./scripts/manage_launchd.sh stop-tracker
./scripts/manage_launchd.sh stop-radar
```

---

## Configuration & Profile Customization

The student profile is configured in `config/profile.json`:
- **Target Location**: Default `Bengaluru, Karnataka`.
- **Location Weights**: Bengaluru (30), Other India (20), Online (14), Int'l onsite (5).
- **Target Themes**: AI/ML, Generative AI, Agentic AI, Software Engineering, Fintech, Quantum, Robotics, Dev Tools.
- **Preferred Team Size**: 3–5 members (preference bonus awarded).
- **Eligibility Criteria**: Explicit inclusion and exclusion rules.

To adjust weights or add interests, edit `config/profile.json`.

---

## Event Sources

| Source | Target / Scope | Method | Status |
|---|---|---|---|
| **Devpost** | Global & India AI/Software Hackathons | Public JSON API | Active |
| **Devfolio** | India National & Regional Hackathons | Public Search API | Active |
| **Luma** | Bengaluru In-Person Meetups & Showcases | Public Place Feed API | Active |
| **Unstop** | Indian College & Open Competitions | Public Opportunity API | Active |
| **MLH** | Major League Hacking Official Seasons | Public Schema.org Feed | Active |
| **Watchlist** | 100 Major AI Companies (Competitions) | News RSS Search | Active |
| **Cerebral Valley**| AI Builders & Showcases | Public Event API | Toggleable (`ENABLE_CV_SOURCE`) |

---

## Database Schema (`tracker.db`)

All data is stored in `tracker.db` under the `events` table:
- `event_id`: Primary key composite slug
- `title`, `host`, `url`, `source`, `summary`, `category`
- `location`, `mode` (`in-person`, `online`, `hybrid`)
- `event_start`, `event_end`, `registration_deadline`
- `team_size`, `eligibility`, `age_restrictions`, `prize`
- `priority` (`HIGH PRIORITY`, `MEDIUM PRIORITY`, `LOW PRIORITY`, `INELIGIBLE`)
- `score` (0–100 integer)
- `why` (Explainable reasoning)
- `state` (`seen`, `tracked`, `applied`, `rejected`, `over`)
- `first_seen`, `last_verified`, `tracked_at`, `applied_at`, `rejected_at`, `updated_at`

---

## Testing

Run the automated test suite (343 tests):
```bash
venv/bin/pytest
```
All tests run with mocked network and zero external API dependencies.
