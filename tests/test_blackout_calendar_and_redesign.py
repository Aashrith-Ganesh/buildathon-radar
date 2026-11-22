import json
import pytest
from datetime import datetime
from fastapi.testclient import TestClient

from buildathon_radar import tracker_service, tracker_store, rule_engine


@pytest.fixture
def test_db(tmp_path, monkeypatch):
    db_file = str(tmp_path / "test_tracker.db")
    monkeypatch.setattr(tracker_service, "DB_PATH", db_file)
    conn = tracker_store.connect(db_file)
    conn.close()
    return db_file


@pytest.fixture
def client(test_db):
    return TestClient(tracker_service.app)


class TestInitialBlackoutCalendarPopulation:
    """Verifies all personal commitments, ALLEN JEE test dates, and examination periods are stored."""

    def test_all_initial_blackout_entries_stored(self, test_db):
        conn = tracker_store.connect(test_db)
        blackouts = tracker_store.get_blackout_dates(conn)
        conn.close()

        # 4 Personal + 22 ALLEN JEE + 3 Examination Period = 29 rules
        assert len(blackouts) == 29

        categories = {b["category"] for b in blackouts}
        assert "Personal" in categories
        assert "Academic Test" in categories
        assert "Examination Period" in categories

        # Verify Personal Dates
        personal_dates = [(b["start_date"], b["end_date"]) for b in blackouts if b["category"] == "Personal"]
        assert ("2026-11-15", "2026-11-15") in personal_dates
        assert ("2026-11-26", "2026-11-30") in personal_dates
        assert ("2026-12-06", "2026-12-06") in personal_dates
        assert ("2026-12-10", "2026-12-16") in personal_dates

        # Verify ALLEN JEE Test Dates (2026 & 2027)
        academic_starts = {b["start_date"] for b in blackouts if b["category"] == "Academic Test"}
        expected_tests = [
            "2026-05-06", "2026-06-07", "2026-06-28", "2026-07-05", "2026-07-19",
            "2026-07-26", "2026-08-09", "2026-08-19", "2026-08-30", "2026-09-06",
            "2026-09-20", "2026-09-27", "2026-10-11", "2026-10-18", "2026-11-15",
            "2026-11-29", "2026-12-06", "2026-12-20", "2026-12-27",
            "2027-01-10", "2027-01-17", "2027-01-31"
        ]
        for t in expected_tests:
            assert t in academic_starts, f"Missing ALLEN JEE test date: {t}"

        # Verify Examination Periods (Feb 2027 continuous weeks)
        exam_ranges = [(b["start_date"], b["end_date"]) for b in blackouts if b["category"] == "Examination Period"]
        assert ("2027-02-08", "2027-02-14") in exam_ranges
        assert ("2027-02-15", "2027-02-21") in exam_ranges
        assert ("2027-02-22", "2027-02-28") in exam_ranges


class TestDateOverlapDetection:
    """Verifies exact user requirement examples and edge cases for date overlaps."""

    def test_prompt_explicit_examples(self, test_db):
        conn = tracker_store.connect(test_db)
        blackouts = tracker_store.get_blackout_dates(conn, enabled_only=True)

        examples = [
            ("2026-11-14", "2026-11-16", True, "14-16 November overlaps with 15 Nov blackout"),
            ("2026-11-25", "2026-11-27", True, "25-27 November overlaps with 26-30 Nov blackout"),
            ("2026-12-09", "2026-12-12", True, "9-12 December overlaps with 10-16 Dec blackout"),
            ("2027-02-07", "2027-02-09", True, "7-9 February overlaps with 8-14 Feb exam period"),
            ("2026-11-20", "2026-11-22", False, "20-22 November has no blackout conflict"),
            ("2026-12-01", "2026-12-03", False, "1-3 December has no blackout conflict"),
        ]

        for start, end, expected_conflict, desc in examples:
            is_conflict, conflicts, date_status, summary = tracker_store.check_event_date_overlap(
                start, end, blackouts
            )
            assert is_conflict == expected_conflict, f"Failed for {desc}: got {is_conflict}, expected {expected_conflict}"
            if expected_conflict:
                assert len(conflicts) > 0
                assert "Blackout Conflict" in summary

        conn.close()

    def test_event_spanning_multiple_blackout_dates(self, test_db):
        conn = tracker_store.connect(test_db)
        blackouts = tracker_store.get_blackout_dates(conn, enabled_only=True)

        # Event spanning Nov 25 to Dec 1:
        # Overlaps with Nov 26-30 personal blackout AND Nov 29 Major Internal Test 2
        is_conflict, conflicts, date_status, summary = tracker_store.check_event_date_overlap(
            "2026-11-25", "2026-12-01", blackouts
        )
        assert is_conflict is True
        assert len(conflicts) >= 2
        categories = {c["category"] for c in conflicts}
        assert "Personal" in categories
        assert "Academic Test" in categories
        conn.close()

    def test_month_and_year_boundary_handling(self, test_db):
        conn = tracker_store.connect(test_db)
        blackouts = tracker_store.get_blackout_dates(conn, enabled_only=True)

        # Month boundary: Nov 30 to Dec 01
        is_conflict, conflicts, _, _ = tracker_store.check_event_date_overlap(
            "2026-11-30", "2026-12-01", blackouts
        )
        assert is_conflict is True
        assert conflicts[0]["overlap_dates"] == "2026-11-30"

        # Year boundary: Dec 31, 2026 to Jan 02, 2027 (clean, tests in Jan are on 10th)
        is_conflict, _, _, _ = tracker_store.check_event_date_overlap(
            "2026-12-31", "2027-01-02", blackouts
        )
        assert is_conflict is False

        # Event spanning into Jan 10 test: Jan 09 to Jan 11, 2027
        is_conflict, conflicts, _, _ = tracker_store.check_event_date_overlap(
            "2027-01-09", "2027-01-11", blackouts
        )
        assert is_conflict is True
        assert any(c["title"] == "Internal Test 9" for c in conflicts)
        conn.close()

    def test_missing_and_uncertain_dates_handling(self, test_db):
        conn = tracker_store.connect(test_db)
        blackouts = tracker_store.get_blackout_dates(conn, enabled_only=True)

        # Missing start date -> date_status = 'uncertain', never silently marked eligible
        is_conflict, conflicts, date_status, summary = tracker_store.check_event_date_overlap(
            None, None, blackouts
        )
        assert is_conflict is False
        assert date_status == "uncertain"
        assert "Dates Unverified" in summary
        conn.close()


class TestBlackoutCalendarCRUDAndRecalculation:
    """Verifies adding, updating, disabling, and deleting blackout rules triggers automatic recalculation."""

    def test_toggle_and_recalculate(self, test_db):
        conn = tracker_store.connect(test_db)

        # Insert an event that only conflicts with Nov 26-30 Personal Blackout
        tracker_store.upsert_events(conn, [{
            "event_id": "test-event-nov27",
            "title": "Nov 27 Test Event",
            "url": "https://example.com/nov27",
            "event_start": "2026-11-27",
            "event_end": "2026-11-27",
            "score": 85,
            "eligibility": "ELIGIBLE",
        }])

        row = conn.execute("SELECT * FROM events WHERE event_id = 'test-event-nov27'").fetchone()
        assert row["blackout_conflict"] == 1
        assert row["priority"] == "CONFLICT (UNAVAILABLE)"

        # Find the blackout rule for 26-30 Nov
        b = conn.execute("SELECT * FROM blackout_dates WHERE start_date = '2026-11-26'").fetchone()
        assert b is not None

        # Disable this blackout rule
        tracker_store.toggle_blackout_date(conn, b["id"])

        # Row must now be automatically recomputed to clean / non-conflicted!
        row_after = conn.execute("SELECT * FROM events WHERE event_id = 'test-event-nov27'").fetchone()
        assert row_after["blackout_conflict"] == 0
        assert row_after["priority"] == "HIGH PRIORITY"

        # Re-enable the blackout rule
        tracker_store.toggle_blackout_date(conn, b["id"])
        row_re_enabled = conn.execute("SELECT * FROM events WHERE event_id = 'test-event-nov27'").fetchone()
        assert row_re_enabled["blackout_conflict"] == 1
        assert row_re_enabled["priority"] == "CONFLICT (UNAVAILABLE)"

        conn.close()

    def test_add_and_delete_blackout_range(self, test_db):
        conn = tracker_store.connect(test_db)

        # Event on Jan 22, 2027 (initially clean)
        tracker_store.upsert_events(conn, [{
            "event_id": "clean-jan-event",
            "title": "Clean Jan Event",
            "url": "https://example.com/jan",
            "event_start": "2027-01-22",
            "event_end": "2027-01-24",
            "score": 80,
            "eligibility": "ELIGIBLE",
        }])

        row = conn.execute("SELECT * FROM events WHERE event_id = 'clean-jan-event'").fetchone()
        assert row["blackout_conflict"] == 0

        # Add a custom continuous blackout range covering Jan 20 to Jan 25
        new_id = tracker_store.add_blackout_date(
            conn,
            title="School Annual Day Prep",
            start_date="2027-01-20",
            end_date="2027-01-25",
            category="Personal",
            reason="Mandatory school attendance",
            enabled=1,
        )

        row_after_add = conn.execute("SELECT * FROM events WHERE event_id = 'clean-jan-event'").fetchone()
        assert row_after_add["blackout_conflict"] == 1
        assert "School Annual Day Prep" in row_after_add["why"]

        # Delete the blackout rule
        tracker_store.delete_blackout_date(conn, new_id)
        row_after_del = conn.execute("SELECT * FROM events WHERE event_id = 'clean-jan-event'").fetchone()
        assert row_after_del["blackout_conflict"] == 0
        conn.close()


class TestDashboardStatsAndExcludedView:
    """Verifies dashboard metrics accurately reflect eligible vs excluded hackathons."""

    def test_dashboard_stats_and_routes(self, client, test_db):
        conn = tracker_store.connect(test_db)
        tracker_store.upsert_events(conn, [
            {
                "event_id": "ev-eligible",
                "title": "Bangalore AI Hackathon",
                "url": "https://example.com/blr-ai",
                "location": "Bengaluru, Karnataka",
                "mode": "in-person",
                "event_start": "2026-12-01",
                "event_end": "2026-12-02",
                "eligibility": "ELIGIBLE",
                "score": 90,
            },
            {
                "event_id": "ev-conflicted",
                "title": "Conflict Hackathon on Test Day",
                "url": "https://example.com/conflict",
                "location": "Bengaluru, Karnataka",
                "mode": "in-person",
                "event_start": "2026-11-29",
                "event_end": "2026-11-29",
                "eligibility": "ELIGIBLE",
                "score": 85,
            },
        ])
        conn.close()

        # Check API stats
        resp = client.get("/api/dashboard-stats")
        assert resp.status_code == 200
        stats = resp.json()
        assert stats["eligible_count"] >= 1
        assert stats["blackout_excluded_count"] >= 1
        assert stats["next_eligible_event"] is not None
        assert stats["next_eligible_event"]["event_id"] == "ev-eligible"

        # Check Excluded Events page view
        resp_excluded = client.get("/dashboard?filter=excluded")
        assert resp_excluded.status_code == 200
        assert "Conflict Hackathon on Test Day" in resp_excluded.text
        assert "Blackout Conflict" in resp_excluded.text

        # Check Blackout Calendar page view
        resp_cal = client.get("/calendar")
        assert resp_cal.status_code == 200
        assert "Personal Blackout Calendar Management" in resp_cal.text
        assert "Internal Test 1" in resp_cal.text
        assert "Examination Period" in resp_cal.text


class TestRestApis:
    """Verifies REST endpoints for blackout management and AJAX actions."""

    def test_blackout_api_endpoints(self, client):
        # 1. List
        resp = client.get("/api/blackouts")
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 29

        # 2. Create
        create_resp = client.post("/api/blackouts", json={
            "title": "Family Trip",
            "start_date": "2027-03-01",
            "end_date": "2027-03-05",
            "category": "Personal",
            "reason": "Out of station",
            "enabled": True
        })
        assert create_resp.status_code == 200
        new_id = create_resp.json()["id"]

        # 3. Toggle
        toggle_resp = client.post(f"/api/blackouts/{new_id}/toggle")
        assert toggle_resp.status_code == 200

        # 4. Update
        update_resp = client.put(f"/api/blackouts/{new_id}", json={
            "title": "Family Vacation Updated",
            "start_date": "2027-03-01",
            "end_date": "2027-03-06",
            "category": "Personal",
            "reason": "Updated duration",
            "enabled": True
        })
        assert update_resp.status_code == 200

        # 5. Delete
        del_resp = client.delete(f"/api/blackouts/{new_id}")
        assert del_resp.status_code == 200

    def test_ajax_action_endpoint(self, client, test_db):
        conn = tracker_store.connect(test_db)
        tracker_store.upsert_events(conn, [{
            "event_id": "ajax-test-event",
            "title": "AJAX Test Event",
            "url": "https://example.com/ajax",
            "event_start": "2026-12-01",
        }])
        conn.close()

        resp = client.post("/api/action", json={
            "event_id": "ajax-test-event",
            "action": "track"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["state"] == "tracked"
