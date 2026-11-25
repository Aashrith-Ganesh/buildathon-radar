import json
import os
import sqlite3
import subprocess
from pathlib import Path
import pytest

from buildathon_radar import analysis, deliver, rule_engine, tracker_service, tracker_store


@pytest.fixture
def temp_db(tmp_path):
    db_path = str(tmp_path / "test_tracker.db")
    conn = tracker_store.connect(db_path)
    conn.close()
    return db_path


class TestStudentRuleEngine:
    def test_class_11_eligible_high_priority(self):
        item = {
            "title": "Bengaluru High School AI Sprint",
            "url": "https://devfolio.co/bengaluru-hs-ai",
            "host": "Bengaluru Tech Foundation",
            "summary": "Build LLM agents and GenAI solutions.",
            "eligibility_rules": "Open to all high school students (Class 11 and Class 12).",
            "location": "Bengaluru, Karnataka",
            "mode": "in-person",
            "themes": ["AI", "GenAI", "Agents"],
            "team_size": "3-5 members",
        }
        res = rule_engine.classify_and_score_event(item)
        assert res["eligibility"] == "ELIGIBLE"
        assert res["priority"] == "HIGH PRIORITY"
        assert res["score"] >= 70
        assert "high school" in res["eligibility_evidence"].lower()
        assert "Bengaluru venue" in res["why"]

    def test_college_hackathon_marked_unknown_not_ineligible(self):
        item = {
            "title": "RVCE Campus AI Hackathon",
            "url": "https://rvce.devfolio.co/ai-hack",
            "host": "RVCE College IEEE Student Branch",
            "summary": "Annual 24hr software buildathon for young builders. Build full-stack and AI apps.",
            "location": "Bengaluru, Karnataka",
            "mode": "in-person",
            "themes": ["AI", "Software"],
            "team_size": "4 members",
        }
        res = rule_engine.classify_and_score_event(item)
        assert res["eligibility"] == "UNKNOWN"
        assert res["score"] > 0
        assert res["priority"] != "HIGH PRIORITY"
        assert "verification" in res["why"].lower()

    def test_explicit_18_plus_excluded_as_ineligible(self):
        item = {
            "title": "Corporate Adult AI Challenge",
            "url": "https://devpost.com/corporate-challenge",
            "host": "MegaCorp",
            "summary": "Enterprise solutions. Must be at least 18 years old to participate. 18+ only.",
            "location": "Bengaluru",
            "mode": "in-person",
            "themes": ["AI"],
        }
        res = rule_engine.classify_and_score_event(item)
        assert res["eligibility"] == "INELIGIBLE"
        assert res["priority"] == "INELIGIBLE"
        assert res["score"] > 0

    def test_university_students_only_excluded(self):
        item = {
            "title": "Undergrad Inter-Collegiate Cup",
            "url": "https://devfolio.co/undergrad-cup",
            "host": "University",
            "summary": "University students only. Must be currently enrolled undergraduate.",
            "location": "Online",
            "mode": "online",
            "themes": ["AI"],
        }
        res = rule_engine.classify_and_score_event(item)
        assert res["eligibility"] == "INELIGIBLE"
        assert res["priority"] == "INELIGIBLE"

    def test_global_online_hackathon_scoring(self):
        item = {
            "title": "Global Agentic AI Hackathon",
            "url": "https://devpost.com/global-agentic-ai",
            "host": "OpenAI / Anthropic Partner",
            "summary": "Build intelligent multi-agent systems.",
            "eligibility_rules": "Anyone can participate.",
            "location": "Online",
            "mode": "online",
            "themes": ["Agentic AI", "LLM", "Deep Learning"],
            "prize": "$50,000",
            "team_size": "1-4 members",
        }
        res = rule_engine.classify_and_score_event(item)
        assert res["eligibility"] == "ELIGIBLE"
        assert res["scoring"]["geo"] == 14  # Online score

    def test_cost_and_timing_priorities(self):
        # 1. Free + Weekend (Highest)
        free_weekend = {
            "title": "Weekend Free Hack",
            "url": "https://devpost.com/free-weekend",
            "summary": "100% free to attend AI hackathon on weekend.",
            "mode": "in-person",
            "event_start": "2026-12-05",  # Saturday
            "event_end": "2026-12-05",    # Saturday
            "location": "Bengaluru",
            "themes": ["AI"],
        }
        res1 = rule_engine.classify_and_score_event(free_weekend)
        assert res1["cost"] == "FREE"
        assert res1["timing"] == "WEEKEND"
        assert res1["timing_tier"] == 1

        # 2. Paid + Weekend
        paid_weekend = {
            "title": "Weekend Paid Hack",
            "url": "https://devpost.com/paid-weekend",
            "summary": "Entry fee: INR 500 per team. Exclusive weekend workshop.",
            "mode": "in-person",
            "event_start": "2026-12-05",  # Saturday
            "event_end": "2026-12-05",
            "location": "Bengaluru",
            "themes": ["AI"],
        }
        res2 = rule_engine.classify_and_score_event(paid_weekend)
        assert res2["cost"] == "PAID"
        assert res2["timing"] == "WEEKEND"
        assert res2["timing_tier"] == 2

        # 3. Free + Weekday
        free_weekday = {
            "title": "Weekday Free Hack",
            "url": "https://devpost.com/free-weekday",
            "summary": "Free community meetup on Wednesday evening.",
            "mode": "in-person",
            "event_start": "2026-12-02",  # Wednesday
            "event_end": "2026-12-02",
            "location": "Bengaluru",
            "themes": ["AI"],
        }
        res3 = rule_engine.classify_and_score_event(free_weekday)
        assert res3["cost"] == "FREE"
        assert res3["timing"] == "WEEKDAY"
        assert res3["timing_tier"] == 3

        # 4. Paid + Weekday
        paid_weekday = {
            "title": "Weekday Paid Hack",
            "url": "https://devpost.com/paid-weekday",
            "summary": "Registration fee: $20. Wednesday conference.",
            "mode": "in-person",
            "event_start": "2026-12-02",  # Wednesday
            "event_end": "2026-12-02",
            "location": "Bengaluru",
            "themes": ["AI"],
        }
        res4 = rule_engine.classify_and_score_event(paid_weekday)
        assert res4["cost"] == "PAID"
        assert res4["timing"] == "WEEKDAY"
        assert res4["timing_tier"] == 4

        # Verify ranking order: Tier 1 > Tier 2 > Tier 3 > Tier 4
        ranked = rule_engine.filter_and_rank_events([paid_weekday, free_weekday, paid_weekend, free_weekend])
        titles = [p["title"] for p in ranked["picks"]]
        assert titles == ["Weekend Free Hack", "Weekend Paid Hack", "Weekday Free Hack", "Weekday Paid Hack"]

    def test_blackout_dates_conflict_deprioritization(self):
        # In-person event overlapping with Nov 26-30 blackout window
        conflict_event = {
            "title": "Bengaluru AI Fest on Blackout Date",
            "url": "https://devpost.com/conflict-event",
            "summary": "Massive AI sprint on Nov 28.",
            "mode": "in-person",
            "event_start": "2026-11-28",  # Blackout date
            "event_end": "2026-11-28",
            "location": "Bengaluru",
            "themes": ["AI"],
        }
        res = rule_engine.classify_and_score_event(conflict_event)
        assert res["is_conflict"] is True
        assert res["priority"] == "CONFLICT (UNAVAILABLE)"
        assert "Blackout Conflict" in res["why"]


class TestDeduplicationAndURLNormalization:
    def test_url_normalization_strips_utm_and_trailing_slash(self):
        raw = "https://example.com/hackathon/?utm_source=twitter&utm_medium=social&ref=partner#details"
        clean = tracker_store.normalize_url(raw)
        assert clean == "https://example.com/hackathon"

    def test_luma_url_canonicalization(self):
        raw = "https://lu.ma/bengaluru-ai-demo?utm_campaign=blast"
        clean = tracker_store.normalize_url(raw)
        assert clean == "https://luma.com/bengaluru-ai-demo"


class TestDatabaseExtendedSchemaAndTracker:
    def test_upsert_events_stores_full_classification(self, temp_db):
        conn = tracker_store.connect(temp_db)
        items = [{
            "event_id": "test-bengaluru-ai",
            "title": "Bengaluru AI Sprint",
            "url": "https://example.com/sprint",
            "host": "AI Guild",
            "source": "Devfolio",
            "summary": "High school friendly hackathon.",
            "location": "Bengaluru",
            "mode": "in-person",
            "event_start": "2026-12-01",
            "event_end": "2026-12-02",
            "registration_deadline": "2026-11-28",
            "team_size": "3-5 members",
            "prize": "INR 1,00,000",
            "category": "Hackathon",
        }]
        eval_map = {
            "test-bengaluru-ai": {
                "priority": "HIGH PRIORITY",
                "score": 85,
                "why": "Local Bengaluru AI hackathon open to school students.",
                "eligibility": "ELIGIBLE",
                "age_restrictions": "Open to school students",
            }
        }
        tracker_store.upsert_events(conn, items, eval_map)

        row = conn.execute("SELECT * FROM events WHERE event_id='test-bengaluru-ai'").fetchone()
        assert row["title"] == "Bengaluru AI Sprint"
        assert row["priority"] == "HIGH PRIORITY"
        assert row["score"] == 85
        assert row["eligibility"] == "ELIGIBLE"
        assert row["registration_deadline"] == "2026-11-28"
        assert row["state"] == "seen"
        conn.close()

    def test_apply_action_transitions_and_rejections(self, temp_db):
        conn = tracker_store.connect(temp_db)
        conn.execute(
            "INSERT INTO events (event_id, title, url, state, first_seen, updated_at) "
            "VALUES ('e1', 'Test', 'https://test.com', 'seen', '2026-01-01', '2026-01-01')"
        )
        conn.commit()

        # Track (Shortlist)
        status, row = tracker_store.apply_action(conn, "track", "e1")
        assert status == "ok"
        assert row["state"] == "tracked"

        # Applied
        status, row = tracker_store.apply_action(conn, "applied", "e1")
        assert status == "ok"
        assert row["state"] == "applied"

        # Attempted track after applied is noop (no downgrade)
        status, row = tracker_store.apply_action(conn, "track", "e1")
        assert status == "noop"
        assert row["state"] == "applied"

        # Explicit reject
        status, row = tracker_store.apply_action(conn, "reject", "e1")
        assert status == "ok"
        assert row["state"] == "rejected"
        conn.close()


class TestAntigravityIntelligence:
    def test_inspect_and_summary(self, temp_db):
        conn = tracker_store.connect(temp_db)
        items = [
            {"event_id": "e1", "title": "A", "url": "https://a.com", "source": "Devpost"},
            {"event_id": "e2", "title": "B", "url": "https://b.com", "source": "Devfolio"}
        ]
        evals = {
            "e1": {"priority": "HIGH PRIORITY", "score": 90, "eligibility": "ELIGIBLE", "why": "Top fit."},
            "e2": {"priority": "MEDIUM PRIORITY", "score": 60, "eligibility": "UNKNOWN", "why": "Check rules."}
        }
        tracker_store.upsert_events(conn, items, evals)
        conn.close()

        summary = analysis.get_database_summary(temp_db)
        assert summary["total_events"] == 2
        assert summary["by_priority"]["HIGH PRIORITY"] == 1
        assert summary["by_priority"]["MEDIUM PRIORITY"] == 1

        high_events = analysis.inspect_database(temp_db, priority="HIGH PRIORITY")
        assert len(high_events) == 1
        assert high_events[0]["event_id"] == "e1"

    def test_analyze_event_and_class_11_eligibility(self, temp_db):
        conn = tracker_store.connect(temp_db)
        items = [{
            "event_id": "e-bengaluru",
            "title": "Bangalore Agentic Hack",
            "url": "https://bangalore-ai.org",
            "host": "Tech Labs",
            "source": "Luma",
            "location": "Bengaluru",
            "mode": "in-person",
            "summary": "Build autonomous agents.",
            "eligibility_rules": "Class 11 students are welcome.",
        }]
        evals = {
            "e-bengaluru": {"priority": "HIGH PRIORITY", "score": 88, "eligibility": "ELIGIBLE", "why": "Bengaluru local agentic hackathon."}
        }
        tracker_store.upsert_events(conn, items, evals)
        conn.close()

        res = analysis.analyze_event("e-bengaluru", temp_db)
        assert res["priority"] == "HIGH PRIORITY"
        assert res["logistics"]["is_local_bengaluru"] is True

        elig = analysis.evaluate_eligibility_for_class_11("e-bengaluru", temp_db)
        assert elig["verdict"] == "ELIGIBLE"
        assert "Class 11" in elig["student_grade"]

    def test_opportunity_report_generation(self, temp_db):
        conn = tracker_store.connect(temp_db)
        tracker_store.upsert_events(conn, [{
            "event_id": "e-rep",
            "title": "Report Test Event",
            "url": "https://report.test",
            "host": "OpenAI",
            "source": "Devpost",
            "event_start": "2026-12-10",
            "registration_deadline": "2026-12-05",
        }], {"e-rep": {"priority": "HIGH PRIORITY", "score": 92, "eligibility": "ELIGIBLE", "why": "Super event."}})
        conn.close()

        report_md = analysis.generate_opportunity_report(temp_db)
        assert "# 🛰️ Buildathon Radar Opportunity Report" in report_md
        assert "Report Test Event" in report_md
        assert "Super event." in report_md


class TestTrackerServiceEndpoints:
    @pytest.fixture
    def client(self, temp_db, monkeypatch, local_client):
        monkeypatch.setattr(tracker_service, "DB_PATH", temp_db)
        conn = tracker_store.connect(temp_db)
        tracker_store.upsert_events(conn, [{
            "event_id": "dash-1",
            "title": "Dashboard Event",
            "provenance": "live",
            "registration_status": "open",
            "url": "https://dash.test",
            "host": "HostA",
            "source": "Devfolio",
            "location": "Bengaluru",
            "mode": "in-person",
            "event_start": "2026-12-01",
            "event_end": "2026-12-02",
            "registration_deadline": "2026-11-25",
        }], {"dash-1": {"priority": "HIGH PRIORITY", "score": 88, "eligibility": "ELIGIBLE", "why": "Top pick.", "eligibility_evidence": "Open to school students"}})
        conn.close()
        return local_client(tracker_service.app)

    def test_dashboard_route_returns_200(self, client):
        resp = client.get("/dashboard")
        assert resp.status_code == 200
        assert "Dashboard Event" in resp.text
        assert "HIGH PRIORITY" in resp.text

    def test_event_detail_route(self, client):
        resp = client.get("/event/dash-1")
        assert resp.status_code == 200
        assert "Dashboard Event" in resp.text
        assert "Top pick." in resp.text

    def test_api_events_json(self, client):
        resp = client.get("/api/events")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["event_id"] == "dash-1"


class TestDeliveryWithoutEmail:
    def test_deliver_without_credentials_saves_archive_cleanly(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("EMAIL_ADDRESS", raising=False)
        monkeypatch.delenv("EMAIL_PASSWORD", raising=False)

        digest = "### [Event](https://test.com)\nTest card\n"
        html = "<html><body>Test</body></html>"
        ok = deliver.send_digest(digest, html)
        assert ok is deliver.DeliveryStatus.SKIPPED
        archive_files = list((tmp_path / "archive").glob("radar_*.md"))
        assert len(archive_files) == 1
        assert "Event" in archive_files[0].read_text()


class TestLaunchdPlistsValidation:
    def test_plists_syntax(self):
        radar_plist = Path(__file__).resolve().parent.parent / "scheduler" / "launchd" / "com.buildathon.radar.plist"
        tracker_plist = Path(__file__).resolve().parent.parent / "scheduler" / "launchd" / "com.buildathon.tracker.plist"

        assert radar_plist.exists()
        assert tracker_plist.exists()

        res1 = subprocess.run(["plutil", "-lint", str(radar_plist)], capture_output=True, text=True)
        assert res1.returncode == 0
        assert "OK" in res1.stdout

        res2 = subprocess.run(["plutil", "-lint", str(tracker_plist)], capture_output=True, text=True)
        assert res2.returncode == 0
        assert "OK" in res2.stdout
