"""Persistent State Manager for Buildathon Radar Automation.

Manages historical discovery data, delivery logs, and digest fingerprints
across ephemeral GitHub Actions runners using a dedicated state directory
(backed by a Git branch or artifact storage).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("buildathon_radar.state_manager")
IST = timezone(timedelta(hours=5, minutes=30))


class StateManager:
    """Handles restoring, updating, and saving state across runner instances."""

    def __init__(self, state_dir: str | Path = "state", db_path: str | Path = "tracker.db"):
        self.state_dir = Path(state_dir)
        self.db_path = Path(db_path)
        self.state_db_path = self.state_dir / "tracker.db"
        self.delivery_history_path = self.state_dir / "delivery_history.json"
        self.last_digest_path = self.state_dir / "last_digest.json"
        self.metadata_path = self.state_dir / "state_metadata.json"

    def ensure_state_dir(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def restore_state(self) -> Dict[str, Any]:
        """Restores state from state_dir into working directory.

        Returns a dictionary describing what was restored.
        """
        self.ensure_state_dir()
        restored = {
            "database_restored": False,
            "previous_deliveries_count": 0,
            "last_delivery": None,
        }

        # 1. Restore SQLite database if it exists in state
        if self.state_db_path.exists() and self.state_db_path.stat().st_size > 0:
            logger.info("Restoring persistent database from %s to %s", self.state_db_path, self.db_path)
            shutil.copy2(self.state_db_path, self.db_path)
            # Remove any stale lock or WAL files
            for stale in [Path(f"{self.db_path}-wal"), Path(f"{self.db_path}-shm"), Path("tracker.scan.lock")]:
                if stale.exists():
                    stale.unlink()
            restored["database_restored"] = True
        elif not self.db_path.exists():
            logger.info("No persistent database found in state; working DB will be initialized fresh.")

        # 2. Inspect delivery history
        history = self.get_delivery_history()
        restored["previous_deliveries_count"] = len(history)
        if history:
            restored["last_delivery"] = history[-1]

        return restored

    def get_delivery_history(self) -> List[Dict[str, Any]]:
        """Reads delivery history log."""
        if not self.delivery_history_path.exists():
            return []
        try:
            with open(self.delivery_history_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except Exception as e:
            logger.warning("Could not read delivery history: %s", e)
            return []

    def is_duplicate_delivery(self, delivery_id: str, content_hash: str) -> Tuple[bool, Optional[str]]:
        """Checks if a delivery ID or identical content hash was already dispatched."""
        history = self.get_delivery_history()
        for record in reversed(history):
            if record.get("status") == "success":
                if record.get("delivery_id") == delivery_id:
                    return True, f"Delivery ID '{delivery_id}' has already been dispatched."
                if record.get("content_hash") == content_hash:
                    sent_at = record.get("sent_at", "recently")
                    return True, f"Digest content is identical to delivery from {sent_at} (hash: {content_hash[:12]}...)."
        return False, None

    def record_delivery(
        self,
        delivery_id: str,
        content_hash: str,
        status: str,
        recipient: str,
        featured_count: int,
        meta: Optional[Dict[str, Any]] = None,
        raw_response: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Appends a delivery event to persistent history."""
        self.ensure_state_dir()
        history = self.get_delivery_history()
        now_iso = datetime.now(IST).isoformat()

        record = {
            "delivery_id": delivery_id,
            "content_hash": content_hash,
            "status": status,
            "recipient": recipient,
            "featured_count": featured_count,
            "sent_at": now_iso,
            "meta": meta or {},
            "response": raw_response or {},
        }
        history.append(record)

        # Keep last 50 deliveries
        history = history[-50:]

        with open(self.delivery_history_path, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)

        return record

    def save_state(
        self,
        digest_data: Optional[Dict[str, Any]] = None,
        delivery_record: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Saves current working DB, last digest snapshot, and state metadata to state_dir."""
        self.ensure_state_dir()
        saved_info = {
            "database_saved": False,
            "timestamp": datetime.now(IST).isoformat(),
        }

        # 1. Copy working database to state directory
        if self.db_path.exists() and self.db_path.stat().st_size > 0:
            # Clean WAL checkpoint before copying if possible
            try:
                conn = sqlite3.connect(str(self.db_path))
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
                conn.close()
            except Exception as e:
                logger.debug("WAL checkpoint before state save: %s", e)

            shutil.copy2(self.db_path, self.state_db_path)
            saved_info["database_saved"] = True
            saved_info["database_size_bytes"] = self.state_db_path.stat().st_size

        # 2. Save last digest snapshot if provided
        if digest_data:
            with open(self.last_digest_path, "w", encoding="utf-8") as f:
                json.dump(digest_data, f, indent=2, ensure_ascii=False)
            saved_info["last_digest_saved"] = True

        # 3. Write state metadata
        metadata = {
            "last_updated": saved_info["timestamp"],
            "database_size": saved_info.get("database_size_bytes", 0),
            "last_delivery": delivery_record or (self.get_delivery_history()[-1] if self.get_delivery_history() else None),
        }
        with open(self.metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        return saved_info
