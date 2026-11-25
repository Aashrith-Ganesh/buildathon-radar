"""Command Line Interface for Buildathon Radar & Antigravity Analysis.
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

from buildathon_radar import antigravity, tracker_store


def main():
    parser = argparse.ArgumentParser(
        description="Buildathon Radar CLI & Antigravity Intelligence Interface"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # inspect
    inspect_parser = subparsers.add_parser("inspect", help="Inspect discovered events")
    inspect_parser.add_argument("--priority", choices=["HIGH PRIORITY", "MEDIUM PRIORITY", "LOW PRIORITY", "INELIGIBLE"], help="Filter by priority")
    inspect_parser.add_argument("--state", choices=["seen", "tracked", "applied", "rejected", "over"], help="Filter by state")
    inspect_parser.add_argument("--eligibility", choices=["ELIGIBLE", "UNKNOWN", "INELIGIBLE"], help="Filter by eligibility")
    inspect_parser.add_argument("--search", help="Search keyword in title, host, summary")
    inspect_parser.add_argument("--limit", type=int, default=20, help="Maximum events to return")
    inspect_parser.add_argument("--json", action="store_true", help="Output raw JSON")

    # summary
    subparsers.add_parser("summary", help="Show database overview statistics")

    # analyze
    analyze_parser = subparsers.add_parser("analyze", help="Detailed analysis of an event")
    analyze_parser.add_argument("event_id", help="Event ID to analyze")
    analyze_parser.add_argument("--json", action="store_true", help="Output raw JSON")

    # eligibility
    elig_parser = subparsers.add_parser("eligibility", help="Evaluate Class 11 eligibility")
    elig_parser.add_argument("event_id", help="Event ID")

    # deadlines
    deadlines_parser = subparsers.add_parser("deadlines", help="Show upcoming registration deadlines")
    deadlines_parser.add_argument("--limit", type=int, default=10, help="Max deadlines")
    deadlines_parser.add_argument("--days", type=int, default=30, help="Days ahead to check")

    # overlaps
    subparsers.add_parser("overlaps", help="Find overlapping event dates")

    # compare
    compare_parser = subparsers.add_parser("compare", help="Compare multiple events")
    compare_parser.add_argument("event_ids", nargs="+", help="Event IDs to compare")

    # recommend
    rec_parser = subparsers.add_parser("recommend", help="Get top recommended events for Class 11 student")
    rec_parser.add_argument("--limit", type=int, default=10, help="Max recommendations")

    # report
    report_parser = subparsers.add_parser("report", help="Generate full opportunity report in Markdown")
    report_parser.add_argument("--output", help="Optional output markdown file path")

    # verify / suspicious
    subparsers.add_parser("verify", help="Detect suspicious or incomplete event listings")
    subparsers.add_parser("suspicious", help="Detect suspicious or incomplete event listings")

    # backup
    backup_parser = subparsers.add_parser("backup", help="Create a timestamped backup of the database")
    backup_parser.add_argument("--dest", default="backups", help="Destination folder")

    # digest
    digest_parser = subparsers.add_parser("digest", help="Export or preview weekly digest data")
    digest_parser.add_argument("--limit", type=int, default=5, help="Max featured hackathons")
    digest_parser.add_argument("--output", help="Optional path to save digest JSON")
    digest_parser.add_argument("--json", action="store_true", help="Print raw JSON to stdout")

    # prune
    prune_parser = subparsers.add_parser("prune", help="Remove events before a cutoff date")
    prune_parser.add_argument("--before", default="2026-11-22", help="Cutoff date YYYY-MM-DD (defaults to 2026-11-22)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "inspect":
        events = antigravity.inspect_database(
            priority=args.priority,
            state=args.state,
            eligibility=args.eligibility,
            search=args.search,
            limit=args.limit
        )
        if getattr(args, "json", False):
            print(json.dumps(events, indent=2))
        else:
            print(f"\nDiscovered Events ({len(events)} matches):\n" + "=" * 70)
            for e in events:
                p = e.get("priority", "UNKNOWN")
                score = e.get("score", 0)
                title = e.get("title", "Untitled")
                host = e.get("host", "Unknown")
                start = e.get("event_start") or "TBD"
                elig = e.get("eligibility", "UNKNOWN")
                print(f"[{p}] (Score {score}) {title}")
                print(f"   ID: {e['event_id']} | Host: {host} | Starts: {start} | Eligibility: {elig}")
                print(f"   URL: {e['url']}")
                print("-" * 70)

    elif args.command == "summary":
        s = antigravity.get_database_summary()
        print("\nDatabase Summary:\n" + "=" * 50)
        print(f"Total Events: {s['total_events']}")
        print("\nBy Priority:")
        for k, v in s["by_priority"].items():
            print(f"  {k}: {v}")
        print("\nBy State:")
        for k, v in s["by_state"].items():
            print(f"  {k}: {v}")
        print("\nBy Student Eligibility:")
        for k, v in s["by_eligibility"].items():
            print(f"  {k}: {v}")
        print("\nBy Source:")
        for k, v in s["by_source"].items():
            print(f"  {k}: {v}")

    elif args.command == "analyze":
        res = antigravity.analyze_event(args.event_id)
        if getattr(args, "json", False):
            print(json.dumps(res, indent=2))
        else:
            if "error" in res:
                print(f"Error: {res['error']}")
            else:
                print(antigravity.explain_event_value(args.event_id))

    elif args.command == "eligibility":
        res = antigravity.evaluate_eligibility_for_class_11(args.event_id)
        print(json.dumps(res, indent=2))

    elif args.command == "deadlines":
        deadlines = antigravity.get_deadlines(limit=args.limit)
        print("\nUpcoming Registration Deadlines:\n" + "=" * 70)
        for d in deadlines:
            days = f"({d['days_remaining']} days left)" if d["days_remaining"] is not None else ""
            print(f"Deadline: {d['deadline']} {days}")
            print(f"  [{d['priority']}] {d['title']}")
            print(f"  URL: {d['url']}")
            print("-" * 70)

    elif args.command == "overlaps":
        overlaps = antigravity.detect_overlapping_dates()
        print("\nOverlapping Event Dates:\n" + "=" * 70)
        if not overlaps:
            print("No date conflicts found between high-priority events.")
        for o in overlaps:
            print(f"Conflict Window: {o['conflict_window']}")
            print(f"  Event A: {o['event_a']['title']} ({o['event_a']['dates']})")
            print(f"  Event B: {o['event_b']['title']} ({o['event_b']['dates']})")
            print("-" * 70)

    elif args.command == "compare":
        res = antigravity.compare_events(args.event_ids)
        print(json.dumps(res, indent=2))

    elif args.command == "recommend":
        recs = antigravity.recommend_events(limit=args.limit)
        print(f"\nTop {len(recs)} Recommended Events for Class 11/12 Student:\n" + "=" * 70)
        for r in recs:
            print(f"[{r['priority']}] Score: {r['score']} | {r['title']}")
            print(f"   Host: {r['host']} | Location: {r['location']} ({r['mode']})")
            print(f"   Eligibility: {r['eligibility']} | Dates: {r['event_start']}")
            print(f"   Why: {r['why']}")
            print(f"   URL: {r['url']}")
            print("-" * 70)

    elif args.command == "report":
        rep = antigravity.generate_opportunity_report(output_path=args.output)
        if args.output:
            print(f"Report written to: {args.output}")
        else:
            print(rep)

    elif args.command in ("verify", "suspicious"):
        susp = antigravity.detect_suspicious_or_incomplete()
        print(f"\nFlagged / Incomplete Listings ({len(susp)}):\n" + "=" * 70)
        for s in susp:
            print(f"Event: {s['title']} ({s['source']})")
            print(f"  Issues: {', '.join(s['issues'])}")
            print(f"  URL: {s['url']}")
            print("-" * 70)

    elif args.command == "backup":
        dest_dir = Path(args.dest)
        dest_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        db_file = tracker_store.DB_FILE
        if os.path.exists(db_file):
            backup_path = dest_dir / f"tracker_backup_{ts}.db"
            shutil.copy2(db_file, backup_path)
            print(f"Database backed up to: {backup_path}")
        else:
            print(f"Database {db_file} does not exist yet; nothing to backup.")

    elif args.command == "digest":
        from buildathon_radar.digest import generate_digest_data
        data = generate_digest_data(limit_featured=args.limit)
        json_str = json.dumps(data, indent=2, ensure_ascii=False)
        if args.output:
            Path(args.output).parent.mkdir(parents=True, exist_ok=True)
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(json_str)
            print(f"Digest exported to: {args.output}")
        elif args.json:
            print(json_str)
        else:
            print(f"\nBuildathon Radar Weekly Digest Data ({data['meta']['date_display']}):\n" + "=" * 70)
            print(f"Featured Opportunities: {len(data['featured_hackathons'])}")
            for f in data["featured_hackathons"]:
                print(f" - [{f['priority']}] {f['title']} ({f['location']}) | Score: {f['score']}")
            print(f"Upcoming Deadlines: {len(data['upcoming_deadlines'])}")
            print(f"Blackout Conflicts Excluded: {data['blackout_calendar']['conflicts_excluded_count']}")
            print(f"Active Blackout Periods: {len(data['blackout_calendar']['upcoming_periods'])}")
            print("Tip: Use --json for raw JSON or --output <file.json> to export.")

    elif args.command == "prune":
        conn = tracker_store.connect()
        try:
            cnt = tracker_store.delete_events_before_date(conn, args.before)
            print(f"Removed {cnt} events starting before {args.before}.")
        finally:
            conn.close()


if __name__ == "__main__":
    main()
