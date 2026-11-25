"""Unit and integration tests for Buildathon Radar weekly digest automation pipeline.

Covers:
- buildathon_radar.state_manager.StateManager
- buildathon_radar.webhook_client.WebhookClient & validation helpers
- scripts.run_weekly_digest CLI execution and flags
"""

import json
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from buildathon_radar import tracker_store
from buildathon_radar.state_manager import StateManager
from buildathon_radar.webhook_client import (
    WebhookClient,
    WebhookDeliveryError,
    compute_payload_hash,
    validate_digest_payload,
)
from scripts.run_weekly_digest import main as run_pipeline_main


@pytest.fixture
def temp_env():
    """Provides isolated temporary directories for state and database testing."""
    tmpdir = tempfile.mkdtemp()
    state_dir = Path(tmpdir) / "state"
    db_path = Path(tmpdir) / "test_tracker.db"
    
    # Initialize a clean database via connect (auto-inits schema)
    conn = tracker_store.connect(str(db_path))
    conn.close()

    yield {
        "root": Path(tmpdir),
        "state_dir": state_dir,
        "db_path": db_path,
    }

    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def sample_payload():
    """Generates a minimal valid digest payload for testing."""
    return {
        "status": "ok",
        "meta": {
            "title": "Buildathon Radar Weekly Digest",
            "date_display": "Sunday, November 29, 2026",
            "date_range": "Nov 29 - Dec 6, 2026",
            "recipient_name": "Student Hacker",
            "generated_at": "2026-11-29T08:00:00+05:30",
        },
        "featured_hackathons": [
            {
                "id": "event-1",
                "title": "Bengaluru AI Hackathon 2026",
                "url": "https://example.com/hackathon",
                "score": 95,
                "mode": "in-person",
                "location": "Bengaluru",
                "dates_display": "Dec 20-21, 2026",
                "eligibility_label": "High School Students",
                "team_size_label": "3-5 members",
                "prize_pool": "₹5,00,000",
                "summary": "Premier student hackathon.",
            }
        ],
        "upcoming_deadlines": [],
        "happening_soon": [],
        "recommended": [],
        "blackout_calendar": {
            "conflicts_excluded_count": 2,
            "upcoming_periods": [],
        },
    }


class TestStateManager:
    """Tests for StateManager persistence, restore, duplicate detection, and logging."""

    def test_ensure_state_dir(self, temp_env):
        mgr = StateManager(state_dir=temp_env["state_dir"], db_path=temp_env["db_path"])
        assert not temp_env["state_dir"].exists()
        mgr.ensure_state_dir()
        assert temp_env["state_dir"].exists()

    def test_restore_state_fresh(self, temp_env):
        mgr = StateManager(state_dir=temp_env["state_dir"], db_path=temp_env["db_path"])
        result = mgr.restore_state()
        assert result["database_restored"] is False
        assert result["previous_deliveries_count"] == 0
        assert result["last_delivery"] is None

    def test_restore_state_existing(self, temp_env):
        state_dir = temp_env["state_dir"]
        state_dir.mkdir(parents=True, exist_ok=True)
        state_db = state_dir / "tracker.db"

        # Create a dummy database in state_dir
        conn = sqlite3.connect(str(state_db))
        conn.execute("CREATE TABLE test_tbl (id INTEGER);")
        conn.commit()
        conn.close()

        # Create fake delivery history
        history_path = state_dir / "delivery_history.json"
        with open(history_path, "w", encoding="utf-8") as f:
            json.dump([{"delivery_id": "d-1", "status": "success"}], f)

        mgr = StateManager(state_dir=state_dir, db_path=temp_env["db_path"])
        result = mgr.restore_state()
        assert result["database_restored"] is True
        assert result["previous_deliveries_count"] == 1
        assert result["last_delivery"]["delivery_id"] == "d-1"
        assert temp_env["db_path"].exists()

    def test_is_duplicate_delivery(self, temp_env):
        mgr = StateManager(state_dir=temp_env["state_dir"], db_path=temp_env["db_path"])
        mgr.record_delivery(
            delivery_id="del-123",
            content_hash="abc456def789",
            status="success",
            recipient="test@example.com",
            featured_count=3,
        )

        is_dup, reason = mgr.is_duplicate_delivery("del-123", "different_hash")
        assert is_dup is True
        assert "already been dispatched" in reason

        is_dup, reason = mgr.is_duplicate_delivery("del-new", "abc456def789")
        assert is_dup is True
        assert "Digest content is identical" in reason

        is_dup, reason = mgr.is_duplicate_delivery("del-brand-new", "new_hash")
        assert is_dup is False
        assert reason is None

    def test_record_delivery_retention_limit(self, temp_env):
        mgr = StateManager(state_dir=temp_env["state_dir"], db_path=temp_env["db_path"])
        # Record 55 deliveries
        for i in range(55):
            mgr.record_delivery(
                delivery_id=f"d-{i}",
                content_hash=f"h-{i}",
                status="success",
                recipient="test@example.com",
                featured_count=1,
            )

        history = mgr.get_delivery_history()
        assert len(history) == 50  # Cap is 50
        assert history[-1]["delivery_id"] == "d-54"

    def test_save_state(self, temp_env, sample_payload):
        mgr = StateManager(state_dir=temp_env["state_dir"], db_path=temp_env["db_path"])
        saved = mgr.save_state(digest_data=sample_payload)
        assert saved["database_saved"] is True
        assert mgr.state_db_path.exists()
        assert mgr.last_digest_path.exists()
        assert mgr.metadata_path.exists()

        with open(mgr.metadata_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
            assert "last_updated" in meta
            assert meta["database_size"] > 0


class TestWebhookClient:
    """Tests for WebhookClient payload validation, hashing, redirect handling, and dry-run."""

    def test_validate_digest_payload_success(self, sample_payload):
        # Should not raise
        validate_digest_payload(sample_payload)

    def test_validate_digest_payload_missing_keys(self):
        with pytest.raises(ValueError, match="Payload status must be 'ok'"):
            validate_digest_payload({})

        with pytest.raises(ValueError, match="Payload missing required 'meta' dictionary"):
            validate_digest_payload({"status": "ok"})

        with pytest.raises(ValueError, match="Payload meta missing 'date_display'"):
            validate_digest_payload({
                "status": "ok",
                "meta": {},
                "featured_hackathons": [],
            })

        with pytest.raises(ValueError, match="Featured event at index 0 missing title"):
            validate_digest_payload({
                "status": "ok",
                "meta": {"date_display": "Sunday, Nov 29"},
                "featured_hackathons": [{}],
            })

    def test_compute_payload_hash_deterministic(self, sample_payload):
        h1 = compute_payload_hash(sample_payload)
        h2 = compute_payload_hash(sample_payload)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256

        # Modifying a title or date changes the hash
        mutated = json.loads(json.dumps(sample_payload))
        mutated["featured_hackathons"][0]["title"] = "Different Hackathon Title"
        h3 = compute_payload_hash(mutated)
        assert h1 != h3

    def test_send_digest_dry_run(self, sample_payload):
        client = WebhookClient(webhook_url="https://example.com/webhook", webhook_secret="secret123")
        res = client.send_digest(sample_payload, delivery_id="del-test", dry_run=True)
        assert res["status"] == "dry_run"
        assert res["delivery_id"] == "del-test"

    def test_send_digest_missing_config_raises(self, sample_payload):
        client = WebhookClient(webhook_url=None, webhook_secret=None)
        with pytest.raises(WebhookDeliveryError, match="GAS_WEB_APP_URL is not configured"):
            client.send_digest(sample_payload, delivery_id="del-123", dry_run=False)

        client2 = WebhookClient(webhook_url="https://script.google.com/macros/s/xyz/exec", webhook_secret=None)
        with pytest.raises(WebhookDeliveryError, match="GAS_WEBHOOK_SECRET is not configured"):
            client2.send_digest(sample_payload, delivery_id="del-123", dry_run=False)

    @patch("buildathon_radar.webhook_client.requests.post")
    def test_send_digest_success_with_redirect(self, mock_post, sample_payload):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "delivery_id": "del-123",
            "recipient": "student@example.com",
            "message": "Weekly digest email sent successfully",
        }
        mock_post.return_value = mock_response

        client = WebhookClient(webhook_url="https://script.google.com/macros/s/xyz/exec", webhook_secret="secret123")
        res = client.send_digest(sample_payload, delivery_id="del-123", dry_run=False)

        assert res["status"] == "success"
        assert res["delivery_id"] == "del-123"
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        assert kwargs["allow_redirects"] is True
        assert kwargs["json"]["auth"]["secret"] == "secret123"
        assert kwargs["headers"]["X-Webhook-Secret"] == "secret123"

    @patch("buildathon_radar.webhook_client.requests.post")
    def test_send_digest_gas_error_response(self, mock_post, sample_payload):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "error",
            "message": "Authentication failed: invalid webhook secret",
        }
        mock_post.return_value = mock_response

        client = WebhookClient(webhook_url="https://script.google.com/macros/s/xyz/exec", webhook_secret="wrong")
        with pytest.raises(WebhookDeliveryError, match="Authentication failed"):
            client.send_digest(sample_payload, delivery_id="del-123", dry_run=False)


class TestRunWeeklyDigestPipelineCli:
    """Integration tests for the automated runner CLI script."""

    def test_cli_dry_run_mock_webhook(self, temp_env, monkeypatch):
        summary_file = temp_env["root"] / "step_summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))
        monkeypatch.setattr(
            "sys.argv",
            [
                "run_weekly_digest.py",
                "--state-dir", str(temp_env["state_dir"]),
                "--db-path", str(temp_env["db_path"]),
                "--dry-run",
                "--mock-webhook",
                "--skip-discovery",
            ],
        )

        exit_code = run_pipeline_main()
        assert exit_code == 0
        assert summary_file.exists()
        summary_text = summary_file.read_text(encoding="utf-8")
        assert "Buildathon Radar Weekly Digest" in summary_text
        assert "DRY-RUN" in summary_text

    def test_cli_live_duplicate_prevention(self, temp_env, monkeypatch):
        summary_file = temp_env["root"] / "step_summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))

        # First run: live simulation (mock webhook, not dry run)
        monkeypatch.setattr(
            "sys.argv",
            [
                "run_weekly_digest.py",
                "--state-dir", str(temp_env["state_dir"]),
                "--db-path", str(temp_env["db_path"]),
                "--mock-webhook",
                "--skip-discovery",
            ],
        )
        assert run_pipeline_main() == 0

        # Verify state files were written
        assert (temp_env["state_dir"] / "delivery_history.json").exists()

        # Second run: identical content should be skipped as duplicate
        monkeypatch.setattr(
            "sys.argv",
            [
                "run_weekly_digest.py",
                "--state-dir", str(temp_env["state_dir"]),
                "--db-path", str(temp_env["db_path"]),
                "--mock-webhook",
                "--skip-discovery",
            ],
        )
        assert run_pipeline_main() == 0

        # Third run: with --force-send, duplicate check is bypassed
        monkeypatch.setattr(
            "sys.argv",
            [
                "run_weekly_digest.py",
                "--state-dir", str(temp_env["state_dir"]),
                "--db-path", str(temp_env["db_path"]),
                "--mock-webhook",
                "--skip-discovery",
                "--force-send",
            ],
        )
        assert run_pipeline_main() == 0
