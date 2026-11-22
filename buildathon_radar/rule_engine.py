"""Rule-based filtering, classification, and scoring engine.

Customised for an Indian Class 11/12 high-school student in Bengaluru.
Replaces mandatory paid LLM APIs with transparent, configurable, explainable rules.
"""

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

PROFILE_PATH = Path(__file__).resolve().parent.parent / "config" / "profile.json"

DEFAULT_PROFILE = {
    "profile_name": "Indian High School Student (Class 11/12)",
    "target_city": "Bengaluru",
    "location_priorities": [
        {"tier": "Bengaluru", "weight": 30, "patterns": ["bengaluru", "bangalore", "karnataka"]},
        {"tier": "Other India", "weight": 20, "patterns": ["india", "delhi", "mumbai", "hyderabad", "pune", "chennai", "gurgaon", "noida"]},
        {"tier": "International Online", "weight": 14, "patterns": ["online", "virtual", "remote", "global", "worldwide"]},
        {"tier": "International In-Person", "weight": 5, "patterns": []}
    ],
    "event_format_weights": {
        "in-person": 10,
        "hybrid": 8,
        "online": 6,
        "unknown": 4
    },
    "preferred_team_size": {"min": 3, "max": 5, "bonus": 5},
    "eligibility_rules": {
        "explicit_inclusions": [
            "class 11", "class 12", "11th grade", "12th grade", "high school", "highschool",
            "school student", "k-12", "secondary school", "open to all", "minors welcome",
            "under 18", "all developers", "open competition", "anyone"
        ],
        "explicit_exclusions": [
            "18+ only", "must be 18", "must be at least 18", "strictly 18",
            "university students only", "college students only", "enrolled undergraduate",
            "undergraduates only", "working professionals only", "employees only"
        ],
    },
    "scoring_weights": {
        "theme_max": 35,
        "geography_max": 30,
        "host_and_signal_max": 20,
        "format_logistics_max": 10,
        "team_fit_bonus_max": 5
    },
    "tier_thresholds": {
        "high_priority": 70,
        "medium_priority": 45,
        "low_priority": 25
    },
    "availability": {
        "blackout_dates": [
            "2026-11-26", "2026-11-27", "2026-11-28", "2026-11-29", "2026-11-30", "2026-12-06"
        ]
    }
}


def load_profile() -> Dict[str, Any]:
    if PROFILE_PATH.exists():
        try:
            with open(PROFILE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"  WARNING: Could not load {PROFILE_PATH}: {e}, using default profile")
    return DEFAULT_PROFILE


def assess_eligibility(item: Dict[str, Any], profile: Dict[str, Any]) -> Tuple[str, str, str]:
    """Evaluates student eligibility for a Class 11/12 high-school student.

    Returns:
        (eligibility_status, age_restriction_label, explanation)
        eligibility_status: 'ELIGIBLE' | 'UNKNOWN' | 'INELIGIBLE'
    """
    text_corpus = " ".join([
        str(item.get("title") or ""),
        str(item.get("summary") or ""),
        str(item.get("host") or ""),
        str(item.get("location") or ""),
        str(item.get("eligibility") or ""),
        str(item.get("age_restrictions") or ""),
        " ".join(item.get("themes") or [])
    ]).lower()

    rules = profile.get("eligibility_rules", DEFAULT_PROFILE["eligibility_rules"])
    exclusions = rules.get("explicit_exclusions", [])
    inclusions = rules.get("explicit_inclusions", [])

    # 1. Check explicit exclusions
    for exc in exclusions:
        if re.search(r"\b" + re.escape(exc) + r"\b", text_corpus):
            return (
                "INELIGIBLE",
                "Strictly restricted (e.g. 18+ or university-only)",
                f"Explicitly excludes target age group: matched '{exc}'."
            )

    # 2. Check explicit inclusions
    matched_inclusions = []
    for inc in inclusions:
        if re.search(r"\b" + re.escape(inc) + r"\b", text_corpus):
            matched_inclusions.append(inc)

    if matched_inclusions:
        return (
            "ELIGIBLE",
            "Open to school students / minors",
            f"Class 11/12 eligible: matched '{matched_inclusions[0]}'."
        )

    # 3. College-organised hackathon check
    host_or_title = f"{item.get('host', '')} {item.get('title', '')}".lower()
    college_keywords = ["college", "university", "institute of technology", "iit", "nit", "bits", "campus", "student chapter", "ieee"]
    is_college_affiliated = any(kw in host_or_title for kw in college_keywords)

    if is_college_affiliated:
        return (
            "UNKNOWN",
            "Verification needed",
            "College-organised event; external high school participation unclear, retained for verification."
        )

    # 4. Fallback: UNKNOWN eligibility (never confuse unknown with ineligible)
    return (
        "UNKNOWN",
        "None specified",
        "No explicit age restriction published; retained for manual verification."
    )


def score_theme(item: Dict[str, Any], profile: Dict[str, Any]) -> Tuple[int, str]:
    """Score technology and theme relevance (0 to 35)."""
    text_corpus = " ".join([
        str(item.get("title") or ""),
        str(item.get("summary") or ""),
        " ".join(item.get("themes") or [])
    ]).lower()

    tech = profile.get("technology_themes", {})
    high_keywords = tech.get("high_relevance", {}).get("keywords", [
        "artificial intelligence", "ai", "machine learning", "ml", "generative ai",
        "genai", "agentic ai", "ai agents", "llm", "large language model", "rag"
    ])
    med_keywords = tech.get("medium_relevance", {}).get("keywords", [
        "software engineering", "fintech", "payments", "quantum computing", "quantum",
        "robotics", "developer tools", "devtools", "startups", "product building", "open innovation"
    ])

    high_matches = [kw for kw in high_keywords if re.search(r"\b" + re.escape(kw) + r"\b", text_corpus)]
    if high_matches:
        score = 35 if len(high_matches) >= 2 or "agentic" in high_matches or "ai" in high_matches else 30
        return score, f"Core AI/ML theme ({', '.join(high_matches[:2])})"

    med_matches = [kw for kw in med_keywords if re.search(r"\b" + re.escape(kw) + r"\b", text_corpus)]
    if med_matches:
        score = 25 if len(med_matches) >= 2 else 20
        return score, f"Target technology track ({', '.join(med_matches[:2])})"

    # Adjacent or general hackathon
    if "hackathon" in text_corpus or "buildathon" in text_corpus or "code" in text_corpus:
        return 12, "General software hackathon"

    return 5, "Low software/AI alignment"


def score_geography(item: Dict[str, Any], profile: Dict[str, Any]) -> Tuple[int, str]:
    """Score geographic practicality (0 to 30)."""
    location = (item.get("location") or "").lower()
    mode = (item.get("mode") or "").lower()

    # 1. Bengaluru (top priority)
    bengaluru_keywords = ["bengaluru", "bangalore", "karnataka", "koramangala", "indiranagar", "whitefield"]
    if any(kw in location for kw in bengaluru_keywords) or (mode == "in-person" and "bengaluru" in location):
        return 30, "In-person in Bengaluru (Top local priority)"

    # 2. Other India
    india_keywords = ["india", "delhi", "mumbai", "hyderabad", "pune", "chennai", "noida", "gurgaon", "kolkata"]
    if any(kw in location for kw in india_keywords):
        return 20, "In-person in India"

    # 3. Online
    if mode == "online" or "online" in location or "virtual" in location or "remote" in location:
        return 14, "Online competition (Globally accessible)"

    # 4. In-person international
    if mode == "in-person":
        return 5, "In-person outside India (Logistically complex)"

    return 10, "Location flexible or unspecified"


def score_host_and_signal(item: Dict[str, Any]) -> Tuple[int, str]:
    """Score organizer prestige and signal (0 to 20)."""
    host = (item.get("host") or "").lower()
    prize = (item.get("prize") or "").strip()
    themes = [t.lower() for t in item.get("themes") or []]

    score = 10
    reasons = []

    prestigious_hosts = [
        "google", "deepmind", "anthropic", "openai", "microsoft", "meta",
        "razorpay", "devfolio", "devpost", "mlh", "major league hacking",
        "nvidia", "aws", "amazon", "github", "hugging face", "cerebral valley"
    ]
    if any(ph in host for ph in prestigious_hosts):
        score += 6
        reasons.append(f"Recognised host ({item.get('host')})")

    if "cerebral valley featured" in themes:
        score += 2
        reasons.append("Featured listing")

    if prize and prize != "0" and "not listed" not in prize.lower():
        score += 4
        reasons.append("Prizes offered")

    score = min(score, 20)
    return score, " · ".join(reasons) if reasons else "Standard community host"


def score_format_and_team(item: Dict[str, Any], profile: Dict[str, Any]) -> Tuple[int, int, str]:
    """Scores event format (0 to 10) and team size fit (0 to 5 bonus)."""
    mode = (item.get("mode") or "").lower()
    format_weights = profile.get("event_format_weights", {"in-person": 10, "hybrid": 8, "online": 6, "unknown": 4})
    format_score = format_weights.get(mode, 6)

    # Team size
    team_bonus = 3  # neutral default
    team_info = item.get("team_size") or ""
    if team_info:
        # Check if 3, 4, or 5 is supported
        if re.search(r"\b[3-5]\b", str(team_info)):
            team_bonus = 5

    return format_score, team_bonus, f"Format {mode.title()}"


def assess_cost(item: Dict[str, Any]) -> str:
    """Detects whether an event has registration fees or is free.
    Returns 'FREE' or 'PAID'.
    """
    text = " ".join([
        str(item.get("title") or ""),
        str(item.get("summary") or ""),
        str(item.get("prize") or ""),
        " ".join(item.get("themes") or [])
    ]).lower()

    paid_patterns = [
        r"\bentry\s*fee\b", r"\bregistration\s*fee\b", r"\bticket\s*price\b",
        r"\btickets?\s*(?:from|at|\:|\$|inr|rs|\d+)", r"\bpaid\s*event\b",
        r"\bpaid\s*registration\b", r"\bfee\s*\:\s*(?:inr|rs|\$|[1-9]\d*)"
    ]
    is_paid = any(re.search(p, text) for p in paid_patterns)
    if "free" in text and not re.search(r"\bnot\s*free\b", text):
        if not re.search(r"\b(?:fee|ticket)\s*\:\s*(?:[1-9]\d*|inr\s*[1-9]|rs\.?\s*[1-9]|\$\s*[1-9])", text):
            is_paid = False

    return "PAID" if is_paid else "FREE"


def assess_schedule_and_blackout(
    item: Dict[str, Any], profile: Dict[str, Any]
) -> Tuple[str, bool, str]:
    """Evaluates timing (WEEKEND vs WEEKDAY) and student blackout date availability.

    Returns:
        (timing_label, is_blackout_conflict, details_explanation)
    """
    start_str = item.get("event_start")
    end_str = item.get("event_end") or start_str
    mode = (item.get("mode") or "").lower()

    # Blackout dates from profile
    avail = profile.get("availability", {})
    blackout_strs = avail.get("blackout_dates", [])
    blackout_dates = set()
    from datetime import datetime as dt_cls, timedelta as td_cls
    for b in blackout_strs:
        try:
            blackout_dates.add(dt_cls.strptime(b[:10], "%Y-%m-%d").date())
        except Exception:
            pass

    if not start_str:
        return "UNKNOWN", False, "⚠️ Dates Unverified: Schedule not published; cannot confirm availability."

    try:
        s_date = dt_cls.strptime(start_str[:10], "%Y-%m-%d").date()
        e_date = dt_cls.strptime(end_str[:10], "%Y-%m-%d").date()
        if e_date < s_date:
            s_date, e_date = e_date, s_date

        # Check date overlap with blackout window (hard exclusion for any overlap)
        has_blackout_overlap = False
        conflicting_dates = []
        cur = s_date
        while cur <= e_date:
            if cur in blackout_dates:
                has_blackout_overlap = True
                conflicting_dates.append(cur.strftime("%Y-%m-%d"))
            cur += td_cls(days=1)

        duration_days = (e_date - s_date).days + 1
        is_direct_conflict = has_blackout_overlap

        # Check weekend (Saturday or Sunday)
        is_weekend = False
        if duration_days <= 4:
            cur = s_date
            while cur <= e_date:
                if cur.weekday() in (5, 6):
                    is_weekend = True
                    break
                cur += td_cls(days=1)
        else:
            # Multi-week online competitions span weekends
            is_weekend = True

        timing = "WEEKEND" if is_weekend else "WEEKDAY"

        if is_direct_conflict:
            conflict_summary = ", ".join(conflicting_dates[:3])
            if len(conflicting_dates) > 3:
                conflict_summary += f" (+{len(conflicting_dates) - 3} more)"
            explanation = f"⚠️ Blackout Conflict: Student unavailable on {conflict_summary}"
        else:
            explanation = f"{timing.title()} schedule"

        return timing, is_direct_conflict, explanation

    except Exception:
        return "UNKNOWN", False, "⚠️ Dates Unverified: Could not parse event schedule."


def classify_and_score_event(item: Dict[str, Any], profile: Dict[str, Any] = None) -> Dict[str, Any]:
    """Classifies and scores an event against the student profile."""
    if profile is None:
        profile = load_profile()

    eligibility, age_restrictions, elig_why = assess_eligibility(item, profile)

    if eligibility == "INELIGIBLE":
        return {
            "url": item.get("url"),
            "title": item.get("title"),
            "priority": "INELIGIBLE",
            "tier": "ineligible",
            "score": 0,
            "eligibility": eligibility,
            "age_restrictions": age_restrictions,
            "cost": "FREE",
            "timing": "WEEKDAY",
            "timing_tier": 5,
            "is_conflict": False,
            "scoring": {"theme": 0, "geo": 0, "host": 0, "format": 0, "team": 0},
            "why": f"Ineligible: {elig_why}",
            "item": item
        }

    theme_score, theme_why = score_theme(item, profile)
    geo_score, geo_why = score_geography(item, profile)
    host_score, host_why = score_host_and_signal(item)
    format_score, team_score, fmt_why = score_format_and_team(item, profile)

    cost = assess_cost(item)
    timing, is_conflict, sched_why = assess_schedule_and_blackout(item, profile)

    # Cost & Timing Prioritization Hierarchy:
    # 1. Free & Weekend (Highest priority)
    # 2. Paid & Weekend
    # 3. Free & Weekday
    # 4. Paid & Weekday
    # 5. Blackout Conflict (Unavailable on 26th-30th Nov & 6th Dec)
    if is_conflict:
        timing_tier = 5
        timing_tier_label = "Unavailable (Blackout Conflict)"
        timing_bonus = -35  # Strong demotion for unavailable events
    elif cost == "FREE" and timing == "WEEKEND":
        timing_tier = 1
        timing_tier_label = "Free & Weekend (Top Priority)"
        timing_bonus = 15
    elif cost == "PAID" and timing == "WEEKEND":
        timing_tier = 2
        timing_tier_label = "Paid & Weekend"
        timing_bonus = 8
    elif cost == "FREE" and timing == "WEEKDAY":
        timing_tier = 3
        timing_tier_label = "Free & Weekday"
        timing_bonus = 4
    else:
        timing_tier = 4
        timing_tier_label = "Paid & Weekday"
        timing_bonus = 0

    total_score = theme_score + geo_score + host_score + format_score + team_score + timing_bonus
    total_score = min(100, max(0, total_score))

    # Priority determination
    thresholds = profile.get("tier_thresholds", {"high_priority": 70, "medium_priority": 45, "low_priority": 25})

    if is_conflict:
        priority = "CONFLICT (UNAVAILABLE)"
        tier = "radar"
    elif total_score >= thresholds.get("high_priority", 70):
        priority = "HIGH PRIORITY"
        tier = "must_see"
    elif total_score >= thresholds.get("medium_priority", 45):
        priority = "MEDIUM PRIORITY"
        tier = "worth_a_look"
    elif total_score >= thresholds.get("low_priority", 25):
        priority = "LOW PRIORITY"
        tier = "radar"
    else:
        priority = "LOW PRIORITY"
        tier = "radar"

    why_parts = [timing_tier_label, theme_why, geo_why, elig_why, sched_why]
    # Deduplicate similar parts
    unique_parts = []
    for p in why_parts:
        if p and p not in unique_parts:
            unique_parts.append(p)
    why = " | ".join(unique_parts)

    return {
        "url": item.get("url"),
        "title": item.get("title"),
        "priority": priority,
        "tier": tier,
        "score": total_score,
        "eligibility": eligibility,
        "age_restrictions": age_restrictions,
        "cost": cost,
        "timing": timing,
        "timing_tier": timing_tier,
        "is_conflict": is_conflict,
        "scoring": {
            "theme": theme_score,
            "geo": geo_score,
            "host": host_score,
            "format": format_score,
            "team": team_score,
            "timing_bonus": timing_bonus
        },
        "why": why,
        "item": item
    }


def filter_and_rank_events(items: List[Dict[str, Any]], max_picks: int = 15) -> Dict[str, Any]:
    """Filters, scores, and ranks events rule-based without any external paid LLM.
    Strictly orders by:
    1. Available before Blackout Conflict
    2. Free & Weekend (Rank 1) -> Paid & Weekend (Rank 2) -> Free & Weekday (Rank 3) -> Paid & Weekday (Rank 4)
    3. Relevance score descending
    4. Student eligibility confidence
    """
    profile = load_profile()
    scored_picks = []
    skipped_count = 0

    for item in items:
        evaluated = classify_and_score_event(item, profile)
        if evaluated["priority"] == "INELIGIBLE":
            skipped_count += 1
            continue
        scored_picks.append(evaluated)

    def sort_key(p):
        is_avail = 0 if p.get("is_conflict") else 1
        tier_rank = p.get("timing_tier", 3)
        score = p.get("score", 0)
        is_elig = 1 if p.get("eligibility") == "ELIGIBLE" else 0
        return (is_avail, -tier_rank, score, is_elig)

    scored_picks.sort(key=sort_key, reverse=True)

    picks = scored_picks[:max_picks]
    skipped_count += max(0, len(scored_picks) - max_picks)

    high_count = sum(1 for p in picks if p["priority"] == "HIGH PRIORITY")
    med_count = sum(1 for p in picks if p["priority"] == "MEDIUM PRIORITY")

    week_note = (
        f"Curated {len(picks)} opportunities: Free & Weekend events prioritized; "
        f"personal commitments, test dates and examination blackout periods strictly avoided."
    )

    return {
        "picks": picks,
        "all_evaluated": scored_picks,
        "skipped_count": skipped_count,
        "week_note": week_note
    }
