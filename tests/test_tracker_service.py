import pytest

from buildathon_radar import tracker_service, tracker_store


@pytest.fixture
def client(tmp_path, monkeypatch, local_client):
    db_path = str(tmp_path / "tracker.db")
    monkeypatch.setattr(tracker_service, "DB_PATH", db_path)
    conn = tracker_store.connect(db_path)
    tracker_store.upsert_seen(conn, [
        {
            "event_id": "e1",
            "title": "Build with Gemma",
            "url": "https://build-with-gemma.devfolio.co/",
            "host": "IEEE",
            "source": "Devfolio",
            "event_start": "2026-08-01",
            "event_end": "2026-08-02",
        }
    ])
    conn.close()
    return local_client(tracker_service.app)


def sign(action, event_id):
    return tracker_store.sign_action(action, event_id)


class TestHealth:
    def test_root_health_page(self, client):
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 307
        assert resp.headers["location"] == "/dashboard"


def record(client, action, event_id="e1"):
    return client.post("/api/action", json={
        "action": action, "event_id": event_id, "token": sign(action, event_id),
    })


class TestTrackEndpoint:
    def test_valid_click_writes_state_and_returns_200(self, client, tmp_path):
        token = sign("track", "e1")
        resp = client.get(f"/track?event_id=e1&t={token}")
        assert resp.status_code == 200
        assert "Build with Gemma" in resp.text
        before = tracker_store.connect(str(tmp_path / "tracker.db"))
        assert before.execute("SELECT state FROM events WHERE event_id='e1'").fetchone()[0] == "seen"
        before.close()
        assert record(client, "track").json()["state"] == "tracked"

        conn = tracker_store.connect(str(tmp_path / "tracker.db"))
        row = conn.execute("SELECT * FROM events WHERE event_id='e1'").fetchone()
        assert row["state"] == "tracked"
        assert row["tracked_at"] is not None
        log = conn.execute("SELECT * FROM action_log WHERE event_id='e1'").fetchall()
        assert len(log) == 1
        assert log[0]["result"] == "ok"

    def test_repeat_click_is_noop_page_and_only_logs(self, client, tmp_path):
        record(client, "track")
        resp = record(client, "track")
        assert resp.status_code == 200
        assert resp.json()["result"] == "noop"

        conn = tracker_store.connect(str(tmp_path / "tracker.db"))
        log = conn.execute("SELECT * FROM action_log WHERE event_id='e1'").fetchall()
        assert len(log) == 2
        assert log[1]["result"] == "noop"

    def test_unknown_event_id_returns_404(self, client):
        token = sign("track", "does-not-exist")
        resp = client.get(f"/track?event_id=does-not-exist&t={token}")
        assert resp.status_code == 404
        assert "Event not found" in resp.text

    def test_bad_token_returns_403_with_no_db_write(self, client, tmp_path):
        resp = client.get("/track?event_id=e1&t=wrongtoken000000000")
        assert resp.status_code == 403
        assert "Invalid link" in resp.text

        conn = tracker_store.connect(str(tmp_path / "tracker.db"))
        row = conn.execute("SELECT * FROM events WHERE event_id='e1'").fetchone()
        assert row["state"] == "seen"  # untouched
        log = conn.execute("SELECT * FROM action_log WHERE event_id='e1'").fetchall()
        assert not log

    def test_missing_token_returns_403(self, client):
        resp = client.get("/track?event_id=e1")
        assert resp.status_code == 403

    def test_missing_event_id_returns_400(self, client):
        resp = client.get("/track")
        assert resp.status_code == 400
        assert "Malformed" in resp.text

    def test_track_click_shows_event_start_date(self, client):
        token = sign("track", "e1")
        resp = client.get(f"/track?event_id=e1&t={token}")
        assert "Aug 01, 2026" in resp.text


class TestAppliedEndpoint:
    def test_valid_applied_click(self, client, tmp_path):
        resp = record(client, "applied")
        assert resp.status_code == 200
        assert resp.json()["state"] == "applied"

        conn = tracker_store.connect(str(tmp_path / "tracker.db"))
        row = conn.execute("SELECT * FROM events WHERE event_id='e1'").fetchone()
        assert row["state"] == "applied"

    def test_track_after_applied_is_noop_no_downgrade(self, client, tmp_path):
        record(client, "applied")
        resp = record(client, "track")
        assert resp.status_code == 200
        assert resp.json()["result"] == "noop"

        conn = tracker_store.connect(str(tmp_path / "tracker.db"))
        row = conn.execute("SELECT * FROM events WHERE event_id='e1'").fetchone()
        assert row["state"] == "applied"  # not downgraded to tracked

    def test_cross_action_token_rejected(self, client):
        track_token = sign("track", "e1")
        resp = client.get(f"/applied?event_id=e1&t={track_token}")
        assert resp.status_code == 403


class TestListEndpoint:
    def test_no_params_or_token_required(self, client):
        resp = client.get("/list")
        assert resp.status_code == 200

    def test_shows_seen_event_by_default(self, client):
        resp = client.get("/list")
        assert "Build with Gemma" in resp.text
        assert "Seen" in resp.text

    def test_empty_store_shows_clear_message(self, tmp_path, monkeypatch, local_client):
        db_path = str(tmp_path / "tracker.db")
        monkeypatch.setattr(tracker_service, "DB_PATH", db_path)
        tracker_store.connect(db_path).close()  # schema only, no rows
        empty_client = local_client(tracker_service.app)
        resp = empty_client.get("/list")
        assert resp.status_code == 200
        assert "Nothing tracked or applied yet" in resp.text

    def test_groups_by_state_with_labels(self, client, tmp_path):
        conn = tracker_store.connect(str(tmp_path / "tracker.db"))
        tracker_store.upsert_seen(conn, [
            {"event_id": "e2", "title": "Applied Event", "url": "https://a.com/",
             "host": "H", "source": "Devpost", "event_start": "2026-08-05", "event_end": None},
        ])
        tracker_store.apply_action(conn, "track", "e1")
        tracker_store.apply_action(conn, "applied", "e2")
        conn.close()

        resp = client.get("/list")
        assert resp.status_code == 200
        assert "Tracked" in resp.text
        assert "Applied" in resp.text
        tracked_pos = resp.text.find("Tracked")
        applied_pos = resp.text.find("Applied")
        gemma_pos = resp.text.find("Build with Gemma")
        applied_event_pos = resp.text.find("Applied Event")
        assert tracked_pos < gemma_pos
        assert applied_pos < applied_event_pos

    def test_read_only_does_not_change_state(self, client, tmp_path):
        conn = tracker_store.connect(str(tmp_path / "tracker.db"))
        before = dict(conn.execute("SELECT * FROM events WHERE event_id='e1'").fetchone())
        conn.close()

        client.get("/list")

        conn = tracker_store.connect(str(tmp_path / "tracker.db"))
        after = dict(conn.execute("SELECT * FROM events WHERE event_id='e1'").fetchone())
        conn.close()
        assert before == after

    def test_title_html_escaped(self, tmp_path, monkeypatch, local_client):
        db_path = str(tmp_path / "tracker.db")
        monkeypatch.setattr(tracker_service, "DB_PATH", db_path)
        conn = tracker_store.connect(db_path)
        tracker_store.upsert_seen(conn, [
            {"event_id": "e3", "title": "<script>alert(1)</script>", "url": "https://x.com/",
             "host": "H", "source": "Devpost", "event_start": None, "event_end": None},
        ])
        conn.close()
        resp = local_client(tracker_service.app).get("/list")
        assert "<script>alert(1)</script>" not in resp.text
        assert "&lt;script&gt;" in resp.text

    def test_event_url_and_dates_rendered(self, client):
        resp = client.get("/list")
        assert 'href="/event/e1"' in resp.text
        assert "Aug 01, 2026" in resp.text
        assert "Aug 02, 2026" in resp.text

    def test_other_endpoints_unaffected_by_list_route(self, client):
        # / health, /track, /applied must behave exactly as before with the
        # new route present.
        health = client.get("/")
        assert health.status_code == 200
        assert "running" in health.text.lower()

        token = sign("track", "e1")
        track_resp = client.get(f"/track?event_id=e1&t={token}")
        assert track_resp.status_code == 200
        assert "Confirm event action" in track_resp.text


class TestPagesAreEscaped:
    def test_title_html_escaped_in_confirmation_page(self, tmp_path, monkeypatch, local_client):
        db_path = str(tmp_path / "tracker.db")
        monkeypatch.setattr(tracker_service, "DB_PATH", db_path)
        conn = tracker_store.connect(db_path)
        tracker_store.upsert_seen(conn, [
            {
                "event_id": "e2",
                "title": "<script>alert(1)</script> & Co",
                "url": "https://example.com/",
                "host": "H",
                "source": "Devpost",
                "event_start": None,
                "event_end": None,
            }
        ])
        conn.close()
        client = local_client(tracker_service.app)
        token = sign("track", "e2")
        resp = client.get(f"/track?event_id=e2&t={token}")
        assert "<script>alert(1)</script>" not in resp.text
        assert "&lt;script&gt;" in resp.text
