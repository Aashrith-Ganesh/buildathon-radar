#!/usr/bin/env python3
"""Buildathon Radar - Automated Weekly Digest Pipeline Runner.

Orchestrates:
1. Persistent state restoration
2. Discovery engine execution
3. Student eligibility and blackout filtering
4. Weekly digest JSON generation
5. Payload validation & duplicate detection
6. Authenticated webhook submission to Google Apps Script
7. Persistent state updates and delivery audit logging
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from buildathon_radar import tracker_store
from buildathon_radar.discovery.engine import DiscoveryEngine
from buildathon_radar.digest import generate_digest_data
from buildathon_radar.state_manager import StateManager
from buildathon_radar.webhook_client import (
    WebhookClient,
    WebhookDeliveryError,
    compute_payload_hash,
    validate_digest_payload,
)

IST = timezone(timedelta(hours=5, minutes=30))
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("buildathon_radar.runner")


def write_github_step_summary(
    digest_data: dict,
    delivery_result: dict,
    scan_result: dict | None,
    dry_run: bool,
) -> None:
    """Appends a Markdown summary to $GITHUB_STEP_SUMMARY for GitHub Actions."""
    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return

    meta = digest_data.get("meta", {})
    featured = digest_data.get("featured_hackathons", [])
    deadlines = digest_data.get("upcoming_deadlines", [])
    blackout = digest_data.get("blackout_calendar", {})

    status_badge = "🟡 DRY-RUN" if dry_run else ("🟢 DELIVERED" if delivery_result.get("status") == "success" else f"⚪ {delivery_result.get('status', 'UNKNOWN').upper()}")

    lines = [
        f"## 🛰️ Buildathon Radar Weekly Digest — {status_badge}",
        f"**Date:** {meta.get('date_display', 'N/A')} ({meta.get('date_range', '')})",
        f"**Delivery ID:** `{delivery_result.get('delivery_id', 'N/A')}`",
        f"**Recipient:** `{delivery_result.get('recipient', os.getenv('RECIPIENT_EMAIL', 'Default'))}`",
        "",
        "### 📊 Execution Statistics",
        f"- **Featured Opportunities:** {len(featured)}",
        f"- **Upcoming Deadlines:** {len(deadlines)}",
        f"- **Blackout Conflicts Safely Avoided:** {blackout.get('conflicts_excluded_count', 0)}",
    ]

    if scan_result:
        lines.extend([
            f"- **Sources Scanned:** {scan_result.get('successful_sources', 0)}/{scan_result.get('total_sources', 0)} successful",
            f"- **New Events Discovered:** {scan_result.get('new_events', 0)}",
            f"- **Events Updated:** {scan_result.get('updated_events', 0)}",
        ])

    lines.extend([
        "",
        "### 🔥 Featured Hackathons",
        "| Score | Title | Mode & Location | Dates | Eligibility |",
        "| :---: | :--- | :--- | :--- | :--- |",
    ])

    for f in featured:
        loc = f.get("location", "Unknown")
        mode = f.get("mode", "").upper()
        elig = f.get("eligibility_label", f.get("eligibility", ""))
        lines.append(
            f"| **{f.get('score', 0)}** | [{f.get('title', '')}]({f.get('url', '#')}) | {loc} ({mode}) | {f.get('dates_display', 'TBD')} | {elig} |"
        )

    if blackout.get("upcoming_periods"):
        lines.extend([
            "",
            "### 🛡️ Active Exam Blackout Periods",
        ])
        for bp in blackout.get("upcoming_periods", []):
            lines.append(f"- **{bp.get('dates_display')}:** {bp.get('title')} ({bp.get('reason', '')})")

    try:
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n\n")
    except Exception as e:
        logger.warning("Could not write GITHUB_STEP_SUMMARY: %s", e)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Buildathon Radar weekly digest pipeline.")
    parser.add_argument("--dry-run", action="store_true", help="Run discovery & validation without sending email or saving persistent delivery")
    parser.add_argument("--force-send", action="store_true", help="Bypass duplicate detection")
    parser.add_argument("--mock-webhook", action="store_true", help="Simulate webhook delivery response without network calls")
    parser.add_argument("--skip-discovery", action="store_true", help="Skip running discovery adapters and use existing SQLite store")
    parser.add_argument("--db-path", default="tracker.db", help="Path to SQLite database")
    parser.add_argument("--state-dir", default="state", help="Directory for persistent state")
    parser.add_argument("--output-json", help="Optional path to save generated digest JSON")
    parser.add_argument("--recipient", help="Override recipient email address")
    args = parser.parse_args()

    now_ist = datetime.now(IST)
    logger.info("=== STARTING BUILDATHON RADAR WEEKLY DIGEST PIPELINE (%s IST) ===", now_ist.strftime("%Y-%m-%d %H:%M:%S"))
    logger.info("Options: dry_run=%s, force_send=%s, mock_webhook=%s, skip_discovery=%s", args.dry_run, args.force_send, args.mock_webhook, args.skip_discovery)

    state_mgr = StateManager(state_dir=args.state_dir, db_path=args.db_path)

    # Step 1: Restore persistent state
    logger.info("Step 1: Restoring persistent state from '%s'...", args.state_dir)
    restore_info = state_mgr.restore_state()
    logger.info("State restoration complete: database_restored=%s, previous_deliveries=%d",
                restore_info["database_restored"], restore_info["previous_deliveries_count"])

    # Step 2: Execute discovery engine
    scan_result = None
    if not args.skip_discovery:
        logger.info("Step 2: Executing multi-source discovery engine on %s...", args.db_path)
        try:
            engine = DiscoveryEngine(db_path=args.db_path)
            scan_result = engine.run_scan()
            logger.info(
                "Discovery scan complete in %.2fs: %d raw, %d deduped, %d new, %d updated",
                scan_result.get("duration_seconds", 0.0),
                scan_result.get("raw_events_count", 0),
                scan_result.get("deduped_events_count", 0),
                scan_result.get("new_events", 0),
                scan_result.get("updated_events", 0),
            )
        except Exception as e:
            logger.error("Discovery engine encountered an error: %s. Continuing with existing store.", e)
    else:
        logger.info("Step 2: Discovery scan skipped by user flag.")

    # Step 3: Generate digest JSON
    logger.info("Step 3: Generating weekly digest data from %s...", args.db_path)
    conn = tracker_store.connect(args.db_path)
    try:
        digest_data = generate_digest_data(conn=conn, limit_featured=5)
    finally:
        conn.close()

    # Step 4: Validate digest payload
    logger.info("Step 4: Validating digest payload...")
    validate_digest_payload(digest_data)
    content_hash = compute_payload_hash(digest_data)
    featured_count = len(digest_data.get("featured_hackathons", []))
    delivery_id = f"radar-{now_ist.strftime('%Y%m%d-%H%M%S')}-{content_hash[:8]}"
    logger.info("Digest validated: %d featured hackathons, content_hash=%s, delivery_id=%s",
                featured_count, content_hash[:12], delivery_id)

    # Save output JSON if requested
    if args.output_json:
        Path(args.output_json).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output_json, "w", encoding="utf-8") as f:
            json.dump(digest_data, f, indent=2, ensure_ascii=False)
        logger.info("Exported digest JSON to: %s", args.output_json)

    # Step 5: Duplicate prevention check
    logger.info("Step 5: Checking for duplicate delivery...")
    if not args.force_send:
        is_dup, dup_reason = state_mgr.is_duplicate_delivery(delivery_id, content_hash)
        if is_dup:
            logger.warning("DUPLICATE PREVENTED: %s", dup_reason)
            logger.info("Exiting pipeline cleanly without re-sending.")
            write_github_step_summary(
                digest_data,
                {"status": "skipped", "delivery_id": delivery_id, "reason": dup_reason},
                scan_result,
                dry_run=args.dry_run,
            )
            return 0
    else:
        logger.info("Duplicate check bypassed via --force-send.")

    # Step 6: Dispatch to Google Apps Script Web App
    logger.info("Step 6: Preparing dispatch to Google Apps Script Web App...")
    webhook_url = os.getenv("GAS_WEB_APP_URL")
    webhook_secret = os.getenv("GAS_WEBHOOK_SECRET")
    recipient = args.recipient or os.getenv("RECIPIENT_EMAIL")

    if args.mock_webhook:
        logger.info("MOCK WEBHOOK: Simulating successful delivery confirmation from GAS...")
        delivery_result = {
            "status": "success",
            "delivery_id": delivery_id,
            "dispatched": True,
            "recipient": recipient or "mock@example.com",
            "timestamp": now_ist.isoformat(),
            "message": "Simulated delivery successful",
        }
    else:
        client = WebhookClient(webhook_url=webhook_url, webhook_secret=webhook_secret)
        try:
            delivery_result = client.send_digest(
                digest_data=digest_data,
                delivery_id=delivery_id,
                dry_run=args.dry_run,
                recipient_override=recipient,
                force_send=args.force_send,
            )
        except WebhookDeliveryError as err:
            logger.error("FATAL: Webhook submission failed: %s", err)
            return 1

    # Step 7: Record persistent state
    if not args.dry_run and delivery_result.get("status") == "success":
        logger.info("Step 7: Recording delivery in persistent state...")
        rec = state_mgr.record_delivery(
            delivery_id=delivery_id,
            content_hash=content_hash,
            status="success",
            recipient=delivery_result.get("recipient", recipient or "unknown"),
            featured_count=featured_count,
            meta=digest_data.get("meta"),
            raw_response=delivery_result,
        )
        saved = state_mgr.save_state(digest_data=digest_data, delivery_record=rec)
        logger.info("State saved: %s", saved)
    else:
        logger.info("Step 7: State persistence skipped (dry_run=%s, status=%s).", args.dry_run, delivery_result.get("status"))

    # Step 8: Write summary
    write_github_step_summary(digest_data, delivery_result, scan_result, dry_run=args.dry_run)

    logger.info("=== BUILDATHON RADAR PIPELINE COMPLETED SUCCESSFULLY ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
