"""SQLite storage for personal event state and activity."""
import hashlib
import re
import unicodedata

STATUSES = {
    "interested": "Interested", "registered": "Registered", "submitted": "Submitted",
    "won": "Won", "not_for_me": "Not for me",
}
EVENT_STATE = {"interested": "tracked", "registered": "applied", "submitted": "applied",
               "won": "applied", "not_for_me": "rejected"}


def event_slug(title, event_id):
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    stem = re.sub(r"[^a-z0-9]+", "-", ascii_title.lower()).strip("-")[:64].rstrip("-")
    suffix = hashlib.sha256(event_id.encode()).hexdigest()[:12]
    return f"{stem or 'hackathon'}-{suffix}"


def migrate(conn):
    for name in ("slug", "registration_url", "country", "image_url", "prize_amount", "prize_currency",
                 "participation_fee", "last_observed", "restrictions"):
        conn.execute(f"ALTER TABLE events ADD COLUMN {name} TEXT")
    conn.execute("CREATE UNIQUE INDEX events_slug ON events(slug)")
    conn.execute("UPDATE events SET last_observed = last_verified, last_verified = NULL WHERE verification_status != 'verified' OR provenance != 'live'")
    conn.executemany("UPDATE events SET slug = ? WHERE event_id = ?", [
        (event_slug(row["title"], row["event_id"]), row["event_id"])
        for row in conn.execute("SELECT event_id, title FROM events")
    ])
    conn.execute("""CREATE TABLE personal_tracker (
        user_id TEXT NOT NULL,
        event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE RESTRICT,
        status TEXT NOT NULL CHECK(status IN ('interested','registered','submitted','won','not_for_me')),
        notes TEXT NOT NULL DEFAULT '' CHECK(length(notes) <= 4000),
        updated_at TEXT NOT NULL,
        PRIMARY KEY(user_id,event_id)
    )""")
    conn.execute("""CREATE TABLE tracker_activity (
        id INTEGER PRIMARY KEY, user_id TEXT NOT NULL, event_id TEXT NOT NULL,
        action TEXT NOT NULL, status TEXT, occurred_at TEXT NOT NULL,
        FOREIGN KEY(user_id,event_id) REFERENCES personal_tracker(user_id,event_id)
    )""")
    conn.execute("CREATE INDEX tracker_recent ON personal_tracker(user_id, updated_at DESC)")
    conn.execute("CREATE INDEX tracker_activity_event ON tracker_activity(user_id,event_id,id DESC)")
    conn.execute("""INSERT INTO personal_tracker (user_id,event_id,status,updated_at)
        SELECT 'local',event_id,
          CASE state WHEN 'tracked' THEN 'interested' WHEN 'rejected' THEN 'not_for_me'
            ELSE CASE outcome WHEN 'won' THEN 'won' WHEN 'participated' THEN 'submitted' ELSE 'registered' END END,
          coalesce(rejected_at,applied_at,tracked_at,updated_at)
        FROM events WHERE state IN ('tracked','applied','rejected')""")
    conn.execute("""INSERT INTO tracker_activity(user_id,event_id,action,status,occurred_at)
        SELECT user_id,event_id,'Added to tracker',status,updated_at FROM personal_tracker""")
    conn.execute("PRAGMA user_version = 2")


def get_entry(conn, event_id):
    return conn.execute("SELECT * FROM personal_tracker WHERE user_id='local' AND event_id=?", (event_id,)).fetchone()


def save_entry(conn, event_id, status, notes, now):
    current = get_entry(conn, event_id)
    if status is None:
        status = current["status"] if current else "interested"
    if notes is None:
        notes = current["notes"] if current else ""
    status_changed = current is None or current["status"] != status
    notes_changed = (current["notes"] if current else "") != notes
    if not status_changed and not notes_changed:
        return current
    conn.execute("""INSERT INTO personal_tracker(user_id,event_id,status,notes,updated_at)
        VALUES ('local',?,?,?,?) ON CONFLICT(user_id,event_id) DO UPDATE SET
        status=excluded.status, notes=excluded.notes, updated_at=excluded.updated_at""",
        (event_id, status, notes, now))
    actions = []
    if status_changed:
        actions.append(("Status changed" if current else "Added to tracker", status))
    if notes_changed:
        actions.append(("Note updated", None))
    conn.executemany("""INSERT INTO tracker_activity(user_id,event_id,action,status,occurred_at)
        VALUES ('local',?,?,?,?)""", ((event_id, action, state, now) for action, state in actions))
    if status_changed:
        state = EVENT_STATE[status]
        conn.execute("""UPDATE events SET state=?, updated_at=?,
            tracked_at=CASE WHEN ?='tracked' THEN ? ELSE tracked_at END,
            applied_at=CASE WHEN ?='applied' THEN ? ELSE applied_at END,
            rejected_at=CASE WHEN ?='rejected' THEN ? ELSE rejected_at END
            WHERE event_id=?""", (state, now, state, now, state, now, state, now, event_id))
    return get_entry(conn, event_id)


def entries(conn):
    return conn.execute("""SELECT events.*, personal_tracker.status AS tracker_status,
        personal_tracker.notes, personal_tracker.updated_at AS tracker_updated_at
        FROM personal_tracker JOIN events USING(event_id)
        WHERE user_id='local' ORDER BY tracker_updated_at DESC,event_id""").fetchall()


def activity(conn, event_id):
    return conn.execute("""SELECT action,status,occurred_at FROM tracker_activity
        WHERE user_id='local' AND event_id=? ORDER BY id DESC LIMIT 30""", (event_id,)).fetchall()
