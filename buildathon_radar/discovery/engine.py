from __future__ import annotations

import concurrent.futures
import fcntl
import hashlib
import os
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from buildathon_radar.discovery.adapters import ADAPTER_REGISTRY, LIVE_SOURCE_KEYS
from buildathon_radar.discovery.integrity import valid_event
from buildathon_radar.discovery.enrichment import normalize, enrich
from buildathon_radar.discovery.deduplicator import Deduplicator, are_duplicates, merge_event_records
from buildathon_radar.rule_engine import classify_and_score_event, load_profile
from buildathon_radar.tracker_store import (
    connect,
    get_discovery_sources,
    log_discovery_scan,
    update_discovery_source_status,
    upsert_events,
)

logger = logging.getLogger("buildathon_radar.discovery.engine")


class ScanInProgress(RuntimeError):
    pass


class DiscoveryEngine:
    """Orchestrates multi-source hackathon discovery, parallel adapter execution,
    tolerant fault isolation, deduplication, student scoring, and persistence.
    """

    def __init__(self, db_path: Optional[str | Path] = None, max_workers: int = 8, timeout: int = 12):
        self.db_path = db_path
        self.max_workers = max_workers
        self.timeout = timeout
        self.deduplicator = Deduplicator()

    def _execute_adapter(self, source_key: str, adapter_cls: Any) -> Tuple[str, List[Dict[str, Any]], Optional[str], float]:
        """Safely executes an adapter with fault isolation."""
        started = time.monotonic()
        try:
            adapter = adapter_cls(timeout=self.timeout)
            items, err = adapter.fetch()
            return source_key, items or [], err, time.monotonic() - started
        except Exception as e:
            logger.warning("Adapter %s failed (%s)", source_key, type(e).__name__)
            return source_key, [], type(e).__name__, time.monotonic() - started

    def run_scan(self, source_keys=None, force_all=False):
        if str(self.db_path) == ":memory:":
            return self._run_scan(source_keys, force_all)
        lock_path = Path(self.db_path or "tracker.db").resolve().with_suffix(".scan.lock")
        with os.fdopen(os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600), "r+") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise ScanInProgress("A discovery scan is already running") from error
            return self._run_scan(source_keys, force_all)

    def _run_scan(
        self,
        source_keys: Optional[List[str]] = None,
        force_all: bool = False,
    ) -> Dict[str, Any]:
        """Runs discovery scan across configured sources.
        
        Args:
            source_keys: Optional list of source_keys to scan. If None, scans all enabled sources.
            force_all: If True, scans supported feeds regardless of enabled flag.
            
        Returns:
            Dict containing scan results, timings, source statistics, and event counts.
        """
        start_time = time.monotonic()
        conn = connect(self.db_path)

        try:
            # 1. Fetch source configurations from DB
            db_sources = get_discovery_sources(conn)
            source_map = {s["source_key"]: s for s in db_sources}

            # Filter target sources
            targets = []
            for key, adapter_cls in ADAPTER_REGISTRY.items():
                if key not in LIVE_SOURCE_KEYS or (source_keys is not None and key not in source_keys):
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
                        s_key, items, err, elapsed = future.result()
                    except Exception as e:
                        s_key, items, err, elapsed = key, [], type(e).__name__, 0

                    now_str = datetime.now(timezone.utc).isoformat()
                    retrieved = len(items)
                    valid = []
                    for item in items:
                        if not isinstance(item, dict):
                            continue
                        item = normalize(item)
                        if not valid_event(item):
                            continue
                        item["provenance"] = "live"
                        item["source"] = ADAPTER_REGISTRY[s_key].name
                        item["verification_status"] = "unverified"
                        item["event_id"] = "live-" + hashlib.sha256(
                            f"{s_key}|{item['url']}|{item.get('event_start') or ''}".encode()
                        ).hexdigest()[:32]
                        item["discovery_sources"] = [{
                            "source": item["source"],
                            "source_key": s_key,
                            "url": item["url"],
                            "announcement_url": item.get("announcement_url"),
                            "discovered_at": now_str,
                        }]
                        valid.append(item)
                    items = valid
                    if retrieved and not items and not err:
                        err = "Listing returned no valid records"
                    pagination = "first page only" if key in {"devfolio", "unstop", "devpost"} else "not reported"
                    incomplete = any(not item.get("event_start") for item in items)
                    degraded = bool(items and (err or retrieved != len(items) or incomplete or pagination == "first page only"))
                    status = "degraded" if degraded else "failed" if err else "ok"
                    outcome = "partial" if degraded else "invalid" if retrieved and not items else "error" if err else "valid" if items else "empty"
                    if status == "failed":
                        failed_sources += 1
                    else:
                        successful_sources += 1
                        all_raw_events.extend(items)
                    source_stats[s_key] = {
                        "status": status,
                        "outcome": outcome,
                        "events": len(items),
                        "error": err,
                        "retrieved": retrieved,
                        "rejected": retrieved - len(items),
                        "duration_seconds": round(elapsed, 3),
                        "pagination": pagination,
                        "duplicates": 0,
                    }

            conn.execute("BEGIN IMMEDIATE")
            for key, stats in source_stats.items():
                update_discovery_source_status(
                    conn, key, stats["status"] != "failed", stats["events"], stats["error"],
                    retrieved=stats["retrieved"], health=stats["status"], commit=False,
                )

            # 3. Deduplicate events
            deduped_events = self.deduplicator.deduplicate(sorted(all_raw_events, key=lambda row: row["event_id"]))
            previous = [
                dict(row) for row in conn.execute("SELECT * FROM events WHERE provenance = 'live' ORDER BY first_seen, event_id")
            ]
            for row in previous:
                row["discovery_sources"] = json.loads(row["discovery_sources"] or "[]")

            by_id = {}
            for item in deduped_events:
                matches = [
                    row for row in previous if are_duplicates(row, item)
                    or any(are_duplicates(dict(row, url=sighting.get("url")), item)
                           for sighting in row["discovery_sources"] if sighting.get("url"))
                ]
                if len(matches) == 1:
                    item["event_id"] = matches[0]["event_id"]
                eid = item["event_id"]
                by_id[eid] = merge_event_records(by_id[eid], item) if eid in by_id else item
            deduped_events = list(by_id.values())
            for key, stats in source_stats.items():
                canonical = sum(row["source"] == ADAPTER_REGISTRY[key].name for row in deduped_events)
                stats["duplicates"] = max(0, stats["events"] - canonical)
            for item in deduped_events:
                enrich(item)
            merges = [
                {"event_id": item["event_id"], "urls": sorted({
                    sighting["url"] for sighting in item["discovery_sources"] if sighting.get("url")
                })}
                for item in deduped_events if len(item["discovery_sources"]) > 1
            ]

            # 4. Score and classify events with student profile
            # The tracker calendar is authoritative for discovered events.
            profile = {**load_profile(), "availability": {}}
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

            duration = round(time.monotonic() - start_time, 2)

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
                    "merges": merges,
                    "observations": [
                        {"event_id": event["event_id"], "sources": event["discovery_sources"]}
                        for event in deduped_events
                    ],
                    "raw_events_count": len(all_raw_events),
                    "deduped_events_count": len(deduped_events),
                },
            }
            scan_id = log_discovery_scan(conn, scan_record, commit=False)
            for event in deduped_events:
                for entry in event["discovery_sources"]:
                    entry["scan_id"] = scan_id
            upsert_events(conn, deduped_events, eval_map, commit=False)
            conn.commit()

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


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Refresh listing data without sending notifications.")
    parser.add_argument("--db", default="tracker.db", help="SQLite database path")
    args = parser.parse_args()
    try:
        print(json.dumps(DiscoveryEngine(db_path=args.db).run_scan(), indent=2))
    except ScanInProgress:
        print("Scan already running")
