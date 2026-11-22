from __future__ import annotations

import logging
import re
import urllib.request
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser
from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("buildathon_radar.discovery")


class RobotsDenied(OSError):
    pass


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

        def read(target):
            req = urllib.request.Request(target, headers=req_headers)
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
                charset = resp.headers.get_content_charset() or "utf-8"
                data = resp.read(2_000_001)
                if len(data) > 2_000_000:
                    raise ValueError("Response exceeded size limit")
                return data.decode(charset, errors="replace")

        target = urlsplit(url)
        robots_url = f"{target.scheme}://{target.netloc}/robots.txt"
        try:
            robots_text = read(robots_url)
        except HTTPError as error:
            if error.code != 404:
                raise
        else:
            rules = RobotFileParser()
            rules.parse(robots_text.splitlines())
            if not rules.can_fetch("BuildathonRadar", url):
                raise RobotsDenied()
        return read(url)

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

    @staticmethod
    def registration_status(value):
        if isinstance(value, str) and value.lower() in {"open", "closed"}:
            return value.lower()
        return None

    def parse_date_safe(self, value: object) -> Optional[str]:
        """Parse a listing date and use the calendar's India time zone for instants."""
        india = timezone(timedelta(hours=5, minutes=30))
        try:
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                if abs(value) >= 10**11:
                    value /= 1000
                if abs(value) < 10**8:
                    return None
                return datetime.fromtimestamp(value, india).date().isoformat()
            if not isinstance(value, str):
                return None
            value = value.strip()
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                return date.fromisoformat(value).isoformat()
            timestamp = datetime.fromisoformat(value)
            if timestamp.tzinfo:
                timestamp = timestamp.astimezone(india)
            return timestamp.date().isoformat()
        except (ValueError, OverflowError, OSError):
            return None
