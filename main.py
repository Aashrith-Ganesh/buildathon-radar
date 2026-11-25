import os
import sys
from datetime import datetime

# Delegate CLI subcommands if passed (e.g. `python main.py inspect`, `summary`, etc.)
CLI_COMMANDS = {
    "inspect", "summary", "analyze", "eligibility", "deadlines",
    "overlaps", "compare", "recommend", "report", "verify", "suspicious", "backup", "digest"
}
if len(sys.argv) > 1 and sys.argv[1] in CLI_COMMANDS:
    from buildathon_radar.cli import main as cli_main
    cli_main()
    sys.exit(0)

from buildathon_radar import tracker_store
from buildathon_radar.agent import run_agent
from buildathon_radar.deliver import DeliveryStatus, get_date_range, send_digest, send_failure_email
from buildathon_radar.digest import build_digest, build_html_digest
from buildathon_radar.fetcher import fetch_events, save_cache
from buildathon_radar.guard import validate_picks
from buildathon_radar.triage import triage_items

dry_run = "--dry-run" in sys.argv
preview_email = "--preview-email" in sys.argv

try:
    print("Fetching hackathons from sources (Devpost, Devfolio, Luma, Unstop, MLH, Watchlist)...")
    items, source_health, pending_cache = fetch_events(dry_run=dry_run)
    print(f"Total items fetched before filtering: {len(items)}")

    # Triage pass (student/college events preserved)
    triaged_items, _ = triage_items(items)

    # Rule-based student evaluation & scoring (zero external LLM required)
    agent_result = run_agent(triaged_items)
    valid_picks, dropped_picks = validate_picks(agent_result["picks"], items)
    digest = build_digest(
        valid_picks, dropped_picks, source_health, agent_result["week_note"]
    )

    print("\n" + "=" * 60)
    print("BUILDATHON RADAR - WEEKLY DIGEST (STUDENT EDITION)")
    print("=" * 60 + "\n")
    print(digest)

    if dry_run:
        print("\nDRY RUN - cache not updated, database untouched, email not sent")
    else:
        tracked_events, applied_events = [], []
        try:
            tracker_conn = tracker_store.connect()
            # Store full event classifications for all discovered items into SQLite
            all_picks = agent_result.get("all_evaluated") or valid_picks
            eval_map = {}
            for p in all_picks:
                it = p.get("item")
                if it and it.get("event_id"):
                    eval_map[it["event_id"]] = p
            items_to_store = [p["item"] for p in all_picks if p.get("item")]
            if not items_to_store:
                items_to_store = [p["item"] for p in valid_picks if p.get("item")]
            tracker_store.upsert_events(tracker_conn, items_to_store, eval_map)

            today_str = datetime.now().strftime("%Y-%m-%d")
            tracked_events = tracker_store.get_tracked_open(tracker_conn, today_str)
            applied_events = tracker_store.get_applied_open(tracker_conn, today_str)
            tracker_conn.close()
        except Exception as e:
            print(f"  WARNING: Tracker store unavailable this run: {e}")
            tracked_events, applied_events = [], []

        html_digest = build_html_digest(
            valid_picks,
            dropped_picks,
            source_health,
            agent_result["week_note"],
            get_date_range(),
            tracked_events=tracked_events,
            applied_events=applied_events,
        )

        delivery = send_digest(digest, html_digest)
        if delivery in (DeliveryStatus.FAILED, False):
            raise RuntimeError("Digest delivery failed; cache left unchanged.")
        if delivery == DeliveryStatus.SKIPPED:
            print("Email notifications disabled. Digest archived locally.")

        save_cache(pending_cache)
        print("Run complete. Cache and database updated.")

    sys.exit(0)

except Exception as e:
    print(f"\nFATAL ERROR: {e}")
    if not dry_run:
        try:
            send_failure_email(str(e))
        except Exception as email_error:
            print(f"  ERROR: Could not send failure email: {email_error}")
    sys.exit(1)
