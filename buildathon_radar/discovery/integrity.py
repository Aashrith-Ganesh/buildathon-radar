"""Validation and lifecycle rules shared by scan ingestion and the dashboard."""
from datetime import date
from urllib.parse import urlsplit


def valid_event(item):
    if item.get("is_hackathon") is False:
        return False
    title = item.get("title")
    url = item.get("url")
    if not isinstance(title, str) or not title.strip() or len(title) > 300:
        return False
    if not isinstance(url, str) or not url or len(url) > 2048:
        return False
    try:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            return False
        dates = {
            key: date.fromisoformat(item[key]) if item.get(key) else None
            for key in ("event_start", "event_end", "registration_deadline")
        }
    except (ValueError, TypeError):
        return False
    start, end = dates["event_start"], dates["event_end"]
    return not (start and end and end < start)


def lifecycle(row, today):
    if row["provenance"] != "live":
        return "Unverified history"
    start, end, deadline = (row[key] for key in ("event_start", "event_end", "registration_deadline"))
    if (end or start) and (end or start) < today:
        return "Completed"
    if deadline and deadline < today:
        return "Registration closed"
    if row["registration_status"] == "open" and (not deadline or deadline >= today):
        return "Registration open"
    if row["registration_status"] == "closed":
        return "Registration closed"
    return "Upcoming" if start and start >= today else "Discovered"
