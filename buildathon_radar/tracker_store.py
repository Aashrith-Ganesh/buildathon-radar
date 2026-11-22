from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
from datetime import datetime as _datetime
from datetime import timedelta, timezone
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from dotenv import load_dotenv

from buildathon_radar import personal_tracker

load_dotenv()

DB_FILE = "tracker.db"
IST = timezone(timedelta(hours=5, minutes=30))

STATE_RANK = {
    "discovered": 0,
    "seen": 1,
    "ineligible": 1,
    "rejected": 2,
    "tracked": 3,
    "applied": 4,
    "over": 5,
}

ACTION_TO_STATE = {
    "track": "tracked",
    "applied": "applied",
    "reject": "rejected",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    event_id              TEXT PRIMARY KEY,
    title                 TEXT NOT NULL,
    url                   TEXT NOT NULL,
    host                  TEXT,
    source                TEXT,
    summary               TEXT,
    category              TEXT,
    location              TEXT,
    mode                  TEXT,
    event_start           TEXT,
    event_end             TEXT,
    registration_deadline TEXT,
    team_size             TEXT,
    eligibility           TEXT,
    age_restrictions      TEXT,
    prize                 TEXT,
    priority              TEXT,
    score                 INTEGER DEFAULT 0,
    why                   TEXT,
    state                 TEXT NOT NULL DEFAULT 'seen'
                          CHECK (state IN ('discovered', 'seen', 'tracked', 'applied', 'rejected', 'ineligible', 'over')),
    outcome               TEXT
                          CHECK (outcome IS NULL OR outcome IN
                                 ('did_not_participate', 'participated', 'won')),
    blackout_conflict     INTEGER DEFAULT 0,
    conflict_details      TEXT DEFAULT '[]',
    date_status           TEXT DEFAULT 'verified',
    first_seen            TEXT NOT NULL,
    last_verified         TEXT,
    tracked_at            TEXT,
    applied_at            TEXT,
    rejected_at           TEXT,
    over_at               TEXT,
    updated_at            TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS action_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id     TEXT NOT NULL,
    action       TEXT NOT NULL,
    result       TEXT NOT NULL,
    occurred_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS blackout_dates (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT NOT NULL,
    start_date   TEXT NOT NULL,
    end_date     TEXT NOT NULL,
    category     TEXT NOT NULL,
    reason       TEXT,
    enabled      INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS discovery_sources (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    source_key        TEXT UNIQUE NOT NULL,
    name              TEXT NOT NULL,
    category          TEXT NOT NULL,
    discovery_method  TEXT NOT NULL,
    confidence_level  TEXT NOT NULL,
    enabled           INTEGER NOT NULL DEFAULT 1,
    last_scan         TEXT,
    events_discovered INTEGER NOT NULL DEFAULT 0,
    success_count     INTEGER NOT NULL DEFAULT 0,
    fail_count        INTEGER NOT NULL DEFAULT 0,
    last_error        TEXT,
    updated_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS discovery_scans (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp          TEXT NOT NULL,
    duration_seconds   REAL NOT NULL DEFAULT 0.0,
    total_sources      INTEGER NOT NULL DEFAULT 0,
    successful_sources INTEGER NOT NULL DEFAULT 0,
    failed_sources     INTEGER NOT NULL DEFAULT 0,
    new_events         INTEGER NOT NULL DEFAULT 0,
    updated_events     INTEGER NOT NULL DEFAULT 0,
    details            TEXT DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_events_state ON events(state);
CREATE INDEX IF NOT EXISTS idx_events_priority ON events(priority);
CREATE INDEX IF NOT EXISTS idx_events_deadline ON events(registration_deadline);
CREATE INDEX IF NOT EXISTS idx_blackout_dates ON blackout_dates(start_date, end_date);
CREATE INDEX IF NOT EXISTS idx_blackout_enabled ON blackout_dates(enabled);
CREATE INDEX IF NOT EXISTS idx_sources_key ON discovery_sources(source_key);
CREATE INDEX IF NOT EXISTS idx_sources_enabled ON discovery_sources(enabled);
"""

# Initial seed data for the personal blackout calendar
INITIAL_BLACKOUT_ENTRIES = [
    # Existing Personal Blackout Dates (2026)
    {
        "title": "Personal Commitment (15 Nov)",
        "start_date": "2026-11-15",
        "end_date": "2026-11-15",
        "category": "Personal",
        "reason": "Personal commitment blackout date",
    },
    {
        "title": "Personal Blackout Period (26-30 Nov)",
        "start_date": "2026-11-26",
        "end_date": "2026-11-30",
        "category": "Personal",
        "reason": "Personal commitment continuous blackout period",
    },
    {
        "title": "Personal Commitment (6 Dec)",
        "start_date": "2026-12-06",
        "end_date": "2026-12-06",
        "category": "Personal",
        "reason": "Personal commitment blackout date",
    },
    {
        "title": "Personal Blackout Period (10-16 Dec)",
        "start_date": "2026-12-10",
        "end_date": "2026-12-16",
        "category": "Personal",
        "reason": "Personal commitment continuous blackout period",
    },
    # ALLEN JEE Examination and Test Dates (2026)
    {
        "title": "Internal Test 1",
        "start_date": "2026-05-06",
        "end_date": "2026-05-06",
        "category": "Academic Test",
        "reason": "ALLEN JEE Internal Test 1",
    },
    {
        "title": "Internal Test 1",
        "start_date": "2026-06-07",
        "end_date": "2026-06-07",
        "category": "Academic Test",
        "reason": "ALLEN JEE Internal Test 1",
    },
    {
        "title": "Internal Test 2",
        "start_date": "2026-06-28",
        "end_date": "2026-06-28",
        "category": "Academic Test",
        "reason": "ALLEN JEE Internal Test 2",
    },
    {
        "title": "Optional Advanced Test",
        "start_date": "2026-07-05",
        "end_date": "2026-07-05",
        "category": "Academic Test",
        "reason": "ALLEN JEE Optional Advanced Test",
    },
    {
        "title": "Internal Test 3",
        "start_date": "2026-07-19",
        "end_date": "2026-07-19",
        "category": "Academic Test",
        "reason": "ALLEN JEE Internal Test 3",
    },
    {
        "title": "Optional Advanced Test",
        "start_date": "2026-07-26",
        "end_date": "2026-07-26",
        "category": "Academic Test",
        "reason": "ALLEN JEE Optional Advanced Test",
    },
    {
        "title": "Internal Test 4",
        "start_date": "2026-08-09",
        "end_date": "2026-08-09",
        "category": "Academic Test",
        "reason": "ALLEN JEE Internal Test 4",
    },
    {
        "title": "Optional Main Test",
        "start_date": "2026-08-19",
        "end_date": "2026-08-19",
        "category": "Academic Test",
        "reason": "ALLEN JEE Optional Main Test",
    },
    {
        "title": "Major Internal Test 1",
        "start_date": "2026-08-30",
        "end_date": "2026-08-30",
        "category": "Academic Test",
        "reason": "ALLEN JEE Major Internal Test 1",
    },
    {
        "title": "Optional Advanced Test",
        "start_date": "2026-09-06",
        "end_date": "2026-09-06",
        "category": "Academic Test",
        "reason": "ALLEN JEE Optional Advanced Test",
    },
    {
        "title": "Internal Test 5",
        "start_date": "2026-09-20",
        "end_date": "2026-09-20",
        "category": "Academic Test",
        "reason": "ALLEN JEE Internal Test 5",
    },
    {
        "title": "Optional Advanced Test",
        "start_date": "2026-09-27",
        "end_date": "2026-09-27",
        "category": "Academic Test",
        "reason": "ALLEN JEE Optional Advanced Test",
    },
    {
        "title": "Internal Test 6",
        "start_date": "2026-10-11",
        "end_date": "2026-10-11",
        "category": "Academic Test",
        "reason": "ALLEN JEE Internal Test 6",
    },
    {
        "title": "Optional Main Test",
        "start_date": "2026-10-18",
        "end_date": "2026-10-18",
        "category": "Academic Test",
        "reason": "ALLEN JEE Optional Main Test",
    },
    {
        "title": "Internal Test 7",
        "start_date": "2026-11-15",
        "end_date": "2026-11-15",
        "category": "Academic Test",
        "reason": "ALLEN JEE Internal Test 7",
    },
    {
        "title": "Major Internal Test 2",
        "start_date": "2026-11-29",
        "end_date": "2026-11-29",
        "category": "Academic Test",
        "reason": "ALLEN JEE Major Internal Test 2",
    },
    {
        "title": "Optional Advanced Test",
        "start_date": "2026-12-06",
        "end_date": "2026-12-06",
        "category": "Academic Test",
        "reason": "ALLEN JEE Optional Advanced Test",
    },
    {
        "title": "Internal Test 8",
        "start_date": "2026-12-20",
        "end_date": "2026-12-20",
        "category": "Academic Test",
        "reason": "ALLEN JEE Internal Test 8",
    },
    {
        "title": "Optional Main Test",
        "start_date": "2026-12-27",
        "end_date": "2026-12-27",
        "category": "Academic Test",
        "reason": "ALLEN JEE Optional Main Test",
    },
    # ALLEN JEE Examination Dates (2027)
    {
        "title": "Internal Test 9",
        "start_date": "2027-01-10",
        "end_date": "2027-01-10",
        "category": "Academic Test",
        "reason": "ALLEN JEE Internal Test 9",
    },
    {
        "title": "Optional Advanced Test",
        "start_date": "2027-01-17",
        "end_date": "2027-01-17",
        "category": "Academic Test",
        "reason": "ALLEN JEE Optional Advanced Test",
    },
    {
        "title": "Internal Test 10",
        "start_date": "2027-01-31",
        "end_date": "2027-01-31",
        "category": "Academic Test",
        "reason": "ALLEN JEE Internal Test 10",
    },
    # Examination Period (Continuous 2027)
    {
        "title": "Examination Period (Week 1: Feb 8-14)",
        "start_date": "2027-02-08",
        "end_date": "2027-02-14",
        "category": "Examination Period",
        "reason": "Continuous academic examination blackout period",
    },
    {
        "title": "Examination Period (Week 2: Feb 15-21)",
        "start_date": "2027-02-15",
        "end_date": "2027-02-21",
        "category": "Examination Period",
        "reason": "Continuous academic examination blackout period",
    },
    {
        "title": "Examination Period (Week 3: Feb 22-28)",
        "start_date": "2027-02-22",
        "end_date": "2027-02-28",
        "category": "Examination Period",
        "reason": "Continuous academic examination blackout period",
    },
]

# Initial discovery sources covering dedicated platforms, social, event directories, communities, colleges, and search
INITIAL_DISCOVERY_SOURCES = [
    # 1. Dedicated Hackathon Platforms
    {
        "source_key": "devpost",
        "name": "Devpost",
        "category": "Dedicated Hackathon Platforms",
        "discovery_method": "API & Public Feed",
        "confidence_level": "High",
    },
    {
        "source_key": "unstop",
        "name": "Unstop",
        "category": "Dedicated Hackathon Platforms",
        "discovery_method": "API & Public Search",
        "confidence_level": "High",
    },
    {
        "source_key": "devfolio",
        "name": "Devfolio",
        "category": "Dedicated Hackathon Platforms",
        "discovery_method": "API & Platform Feed",
        "confidence_level": "High",
    },
    {
        "source_key": "mlh",
        "name": "Major League Hacking (MLH)",
        "category": "Dedicated Hackathon Platforms",
        "discovery_method": "Season Schedule",
        "confidence_level": "High",
    },
    {
        "source_key": "hackerearth",
        "name": "HackerEarth",
        "category": "Dedicated Hackathon Platforms",
        "discovery_method": "Public Challenges API",
        "confidence_level": "High",
    },
    {
        "source_key": "hack2skill",
        "name": "Hack2skill",
        "category": "Dedicated Hackathon Platforms",
        "discovery_method": "Platform Index",
        "confidence_level": "Medium-High",
    },
    {
        "source_key": "dorahacks",
        "name": "DoraHacks",
        "category": "Dedicated Hackathon Platforms",
        "discovery_method": "Bounties & Hackathons API",
        "confidence_level": "High",
    },
    {
        "source_key": "ethglobal",
        "name": "ETHGlobal",
        "category": "Dedicated Hackathon Platforms",
        "discovery_method": "Calendar Index",
        "confidence_level": "High",
    },
    {
        "source_key": "hackathon_com",
        "name": "Hackathon.com",
        "category": "Dedicated Hackathon Platforms",
        "discovery_method": "Directory Feed",
        "confidence_level": "Medium",
    },
    # 2. Professional & Social Networks
    {
        "source_key": "linkedin",
        "name": "LinkedIn Announcements",
        "category": "Professional and Social Networks",
        "discovery_method": "Public Search & Feed Indexing",
        "confidence_level": "Medium-High",
    },
    {
        "source_key": "twitter",
        "name": "X (Twitter) Announcements",
        "category": "Professional and Social Networks",
        "discovery_method": "Public Announcement Feeds",
        "confidence_level": "Medium",
    },
    {
        "source_key": "reddit",
        "name": "Reddit Developer Communities",
        "category": "Professional and Social Networks",
        "discovery_method": "r/developersIndia & r/hackathons",
        "confidence_level": "Medium",
    },
    # 3. Event Discovery Platforms
    {
        "source_key": "meetup",
        "name": "Meetup Bangalore Tech",
        "category": "Event Discovery Platforms",
        "discovery_method": "Public Developer Groups Feed",
        "confidence_level": "Medium-High",
    },
    {
        "source_key": "eventbrite",
        "name": "Eventbrite India",
        "category": "Event Discovery Platforms",
        "discovery_method": "Public Events Search",
        "confidence_level": "Medium-High",
    },
    {
        "source_key": "townscript",
        "name": "Townscript",
        "category": "Event Discovery Platforms",
        "discovery_method": "Tech Events Index",
        "confidence_level": "Medium-High",
    },
    {
        "source_key": "allevents",
        "name": "AllEvents Bangalore",
        "category": "Event Discovery Platforms",
        "discovery_method": "Developer Category Feed",
        "confidence_level": "Medium",
    },
    {
        "source_key": "tentimes",
        "name": "10times",
        "category": "Event Discovery Platforms",
        "discovery_method": "Tech Conferences & Hackathons",
        "confidence_level": "Medium",
    },
    # 4. Developer and Technology Communities
    {
        "source_key": "gdg",
        "name": "Google Developer Groups (GDG & GDSC)",
        "category": "Developer and Technology Communities",
        "discovery_method": "Community Chapter Events",
        "confidence_level": "High",
    },
    {
        "source_key": "microsoft_reactor",
        "name": "Microsoft Reactor Bengaluru",
        "category": "Developer and Technology Communities",
        "discovery_method": "Reactor Calendar & Challenges",
        "confidence_level": "High",
    },
    {
        "source_key": "aws_community",
        "name": "AWS User Groups India",
        "category": "Developer and Technology Communities",
        "discovery_method": "Community Group Feeds",
        "confidence_level": "High",
    },
    {
        "source_key": "github_community",
        "name": "GitHub Education & Campus",
        "category": "Developer and Technology Communities",
        "discovery_method": "Global Campus Announcements",
        "confidence_level": "High",
    },
    {
        "source_key": "nvidia_dev",
        "name": "NVIDIA Developer Contests",
        "category": "Developer and Technology Communities",
        "discovery_method": "AI Developer Contests",
        "confidence_level": "High",
    },
    {
        "source_key": "foss_united",
        "name": "FOSS United",
        "category": "Developer and Technology Communities",
        "discovery_method": "FOSS Hack & City Meetups",
        "confidence_level": "High",
    },
    {
        "source_key": "cncf",
        "name": "CNCF Community Groups",
        "category": "Developer and Technology Communities",
        "discovery_method": "Cloud Native Hackathons",
        "confidence_level": "High",
    },
    # 5. Indian College and University Sources
    {
        "source_key": "indian_colleges",
        "name": "Indian Engineering Colleges & Tech Fests",
        "category": "Indian College and University Sources",
        "discovery_method": "IIT/NIT/IIIT & Bangalore Colleges",
        "confidence_level": "High",
    },
    # 6. Company and Startup Sources
    {
        "source_key": "tech_companies",
        "name": "Top AI Companies & Indian Startups",
        "category": "Company and Startup Sources",
        "discovery_method": "Official Developer Challenges",
        "confidence_level": "High",
    },
    # 7. Search Engine-Based Discovery Pipeline
    {
        "source_key": "search_discovery",
        "name": "Targeted Web Search Engine Discovery",
        "category": "Search Engine-Based Discovery",
        "discovery_method": "Multi-Query Targeted Web Search",
        "confidence_level": "Medium-High",
    },
]


def _now_ist():
    return _datetime.now(IST).isoformat()


def normalize_url(url: str) -> str:
    """Canonicalize and normalize URLs across platforms.
    Strips trailing slashes, tracking parameters (UTM, etc.), forces https,
    and folds known alias domains (e.g. lu.ma -> luma.com)."""
    if not url:
        return ""
    u = url.strip()
    if u.startswith("http://"):
        u = "https://" + u[len("http://") :]
    if u.startswith("https://lu.ma/"):
        u = "https://luma.com/" + u[len("https://lu.ma/") :]

    try:
        parsed = urlparse(u)
        scheme = parsed.scheme.lower() or "https"
        netloc = parsed.netloc.lower()

        tracking_keys = {
            "utm_source", "utm_medium", "utm_campaign", "utm_term",
            "utm_content", "ref", "fbclid", "gclid", "mc_eid", "_hsenc"
        }
        query_dict = parse_qs(parsed.query, keep_blank_values=False)
        clean_query_dict = {
            k: v for k, v in query_dict.items()
            if k.lower() not in tracking_keys and not k.lower().startswith("utm_")
        }
        clean_query = urlencode(clean_query_dict, doseq=True)
        path = parsed.path.rstrip("/")
        if not path and not clean_query:
            path = "/"

        return urlunparse((scheme, netloc, path, parsed.params, clean_query, ""))
    except Exception:
        return u.rstrip("/")


def _seed_blackout_dates_if_empty(conn: sqlite3.Connection):
    """Initializes the blackout_dates table with supplied dates if empty."""
    cur = conn.execute("SELECT COUNT(*) as c FROM blackout_dates")
    if cur.fetchone()["c"] == 0:
        now = _now_ist()
        for item in INITIAL_BLACKOUT_ENTRIES:
            conn.execute(
                """
                INSERT INTO blackout_dates (title, start_date, end_date, category, reason, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    item["title"],
                    item["start_date"],
                    item["end_date"],
                    item["category"],
                    item.get("reason", ""),
                    now,
                    now,
                ),
            )


def _seed_discovery_sources_if_empty(conn: sqlite3.Connection):
    """Initializes the discovery_sources table if empty."""
    cur = conn.execute("SELECT COUNT(*) as c FROM discovery_sources")
    if cur.fetchone()["c"] == 0:
        now = _now_ist()
        for s in INITIAL_DISCOVERY_SOURCES:
            conn.execute(
                """
                INSERT INTO discovery_sources (
                    source_key, name, category, discovery_method, confidence_level,
                    enabled, last_scan, events_discovered, success_count, fail_count,
                    last_error, updated_at
                )
                VALUES (?, ?, ?, ?, ?, 1, NULL, 0, 0, 0, NULL, ?)
                """,
                (s["source_key"], s["name"], s["category"], s["discovery_method"], s["confidence_level"], now),
            )


def check_event_date_overlap(event_start: str | None, event_end: str | None, blackouts: list) -> tuple:
    """Checks whether an event's date window overlaps with any enabled blackout entry.

    Returns:
        (is_conflict, conflict_list, date_status, human_readable_summary)
    """
    if not event_start:
        return False, [], "uncertain", "⚠️ Dates Unverified: Schedule not published; cannot confirm eligibility."

    es = str(event_start)[:10]
    ee = str(event_end)[:10] if event_end else es
    if ee < es:
        es, ee = ee, es

    conflicts = []
    for b in blackouts:
        enabled = b["enabled"] if isinstance(b, sqlite3.Row) or isinstance(b, dict) else 1
        if not enabled:
            continue
        bs = str(b["start_date"])[:10]
        be = str(b["end_date"])[:10]
        o_start = max(es, bs)
        o_end = min(ee, be)
        if o_start <= o_end:
            overlap_str = f"{o_start} to {o_end}" if o_start != o_end else o_start
            b_range = f"{bs} to {be}" if bs != be else bs
            conflicts.append({
                "blackout_id": b["id"] if "id" in (b.keys() if hasattr(b, "keys") else {}) else None,
                "title": b["title"],
                "category": b["category"],
                "reason": b.get("reason") or b["title"],
                "blackout_range": b_range,
                "overlap_dates": overlap_str,
            })

    is_conflict = len(conflicts) > 0
    if is_conflict:
        details_str = "; ".join([f"{c['title']} ({c['overlap_dates']})" for c in conflicts])
        summary = f"⚠️ Blackout Conflict: Overlaps with {details_str}"
    else:
        summary = ""

    return is_conflict, conflicts, "verified", summary


def recalculate_event_blackout_conflicts(conn: sqlite3.Connection):
    """Recomputes blackout conflicts for all stored events against active blackout dates."""
    cur = conn.execute("SELECT * FROM blackout_dates WHERE enabled = 1 ORDER BY start_date ASC")
    active_blackouts = [dict(r) for r in cur.fetchall()]

    events = conn.execute("SELECT event_id, event_start, event_end, priority, score, why, eligibility, provenance FROM events").fetchall()

    for e in events:
        eid = e["event_id"]
        is_conflict, conflicts, date_status, summary = check_event_date_overlap(
            e["event_start"], e["event_end"], active_blackouts
        )

        why_text = e["why"] or ""
        # Strip existing blackout conflict tags from why
        clean_why = re.sub(
            r"(?:Unavailable \(Blackout Conflict\)|⚠️ Blackout Conflict[^\|]*|Overlaps with [^\|]*)(?:\s*\|\s*)?",
            "",
            why_text,
            flags=re.IGNORECASE,
        ).strip(" |")

        if is_conflict:
            blackout_conflict = 1
            conflict_details = json.dumps(conflicts)
            priority = "CONFLICT (UNAVAILABLE)"
            new_why = f"Unavailable (Blackout Conflict) | {summary}" + (f" | {clean_why}" if clean_why else "")
        else:
            blackout_conflict = 0
            conflict_details = "[]"
            # Restore priority if previously marked conflict
            if e["priority"] == "CONFLICT (UNAVAILABLE)":
                sc = e["score"] or 0
                if e["eligibility"] == "INELIGIBLE":
                    priority = "INELIGIBLE"
                elif sc >= 70 and (e["eligibility"] == "ELIGIBLE" or e["provenance"] == "legacy"):
                    priority = "HIGH PRIORITY"
                elif sc >= 45:
                    priority = "MEDIUM PRIORITY"
                else:
                    priority = "LOW PRIORITY"
                new_why = clean_why or "Student-eligible opportunity"
            else:
                priority = e["priority"]
                new_why = clean_why or why_text

        if date_status == "uncertain" and "⚠️ Dates Unverified" not in new_why:
            new_why = f"⚠️ Dates Unverified | {new_why}".strip(" |")

        conn.execute(
            """
            UPDATE events
            SET blackout_conflict = ?, conflict_details = ?, date_status = ?, priority = ?, why = ?
            WHERE event_id = ?
            """,
            (blackout_conflict, conflict_details, date_status, priority, new_why, eid),
        )
    conn.commit()


def _migrate_schema_if_needed(conn: sqlite3.Connection):
    """Adds missing columns dynamically if migrating from an older schema."""
    cursor = conn.execute("PRAGMA table_info(events)")
    existing_columns = {row[1] for row in cursor.fetchall()}

    columns_to_add = {
        "summary": "TEXT",
        "category": "TEXT",
        "location": "TEXT",
        "mode": "TEXT",
        "registration_deadline": "TEXT",
        "team_size": "TEXT",
        "eligibility": "TEXT",
        "age_restrictions": "TEXT",
        "prize": "TEXT",
        "priority": "TEXT",
        "score": "INTEGER DEFAULT 0",
        "why": "TEXT",
        "last_verified": "TEXT",
        "rejected_at": "TEXT",
        "blackout_conflict": "INTEGER DEFAULT 0",
        "conflict_details": "TEXT DEFAULT '[]'",
        "date_status": "TEXT DEFAULT 'verified'",
        "announcement_url": "TEXT",
        "discovery_sources": "TEXT DEFAULT '[]'",
        "confidence": "TEXT DEFAULT 'Medium'",
        "tech_categories": "TEXT DEFAULT '[]'",
        "verification_status": "TEXT DEFAULT 'verified'",
        "provenance": "TEXT NOT NULL DEFAULT 'legacy'",
        "registration_status": "TEXT",
        "scoring": "TEXT DEFAULT '{}'",
        "eligibility_evidence": "TEXT",
        "eligibility_rules": "TEXT",
        "date_source": "TEXT",
    }

    for col_name, col_type in columns_to_add.items():
        if col_name not in existing_columns:
            conn.execute(f"ALTER TABLE events ADD COLUMN {col_name} {col_type}")

    source_columns = {row[1] for row in conn.execute("PRAGMA table_info(discovery_sources)")}
    for name in ("last_success_at", "last_failed_at", "last_status"):
        if name not in source_columns:
            conn.execute(f"ALTER TABLE discovery_sources ADD COLUMN {name} TEXT")
    for name in ("last_retrieved", "last_valid", "last_rejected"):
        if name not in source_columns:
            conn.execute(f"ALTER TABLE discovery_sources ADD COLUMN {name} INTEGER")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_conflict ON events(blackout_conflict)")
    _seed_blackout_dates_if_empty(conn)
    _seed_discovery_sources_if_empty(conn)
    conn.execute("PRAGMA user_version = 1")


def connect(db_path=None):
    """Opens (creating if needed) the tracker SQLite database in WAL mode."""
    path = db_path or DB_FILE
    if str(path) != ":memory:":
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            os.fchmod(fd, 0o600)
        finally:
            os.close(fd)
    conn = sqlite3.connect(path, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA foreign_keys = ON")
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version < 2:
        if version == 0:
            conn.executescript(SCHEMA)
        try:
            conn.execute("BEGIN IMMEDIATE")
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                _migrate_schema_if_needed(conn)
            if version < 2:
                personal_tracker.migrate(conn)
            conn.commit()
        except Exception:
            conn.close()
            raise
    return conn


get_connection = connect


def get_blackout_dates(conn: sqlite3.Connection, enabled_only: bool = False, category: str | None = None) -> list:
    """Retrieves stored blackout dates."""
    query = "SELECT * FROM blackout_dates WHERE 1=1"
    params = []
    if enabled_only:
        query += " AND enabled = 1"
    if category:
        query += " AND category = ?"
        params.append(category)
    query += " ORDER BY start_date ASC, id ASC"
    return [dict(r) for r in conn.execute(query, params).fetchall()]


def get_blackout_date(conn: sqlite3.Connection, blackout_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM blackout_dates WHERE id = ?", (blackout_id,)).fetchone()
    return dict(row) if row else None


def add_blackout_date(
    conn: sqlite3.Connection,
    title: str,
    start_date: str,
    end_date: str,
    category: str,
    reason: str | None = None,
    enabled: int = 1,
) -> int:
    """Adds a new blackout date or continuous range and recomputes event conflicts."""
    now = _now_ist()
    s = start_date[:10]
    e = (end_date or start_date)[:10]
    if e < s:
        s, e = e, s

    cur = conn.execute(
        """
        INSERT INTO blackout_dates (title, start_date, end_date, category, reason, enabled, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (title.strip(), s, e, category.strip(), (reason or "").strip(), 1 if enabled else 0, now, now),
    )
    new_id = cur.lastrowid
    recalculate_event_blackout_conflicts(conn)
    return new_id


def update_blackout_date(
    conn: sqlite3.Connection,
    blackout_id: int,
    title: str,
    start_date: str,
    end_date: str,
    category: str,
    reason: str | None = None,
    enabled: int = 1,
) -> bool:
    """Updates an existing blackout date entry and recomputes conflicts."""
    now = _now_ist()
    s = start_date[:10]
    e = (end_date or start_date)[:10]
    if e < s:
        s, e = e, s

    cur = conn.execute(
        """
        UPDATE blackout_dates
        SET title = ?, start_date = ?, end_date = ?, category = ?, reason = ?, enabled = ?, updated_at = ?
        WHERE id = ?
        """,
        (title.strip(), s, e, category.strip(), (reason or "").strip(), 1 if enabled else 0, now, blackout_id),
    )
    if cur.rowcount > 0:
        recalculate_event_blackout_conflicts(conn)
        return True
    return False


def delete_blackout_date(conn: sqlite3.Connection, blackout_id: int) -> bool:
    """Deletes a blackout date and recomputes event conflicts."""
    cur = conn.execute("DELETE FROM blackout_dates WHERE id = ?", (blackout_id,))
    if cur.rowcount > 0:
        recalculate_event_blackout_conflicts(conn)
        return True
    return False


def toggle_blackout_date(conn: sqlite3.Connection, blackout_id: int) -> bool:
    """Toggles enabled state of a blackout entry and recomputes event conflicts."""
    result = conn.execute(
        "UPDATE blackout_dates SET enabled = 1 - enabled, updated_at = ? WHERE id = ?",
        (_now_ist(), blackout_id),
    )
    if not result.rowcount:
        return False
    recalculate_event_blackout_conflicts(conn)
    return True


def get_discovery_sources(conn: sqlite3.Connection, enabled_only: bool = False, category: str | None = None) -> list:
    """Retrieves all monitored discovery sources."""
    query = "SELECT * FROM discovery_sources WHERE 1=1"
    params = []
    if enabled_only:
        query += " AND enabled = 1"
    if category:
        query += " AND category = ?"
        params.append(category)
    query += " ORDER BY id ASC"
    return [dict(r) for r in conn.execute(query, params).fetchall()]


def get_discovery_source(conn: sqlite3.Connection, source_key: str) -> dict | None:
    row = conn.execute("SELECT * FROM discovery_sources WHERE source_key = ?", (source_key,)).fetchone()
    return dict(row) if row else None


def toggle_discovery_source(conn: sqlite3.Connection, source_key: str) -> bool | None:
    row = conn.execute("SELECT enabled FROM discovery_sources WHERE source_key = ?", (source_key,)).fetchone()
    if not row:
        return None
    new_enabled = 0 if row["enabled"] else 1
    now = _now_ist()
    conn.execute(
        "UPDATE discovery_sources SET enabled = ?, updated_at = ? WHERE source_key = ?",
        (new_enabled, now, source_key),
    )
    conn.commit()
    return bool(new_enabled)


def update_discovery_source_status(
    conn: sqlite3.Connection,
    source_key: str,
    success: bool,
    events_count: int = 0,
    error: str | None = None,
    error_msg: str | None = None,
    retrieved: int | None = None,
    *, health=None, commit=True,
):
    now = _now_ist()
    err_text = error or error_msg
    if success:
        conn.execute(
            """
            UPDATE discovery_sources
            SET last_scan = ?,
                events_discovered = events_discovered + ?,
                success_count = success_count + 1,
                last_error = ?,
                updated_at = ?
            WHERE source_key = ?
            """,
            (now, events_count, err_text, now, source_key),
        )
    else:
        conn.execute(
            """
            UPDATE discovery_sources
            SET last_scan = ?,
                fail_count = fail_count + 1,
                last_error = ?,
                updated_at = ?
            WHERE source_key = ?
            """,
            (now, str(err_text or "Scan error"), now, source_key),
        )
    if retrieved is not None:
        status = health or ("ok" if success else "failed")
        time_column = "last_success_at" if success else "last_failed_at"
        conn.execute(
            f"""UPDATE discovery_sources SET {time_column} = ?, last_status = ?,
            last_retrieved = ?, last_valid = ?, last_rejected = ? WHERE source_key = ?""",
            (now, status, retrieved, events_count, retrieved - events_count, source_key),
        )
    if commit:
        conn.commit()


def log_discovery_scan(conn: sqlite3.Connection, scan_data: dict, *, commit=True) -> int:
    now = _now_ist()
    cur = conn.execute(
        """
        INSERT INTO discovery_scans (
            timestamp, duration_seconds, total_sources, successful_sources,
            failed_sources, new_events, updated_events, details
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            now,
            float(scan_data.get("duration_seconds", 0.0)),
            int(scan_data.get("total_sources", 0)),
            int(scan_data.get("successful_sources", 0)),
            int(scan_data.get("failed_sources", 0)),
            int(scan_data.get("new_events", 0)),
            int(scan_data.get("updated_events", 0)),
            json.dumps(scan_data.get("details", {})),
        ),
    )
    if commit:
        conn.commit()
    return cur.lastrowid


def get_recent_discovery_scans(conn: sqlite3.Connection, limit: int = 10) -> list:
    rows = conn.execute(
        "SELECT * FROM discovery_scans ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


def get_last_discovery_scan(conn: sqlite3.Connection) -> dict | None:
    row = conn.execute("SELECT * FROM discovery_scans ORDER BY id DESC LIMIT 1").fetchone()
    return dict(row) if row else None


def upsert_events(conn, items, evaluated_map=None, *, commit=True):
    """Upserts full event metadata into the database while preserving existing user states.
    evaluated_map is optional mapping of event_id -> evaluated dict with score, priority, why."""
    now = _now_ist()
    # Fetch active blackout dates for overlap check during upsert
    active_blackouts = get_blackout_dates(conn, enabled_only=True)

    for item in items:
        event_id = item.get("event_id")
        if not event_id:
            continue

        eval_info = (evaluated_map or {}).get(event_id, {})
        priority = eval_info.get("priority") or item.get("priority") or "UNKNOWN"
        score = eval_info.get("score") if eval_info.get("score") is not None else item.get("score", 0)
        why = eval_info.get("why") or item.get("why") or ""
        eligibility = eval_info.get("eligibility") or item.get("eligibility") or "UNKNOWN"
        if item.get("provenance") == "live" and not eval_info.get("eligibility_evidence"):
            eligibility = "UNKNOWN"
        age_restrictions = eval_info.get("age_restrictions") or item.get("age_restrictions") or "None specified"
        norm_url = normalize_url(item.get("url") or "")

        start_date = item.get("event_start")
        end_date = item.get("event_end")

        announcement_url = item.get("announcement_url") or item.get("original_url") or ""
        confidence = item.get("confidence") or "Medium"
        tech_cats = json.dumps(item.get("tech_categories") or [])
        verification_status = item.get("verification_status") or "unverified"

        incoming_source_entry = {
            "source": item.get("source") or "Unknown",
            "url": norm_url,
            "announcement_url": announcement_url,
            "discovered_at": now,
        }

        existing_row = conn.execute(
            "SELECT discovery_sources, announcement_url, url FROM events WHERE event_id = ?",
            (event_id,),
        ).fetchone()

        merged_sources = list(item.get("discovery_sources") or [incoming_source_entry])
        if existing_row:
            previous = json.loads(existing_row["discovery_sources"] or "[]")
            seen = {(entry.get("source") or entry.get("source_name"), entry.get("url"), entry.get("announcement_url")): entry
                    for entry in merged_sources}
            for entry in previous:
                key = (entry.get("source") or entry.get("source_name"), entry.get("url"), entry.get("announcement_url"))
                if key in seen:
                    first = entry.get("first_observed_at") or entry.get("discovered_at")
                    if first:
                        seen[key]["first_observed_at"] = first
                else:
                    seen[key] = entry
                    merged_sources.append(entry)
            if not announcement_url and existing_row["announcement_url"]:
                announcement_url = existing_row["announcement_url"]

        discovery_sources_str = json.dumps(merged_sources)

        is_conflict, conflicts, date_status, summary = check_event_date_overlap(start_date, end_date, active_blackouts)
        blackout_conflict = 1 if is_conflict else 0
        conflict_details = json.dumps(conflicts)

        if is_conflict:
            priority = "CONFLICT (UNAVAILABLE)"
            clean_why = re.sub(
                r"(?:Unavailable \(Blackout Conflict\)|⚠️ Blackout Conflict[^\|]*|Overlaps with [^\|]*)(?:\s*\|\s*)?",
                "",
                why,
                flags=re.IGNORECASE,
            ).strip(" |")
            why = f"Unavailable (Blackout Conflict) | {summary}" + (f" | {clean_why}" if clean_why else "")

        conn.execute(
            """
            INSERT INTO events (
                event_id, title, url, host, source, summary, category,
                location, mode, event_start, event_end, registration_deadline,
                team_size, eligibility, age_restrictions, prize, priority,
                score, why, state, blackout_conflict, conflict_details, date_status,
                announcement_url, discovery_sources, confidence, tech_categories,
                verification_status, first_seen, last_verified, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'seen', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_id) DO UPDATE SET
                title                 = excluded.title,
                url                   = excluded.url,
                host                  = excluded.host,
                source                = excluded.source,
                summary               = COALESCE(excluded.summary, events.summary),
                category              = COALESCE(excluded.category, events.category),
                location              = excluded.location,
                mode                  = excluded.mode,
                event_start           = COALESCE(excluded.event_start, events.event_start),
                event_end             = COALESCE(excluded.event_end, events.event_end),
                registration_deadline = COALESCE(excluded.registration_deadline, events.registration_deadline),
                team_size             = COALESCE(excluded.team_size, events.team_size),
                eligibility           = excluded.eligibility,
                age_restrictions      = excluded.age_restrictions,
                prize                 = COALESCE(excluded.prize, events.prize),
                priority              = excluded.priority,
                score                 = excluded.score,
                why                   = excluded.why,
                blackout_conflict     = excluded.blackout_conflict,
                conflict_details      = excluded.conflict_details,
                date_status           = excluded.date_status,
                announcement_url      = COALESCE(excluded.announcement_url, events.announcement_url),
                discovery_sources     = excluded.discovery_sources,
                confidence            = excluded.confidence,
                tech_categories       = excluded.tech_categories,
                verification_status   = excluded.verification_status,
                last_verified         = COALESCE(excluded.last_verified, events.last_verified),
                updated_at            = excluded.updated_at
            """,
            (
                event_id,
                item.get("title") or "Unknown",
                norm_url,
                item.get("host"),
                item.get("source"),
                item.get("summary") or "",
                item.get("category") or "Hackathon",
                item.get("location") or "Unknown",
                item.get("mode") or "unknown",
                start_date,
                end_date,
                item.get("registration_deadline"),
                item.get("team_size"),
                eligibility,
                age_restrictions,
                item.get("prize") or "",
                priority,
                score,
                why,
                blackout_conflict,
                conflict_details,
                date_status,
                announcement_url,
                discovery_sources_str,
                confidence,
                tech_cats,
                verification_status,
                now,
                now if item.get("provenance") == "live" and verification_status == "verified" else None,
                now,
            ),
        )
        conn.execute(
            """UPDATE events SET provenance = ?, registration_status = ?, scoring = ?,
            eligibility_evidence = ?, eligibility_rules = ?, date_source = ?,
            slug = COALESCE(slug, ?), last_observed = ?,
            registration_url = COALESCE(?, registration_url), country = COALESCE(?, country),
            image_url = COALESCE(?, image_url), prize_amount = COALESCE(?, prize_amount),
            prize_currency = COALESCE(?, prize_currency), participation_fee = COALESCE(?, participation_fee),
            restrictions = COALESCE(?, restrictions) WHERE event_id = ?""",
            (item.get("provenance", "legacy"), item.get("registration_status"),
             json.dumps(eval_info.get("scoring", {})), eval_info.get("eligibility_evidence"), item.get("eligibility_rules") if isinstance(item.get("eligibility_rules"), str) else None,
             "listing" if item.get("provenance") == "live" and start_date else None,
             personal_tracker.event_slug(item.get("title") or "Hackathon", event_id),
             now if item.get("provenance") == "live" else None,
             item.get("registration_url"), item.get("country"), item.get("image_url"),
             item.get("prize_amount"), item.get("prize_currency"), item.get("participation_fee"),
             json.dumps(item["restrictions"]) if "restrictions" in item else None, event_id),
        )
    if commit:
        conn.commit()


def upsert_seen(conn, items):
    """Backwards-compatible seen upsert."""
    eval_map = {}
    for it in items:
        eid = it.get("event_id")
        if eid:
            eval_map[eid] = {
                "priority": it.get("priority", "HIGH PRIORITY"),
                "score": it.get("score", 70),
                "why": it.get("why", ""),
                "eligibility": it.get("eligibility", "ELIGIBLE"),
                "age_restrictions": it.get("age_restrictions", "Open"),
            }
    upsert_events(conn, items, eval_map)


def log_action(conn, event_id, action, result):
    conn.execute(
        "INSERT INTO action_log (event_id, action, result, occurred_at) VALUES (?, ?, ?, ?)",
        (event_id, action, result, _now_ist()),
    )
    conn.commit()


def apply_action(conn, action, event_id):
    """Applies a track/applied/reject action to an existing row.
    Returns (result, row) where result is 'ok', 'noop', or 'unknown_event'."""
    now = _now_ist()
    if action not in ACTION_TO_STATE:
        return "noop", None

    target_state = ACTION_TO_STATE[action]
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")
    row = conn.execute("SELECT * FROM events WHERE event_id = ?", (event_id,)).fetchone()

    if row is None:
        log_action(conn, event_id, action, "unknown_event")
        return "unknown_event", None

    current_rank = STATE_RANK.get(row["state"], 0)
    target_rank = STATE_RANK.get(target_state, 0)
    if row["state"] == target_state or (action != "reject" and current_rank >= target_rank):
        log_action(conn, event_id, action, "noop")
        return "noop", row

    status = {"track": "interested", "applied": "registered", "reject": "not_for_me"}[action]
    personal_tracker.save_entry(conn, event_id, status, None, now)
    log_action(conn, event_id, action, "ok")
    updated_row = conn.execute("SELECT * FROM events WHERE event_id = ?", (event_id,)).fetchone()
    return "ok", updated_row


def get_tracked_open(conn, today_str):
    return conn.execute(
        """
        SELECT * FROM events
        WHERE state = 'tracked'
          AND (COALESCE(event_end, event_start) IS NULL
               OR COALESCE(event_end, event_start) >= ?)
        ORDER BY COALESCE(event_start, '9999-12-31')
        """,
        (today_str,),
    ).fetchall()


def get_applied_open(conn, today_str):
    return conn.execute(
        """
        SELECT * FROM events
        WHERE state = 'applied'
          AND (event_end IS NULL OR event_end >= ?)
        ORDER BY COALESCE(event_start, '9999-12-31')
        """,
        (today_str,),
    ).fetchall()


def get_all_events(conn, min_date=None, include_conflicts=True):
    query = "SELECT * FROM events WHERE 1=1"
    params = []
    if min_date:
        query += " AND COALESCE(event_start, event_end, '9999-12-31') >= ?"
        params.append(min_date)
    if not include_conflicts:
        query += " AND blackout_conflict = 0"
    query += " ORDER BY score DESC, updated_at DESC"
    return conn.execute(query, params).fetchall()


def get_events_by_filter(
    conn,
    priority=None,
    state=None,
    eligibility=None,
    search=None,
    limit=200,
    min_date=None,
    blackout_conflict=None,
    date_status=None,
    mode=None,
    location_keyword=None,
    category=None,
    order_by=None,
):
    query = "SELECT * FROM events WHERE 1=1"
    params = []
    if min_date:
        query += " AND COALESCE(event_start, event_end, '9999-12-31') >= ?"
        params.append(min_date)
    if priority:
        query += " AND priority = ?"
        params.append(priority)
    if state:
        query += " AND state = ?"
        params.append(state)
    if eligibility:
        query += " AND eligibility = ?"
        params.append(eligibility)
    if blackout_conflict is not None:
        query += " AND blackout_conflict = ?"
        params.append(int(blackout_conflict))
    if date_status:
        query += " AND date_status = ?"
        params.append(date_status)
    if mode:
        query += " AND LOWER(mode) = ?"
        params.append(mode.lower())
    if category:
        query += " AND LOWER(category) = ?"
        params.append(category.lower())
    if location_keyword:
        query += " AND (LOWER(location) LIKE ? OR LOWER(title) LIKE ? OR LOWER(summary) LIKE ?)"
        lk = f"%{location_keyword.lower()}%"
        params.extend([lk, lk, lk])
    if search:
        query += " AND (title LIKE ? OR host LIKE ? OR summary LIKE ? OR why LIKE ? OR location LIKE ?)"
        s = f"%{search}%"
        params.extend([s, s, s, s, s])

    # Sorting
    if order_by == "date":
        query += " ORDER BY COALESCE(event_start, '9999-12-31') ASC, score DESC"
    elif order_by == "deadline":
        query += " ORDER BY COALESCE(registration_deadline, event_start, '9999-12-31') ASC, score DESC"
    elif order_by == "recent":
        query += " ORDER BY first_seen DESC, updated_at DESC"
    elif order_by == "score":
        query += " ORDER BY score DESC, COALESCE(event_start, '9999-12-31') ASC"
    else:
        query += " ORDER BY score DESC, COALESCE(event_start, '9999-12-31') ASC"

    query += " LIMIT ?"
    params.append(limit)
    return conn.execute(query, params).fetchall()


def delete_events_before_date(conn, cutoff_date: str) -> int:
    """Deletes events starting before cutoff_date (YYYY-MM-DD) and their associated action logs."""
    with conn:
        conn.execute(
            """
            DELETE FROM action_log
            WHERE event_id IN (
                SELECT event_id FROM events
                WHERE COALESCE(event_start, event_end) < ?
                AND event_id NOT IN (SELECT event_id FROM personal_tracker)
            )
            """,
            (cutoff_date,),
        )
        cur = conn.execute(
            "DELETE FROM events WHERE event_id NOT IN (SELECT event_id FROM personal_tracker) AND COALESCE(event_start, event_end) < ?",
            (cutoff_date,),
        )
        return cur.rowcount


def get_upcoming_deadlines(conn, limit=10, min_date=None, exclude_conflicts=True):
    today = _datetime.now(IST).strftime("%Y-%m-%d")
    effective_min = max(today, min_date) if min_date else today
    query = """
        SELECT * FROM events
        WHERE (registration_deadline >= ? OR event_start >= ?)
          AND state != 'rejected'
    """
    params = [effective_min, effective_min]
    if exclude_conflicts:
        query += " AND blackout_conflict = 0"
    query += """
        ORDER BY COALESCE(registration_deadline, event_start) ASC
        LIMIT ?
    """
    params.append(limit)
    return conn.execute(query, params).fetchall()


def is_bengaluru_listing(row):
    return str(row["mode"] or "").lower() != "online" and bool(re.search(
        r"\b(bengaluru|bangalore|koramangala|indiranagar|whitefield|electronic city|hebbal)\b",
        row["location"] or "", re.I,
    ))


def dashboard_views(conn):
    from buildathon_radar.discovery.integrity import lifecycle

    today = _datetime.now(IST).date()
    date_text = today.isoformat()
    cutoff = (today + timedelta(days=7)).isoformat()
    rows = [dict(row) for row in conn.execute(
        """SELECT events.*, (SELECT status FROM personal_tracker WHERE user_id='local'
            AND personal_tracker.event_id=events.event_id) AS tracker_status
           FROM events ORDER BY score DESC, event_start, event_id"""
    )]
    views = {key: [] for key in ("discover", "open", "upcoming", "unverified", "history", "eligible", "bengaluru",
                                "closing_soon", "high", "free_weekend", "excluded", "tracked", "applied", "discard")}
    for row in rows:
        status = row["lifecycle"] = lifecycle(row, date_text)
        if row["state"] == "rejected":
            views["discard"].append(row)
            continue
        if row["state"] in {"tracked", "applied"}:
            views[row["state"]].append(row)
        upcoming = bool(row["event_start"] and row["event_start"] >= date_text)
        if status in {"Unverified history", "Completed", "Registration closed"}:
            views["history"].append(row)
            if status != "Registration closed" or not upcoming:
                continue
        views["discover"].append(row)
        if row["blackout_conflict"]:
            views["excluded"].append(row)
        if upcoming:
            views["upcoming"].append(row)
        if (not row["event_start"] or row["eligibility"] == "UNKNOWN"
                or row["registration_status"] is None):
            views["unverified"].append(row)
        if is_bengaluru_listing(row):
            views["bengaluru"].append(row)
        deadline = row["registration_deadline"]
        if status != "Registration closed" and deadline and date_text <= deadline <= cutoff:
            views["closing_soon"].append(row)
        if row["eligibility"] == "ELIGIBLE" and row["eligibility_evidence"]:
            views["eligible"].append(row)
            if row["priority"] == "HIGH PRIORITY" and status != "Registration closed":
                views["high"].append(row)
        if "Free & Weekend" in (row["why"] or "") and status != "Registration closed":
            views["free_weekend"].append(row)
        if (status == "Registration open" and not row["blackout_conflict"]
                and row["eligibility"] != "INELIGIBLE"):
            views["open"].append(row)
    views["closing_soon"].sort(key=lambda row: row["registration_deadline"])
    views["discover"].sort(key=lambda row: (
        bool(row["blackout_conflict"]), row["eligibility"] == "INELIGIBLE", not row["event_start"],
    ))
    views["discard"].sort(key=lambda row: row["rejected_at"] or "", reverse=True)
    return views


def get_dashboard_stats(conn, views=None):
    from buildathon_radar.rule_engine import load_profile

    if views is None:
        views = dashboard_views(conn)
    profile = load_profile().get("user_preferences", {})
    local_ids = {row["event_id"] for row in views["bengaluru"]}
    candidates = [
        row for row in views["eligible"] if row["event_start"] and row in views["open"]
        and (not profile.get("only_in_person") or row["mode"] in {"in-person", "offline"})
        and (not profile.get("target_city_only") or row["event_id"] in local_ids)
    ]
    candidates.sort(key=lambda row: (row["event_start"], -int(row["score"] or 0)))
    latest_scan = get_last_discovery_scan(conn)
    scan_id = latest_scan["id"] if latest_scan else None
    last_success = conn.execute("SELECT MAX(last_success_at) FROM discovery_sources").fetchone()[0]
    stale = not last_success or (_datetime.now(IST) - _datetime.fromisoformat(last_success)) > timedelta(hours=48)
    return {
        "last_scan_id": scan_id,
        "scan_failures": latest_scan["failed_sources"] if latest_scan else 0,
        "last_success_at": last_success,
        "stale": stale,
        "discard_count": len(views["discard"]),
        "discovered_count": len(views["discover"]),
        "total_upcoming": len(views["open"]),
        "upcoming_count": len(views["upcoming"]),
        "eligible_count": len(views["eligible"]),
        "blackout_excluded_count": len(views["excluded"]),
        "unverified_count": len(views["unverified"]),
        "bangalore_count": len(views["bengaluru"]),
        "closing_soon_count": len(views["closing_soon"]),
        "tracked_count": len(views["tracked"]),
        "applied_count": len(views["applied"]),
        "next_eligible_event": candidates[0] if candidates else None,
        "recently_discovered": sorted(views["upcoming"], key=lambda row: row["first_seen"] or "", reverse=True)[:5],
    }


def get_secret():
    """Retrieves or generates a secure TRACKER_SECRET without requiring manual setup."""
    sec = os.getenv("TRACKER_SECRET")
    if not sec:
        sec = secrets.token_hex(32)
        os.environ["TRACKER_SECRET"] = sec
    return sec


def sign_action(action, event_id, secret=None):
    key = os.getenv("TRACKER_SECRET") if secret is None else secret
    if not key:
        return None
    message = f"{action}:{event_id}".encode()
    return hmac.new(key.encode(), message, hashlib.sha256).hexdigest()[:20]


def verify_action(action, event_id, token, secret=None):
    if not isinstance(token, str) or not re.fullmatch(r"[0-9a-f]{20}", token):
        return False
    expected = sign_action(action, event_id, secret=secret)
    if expected is None:
        return False
    return hmac.compare_digest(expected, token)
