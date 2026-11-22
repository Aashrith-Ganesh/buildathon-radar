from __future__ import annotations

import difflib
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from buildathon_radar.discovery.models import normalize_title, normalize_url

logger = logging.getLogger("buildathon_radar.discovery.deduplicator")

SOURCE_PRIORITY = {
    "Indian Engineering Colleges & Tech Fests": 100,
    "Top AI Companies & Indian Startups": 95,
    "Google Developer Groups (GDG & GDSC)": 90,
    "Microsoft Reactor Bengaluru": 90,
    "AWS User Groups India": 90,
    "Devfolio": 85,
    "Devpost": 85,
    "Unstop": 85,
    "Major League Hacking (MLH)": 85,
    "HackerEarth": 80,
    "Hack2skill": 80,
    "DoraHacks": 80,
    "ETHGlobal": 80,
    "Hackathon.com": 75,
    "FOSS United": 75,
    "CNCF Community Groups": 75,
    "Meetup Bangalore Tech": 65,
    "Eventbrite India": 65,
    "Townscript": 65,
    "AllEvents Bangalore": 60,
    "10times": 60,
    "LinkedIn Announcements": 55,
    "Reddit Developer Communities": 50,
    "X (Twitter) Announcements": 50,
    "Targeted Web Search Engine Discovery": 40,
}


def _dates_compatible(d1: Optional[str], d2: Optional[str]) -> bool:
    """True if either date is missing, or they are within 2 days of each other."""
    if not d1 or not d2:
        return True
    try:
        dt1 = datetime.strptime(d1[:10], "%Y-%m-%d")
        dt2 = datetime.strptime(d2[:10], "%Y-%m-%d")
        return abs((dt1 - dt2).days) <= 2
    except Exception:
        return d1[:7] == d2[:7]  # Same year and month


def _title_similarity(t1: str, t2: str) -> float:
    """Calculates token overlap and sequence similarity between two normalized titles."""
    norm1 = normalize_title(t1).replace("bangalore", "bengaluru")
    norm2 = normalize_title(t2).replace("bangalore", "bengaluru")
    if not norm1 or not norm2:
        return 0.0
    if norm1 == norm2:
        return 1.0

    # Token overlap (Jaccard)
    words1 = set(norm1.split())
    words2 = set(norm2.split())
    # Remove generic filler words
    stop = {"the", "a", "an", "and", "or", "in", "at", "for", "of", "to", "blr", "bangalore", "india", "hackathon", "challenge"}
    w1 = words1 - stop
    w2 = words2 - stop

    if w1 and w2:
        overlap = len(w1 & w2) / len(w1 | w2)
        if overlap >= 0.65:
            return overlap

    # Fallback to string similarity ratio
    return difflib.SequenceMatcher(None, norm1, norm2).ratio()


def are_duplicates(e1: Dict[str, Any], e2: Dict[str, Any]) -> bool:
    """Determines whether two raw or normalized event items represent the same event."""
    d1, d2 = e1.get("event_start"), e2.get("event_start")
    if d1 and d2 and not _dates_compatible(d1, d2):
        return False
    title1, title2 = e1.get("title") or "", e2.get("title") or ""
    years1, years2 = (set(re.findall(r"\b20\d{2}\b", title)) for title in (title1, title2))
    if years1 and years2 and years1 != years2:
        return False
    loc1, loc2 = (normalize_title(e.get("location") or "").replace("bangalore", "bengaluru") for e in (e1, e2))
    if loc1 not in {"", "unknown", "online", "india"} and loc2 not in {"", "unknown", "online", "india"}:
        if loc1 not in loc2 and loc2 not in loc1:
            return False
    for field in ("url", "announcement_url", "registration_url"):
        first, second = (normalize_url(e.get(field) or "") for e in (e1, e2))
        if first and first == second:
            return True
    host1, host2 = (normalize_title(e.get("host") or "") for e in (e1, e2))
    return bool(
        d1 and d2 and host1 and host1 not in {"unknown", "community"}
        and host1 == host2 and len(normalize_title(title1).split()) > 2
        and _title_similarity(title1, title2) >= 0.85
    )


def merge_event_records(existing: Dict[str, Any], new_item: Dict[str, Any]) -> Dict[str, Any]:
    """Merges a newly discovered sighting into an existing event, updating discovery sources
    and selecting the most reliable primary source and official URL.
    """
    merged = dict(existing)

    # 1. Discovery sources preservation
    sources: List[Dict[str, Any]] = list(merged.get("discovery_sources") or [])
    new_source_name = new_item.get("source") or "Unknown"
    new_source_url = new_item.get("url") or ""
    new_ann_url = new_item.get("announcement_url") or ""

    # Ensure existing primary is represented in discovery_sources
    if not sources and merged.get("source"):
        sources.append({
            "source_name": merged["source"],
            "url": merged.get("url", ""),
            "announcement_url": merged.get("announcement_url", ""),
            "confidence": merged.get("confidence", "Medium"),
        })

    incoming = new_item.get("discovery_sources") or [{
        "source_name": new_source_name,
        "url": new_source_url,
        "announcement_url": new_ann_url,
        "confidence": new_item.get("confidence", "Medium"),
    }]
    for entry in incoming:
        if entry not in sources:
            sources.append(entry)
    merged["discovery_sources"] = sources

    # 2. Primary Source / URL selection based on authoritative priority
    existing_prio = SOURCE_PRIORITY.get(merged.get("source", ""), 50)
    new_prio = SOURCE_PRIORITY.get(new_item.get("source", ""), 50)

    if new_prio > existing_prio:
        merged["source"] = new_item.get("source")
        if new_item.get("url"):
            merged["url"] = new_item.get("url")
        if new_item.get("host") and new_item.get("host") != "Community":
            merged["host"] = new_item.get("host")
        if new_item.get("summary"):
            merged["summary"] = new_item.get("summary")

    # 3. Fill in missing details
    for field in ["event_start", "event_end", "registration_deadline", "location", "mode", "team_size", "prize", "host"]:
        if not merged.get(field) and new_item.get(field):
            merged[field] = new_item[field]

    if existing.get("registration_status") == "closed" or new_item.get("registration_status") == "closed":
        merged["registration_status"] = "closed"
    elif new_item.get("registration_status") == "open":
        merged["registration_status"] = "open"
    eligibility_text = dict.fromkeys(
        text for text in (existing.get("eligibility_rules"), new_item.get("eligibility_rules"))
        if isinstance(text, str) and text
    )
    if eligibility_text:
        merged["eligibility_rules"] = "\n".join(eligibility_text)

    for field in ("image_url", "country", "registration_url", "participation_fee"):
        if not merged.get(field) and new_item.get(field):
            merged[field] = new_item[field]

    # 4. Tech categories union
    existing_cats = set(merged.get("tech_categories") or [])
    new_cats = set(new_item.get("tech_categories") or [])
    merged["tech_categories"] = sorted(list(existing_cats | new_cats))

    # 5. Verification status upgrade (verified > partially_verified > unverified)
    status_order = {"verified": 3, "partially_verified": 2, "unverified": 1, "expired": 0}
    curr_stat = merged.get("verification_status", "unverified")
    new_stat = new_item.get("verification_status", "unverified")
    if status_order.get(new_stat, 0) > status_order.get(curr_stat, 0):
        merged["verification_status"] = new_stat

    return merged


class Deduplicator:
    """Manages collection-wide deduplication of discovered events."""

    def deduplicate(self, raw_events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        deduped: List[Dict[str, Any]] = []

        for item in raw_events:
            match_index = -1
            for idx, existing in enumerate(deduped):
                if are_duplicates(existing, item):
                    match_index = idx
                    break

            if match_index >= 0:
                deduped[match_index] = merge_event_records(deduped[match_index], item)
            else:
                event_copy = dict(item)
                # Initialize discovery_sources list
                if not event_copy.get("discovery_sources"):
                    event_copy["discovery_sources"] = [{
                        "source_name": event_copy.get("source", "Unknown"),
                        "url": event_copy.get("url", ""),
                        "announcement_url": event_copy.get("announcement_url", ""),
                        "confidence": event_copy.get("confidence", "Medium"),
                    }]
                deduped.append(event_copy)

        return deduped
