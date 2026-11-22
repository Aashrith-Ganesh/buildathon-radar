"""Conservative local enrichment of source-provided event fields."""
import html
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

THEMES = {
    "AI/ML": r"\b(?:AI|ML|GenAI|LLM|machine learning|artificial intelligence)\b",
    "Agentic AI": r"\b(?:agentic|AI agents|multi-agent)\b",
    "Fintech": r"\b(?:fintech|digital payments|financial technology)\b",
    "Quantum": r"\bquantum\b",
    "Robotics": r"\b(?:robotics|robots|robot)\b",
    "Developer tools": r"\b(?:developer tools|devtools|developer tooling)\b",
    "Open innovation": r"\bopen innovation\b",
}
CURRENCIES = {"₹": "INR", "$": "USD", "€": "EUR", "£": "GBP", "rs": "INR"}
MONEY = re.compile(
    r"(?P<prefix>INR|USD|EUR|GBP|CAD|AUD|₹|\$|€|£|Rs\.?)?\s*"
    r"(?P<amount>\d[\d,]*(?:\.\d+)?)\s*(?P<scale>lakhs?|crores?|[km](?![a-z]))?"
    r"\s*(?P<suffix>INR|USD|EUR|GBP|CAD|AUD)?", re.I,
)


def _text(value):
    if not isinstance(value, str):
        return None
    value = html.unescape(re.sub(r"<[^>]+>", " ", value))
    return " ".join(value.split()) or None


def https_url(value):
    if not isinstance(value, str) or len(value) > 2048:
        return None
    try:
        parts = urlsplit(value)
        if parts.scheme == "https" and parts.hostname and not parts.username and not parts.password:
            return value
    except ValueError:
        pass
    return None


def normalize(item):
    result = dict(item)
    for key in ("title", "summary", "host", "location", "country", "category", "team_size",
                "prize", "participation_fee", "eligibility_rules", "age_restrictions", "mode"):
        text = _text(result.get(key))
        result[key] = None if not text or text.casefold() in {"unknown", "n/a", "tbd", "unspecified"} else text
    for key in ("url", "registration_url", "announcement_url", "image_url"):
        result[key] = https_url(result.get(key))
    mode = (result.get("mode") or "").casefold()
    result["mode"] = {"offline": "in-person", "virtual": "online", "in person": "in-person"}.get(mode, mode)
    if result["mode"] not in {"online", "hybrid", "in-person"}:
        result["mode"] = None
    for key in ("themes", "tech_categories"):
        result[key] = [word for word in result.get(key) or [] if isinstance(word, str) and word.strip()] if isinstance(result.get(key), list) else []
    return result


def enrich(item):
    prior = item.get("tech_categories") or []
    text = " ".join((item.get("title") or "", item.get("summary") or "", *item.get("themes", []), *prior))
    inferred = [label for label, pattern in THEMES.items() if re.search(pattern, text, re.I)]
    item["tech_categories"] = list(dict.fromkeys([*prior, *inferred]))
    item["themes"] = list(dict.fromkeys([*item.get("themes", []), *inferred]))

    matches = [match for match in MONEY.finditer(item.get("prize") or "") if match["prefix"] or match["suffix"]]
    if len(matches) == 1:
        match = matches[0]
        prefix = (match["prefix"] or "").lower().rstrip(".")
        currency = (match["suffix"] or CURRENCIES.get(prefix, prefix)).upper()
        scale = match["scale"].lower() if match["scale"] else ""
        multiplier = 100000 if scale.startswith("lakh") else 10000000 if scale.startswith("crore") else {"k": 1000, "m": 1000000}.get(scale, 1)
        try:
            amount = Decimal(match["amount"].replace(",", "")) * multiplier
            if amount > 0:
                item["prize_amount"] = format(amount, "f")
                item["prize_currency"] = currency
        except InvalidOperation:
            pass

    rules = item.get("eligibility_rules") or ""
    item["restrictions"] = {
        kind: match.group() for kind, pattern in (
            ("student_only", r"\b(?:students? only|only (?:open )?to students|only for students)\b"),
            ("women_only", r"\b(?:women only|only (?:open )?to women|only for women|girls only|female participants only)\b"),
        ) if (match := re.search(pattern, rules, re.I))
    }
    return item
