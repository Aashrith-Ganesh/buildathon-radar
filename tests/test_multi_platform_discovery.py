from __future__ import annotations

import json
import sqlite3
import pytest

from buildathon_radar import tracker_service, tracker_store
from buildathon_radar.discovery.adapters import ADAPTER_REGISTRY, LIVE_SOURCE_KEYS
from buildathon_radar.discovery.base_adapter import BaseSourceAdapter
from buildathon_radar.discovery.deduplicator import (
    Deduplicator,
    are_duplicates,
    merge_event_records,
)
from buildathon_radar.discovery.engine import DiscoveryEngine
from buildathon_radar.discovery.models import (
    derive_event_id,
    normalize_title,
    normalize_url,
)


@pytest.fixture
def test_db(tmp_path):
    db_file = tmp_path / "test_discovery.db"
    conn = tracker_store.connect(str(db_file))
    conn.close()
    return str(db_file)


@pytest.fixture
def client(test_db, monkeypatch, local_client):
    monkeypatch.setattr(tracker_service, "DB_PATH", test_db)
    return local_client(tracker_service.app)


@pytest.fixture
def listing_responses(monkeypatch):
    payloads = {
        "devpost": {"hackathons": [{
            "title": "Example Robotics Hackathon", "url": "https://example.test/robotics",
            "event_start": "2029-07-10T18:45:00Z", "registration_status": "open",
            "eligibility_rules": "High school students are welcome.",
        }]},
        "unstop": {"data": {"data": [{"title": "Example AI Hackathon", "slug": "example-ai-123"}]}},
        "devfolio": {"result": [{"name": "Example Fintech Hackathon", "slug": "example-fintech"}]},
        "hackerearth": {"response": [{
            "title": "Example Coding Hackathon", "url": "https://example.test/coding", "challenge_type": "Hackathon",
        }]},
    }
    mlh = ('<div itemType="https://schema.org/Event">'
           '<meta itemProp="url" content="https://example.test/school"/>'
           '<meta itemProp="startDate" content="2029-08-01"/>'
           '<h4>School Hackathon</h4></div>')
    ethglobal = '<script>self.__next_f.push([1,' + json.dumps(json.dumps({
        "id": 12, "name": "Example ETH Hackathon", "slug": "example-eth", "type": "hackathon",
        "status": "future", "startTime": "2029-09-01T12:00:00Z", "medium": "virtual",
    }, separators=(",", ":"))) + '])</script>'
    public_event = '<script type="application/ld+json">' + json.dumps([
        {"@type": "Event", "name": "Robotics Hackathon", "startDate": "2029-09-01", "url": "https://example.test/robots"},
        {"@type": "Event", "name": "Robotics Talk", "startDate": "2029-09-01", "url": "https://example.test/talk"},
    ]) + '</script>'
    pages = {key: public_event for key in ("gdg", "meetup", "eventbrite", "allevents")}
    pages.update({"mlh": mlh, "ethglobal": ethglobal, "foss_united": """
      <rss><channel><item><title>FOSS Hack</title><link>https://example.test/foss</link>
      <description><![CDATA[<strong>Type:</strong> Hackathon<p><strong>Start:</strong>
      01 September 2029, 09:30 AM</p>]]></description></item></channel></rss>"""})


    def request(adapter, *args, **kwargs):
        if adapter.source_key in pages:
            return pages[adapter.source_key]
        return json.dumps(payloads[adapter.source_key])

    monkeypatch.setattr(BaseSourceAdapter, "make_request", request)
    return payloads


class TestPlatformAdapters:
    def test_registry_contains_27_sources(self):
        assert len(ADAPTER_REGISTRY) == 27

    @pytest.mark.parametrize("source_key", sorted(ADAPTER_REGISTRY))
    def test_adapter_fetch_contract(self, source_key, listing_responses):
        adapter = ADAPTER_REGISTRY[source_key]()
        items, error = adapter.fetch()
        if source_key not in LIVE_SOURCE_KEYS:
            assert items == []
            assert error
        else:
            assert error is None
            assert len(items) == 1
            assert items[0]["url"].startswith("https://")
            assert "eligibility" not in items[0]
            if source_key == "devpost":
                assert items[0]["event_start"] == "2029-07-11"
            elif source_key in {"mlh", "ethglobal", "gdg", "meetup", "eventbrite", "allevents", "foss_united"}:
                assert items[0]["event_start"] is not None
                assert items[0].get("registration_status") is None
            else:
                assert items[0]["event_start"] is None

    @pytest.mark.parametrize("source_key", sorted(LIVE_SOURCE_KEYS))
    def test_network_failures_have_no_fallback(self, source_key, monkeypatch):
        def timeout(*args, **kwargs):
            raise TimeoutError()

        monkeypatch.setattr(BaseSourceAdapter, "make_request", timeout)
        assert ADAPTER_REGISTRY[source_key]().fetch() == ([], "TimeoutError")

    def test_malformed_json_has_no_fallback(self, monkeypatch):
        monkeypatch.setattr(BaseSourceAdapter, "make_request", lambda *args, **kwargs: "<html>Blocked</html>")
        assert ADAPTER_REGISTRY["devpost"]().fetch() == ([], "JSONDecodeError")


class TestDeduplicationAndNormalization:
    """Tests URL canonicalization, fuzzy title matching, and multi-source reference merging."""

    def test_normalize_url_strips_tracking_params(self):
        raw_url = "https://devpost.com/software/my-hack?utm_source=twitter&utm_medium=social&ref=newsletter&fbclid=123"
        clean = normalize_url(raw_url)
        assert "utm_source" not in clean
        assert "ref=" not in clean
        assert "fbclid=" not in clean
        assert clean == "https://devpost.com/software/my-hack"

    def test_normalize_url_canonicalizes_luma_and_http(self):
        assert normalize_url("http://example.com/event/") == "https://example.com/event"
        assert normalize_url("https://lu.ma/ai-hackathon-blr") == "https://luma.com/ai-hackathon-blr"

    def test_normalize_title_strips_years_and_noise(self):
        t1 = normalize_title("Bangalore AI Buildathon 2026 - Winter Edition!")
        t2 = normalize_title("Bangalore AI Buildathon (Winter Edition)")
        assert "2026" not in t1
        assert "bangalore ai buildathon winter edition" in t1
        assert t1 == t2

    def test_are_duplicates_by_url(self):
        e1 = {"title": "AI Hack 1", "url": "https://devpost.com/hackathons/gemini-2026?utm_source=x"}
        e2 = {"title": "Different Title", "url": "https://devpost.com/hackathons/gemini-2026"}
        assert are_duplicates(e1, e2) is True

    def test_are_duplicates_by_fuzzy_title_and_date(self):
        e1 = {
            "title": "Autonomous AI Agents Hackathon Bengaluru 2026",
            "url": "https://lu.ma/ai-agents-blr-2026",
            "event_start": "2026-12-19",
            "host": "Example Organizer",
        }
        e2 = {
            "title": "Autonomous AI Agents Hackathon Bangalore",
            "url": "https://twitter.com/organizer/status/1859018273645019283",
            "event_start": "2026-12-19",
            "host": "Example Organizer",
        }
        assert are_duplicates(e1, e2) is True

    def test_merge_event_records_preserves_discovery_sources(self):
        existing = {
            "event_id": "sarvam-hack-2026",
            "title": "Sarvam AI Indic GenAI Buildathon",
            "url": "https://www.sarvam.ai/hackathon",
            "source": "Top AI Companies & Indian Startups",
            "confidence": "High",
            "discovery_sources": [
                {
                    "source_name": "Top AI Companies & Indian Startups",
                    "url": "https://www.sarvam.ai/hackathon",
                    "confidence": "High",
                }
            ],
            "tech_categories": ["Indic AI", "Voice"],
        }
        new_sighting = {
            "title": "Sarvam AI Hackathon on LinkedIn",
            "url": "https://www.sarvam.ai/hackathon?ref=linkedin",
            "announcement_url": "https://www.linkedin.com/posts/sarvam-announcement-12345",
            "source": "LinkedIn Announcements",
            "confidence": "Medium-High",
            "tech_categories": ["Voice", "NLP", "LLMs"],
        }
        merged = merge_event_records(existing, new_sighting)
        assert len(merged["discovery_sources"]) == 2
        source_names = [s["source_name"] for s in merged["discovery_sources"]]
        assert "Top AI Companies & Indian Startups" in source_names
        assert "LinkedIn Announcements" in source_names
        assert sorted(merged["tech_categories"]) == ["Indic AI", "LLMs", "NLP", "Voice"]


class TestDiscoveryEngine:
    """Tests the discovery orchestrator with fault isolation and SQLite persistence."""

    def test_engine_scan_execution(self, test_db, listing_responses):
        engine = DiscoveryEngine(db_path=test_db, max_workers=4)
        keys = ["devpost", "unstop", "linkedin", "aws_community", "indian_colleges"]
        first = engine.run_scan(source_keys=keys)
        second = engine.run_scan(source_keys=keys)
        assert first["total_sources"] == first["successful_sources"] == first["new_events"] == 2
        assert second["new_events"] == 0

        with tracker_store.connect(test_db) as conn:
            rows = conn.execute("SELECT provenance, source, event_start FROM events ORDER BY source").fetchall()
            assert [tuple(row) for row in rows] == [
                ("live", "Devpost", "2029-07-11"), ("live", "Unstop", None),
            ]
            source = tracker_store.get_discovery_source(conn, "devpost")
            assert source["last_status"] == "degraded"
            assert source["last_success_at"]
            assert len(tracker_store.get_recent_discovery_scans(conn)) == 2

    def test_engine_fault_isolation(self, test_db, monkeypatch, listing_responses):
        request = BaseSourceAdapter.make_request

        def sometimes_timeout(self, *args, **kwargs):
            if self.source_key == "devpost":
                raise TimeoutError()
            return request(self, *args, **kwargs)

        monkeypatch.setattr(BaseSourceAdapter, "make_request", sometimes_timeout)
        summary = DiscoveryEngine(db_path=test_db).run_scan(source_keys=["devpost", "unstop"])
        assert summary["successful_sources"] == summary["failed_sources"] == 1
        with tracker_store.connect(test_db) as conn:
            source = tracker_store.get_discovery_source(conn, "devpost")
            assert source["last_error"] == "TimeoutError"
            assert source["last_failed_at"]
            assert not source["last_success_at"]

    def test_rejected_url_counts_and_cross_source_lineage(self, test_db, listing_responses):
        listing_responses["hackerearth"]["response"].extend([
            {"title": "Same event", "url": "https://example.test/robotics?utm_source=listing", "challenge_type": "Hackathon"},
            {"title": "Invalid event", "url": "javascript:invalid"},
        ])
        engine = DiscoveryEngine(db_path=test_db)
        result = engine.run_scan(source_keys=["devpost", "hackerearth"])
        assert result["source_stats"]["hackerearth"]["rejected"] == 1
        with tracker_store.connect(test_db) as conn:
            row = conn.execute("SELECT discovery_sources FROM events WHERE url LIKE '%/robotics'").fetchone()
            lineage = json.loads(row["discovery_sources"])
            assert {entry["source_key"] for entry in lineage} == {"devpost", "hackerearth"}
            assert all(entry["scan_id"] == result["scan_id"] for entry in lineage)
            scan = tracker_store.get_recent_discovery_scans(conn)[0]
            assert json.loads(scan["details"])["merges"][0]["urls"] == ["https://example.test/robotics"]


class TestDiscoveryServiceRoutes:
    """Verifies the UI pages and REST API endpoints for discovery sources and manual scanning."""

    def test_sources_html_page_rendering(self, client):
        resp = client.get("/sources")
        assert resp.status_code == 200
        assert "Discovery sources" in resp.text
        assert "Dedicated Platforms" in resp.text
        assert "Professional &amp; Social Networks" in resp.text or "Professional & Social Networks" in resp.text
        assert "Scan All Sources Now" in resp.text
        assert "devpost" in resp.text
        assert "linkedin" in resp.text

    def test_api_get_sources_returns_27_platforms(self, client):
        resp = client.get("/api/sources")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 27
        keys = [s["source_key"] for s in data]
        assert "devpost" in keys
        assert "linkedin" in keys
        assert "indian_colleges" in keys
        assert "search_discovery" in keys

    def test_api_toggle_source(self, client):
        # Toggle off
        resp = client.post("/api/sources/devpost/toggle")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

        # Toggle on
        resp2 = client.post("/api/sources/devpost/toggle")
        assert resp2.status_code == 200
        assert resp2.json()["enabled"] is True

    def test_api_run_scan_endpoint(self, client):
        resp = client.post("/api/scan", json={"sources": ["linkedin", "microsoft_reactor"]})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["total_sources"] == 0
        assert data["new_events"] == 0

    def test_api_scans_history(self, client):
        # Run a scan first
        client.post("/api/scan", json={"sources": ["linkedin"]})
        resp = client.get("/api/scans")
        assert resp.status_code == 200
        scans = resp.json()
        assert len(scans) >= 1
        assert "duration_seconds" in scans[0]
        assert "total_sources" in scans[0]

    def test_dashboard_displays_scan_button_and_sources_nav(self, client):
        resp = client.get("/dashboard")
        assert resp.status_code == 200
        assert "/sources" in resp.text
        assert "Scan Hackathons" in resp.text


@pytest.mark.parametrize("other", [
    {"title": "AI Hackathon", "host": "Organizer", "event_start": "2030-01-01", "location": "Delhi"},
    {"title": "AI Hackathon", "host": "Organizer", "event_start": "2031-01-01", "location": "Bengaluru"},
    {"title": "AI Hackathon", "host": "Other Organizer", "event_start": "2030-01-01", "location": "Bengaluru"},
    {"title": "AI Hackathon", "host": "Organizer", "location": "Bengaluru"},
])
def test_dedup_preserves_distinct_events(other):
    assert not are_duplicates({
        "title": "AI Hackathon", "host": "Organizer", "event_start": "2030-01-01", "location": "Bengaluru",
    }, other)


def test_atomic_scan_rolls_back_listings_and_health(test_db, listing_responses, monkeypatch):
    from buildathon_radar.discovery import engine

    def broken_history(*args, **kwargs):
        raise OSError("Scan log write failed")

    monkeypatch.setattr(engine, "log_discovery_scan", broken_history)
    with pytest.raises(OSError):
        DiscoveryEngine(db_path=test_db).run_scan(source_keys=["devpost"])
    with tracker_store.connect(test_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0
        assert not tracker_store.get_discovery_source(conn, "devpost")["last_success_at"]


def test_dashboard_views_share_counts_and_exclude_legacy_closed_and_expired(client, test_db):
    from datetime import datetime, timedelta

    today = datetime.now(tracker_store.IST).date()
    date_after = lambda days: (today + timedelta(days=days)).isoformat()
    event = {"event_id": "valid", "title": "Open Robotics Hackathon", "provenance": "live",
             "url": "https://example.test/robotics", "registration_status": "open",
             "event_start": date_after(1000), "registration_deadline": date_after(2),
             "location": "Bangalore", "mode": "in-person"}
    rows = [
        event,
        dict(event, event_id="expired", title="Expired 2014 event", event_start="2014-01-01"),
        dict(event, event_id="closed", title="Closed registration", registration_deadline=date_after(-1)),
        dict(event, event_id="legacy", title="Old news", provenance="legacy"),
        dict(event, event_id="undated", title="Undated registration", event_start=None),
    ]
    with tracker_store.connect(test_db) as conn:
        tracker_store.upsert_events(conn, rows)
    stats = client.get("/api/dashboard-stats").json()
    assert stats["total_upcoming"] == stats["closing_soon_count"] == 2
    assert stats["bangalore_count"] == 3
    for key, count in (("open", 2), ("bengaluru", 3), ("closing_soon", 2)):
        html = client.get("/dashboard", params={"filter": key}).text
        assert html.count('data-start=') == 2 * count
        assert f"{count} results ·" in html
        assert "Expired 2014 event" not in html
        assert "Undated registration" in html
        assert "Schedule unconfirmed" in html
        assert "Old news" not in html
    assert "Closed registration" not in client.get("/dashboard?filter=closing_soon").text

    discovery = client.get("/dashboard").text
    assert stats["discovered_count"] == 3
    assert "3 results ·" in discovery
    assert "Undated registration" in discovery
    query = client.get("/dashboard", params={"filter": "bengaluru", "search": "bengaluru robot"}).text
    assert "1 result ·" in query
    assert "Open Robotics Hackathon" in query
    assert 'id="clearRadarSearch" href="/dashboard?filter=bengaluru"' in query
    assert 'filter=closing_soon&amp;search=bengaluru+robot' in query
    assert "Eligibility unconfirmed" in discovery
    assert "Expired 2014 event" not in discovery
    assert "Old news" not in discovery


@pytest.mark.parametrize(("item", "expected"), [
    ({"eligibility": "ELIGIBLE", "summary": "A high school hackathon recap"}, "UNKNOWN"),
    ({"eligibility_rules": "Open to all students."}, "ELIGIBLE"),
    ({"eligibility_rules": "High school students are welcome."}, "ELIGIBLE"),
    ({"eligibility_rules": "High school students are welcome. 18+ only."}, "INELIGIBLE"),
    ({"eligibility_rules": "Undergraduates only."}, "INELIGIBLE"),
])
def test_eligibility_needs_explicit_evidence(item, expected):
    from buildathon_radar.rule_engine import classify_and_score_event

    outcome = classify_and_score_event(item)
    assert outcome["eligibility"] == expected
    assert bool(outcome["eligibility_evidence"]) == (expected != "UNKNOWN")


def test_bengaluru_listing_survives_exam_conflict_and_missing_registration(test_db):
    with tracker_store.connect(test_db) as conn:
        tracker_store.add_blackout_date(conn, "Exam", "2090-10-01", "2090-10-02", "Academic Test")
        tracker_store.upsert_events(conn, [{
            "event_id": "local-conflict", "title": "Bengaluru Code Sprint",
            "url": "https://example.test/local", "location": "Bengaluru, Karnataka",
            "event_start": "2090-10-02", "provenance": "live",
        }])
        views = tracker_store.dashboard_views(conn)
    assert [row["event_id"] for row in views["bengaluru"]] == ["local-conflict"]
    assert [row["event_id"] for row in views["upcoming"]] == ["local-conflict"]
    assert [row["event_id"] for row in views["excluded"]] == ["local-conflict"]
    assert not views["open"]


def test_discard_pile_retains_rejected_listings_after_refresh(client, test_db):
    event = {
        "event_id": "discard-me", "title": "Discardable Robotics Hackathon",
        "url": "https://example.test/discard-me", "provenance": "live",
        "event_start": "2090-02-04", "registration_status": "open",
    }
    with tracker_store.connect(test_db) as conn:
        tracker_store.upsert_events(conn, [event])
    assert event["title"] in client.get("/dashboard").text
    assert 'id="discardDetail"' in client.get("/event/discard-me").text
    assert 'data-event-action="reject"' in client.get("/dashboard").text
    response = client.post("/api/action", json={
        "event_id": event["event_id"], "action": "reject",
        "token": tracker_store.sign_action("reject", event["event_id"]),
    })
    assert response.status_code == 200
    assert response.json()["state"] == "rejected"
    with tracker_store.connect(test_db) as conn:
        tracker_store.upsert_events(conn, [event])
    assert event["title"] not in client.get("/dashboard").text
    assert event["title"] not in client.get("/dashboard?filter=upcoming").text
    pile = client.get("/dashboard?filter=discard").text
    assert event["title"] in pile
    assert 'data-event-action="reject"' not in pile
    assert "Discard pile (1)" in pile
    detail = client.get("/event/discard-me").text
    assert "Moved to the Discard pile." in detail
    assert 'id="discardDetail"' not in detail
    assert client.get("/api/dashboard-stats").json()["discard_count"] == 1


def test_linkedin_search_leads_stay_separate_from_discovery(client, monkeypatch):
    from datetime import datetime

    class November2026(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 11, 22, tzinfo=tz)

    monkeypatch.setattr(tracker_service, "_datetime", November2026)
    leads = client.get("/leads")
    assert leads.status_code == 200
    assert "CODERED" in leads.text and "AgentMaX" in leads.text
    assert "google.com/search" in leads.text
    assert "Confirm dates, registration and eligibility" in leads.text
    assert "CODERED" not in client.get("/dashboard").text
