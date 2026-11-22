import hashlib
import hmac
import os
import secrets
import sqlite3
from datetime import datetime as _datetime
from datetime import timedelta, timezone
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from dotenv import load_dotenv

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

CREATE INDEX IF NOT EXISTS idx_events_state ON events(state);
CREATE INDEX IF NOT EXISTS idx_events_priority ON events(priority);
CREATE INDEX IF NOT EXISTS idx_events_deadline ON events(registration_deadline);
"""


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

        # Filter out common marketing/tracking parameters
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
    }

    for col_name, col_type in columns_to_add.items():
        if col_name not in existing_columns:
            try:
                conn.execute(f"ALTER TABLE events ADD COLUMN {col_name} {col_type}")
            except sqlite3.OperationalError:
                pass
    conn.commit()


def connect(db_path=None):
    """Opens (creating if needed) the tracker SQLite database in WAL mode."""
    path = db_path or DB_FILE
    conn = sqlite3.connect(path, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.executescript(SCHEMA)
    _migrate_schema_if_needed(conn)
    conn.commit()
    return conn


def upsert_events(conn, items, evaluated_map=None):
    """Upserts full event metadata into the database while preserving existing user states.
    evaluated_map is optional mapping of event_id -> evaluated dict with score, priority, why."""
    now = _now_ist()
    for item in items:
        event_id = item.get("event_id")
        if not event_id:
            continue

        eval_info = (evaluated_map or {}).get(event_id, {})
        priority = eval_info.get("priority") or item.get("priority") or "UNKNOWN"
        score = eval_info.get("score") if eval_info.get("score") is not None else item.get("score", 0)
        why = eval_info.get("why") or item.get("why") or ""
        eligibility = eval_info.get("eligibility") or item.get("eligibility") or "UNKNOWN"
        age_restrictions = eval_info.get("age_restrictions") or item.get("age_restrictions") or "None specified"
        norm_url = normalize_url(item.get("url") or "")

        conn.execute(
            """
            INSERT INTO events (
                event_id, title, url, host, source, summary, category,
                location, mode, event_start, event_end, registration_deadline,
                team_size, eligibility, age_restrictions, prize, priority,
                score, why, state, first_seen, last_verified, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'seen', ?, ?, ?)
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
                last_verified         = excluded.last_verified,
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
                item.get("event_start"),
                item.get("event_end"),
                item.get("registration_deadline"),
                item.get("team_size") or "3-5 preferred",
                eligibility,
                age_restrictions,
                item.get("prize") or "",
                priority,
                score,
                why,
                now,
                now,
                now,
            ),
        )
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
    row = conn.execute("SELECT * FROM events WHERE event_id = ?", (event_id,)).fetchone()

    if row is None:
        log_action(conn, event_id, action, "unknown_event")
        return "unknown_event", None

    # Track rank to prevent accidental downgrade (except explicit reject)
    current_rank = STATE_RANK.get(row["state"], 0)
    target_rank = STATE_RANK.get(target_state, 0)
    if action != "reject" and current_rank >= target_rank:
        log_action(conn, event_id, action, "noop")
        return "noop", row

    ts_column = "tracked_at" if target_state == "tracked" else ("applied_at" if target_state == "applied" else "rejected_at")
    conn.execute(
        f"UPDATE events SET state = ?, {ts_column} = ?, updated_at = ? WHERE event_id = ?",
        (target_state, now, now, event_id),
    )
    conn.commit()
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


def get_all_events(conn, min_date=None):
    if min_date:
        return conn.execute(
            """
            SELECT * FROM events
            WHERE COALESCE(event_start, event_end, '9999-12-31') >= ?
            ORDER BY score DESC, updated_at DESC
            """,
            (min_date,),
        ).fetchall()
    return conn.execute("SELECT * FROM events ORDER BY score DESC, updated_at DESC").fetchall()


def get_events_by_filter(conn, priority=None, state=None, eligibility=None, search=None, limit=100, min_date=None):
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
    if search:
        query += " AND (title LIKE ? OR host LIKE ? OR summary LIKE ? OR why LIKE ?)"
        s = f"%{search}%"
        params.extend([s, s, s, s])

    query += " ORDER BY score DESC, COALESCE(event_start, '9999-12-31') ASC LIMIT ?"
    params.append(limit)
    return conn.execute(query, params).fetchall()


def delete_events_before_date(conn, cutoff_date: str) -> int:
    """Deletes events starting before cutoff_date (YYYY-MM-DD) and their associated action logs.

    Returns the number of events deleted.
    """
    with conn:
        conn.execute(
            """
            DELETE FROM action_log
            WHERE event_id IN (
                SELECT event_id FROM events
                WHERE COALESCE(event_start, event_end) < ?
            )
            """,
            (cutoff_date,),
        )
        cur = conn.execute(
            "DELETE FROM events WHERE COALESCE(event_start, event_end) < ?",
            (cutoff_date,),
        )
        return cur.rowcount


def get_upcoming_deadlines(conn, limit=10, min_date=None):
    today = _datetime.now(IST).strftime("%Y-%m-%d")
    effective_min = max(today, min_date) if min_date else today
    return conn.execute(
        """
        SELECT * FROM events
        WHERE (registration_deadline >= ? OR event_start >= ?)
          AND state != 'rejected'
        ORDER BY COALESCE(registration_deadline, event_start) ASC
        LIMIT ?
        """,
        (effective_min, effective_min, limit),
    ).fetchall()


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
    if not token:
        return False
    expected = sign_action(action, event_id, secret=secret)
    if expected is None:
        return False
    return hmac.compare_digest(expected, token)
