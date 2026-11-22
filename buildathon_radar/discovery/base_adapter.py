from __future__ import annotations

import logging
import re
import urllib.request
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("buildathon_radar.discovery")


class BaseSourceAdapter(ABC):
    """Abstract base class for all multi-platform discovery source adapters."""

    source_key: str = "base"
    name: str = "Base Source"
    category: str = "General"
    discovery_method: str = "Web"
    confidence_level: str = "Medium"  # 'High', 'Medium-High', 'Medium', 'Low'

    def __init__(self, timeout: int = 10):
        self.timeout = timeout

    @abstractmethod
    def fetch(self) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """Discovers events from this source.

        Returns:
            (items_list, error_message_or_none)
        """
        raise NotImplementedError

    def make_request(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
    ) -> str:
        """Performs a safe, legitimate public HTTP GET request with proper user-agent headers."""
        req_headers = {
            "User-Agent": "BuildathonRadar/2.0 (Student Hackathon Discovery; mailto:radar@buildathon.local)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json;q=0.8,*/*;q=0.7",
            "Accept-Language": "en-US,en;q=0.9",
        }
        if headers:
            req_headers.update(headers)

        req = urllib.request.Request(url, headers=req_headers)
        with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.read().decode(charset, errors="replace")

    def clean_text(self, text: Optional[str]) -> str:
        if not text:
            return ""
        # Strip html tags and normalize whitespace
        t = re.sub(r"<[^>]+>", " ", text)
        t = re.sub(r"\s+", " ", t).strip()
        return t

    def extract_urls(self, text: str) -> List[str]:
        if not text:
            return []
        pattern = r"https?://[^\s<>\"']+"
        return re.findall(pattern, text)

    def parse_date_safe(self, text: Optional[str]) -> Optional[str]:
        """Attempts to parse varied date representations into YYYY-MM-DD."""
        if not text:
            return None
        text = text.strip()
        # Direct YYYY-MM-DD
        m = re.search(r"\b(202[5-9]-\d{2}-\d{2})\b", text)
        if m:
            return m.group(1)

        # Common format: "Nov 28, 2026" or "28 Nov 2026"
        month_map = {
            "jan": "01", "feb": "02", "mar": "03", "apr": "04", "may": "05", "jun": "06",
            "jul": "07", "aug": "08", "sep": "09", "oct": "10", "nov": "11", "dec": "12",
            "january": "01", "february": "02", "march": "03", "april": "04", "june": "06",
            "july": "07", "august": "08", "september": "09", "october": "10", "november": "11", "december": "12"
        }
        m_named = re.search(r"\b([a-zA-Z]{3,9})\s+(\d{1,2}),?\s+(202[5-9])\b", text)
        if m_named:
            mon_str, day_str, yr_str = m_named.groups()
            mon_num = month_map.get(mon_str.lower())
            if mon_num:
                return f"{yr_str}-{mon_num}-{int(day_str):02d}"

        m_named2 = re.search(r"\b(\d{1,2})\s+([a-zA-Z]{3,9})\s+(202[5-9])\b", text)
        if m_named2:
            day_str, mon_str, yr_str = m_named2.groups()
            mon_num = month_map.get(mon_str.lower())
            if mon_num:
                return f"{yr_str}-{mon_num}-{int(day_str):02d}"

        return None
