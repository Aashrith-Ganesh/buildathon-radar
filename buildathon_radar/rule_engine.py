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
            "scoring": {"theme": 0, "geo": 0, "host": 0, "format": 0, "team": 0},
            "why": f"Ineligible: {elig_why}",
            "item": item
        }

    theme_score, theme_why = score_theme(item, profile)
    geo_score, geo_why = score_geography(item, profile)
    host_score, host_why = score_host_and_signal(item)
    format_score, team_score, fmt_why = score_format_and_team(item, profile)

    total_score = theme_score + geo_score + host_score + format_score + team_score
    total_score = min(100, max(0, total_score))

    # Priority determination
    thresholds = profile.get("tier_thresholds", {"high_priority": 70, "medium_priority": 45, "low_priority": 25})

    # Event relevance is separated from eligibility confidence:
    # High-relevance opportunities retain their true score and high priority
    # so that unknown eligibility does not bury exceptional events.
    if total_score >= thresholds.get("high_priority", 70):
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

    why_parts = [theme_why, geo_why, elig_why]
    why = " | ".join([p for p in why_parts if p])

    return {
        "url": item.get("url"),
        "title": item.get("title"),
        "priority": priority,
        "tier": tier,
        "score": total_score,
        "eligibility": eligibility,
        "age_restrictions": age_restrictions,
        "scoring": {
            "theme": theme_score,
            "geo": geo_score,
            "host": host_score,
            "format": format_score,
            "team": team_score
        },
        "why": why,
        "item": item
    }


def filter_and_rank_events(items: List[Dict[str, Any]], max_picks: int = 15) -> Dict[str, Any]:
    """Filters, scores, and ranks events rule-based without any external paid LLM."""
    profile = load_profile()
    scored_picks = []
    skipped_count = 0

    for item in items:
        evaluated = classify_and_score_event(item, profile)
        if evaluated["priority"] == "INELIGIBLE":
            skipped_count += 1
            continue
        scored_picks.append(evaluated)

    # Sort descending by score, tie-breaking on in-person Bengaluru and eligibility
    def sort_key(p):
        is_high = 1 if p["priority"] == "HIGH PRIORITY" else 0
        is_elig = 1 if p["eligibility"] == "ELIGIBLE" else 0
        return (is_high, is_elig, p["score"])

    scored_picks.sort(key=sort_key, reverse=True)

    picks = scored_picks[:max_picks]
    skipped_count += max(0, len(scored_picks) - max_picks)

    high_count = sum(1 for p in picks if p["priority"] == "HIGH PRIORITY")
    med_count = sum(1 for p in picks if p["priority"] == "MEDIUM PRIORITY")

    week_note = (
        f"Curated {len(picks)} opportunities for Class 11/12 student: "
        f"{high_count} high-priority, {med_count} requiring eligibility verification."
    )

    return {
        "picks": picks,
        "all_evaluated": scored_picks,
        "skipped_count": skipped_count,
        "week_note": week_note
    }
