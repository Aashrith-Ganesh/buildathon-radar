import fcntl
import socket

import pytest
from fastapi.testclient import TestClient

from buildathon_radar import event_images, tracker_service, tracker_store
from buildathon_radar.discovery import engine
from buildathon_radar.discovery.enrichment import enrich, normalize

EVENT = {
    "event_id": "retained-robotics", "title": "Robotics & AI Hackathon",
    "url": "https://example.test/robotics", "location": "Bengaluru",
    "mode": "in-person", "event_start": "2020-01-01", "provenance": "live",
}
ORIGIN = "http://127.0.0.1:8015"


@pytest.fixture
def saved_event(tmp_path, monkeypatch):
    path = tmp_path / "tracker.db"
    monkeypatch.setattr(tracker_service, "DB_PATH", str(path))
    conn = tracker_store.connect(path)
    tracker_store.upsert_events(conn, [EVENT])
    slug = conn.execute("SELECT slug FROM events").fetchone()[0]
    conn.close()
    return path, slug


def test_tracker_status_history_notes_restart_and_expiry(saved_event, local_client):
    path, slug = saved_event
    client = local_client(tracker_service.app)
    api = "/api/tracker/retained-robotics"
    assert client.put(api, json={"status": "interested"}).status_code == 200
    assert client.put(api, json={"status": "submitted", "notes": "<script>abc</script>"}).status_code == 200
    assert client.put(api, json={"status": "invalid"}).status_code == 422
    assert client.put(api, json={"notes": "a" * 4001}).status_code == 422
    assert client.put("/api/tracker/missing", json={"status": "won"}).status_code == 404
    restarted = local_client(tracker_service.app)
    response = restarted.get("/tracker", params={"status": "submitted", "after": "2019-01-01", "before": "2020-12-31"})
    assert "Status changed" in response.text
    assert "Note updated" in response.text
    assert "Added to tracker" in response.text
    assert "&lt;script&gt;abc&lt;/script&gt;" in response.text
    assert "Robotics &amp; AI Hackathon" not in restarted.get("/dashboard").text
    assert restarted.get("/api/tracker").json()[0]["tracker_status"] == "submitted"
    with tracker_store.connect(path) as conn:
        assert tracker_store.delete_events_before_date(conn, "2021-01-01") == 0
    assert restarted.get("/h/" + slug).status_code == 200


def test_event_slug_metadata_placeholder_and_stability(saved_event, local_client):
    path, slug = saved_event
    client = local_client(tracker_service.app)
    page = client.get("/h/" + slug)
    assert page.status_code == 200
    assert f'rel="canonical" href="{ORIGIN}/h/{slug}"' in page.text
    assert 'property="og:image"' in page.text and 'id="nativeShare"' in page.text
    assert 'type="application/ld+json"' in page.text
    assert "Last independently verified: Unknown" in page.text
    assert client.get("/h/missing").status_code == 404
    assert client.get("/h/INVALID").status_code == 404
    assert client.get("/event-image/" + slug).content.startswith(b"\x89PNG")
    with tracker_store.connect(path) as conn:
        tracker_store.upsert_events(conn, [dict(EVENT, title="Renamed Robotics")])
    assert client.get("/h/" + slug).status_code == 200
    assert "Renamed Robotics" in client.get("/h/" + slug).text


def test_tracker_unlock_and_cross_origin(saved_event, monkeypatch):
    monkeypatch.setenv("TRACKER_SECRET", "fixture-secret")
    client = TestClient(tracker_service.app, base_url=ORIGIN)
    headers = {"X-Radar-Request": "1"}
    assert client.get("/api/tracker").status_code == 401
    assert client.put("/api/tracker/retained-robotics", headers=headers, json={"status": "won"}).status_code == 401
    bad = client.post("/api/session", headers=headers, json={"password": "wrong"})
    assert bad.status_code == 401
    unlocked = client.post("/api/session", headers=headers, json={"password": "fixture-secret"})
    assert "HttpOnly" in unlocked.headers["set-cookie"]
    assert "fixture-secret" not in unlocked.headers["set-cookie"]
    assert client.get("/api/tracker").status_code == 200
    assert client.put("/api/tracker/retained-robotics", headers={**headers, "Origin": "https://example.test"},
                      json={"status": "won"}).status_code == 403
    assert client.get("/settings").status_code == 200
    assert client.delete("/api/session", headers=headers).status_code == 200
    assert client.get("/api/tracker").status_code == 401


@pytest.mark.parametrize(("raw", "amount", "currency"), [
    ("₹50,000", "50000", "INR"), ("$1,000 USD", "1000", "USD"), ("€500", "500", "EUR"),
    ("2nd prize", None, None), ("INR 1.5 lakh", "150000.0", "INR"),
])
def test_enrichment_preserves_currency(raw, amount, currency):
    row = enrich(normalize({"title": "Agentic AI Robotics", "prize": raw,
                            "eligibility_rules": "Women only. Students only.", "mode": "offline"}))
    assert row["prize"] == raw
    assert row.get("prize_amount") == amount and row.get("prize_currency") == currency
    assert set(row["tech_categories"]) == {"AI/ML", "Agentic AI", "Robotics"}
    assert row["mode"] == "in-person"
    assert set(row["restrictions"]) == {"student_only", "women_only"}


def test_image_fetch_rejects_unlisted_signed_and_nonpublic_targets(monkeypatch):
    assert event_images.image_target("https://127.0.0.1/private.png") is None
    assert event_images.image_target("https://assets.devfolio.co/image.png?signature=example") is None
    assert event_images.image_target("https://assets.devfolio.co.example.test/image.png") is None
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
    ])
    assert event_images._fetch("https://assets.devfolio.co/image.png") is None


def test_scan_lock_blocks_another_process_lock(saved_event):
    path, _ = saved_event
    with path.with_suffix(".scan.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(engine.ScanInProgress):
            engine.DiscoveryEngine(path).run_scan()


def test_partial_failure_and_empty_scan_preserve_prior_events(saved_event, monkeypatch, local_client):
    path, _ = saved_event
    result_event = dict(EVENT, title="Different organizer hackathon", url="https://example.test/another")
    scanner = engine.DiscoveryEngine(path)
    monkeypatch.setattr(scanner, "_execute_adapter", lambda key, adapter: (key, [result_event], "Page 2 timeout", .5))
    partial = scanner.run_scan(source_keys=["devpost"])["source_stats"]["devpost"]
    assert partial["status"] == "degraded" and partial["events"] == 1
    monkeypatch.setattr(scanner, "_execute_adapter", lambda key, adapter: (key, [], None, .1))
    empty = scanner.run_scan(source_keys=["devpost"])["source_stats"]["devpost"]
    assert empty["status"] == "ok" and empty["outcome"] == "empty"
    monkeypatch.setattr(scanner, "_execute_adapter", lambda key, adapter: (key, [], "Timeout", .1))
    failure = scanner.run_scan(source_keys=["devpost"])["source_stats"]["devpost"]
    assert failure["status"] == "failed"
    with tracker_store.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 2
    page = local_client(tracker_service.app).get("/sources?health=failed")
    assert "FAILED" in page.text and "Page 2 timeout" in page.text


def test_image_cache_rejects_redirects_and_oversized_bodies(monkeypatch):
    from io import BytesIO

    class Remote:
        def __init__(self, status, data, kind):
            self.status = status
            self.data = BytesIO(data)
            self.kind = kind

        def read1(self, size):
            return self.data.read(size)

        def getheader(self, name, default=None):
            return self.kind if name == "Content-Type" else default

    class Connection:
        responses = iter([
            Remote(302, b"", "image/png"),
            Remote(200, b"\x89PNG\r\n\x1a\n" + b"x" * event_images.MAX_BYTES, "image/png"),
            Remote(200, b"ignored", "image/svg+xml"),
            Remote(200, b"\x89PNG\r\n\x1a\n" + b"x", "image/png"),
        ])
        calls = 0

        def __init__(self, *args, **kwargs):
            self._create_connection = None

        def request(self, *args, **kwargs):
            type(self).calls += 1

        def getresponse(self):
            return next(self.responses)

        def close(self):
            pass

    monkeypatch.setattr(event_images.socket, "getaddrinfo", lambda *args, **kwargs: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.1.1.1", 443)),
    ])
    monkeypatch.setattr(event_images.http.client, "HTTPSConnection", Connection)
    url = "https://assets.devfolio.co/thumb-test.png"
    assert event_images._fetch(url) is None
    assert event_images._fetch(url) is None
    assert event_images._fetch(url) is None
    assert event_images.thumbnail(url) == event_images.thumbnail(url) == ("image/png", b"\x89PNG\r\n\x1a\nx")
    assert Connection.calls == 4
    event_images._cached_thumbnail.cache_clear()


def test_v1_migration_backfills_stable_slug_and_tracker_entry(tmp_path):
    import sqlite3

    path = tmp_path / "prior.db"
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(tracker_store.SCHEMA)
    tracker_store._migrate_schema_if_needed(conn)
    conn.execute("""INSERT INTO events(event_id,title,url,state,first_seen,updated_at,last_verified,provenance,verification_status)
        VALUES ('prior-event','Prior Event','https://example.test/prior','tracked',
                '2025-01-01','2025-01-01','2025-01-01','live','unverified')""")
    dates = [tuple(row) for row in conn.execute("SELECT * FROM blackout_dates ORDER BY id")]
    conn.commit()
    conn.close()
    with tracker_store.connect(path) as migrated:
        assert migrated.execute("PRAGMA user_version").fetchone()[0] == 2
        event = migrated.execute("SELECT * FROM events").fetchone()
        assert event["slug"].startswith("prior-event-")
        assert not event["last_verified"] and event["last_observed"] == "2025-01-01"
        assert migrated.execute("SELECT status FROM personal_tracker").fetchone()[0] == "interested"
        assert [tuple(row) for row in migrated.execute("SELECT * FROM blackout_dates ORDER BY id")] == dates
        assert not migrated.execute("PRAGMA foreign_key_check").fetchall()
