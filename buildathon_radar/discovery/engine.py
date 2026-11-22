from __future__ import annotations

import concurrent.futures
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from buildathon_radar.discovery.adapters import ADAPTER_REGISTRY
from buildathon_radar.discovery.deduplicator import Deduplicator
from buildathon_radar.rule_engine import classify_and_score_event, load_profile
from buildathon_radar.tracker_store import (
    connect,
    get_discovery_sources,
    log_discovery_scan,
    update_discovery_source_status,
    upsert_events,
)

logger = logging.getLogger("buildathon_radar.discovery.engine")


class DiscoveryEngine:
    """Orchestrates multi-source hackathon discovery, parallel adapter execution,
    tolerant fault isolation, deduplication, student scoring, and persistence.
    """

    def __init__(self, db_path: Optional[str | Path] = None, max_workers: int = 8, timeout: int = 12):
        self.db_path = db_path
        self.max_workers = max_workers
        self.timeout = timeout
        self.deduplicator = Deduplicator()

    def _execute_adapter(self, source_key: str, adapter_cls: Any) -> Tuple[str, List[Dict[str, Any]], Optional[str]]:
        """Safely executes an adapter with fault isolation."""
        try:
            adapter = adapter_cls(timeout=self.timeout)
            items, err = adapter.fetch()
            return source_key, items or [], err
        except Exception as e:
            logger.exception("Adapter %s crashed during execution: %s", source_key, e)
            return source_key, [], str(e)

    def run_scan(
        self,
        source_keys: Optional[List[str]] = None,
        force_all: bool = False,
    ) -> Dict[str, Any]:
        """Runs discovery scan across configured sources.
        
        Args:
            source_keys: Optional list of source_keys to scan. If None, scans all enabled sources.
            force_all: If True, scans all registered sources regardless of enabled flag.
            
        Returns:
            Dict containing scan results, timings, source statistics, and event counts.
        """
        start_time = time.time()
        conn = connect(self.db_path)

        try:
            # 1. Fetch source configurations from DB
            db_sources = get_discovery_sources(conn)
            source_map = {s["source_key"]: s for s in db_sources}

            # Filter target sources
            targets = []
            for key, adapter_cls in ADAPTER_REGISTRY.items():
                if source_keys and key not in source_keys:
                    continue
                db_cfg = source_map.get(key)
                if force_all or (db_cfg and db_cfg.get("enabled", 1)):
                    targets.append((key, adapter_cls))

            total_sources = len(targets)
            all_raw_events: List[Dict[str, Any]] = []
            source_stats: Dict[str, Any] = {}
            successful_sources = 0
            failed_sources = 0

            # 2. Concurrently execute adapters with ThreadPoolExecutor
            logger.info("Starting discovery scan across %d sources with max_workers=%d", total_sources, self.max_workers)
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                future_to_source = {
                    executor.submit(self._execute_adapter, key, cls): key
                    for key, cls in targets
                }

                for future in concurrent.futures.as_completed(future_to_source):
                    key = future_to_source[future]
                    try:
                        s_key, items, err = future.result()
                    except Exception as e:
                        s_key, items, err = key, [], str(e)

                    now_str = datetime.now(timezone.utc).isoformat()
                    if err:
                        failed_sources += 1
                        update_discovery_source_status(
                            conn,
                            source_key=s_key,
                            success=False,
                            events_count=0,
                            error=err,
                        )
                        source_stats[s_key] = {
                            "status": "failed",
                            "events": 0,
                            "error": err,
                        }
                    else:
                        successful_sources += 1
                        update_discovery_source_status(
                            conn,
                            source_key=s_key,
                            success=True,
                            events_count=len(items),
                            error=None,
                        )
                        source_stats[s_key] = {
                            "status": "success",
                            "events": len(items),
                            "error": None,
                        }
                        all_raw_events.extend(items)

            # 3. Deduplicate events
            deduped_events = self.deduplicator.deduplicate(all_raw_events)

            # 4. Score and classify events with student profile
            profile = load_profile()
            eval_map: Dict[str, Dict[str, Any]] = {}
            for item in deduped_events:
                eid = item.get("event_id")
                if eid:
                    res = classify_and_score_event(item, profile)
                    eval_map[eid] = res

            # 5. Check existing event IDs to compute new vs updated counts
            cur = conn.execute("SELECT event_id FROM events")
            existing_eids = {row["event_id"] for row in cur.fetchall()}

            new_events_count = sum(1 for e in deduped_events if e.get("event_id") not in existing_eids)
            updated_events_count = len(deduped_events) - new_events_count

            # 6. Upsert into database
            upsert_events(conn, deduped_events, eval_map)

            duration = round(time.time() - start_time, 2)

            # 7. Log discovery scan to SQLite
            scan_record = {
                "duration_seconds": duration,
                "total_sources": total_sources,
                "successful_sources": successful_sources,
                "failed_sources": failed_sources,
                "new_events": new_events_count,
                "updated_events": updated_events_count,
                "details": {
                    "source_stats": source_stats,
                    "raw_events_count": len(all_raw_events),
                    "deduped_events_count": len(deduped_events),
                },
            }
            scan_id = log_discovery_scan(conn, scan_record)

            return {
                "scan_id": scan_id,
                "duration_seconds": duration,
                "total_sources": total_sources,
                "successful_sources": successful_sources,
                "failed_sources": failed_sources,
                "new_events": new_events_count,
                "updated_events": updated_events_count,
                "raw_events_count": len(all_raw_events),
                "deduped_events_count": len(deduped_events),
                "source_stats": source_stats,
            }
        finally:
            conn.close()
