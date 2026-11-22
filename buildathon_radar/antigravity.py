"""Antigravity Integration Layer for Buildathon Radar.

Provides a read-only query and reasoning interface for Antigravity (or local CLI)
to inspect the SQLite event database, analyze opportunities, evaluate Class 11/12 eligibility,
compare events, detect date conflicts, and generate personalized reports on demand.

Works completely independently of background services and requires NO paid LLM APIs.
"""

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from buildathon_radar import tracker_store
from buildathon_radar.rule_engine import assess_eligibility, load_profile

IST = timezone(timedelta(hours=5, minutes=30))


def _get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    return tracker_store.connect(db_path)


def inspect_database(
    db_path: Optional[str] = None,
    priority: Optional[str] = None,
    state: Optional[str] = None,
    eligibility: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """1. Inspect the event database with flexible filters."""
    conn = _get_connection(db_path)
    try:
        rows = tracker_store.get_events_by_filter(
            conn, priority=priority, state=state, eligibility=eligibility, search=search, limit=limit
        )
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_database_summary(db_path: Optional[str] = None) -> Dict[str, Any]:
    """Overview statistics of the event database."""
    conn = _get_connection(db_path)
    try:
        total = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        by_priority = dict(conn.execute(
            "SELECT COALESCE(priority, 'UNKNOWN'), COUNT(*) FROM events GROUP BY priority"
        ).fetchall())
        by_state = dict(conn.execute(
            "SELECT state, COUNT(*) FROM events GROUP BY state"
        ).fetchall())
        by_eligibility = dict(conn.execute(
            "SELECT COALESCE(eligibility, 'UNKNOWN'), COUNT(*) FROM events GROUP BY eligibility"
        ).fetchall())
        by_source = dict(conn.execute(
            "SELECT source, COUNT(*) FROM events GROUP BY source"
        ).fetchall())
        blackout_excluded = conn.execute("SELECT COUNT(*) FROM events WHERE blackout_conflict = 1").fetchone()[0]
        return {
            "total_events": total,
            "by_priority": by_priority,
            "by_state": by_state,
            "by_eligibility": by_eligibility,
            "by_source": by_source,
            "blackout_excluded": blackout_excluded,
        }
    finally:
        conn.close()


def analyze_event(event_id: str, db_path: Optional[str] = None) -> Dict[str, Any]:
    """2. Analyse discovered hackathon in detail for an Indian high-school student."""
    conn = _get_connection(db_path)
    try:
        row = conn.execute("SELECT * FROM events WHERE event_id = ?", (event_id,)).fetchone()
        if not row:
            return {"error": f"Event '{event_id}' not found"}

        item = dict(row)
        profile = load_profile()
        elig, age_restr, elig_why = assess_eligibility(item, profile)

        # Logistics assessment
        mode = (item.get("mode") or "").lower()
        location = item.get("location") or "Unknown"
        is_bengaluru = any(k in location.lower() for k in ["bengaluru", "bangalore", "karnataka"])

        logistics = {
            "is_local_bengaluru": is_bengaluru,
            "mode": mode,
            "practicality": "High (Local)" if is_bengaluru else ("High (Online)" if mode == "online" else "Requires Travel"),
        }

        return {
            "event_id": item["event_id"],
            "title": item["title"],
            "host": item["host"],
            "url": item["url"],
            "source": item["source"],
            "priority": item["priority"],
            "score": item["score"],
            "dates": {
                "start": item["event_start"],
                "end": item["event_end"],
                "registration_deadline": item["registration_deadline"],
            },
            "eligibility_analysis": {
                "verdict": elig,
                "age_restrictions": age_restr,
                "explanation": elig_why,
            },
            "team_size": item["team_size"],
            "logistics": logistics,
            "summary": item["summary"],
            "why_participate": item["why"],
        }
    finally:
        conn.close()


def evaluate_eligibility_for_class_11(event_id: str, db_path: Optional[str] = None) -> Dict[str, Any]:
    """3. Evaluate eligibility specifically for a Class 11 student (minor, age 16-17)."""
    analysis = analyze_event(event_id, db_path)
    if "error" in analysis:
        return analysis

    elig = analysis["eligibility_analysis"]
    verdict = elig["verdict"]

    action_needed = "None; registration can proceed."
    if verdict == "UNKNOWN":
        action_needed = "Manual verification required: check official event Discord/FAQ or email organizer to confirm if high schoolers/minors are permitted."
    elif verdict == "INELIGIBLE":
        action_needed = "Do not apply; event restricts participation to college undergraduates or 18+ adults."

    return {
        "event_id": analysis["event_id"],
        "title": analysis["title"],
        "student_grade": "Class 11 (High School / Minor)",
        "verdict": verdict,
        "age_restrictions": elig["age_restrictions"],
        "reasoning": elig["explanation"],
        "action_required": action_needed,
    }


def detect_suspicious_or_incomplete(db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """4. Identify suspicious or incomplete event listings."""
    conn = _get_connection(db_path)
    try:
        rows = conn.execute("SELECT * FROM events WHERE state != 'rejected'").fetchall()
        flagged = []
        for r in rows:
            issues = []
            if not r["url"] or r["url"] == "Unknown":
                issues.append("Missing or invalid URL")
            if not r["host"] or r["host"] == "Unknown":
                issues.append("Unknown or unverified organizer")
            if not r["event_start"]:
                issues.append("Missing event start date")
            if not r["summary"] or len(r["summary"].strip()) < 20:
                issues.append("Extremely sparse description")
            if r["eligibility"] == "UNKNOWN":
                issues.append("Eligibility unverified")

            if len(issues) >= 2 or ("Missing or invalid URL" in issues):
                flagged.append({
                    "event_id": r["event_id"],
                    "title": r["title"],
                    "url": r["url"],
                    "source": r["source"],
                    "issues": issues,
                    "confidence": "Low" if len(issues) >= 3 else "Moderate",
                })
        return flagged
    finally:
        conn.close()


def compare_events(event_ids: List[str], db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """5. Compare events side-by-side based on relevance and quality."""
    results = []
    for eid in event_ids:
        info = analyze_event(eid, db_path)
        if "error" not in info:
            results.append(info)
    return results


def explain_event_value(event_id: str, db_path: Optional[str] = None) -> str:
    """6. Explain why an event is worth participating in."""
    info = analyze_event(event_id, db_path)
    if "error" in info:
        return f"Event not found: {event_id}"

    title = info["title"]
    score = info["score"]
    priority = info["priority"]
    host = info["host"]
    why = info["why_participate"]
    elig = info["eligibility_analysis"]["verdict"]
    mode = info["logistics"]["mode"]
    loc = "Bengaluru (Local)" if info["logistics"]["is_local_bengaluru"] else info["logistics"]["mode"]

    explanation = (
        f"### {title}\n"
        f"**Priority:** {priority} (Score: {score}/100)\n"
        f"**Host:** {host} | **Format:** {mode.title()} ({loc})\n"
        f"**Student Eligibility:** {elig}\n\n"
        f"**Strategic Value:**\n"
        f"{why}\n\n"
        f"**Practical Recommendation:**\n"
    )

    if priority == "HIGH PRIORITY" and elig == "ELIGIBLE":
        explanation += "Strongly recommended for your portfolio and hands-on builder experience. Form a 3-5 person team and register."
    elif elig == "UNKNOWN":
        explanation += "Good potential opportunity, but confirm with the organizer whether Class 11 students may submit before committing significant building time."
    else:
        explanation += "Review dates and team availability before deciding."

    return explanation


def get_deadlines(db_path: Optional[str] = None, limit: int = 15) -> List[Dict[str, Any]]:
    """7. Identify upcoming registration deadlines sorted chronologically."""
    conn = _get_connection(db_path)
    try:
        rows = tracker_store.get_upcoming_deadlines(conn, limit=limit)
        today = datetime.now(IST).date()
        result = []
        for r in rows:
            deadline_str = r["registration_deadline"] or r["event_start"]
            days_left = None
            if deadline_str:
                try:
                    d_date = datetime.strptime(deadline_str[:10], "%Y-%m-%d").date()
                    days_left = (d_date - today).days
                except Exception:
                    pass

            result.append({
                "event_id": r["event_id"],
                "title": r["title"],
                "deadline": deadline_str,
                "days_remaining": days_left,
                "priority": r["priority"],
                "url": r["url"],
            })
        return result
    finally:
        conn.close()


def detect_overlapping_dates(db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """8. Compare overlapping event dates among high-priority and shortlisted events."""
    conn = _get_connection(db_path)
    try:
        rows = conn.execute(
            """
            SELECT event_id, title, event_start, event_end, priority, state
            FROM events
            WHERE event_start IS NOT NULL
              AND state IN ('tracked', 'applied', 'seen')
              AND priority IN ('HIGH PRIORITY', 'MEDIUM PRIORITY')
            ORDER BY event_start ASC
            """
        ).fetchall()

        events = [dict(r) for r in rows]
        overlaps = []
        for i in range(len(events)):
            for j in range(i + 1, len(events)):
                e1 = events[i]
                e2 = events[j]
                s1, e1_end = e1["event_start"], e1["event_end"] or e1["event_start"]
                s2, e2_end = e2["event_start"], e2["event_end"] or e2["event_start"]

                if s1 <= e2_end and s2 <= e1_end:
                    overlaps.append({
                        "event_a": {"id": e1["event_id"], "title": e1["title"], "dates": f"{s1} to {e1_end}", "priority": e1["priority"]},
                        "event_b": {"id": e2["event_id"], "title": e2["title"], "dates": f"{s2} to {e2_end}", "priority": e2["priority"]},
                        "conflict_window": f"{max(s1, s2)} to {min(e1_end, e2_end)}",
                    })
        return overlaps
    finally:
        conn.close()


def recommend_events(db_path: Optional[str] = None, limit: int = 10, exclude_conflicts: bool = False) -> List[Dict[str, Any]]:
    """9. Recommend suitable events ranked for an Indian high school student."""
    conn = _get_connection(db_path)
    try:
        query = """
            SELECT * FROM events
            WHERE state != 'rejected'
              AND priority != 'INELIGIBLE'
        """
        if exclude_conflicts:
            query += " AND blackout_conflict = 0"
        query += """
            ORDER BY
              CASE WHEN priority = 'HIGH PRIORITY' THEN 1
                   WHEN priority = 'MEDIUM PRIORITY' THEN 2
                   ELSE 3 END,
              score DESC
            LIMIT ?
        """
        rows = conn.execute(query, (limit,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def generate_opportunity_report(db_path: Optional[str] = None, output_path: Optional[str] = None) -> str:
    """10. Generate personalised hackathon opportunity report in clean Markdown."""
    summary = get_database_summary(db_path)
    recommendations = recommend_events(db_path, limit=12)
    deadlines = get_deadlines(db_path, limit=8)
    overlaps = detect_overlapping_dates(db_path)

    now_str = datetime.now(IST).strftime("%B %d, %Y (%I:%M %p IST)")

    lines = [
        "# 🛰️ Buildathon Radar Opportunity Report",
        f"*Generated on {now_str} for Indian High-School Student (Class 11/12)*",
        "",
        "## 📊 Discovery Overview",
        f"- **Total Tracked Opportunities:** {summary['total_events']}",
        f"- **High Priority (Student-Eligible & Local/Global):** {summary['by_priority'].get('HIGH PRIORITY', 0)}",
        f"- **Needs Eligibility Verification:** {summary['by_priority'].get('MEDIUM PRIORITY', 0)}",
        f"- **Currently Shortlisted:** {summary['by_state'].get('tracked', 0)}",
        f"- **Applied:** {summary['by_state'].get('applied', 0)}",
        "",
        "## 🔥 Top Curated Recommendations",
        "",
    ]

    for p in recommendations:
        title = p["title"]
        url = p["url"]
        host = p["host"] or "Community"
        loc = p["location"] or "Online"
        mode = p["mode"] or "unknown"
        start = p["event_start"] or "TBD"
        score = p["score"]
        priority = p["priority"]
        elig = p["eligibility"]
        why = p["why"] or "Strong thematic alignment."
        badge = "🔥 [HIGH]" if priority == "HIGH PRIORITY" else "👀 [MEDIUM]"

        lines.extend([
            f"### {badge} [{title}]({url})",
            f"**Host:** {host} &middot; **Location:** {loc} ({mode}) &middot; **Starts:** {start}",
            f"**Score:** {score}/100 &middot; **Eligibility:** {elig}",
            f"> {why}",
            "",
        ])

    if deadlines:
        lines.extend([
            "## ⏰ Upcoming Registration Deadlines",
            "",
            "| Event | Deadline | Days Left | Priority |",
            "|---|---|---|---|",
        ])
        for d in deadlines:
            dl_str = d["deadline"] or "TBD"
            days = f"{d['days_remaining']} days" if d["days_remaining"] is not None else "Soon"
            lines.append(f"| [{d['title']}]({d['url']}) | {dl_str} | {days} | {d['priority']} |")
        lines.append("")

    if overlaps:
        lines.extend([
            "## ⚠️ Schedule Conflicts / Overlapping Dates",
            "",
        ])
        for o in overlaps[:5]:
            lines.append(
                f"- **Conflict ({o['conflict_window']}):** '{o['event_a']['title']}' vs '{o['event_b']['title']}'"
            )
        lines.append("")

    report_content = "\n".join(lines)

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(report_content)

    return report_content
