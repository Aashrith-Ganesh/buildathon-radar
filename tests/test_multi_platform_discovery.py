from __future__ import annotations

import json
import sqlite3
import pytest
from starlette.testclient import TestClient

from buildathon_radar import tracker_service, tracker_store
from buildathon_radar.discovery.adapters import ADAPTER_REGISTRY
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
def client(test_db, monkeypatch):
    monkeypatch.setattr(tracker_service, "DB_PATH", test_db)
    return TestClient(tracker_service.app)


class TestPlatformAdapters:
    """Verifies that all 27 multi-platform discovery source adapters execute cleanly."""

    def test_registry_contains_27_sources(self):
        assert len(ADAPTER_REGISTRY) == 27

    @pytest.mark.parametrize("source_key,adapter_cls", list(ADAPTER_REGISTRY.items()))
    def test_adapter_fetch_contract(self, source_key, adapter_cls):
        adapter = adapter_cls(timeout=5)
        assert isinstance(adapter, BaseSourceAdapter)
        assert adapter.source_key == source_key
        assert adapter.name
        assert adapter.category
        assert adapter.discovery_method
        assert adapter.confidence_level in ("High", "Medium-High", "Medium", "Low")

        items, err = adapter.fetch()
        assert isinstance(items, list)
        assert len(items) >= 1  # Every adapter provides discovered or curated events

        for item in items:
            assert "event_id" in item
            assert "title" in item
            assert "url" in item
            assert "source" in item
            assert "category" in item
            assert item["title"].strip() != ""
            assert item["url"].startswith("http")


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
        }
        e2 = {
            "title": "Autonomous AI Agents Hackathon Bangalore",
            "url": "https://twitter.com/organizer/status/1859018273645019283",
            "event_start": "2026-12-19",
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

    def test_engine_scan_execution(self, test_db):
        engine = DiscoveryEngine(db_path=test_db, max_workers=8, timeout=5)
        # Test scan across a subset of sources for fast determinism
        sample_sources = ["devpost", "unstop", "linkedin", "gdg", "indian_colleges"]
        summary = engine.run_scan(source_keys=sample_sources)

        assert summary["total_sources"] == 5
        assert summary["successful_sources"] == 5
        assert summary["failed_sources"] == 0
        assert summary["new_events"] >= 5
        assert summary["duration_seconds"] > 0

        # Verify DB records
        conn = tracker_store.connect(test_db)
        cur = conn.execute("SELECT COUNT(*) as c FROM events")
        assert cur.fetchone()["c"] >= 5

        # Verify discovery_scans table
        scans = tracker_store.get_recent_discovery_scans(conn)
        assert len(scans) == 1
        assert scans[0]["total_sources"] == 5

        # Verify discovery_sources metadata was updated
        s_row = tracker_store.get_discovery_source(conn, "devpost")
        assert s_row["success_count"] >= 1
        assert s_row["events_discovered"] >= 1
        assert s_row["last_scan"] is not None
        conn.close()

    def test_engine_fault_isolation(self, test_db, monkeypatch):
        """Simulate an adapter crash and verify discovery engine continues and records error."""
        engine = DiscoveryEngine(db_path=test_db, max_workers=4, timeout=5)

        class BrokenAdapter(BaseSourceAdapter):
            source_key = "broken"
            name = "Broken Adapter"
            category = "Test"
            discovery_method = "Mock"
            confidence_level = "Low"

            def fetch(self):
                raise RuntimeError("Simulated network timeout/Cloudflare block")

        monkeypatch.setitem(ADAPTER_REGISTRY, "broken", BrokenAdapter)
        # Register in DB
        conn = tracker_store.connect(test_db)
        conn.execute(
            """
            INSERT OR REPLACE INTO discovery_sources (
                source_key, name, category, discovery_method, confidence_level,
                enabled, last_scan, events_discovered, success_count, fail_count,
                last_error, updated_at
            ) VALUES ('broken', 'Broken Adapter', 'Test', 'Mock', 'Low', 1, NULL, 0, 0, 0, NULL, '2026-11-22')
            """
        )
        conn.commit()
        conn.close()

        # Run scan on broken + working adapter
        summary = engine.run_scan(source_keys=["broken", "gdg"])
        assert summary["total_sources"] == 2
        assert summary["successful_sources"] == 1
        assert summary["failed_sources"] == 1

        # Check DB updated with error message
        conn = tracker_store.connect(test_db)
        broken_cfg = tracker_store.get_discovery_source(conn, "broken")
        assert broken_cfg["fail_count"] == 1
        assert "Simulated network timeout" in broken_cfg["last_error"]
        conn.close()


class TestDiscoveryServiceRoutes:
    """Verifies the UI pages and REST API endpoints for discovery sources and manual scanning."""

    def test_sources_html_page_rendering(self, client):
        resp = client.get("/sources")
        assert resp.status_code == 200
        assert "Multi-Platform Hackathon Discovery Engine" in resp.text
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
        resp = client.post("/api/scan", json={"sources": ["gdg", "microsoft_reactor"]})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["total_sources"] == 2
        assert data["successful_sources"] == 2
        assert data["new_events"] >= 1

    def test_api_scans_history(self, client):
        # Run a scan first
        client.post("/api/scan", json={"sources": ["gdg"]})
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
