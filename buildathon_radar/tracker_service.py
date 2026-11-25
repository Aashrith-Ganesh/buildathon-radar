from __future__ import annotations

import html
import json
import os
import re
from pathlib import Path
from threading import Lock
from datetime import date, datetime as _datetime, timedelta, timezone
from typing import Annotated, Any, Dict, List, Literal, Optional

from fastapi import FastAPI, HTTPException, Path as ApiPath, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field, model_validator
from dotenv import load_dotenv
from urllib.parse import quote, urlencode, urlsplit

from buildathon_radar.local_security import (
    HTMLResponse, SESSION_AGE, SESSION_COOKIE, authenticated, issue_session, protect_local_request, valid_password,
)

from buildathon_radar import event_images, personal_tracker, tracker_store
from buildathon_radar.discovery.engine import DiscoveryEngine, ScanInProgress
from buildathon_radar.discovery.adapters import ADAPTER_REGISTRY, LIVE_SOURCE_KEYS, MANUAL_SOURCE_URLS
from buildathon_radar.discovery.integrity import lifecycle

load_dotenv()
app = FastAPI(title="Buildathon Radar Tracker & Blackout Manager", docs_url=None, redoc_url=None, openapi_url=None)
app.middleware("http")(protect_local_request)
DB_PATH = "tracker.db"
_ASSETS = Path(__file__).resolve().parent / "assets"
_DASHBOARD_GLOBE = (_ASSETS / "dashboard-globe.svg").read_text(encoding="utf-8")
_scan_lock = Lock()

ACCENT = "#0d9488"
TEAL_DARK = "#042f2e"
PAGE_BG = "#f8fafc"
CARD_BG = "#ffffff"
FONT_STACK = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Inter", Helvetica, Arial, sans-serif'

STATE_ORDER = ("tracked", "applied", "seen")
STATE_LABELS = {
    "tracked": "Tracked",
    "applied": "Applied",
    "seen": "Seen",
}


class BlackoutCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    start_date: date
    end_date: date
    category: str = Field(min_length=1, max_length=80)
    reason: Optional[str] = Field(default="", max_length=2000)
    enabled: bool = True

    @model_validator(mode="after")
    def validate_span(self):
        if not self.title.strip() or not self.category.strip():
            raise ValueError("Title and category are required")
        if self.end_date < self.start_date or (self.end_date - self.start_date).days > 3660:
            raise ValueError("Date range must be ordered and no longer than ten years")
        return self


class BlackoutUpdate(BlackoutCreate):
    pass


class ActionRequest(BaseModel):
    event_id: str = Field(min_length=1, max_length=300)
    action: str = Field(max_length=20)
    token: Optional[str] = Field(default=None, max_length=128)


class ScanRequest(BaseModel):
    sources: Optional[List[str]] = Field(default=None, max_length=27)
    force_all: bool = False


def _get_conn():
    return tracker_store.connect(DB_PATH)


def _esc(value):
    if value is None:
        return ""
    return html.escape(str(value))


def _external_url(value):
    try:
        parts = urlsplit(value or "")
        if parts.scheme in {"http", "https"} and parts.hostname and not parts.username and not parts.password:
            return _esc(parts.geturl())
    except ValueError:
        pass
    return "#"


def _format_date(value):
    if not value:
        return ""
    try:
        dt = _datetime.strptime(value[:10], "%Y-%m-%d")
        return dt.strftime("%b %d, %Y")
    except Exception:
        return value


def _format_ts_date(iso_ts):
    if not iso_ts:
        return "recently"
    try:
        cleaned = iso_ts.split(".")[0]
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                dt = _datetime.strptime(cleaned, fmt)
                return dt.strftime("%b %d, %Y")
            except ValueError:
                continue
        return iso_ts[:10]
    except Exception:
        return "recently"


def _page(headline, lines, event_url=None, accent=ACCENT):
    paras = "".join(f"<p>{line}</p>" for line in lines)
    link_html = ""
    if event_url:
        link_html = f'<p class="link-p"><a href="{_external_url(event_url)}" class="event-link" target="_blank" rel="noopener">Open event &rarr;</a></p>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_esc(headline)} - Buildathon Radar</title>
<style>
:root {{
  --bg-canvas: #f8fafc;
  --bg-card: #ffffff;
  --text-main: #0f172a;
  --text-muted: #64748b;
  --border: #e2e8f0;
  --accent: #0d9488;
}}
[data-theme="dark"] {{
  --bg-canvas: #090d16;
  --bg-card: #131b2e;
  --text-main: #f8fafc;
  --text-muted: #94a3b8;
  --border: #1e293b;
  --accent: #14b8a6;
}}
* {{ box-sizing: border-box; }}
body {{ margin:0; padding:0; background:var(--bg-canvas); font-family:{FONT_STACK}; color:var(--text-main); display:flex; justify-content:center; align-items:center; min-height:100%; }}
.card {{ background:var(--bg-card); border-radius:12px; border:1px solid var(--border); padding:36px; max-width:540px; width:90%; box-shadow:0 4px 12px rgba(0,0,0,0.06); text-align:center; }}
h1 {{ font-size:20px; font-weight:700; margin-top:0; margin-bottom:14px; color:var(--text-main); }}
p {{ font-size:14px; color:var(--text-muted); line-height:1.6; margin:8px 0; }}
.event-link {{ display:inline-block; margin-top:12px; padding:8px 16px; background:var(--accent); color:#ffffff; text-decoration:none; border-radius:6px; font-weight:600; font-size:13px; }}
.back-link {{ display:inline-block; margin-top:16px; color:var(--accent); font-size:13px; text-decoration:none; font-weight:600; }}
</style>
<script>
const savedTheme = new URLSearchParams(window.location.search).get('theme') || localStorage.getItem('radar_theme') || (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
document.documentElement.setAttribute('data-theme', savedTheme);
</script>
</head>
<body>
<div class="card">
  <h1>{_esc(headline)}</h1>
  {paras}
  {link_html}
  <div><a class="back-link" href="/dashboard">&larr; Return to Dashboard</a></div>
</div>
</body>
</html>"""


def _health_page():
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Buildathon Radar - System Running</title>
<script>if (!window.location.search.includes("health")) { window.location.href = "/dashboard"; }</script>
<style>
:root {
  --bg-canvas: #09090b;
  --bg-card: #121215;
  --text-main: #fafafa;
  --text-muted: #a1a1aa;
  --border: #27272a;
  --accent: #10b981;
}
[data-theme="light"] {
  --bg-canvas: #fafafa;
  --bg-card: #ffffff;
  --text-main: #09090b;
  --text-muted: #52525b;
  --border: #e4e4e7;
  --accent: #059669;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  padding: 0;
  background: var(--bg-canvas);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Inter", sans-serif;
  color: var(--text-main);
  min-height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}
.landing-wrap {
  width: 100%;
  padding: 48px 16px;
  display: flex;
  justify-content: center;
}
.landing-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 44px 32px;
  max-width: 520px;
  width: 100%;
  box-shadow: 0 10px 25px -5px rgba(0,0,0,0.4);
  text-align: center;
}
.radar-pulse-wrap {
  width: 60px;
  height: 60px;
  border-radius: 50%;
  background: rgba(16, 185, 129, 0.12);
  color: var(--accent);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 20px;
  position: relative;
}
.radar-pulse-ring {
  position: absolute;
  inset: -6px;
  border-radius: 50%;
  border: 2px solid var(--accent);
  opacity: 0.35;
  animation: radarPing 2.5s cubic-bezier(0, 0, 0.2, 1) infinite;
}
@keyframes radarPing {
  75%, 100% { transform: scale(1.4); opacity: 0; }
}
.status-pill-running {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 700;
  color: #10b981;
  background: rgba(16, 185, 129, 0.15);
  padding: 4px 12px;
  border-radius: 9999px;
  margin-bottom: 18px;
}
.status-pill-running::before {
  content: "";
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #10b981;
  display: inline-block;
}
.landing-title {
  font-size: 22px;
  font-weight: 800;
  margin: 0 0 10px 0;
  letter-spacing: -0.4px;
}
.landing-desc {
  font-size: 14px;
  color: var(--text-muted);
  line-height: 1.6;
  margin: 0 0 24px 0;
}
.btn-launch {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  background: var(--accent);
  color: #ffffff;
  padding: 12px 20px;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 700;
  text-decoration: none;
  transition: opacity 0.15s ease, transform 0.15s ease;
}
.btn-launch:hover {
  opacity: 0.92;
  transform: translateY(-1px);
}
.secondary-links {
  font-size: 12px;
  color: var(--text-muted);
  display: flex;
  justify-content: center;
  gap: 16px;
  margin-top: 18px;
}
.secondary-links a {
  color: var(--text-muted);
  text-decoration: none;
}
.secondary-links a:hover {
  color: var(--text-main);
  text-decoration: underline;
}
</style>
<script>
const savedTheme = localStorage.getItem('radar_theme') || (window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
document.documentElement.setAttribute('data-theme', savedTheme);
</script>
</head>
<body>
<div class="landing-wrap">
  <div class="landing-card">
    <div class="radar-pulse-wrap">
      <div class="radar-pulse-ring"></div>
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="m4.93 4.93 4.24 4.24"/><path d="m14.83 9.17 4.24-4.24"/><path d="M12 2v20"/><path d="M2 12h20"/></svg>
    </div>
    <div class="status-pill-running">Buildathon Radar is running</div>
    <h1 class="landing-title">Student Opportunity Engine</h1>
    <p class="landing-desc">Personalized AI/SWE buildathon discovery for high school students in Bengaluru with blackout-aware calendar filtering.</p>
    <a class="btn-launch" href="/dashboard">Launch Interactive Dashboard &rarr;</a>
    <div class="secondary-links">
      <a href="/calendar">Blackout Calendar</a>
      <span>&middot;</span>
      <a href="/sources">27 Live Sources</a>
      <span>&middot;</span>
      <a href="/list">Read-only List</a>
    </div>
  </div>
</div>
</body>
</html>"""


def _malformed_page():
    return _page("Malformed link", ["This link is missing its event. Nothing was recorded."])


def _invalid_token_page():
    return _page("Invalid link", [
        "This link is missing its signature or the signature does not match.",
        "Nothing was recorded.",
    ])


def _unknown_event_page():
    return f"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Event not found</title><style>{_SHARED_HEAD_CSS}</style>
<body>{_navigation("")}{_THEME_SCRIPT}
<main class="container"><h1>Event not found</h1>
<p>Open the dashboard to find another event.</p>
<a href="/dashboard">Return to dashboard</a></main></body></html>"""


def _ok_page(action, row):
    title = _esc(row["title"])
    if action == "track":
        lines = [f"<strong>{title}</strong>"]
        start = _format_date(row["event_start"])
        if start:
            lines.append(f"Starts {_esc(start)}.")
        lines.append(
            "This event is shortlisted and will reappear in your Sunday digest as a reminder."
        )
        return _page("\U0001F4CC Tracked (Shortlisted)", lines, event_url=row["url"])
    elif action == "applied":
        lines = [
            f"<strong>{title}</strong>",
            "It is now in your participation log at the bottom of every digest.",
        ]
        return _page("\U0001F3AF Applied", lines, event_url=row["url"])
    elif action == "reject":
        lines = [
            f"<strong>{title}</strong>",
            "Marked as rejected/dismissed. It will no longer be recommended.",
        ]
        return _page("\U0001F5D1 Rejected", lines, event_url=row["url"])
    return _page("Updated", [f"<strong>{title}</strong>"], event_url=row["url"])


def _noop_page(action, row):
    title = _esc(row["title"])
    state = row["state"]

    if action == "track" and state == "applied":
        headline = "Already applied"
        marked = _format_ts_date(row["applied_at"])
        lines = [
            f"<strong>{title}</strong>",
            f"Marked applied on {_esc(marked)}. Applied outranks Track, so nothing was downgraded.",
        ]
    elif action == "track":
        headline = "Already tracked"
        marked = _format_ts_date(row["tracked_at"])
        lines = [
            f"<strong>{title}</strong>",
            f"Marked on {_esc(marked)}. Nothing was changed.",
        ]
    else:
        headline = "Already applied"
        marked = _format_ts_date(row["applied_at"])
        lines = [
            f"<strong>{title}</strong>",
            f"Marked on {_esc(marked)}. Nothing was changed.",
        ]
    return _page(headline, lines, event_url=row["url"])


def _list_row(row):
    title = _esc(row["title"])
    url = "/event/" + quote(row["event_id"], safe="")
    source = _esc(row["source"] or "Unknown")
    start = _esc(_format_date(row["event_start"]) or "TBD")
    end = _esc(_format_date(row["event_end"]) or "TBD")
    return f"""<div class="event-row">
<a class="event-title" href="{url}">{title}</a>
<div class="event-meta">{source} &middot; {start} to {end}</div>
</div>"""


def _list_page(rows):
    if not rows:
        body = (
            '<p class="empty">Nothing tracked or applied yet. Tap Track or '
            "Applied on an event in your weekly digest and it will show up "
            "here.</p>"
        )
    else:
        by_state = {}
        for row in rows:
            by_state.setdefault(row["state"], []).append(row)

        sections = []
        for state in STATE_ORDER:
            state_rows = by_state.get(state)
            if not state_rows:
                continue
            rows_html = "".join(_list_row(r) for r in state_rows)
            sections.append(f"""<section>
<h2>{_esc(STATE_LABELS.get(state, state.title()))} <span class="count">{len(state_rows)}</span></h2>
{rows_html}
</section>""")
        body = "".join(sections)

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Buildathon Radar Tracker</title>
<style>
{_SHARED_HEAD_CSS}
.event-row {{ padding: 12px 16px; margin-bottom: 8px; background: var(--bg-card); border: 1px solid var(--border); }}
.event-meta {{ color: var(--text-muted); font-size: 14px; }}
</style>
</head>
<body>
{_navigation("list")}
{_THEME_SCRIPT}
<main class="container">
<h1>Event history</h1>
{body}
</main>
</body>
</html>"""


# ---------------------------------------------------------------------------
# SHARED MODERN CSS FOR DASHBOARD & CALENDAR
# ---------------------------------------------------------------------------
_SHARED_HEAD_CSS = """
:root {
  --bg-page: #0a0a0a;
  --bg-card: #0d0d0d;
  --bg-card-hover: rgba(255, 255, 255, 0.04);
  --border-color: rgba(255, 255, 255, 0.08);
  --border-subtle: rgba(255, 255, 255, 0.05);
  --text-primary: #ededed;
  --text-muted: #a1a1aa;
  --text-dim: #71717a;
  --teal-accent: #5eead4;
  --gold-prize: #e8b75b;
  --green-score: #4ade80;
  --orange-featured: #fb923c;
  --rose-conflict: #fda4af;
  --rose-border: rgba(244, 63, 94, 0.3);
  --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Inter", "Helvetica Neue", sans-serif;
  --font-mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;

  /* Legacy variable mappings for other pages */
  --bg-canvas: var(--bg-page);
  --bg-subtle: #141414;
  --bg-hover: var(--bg-card-hover);
  --bg-header: rgba(10, 10, 10, 0.85);
  --text-main: var(--text-primary);
  --border: var(--border-color);
  --teal-primary: #10b981;
  --teal-hover: #34d399;
  --teal-light: rgba(94, 234, 212, 0.1);
  --indigo-primary: #818cf8;
  --indigo-light: rgba(129, 140, 248, 0.15);
  --emerald-primary: #34d399;
  --emerald-light: rgba(16, 185, 129, 0.15);
  --rose-primary: #f43f5e;
  --rose-light: rgba(244, 63, 94, 0.15);
  --amber-primary: #fbbf24;
  --amber-light: rgba(251, 191, 36, 0.15);
  --shadow-sm: 0 1px 3px 0 rgba(0, 0, 0, 0.5);
  --shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.5);
  --shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.6);
  --radius-sm: 6px;
  --radius-md: 11px;
  --radius-lg: 14px;
}

[data-theme="light"] {
  --bg-page: #fafafa;
  --bg-card: #ffffff;
  --bg-card-hover: rgba(0, 0, 0, 0.02);
  --border-color: #e4e4e7;
  --border-subtle: #f4f4f5;
  --text-primary: #09090b;
  --text-muted: #52525b;
  --text-dim: #71717a;
  --teal-accent: #086658;
  --gold-prize: #844700;
  --green-score: #146a36;
  --orange-featured: #ea580c;
  --rose-conflict: #e11d48;
  --bg-canvas: #fafafa;
  --bg-subtle: #f4f4f5;
  --bg-header: rgba(255, 255, 255, 0.9);
  --text-main: #09090b;
  --border: #e4e4e7;
}

* { box-sizing: border-box; }
html, body {
  overflow-x: clip;
}
body {
  margin: 0;
  padding: 0;
  background-color: var(--bg-page);
  color: var(--text-primary);
  font-family: var(--font-sans);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  letter-spacing: -0.015em;
  min-height: 100%;
  display: flex;
  flex-direction: column;
}

/* Accessibility: Skip Link & Focus Rings */
.skip-link {
  position: absolute;
  top: -40px;
  left: 16px;
  background: var(--teal-accent);
  color: #0a0a0a;
  padding: 8px 16px;
  border-radius: 6px;
  font-weight: 700;
  text-decoration: none;
  z-index: 1000;
  transition: top 0.2s cubic-bezier(0.16, 1, 0.3, 1);
}
.skip-link:focus { top: 16px; }
:focus-visible {
  outline: 2px solid var(--teal-accent);
  outline-offset: 2px;
}

/* Shared navigation */
header.app-header {
  position: sticky;
  top: 0;
  z-index: 50;
  border-bottom: 1px solid var(--border-color);
  background: var(--bg-header);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  padding: 12px 24px;
}
.header-inner {
  max-width: 1240px;
  margin: 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.brand-link {
  display: flex;
  align-items: center;
  gap: 8px;
  text-decoration: none;
  color: var(--text-primary);
  font-size: 15px;
  font-weight: 600;
  transition: color 0.15s ease;
}
.brand-link:hover { color: var(--teal-accent); }
.brand-icon { color: var(--teal-accent); display: flex; align-items: center; }

.nav-links {
  display: flex;
  align-items: center;
  gap: 8px;
}
.nav-link {
  color: var(--text-muted);
  text-decoration: none;
  font-size: 13px;
  font-weight: 500;
  padding: 6px 12px;
  border-radius: 6px;
  transition: all 0.15s ease;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.nav-link:hover { color: var(--text-primary); background: rgba(255,255,255,0.06); }
.nav-link.active { color: var(--text-primary); background: rgba(255,255,255,0.08); border: 1px solid var(--border-color); }
.btn-scan {
  background: var(--teal-accent);
  color: #0a0a0a;
  font-weight: 700;
  padding: 6px 14px;
  border-radius: 6px;
  border: none;
  font-size: 13px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  transition: opacity 0.15s ease;
}
.btn-scan:hover { opacity: 0.9; }

/* Container */
.container {
  max-width: 1240px;
  width: 100%;
  margin: 0 auto;
  padding: 32px 24px 64px 24px;
  flex: 1;
}
.nav-links, .header-inner { flex-wrap: wrap; }
.nav-link[aria-current="page"] { color: var(--text-primary); background: var(--bg-subtle); }
.container { min-width: 0; overflow-wrap: anywhere; }
a { color: var(--teal-accent); }
button, input, select, textarea { font: inherit; }
button, .btn {
  color: var(--text-primary); background: var(--bg-subtle);
  border: 1px solid var(--border); padding: 8px 12px; border-radius: var(--radius-sm);
  cursor: pointer; text-decoration: none;
}
.exam-overlap {
  padding: 8px 12px;
  border-left: 2px solid var(--rose-conflict);
  background: var(--bg-subtle);
  font-size: 13px;
  overflow-wrap: anywhere;
}
.exam-overlap ul { margin: 4px 0 0; padding-inline-start: 18px; }
.exam-overlap li span { color: var(--text-muted); }
.tracker-form { display:flex; flex-wrap:wrap; align-items:end; gap:10px; }
.tracker-form label { display:flex; flex-direction:column; gap:4px; font-size:14px; min-width:0; }
.tracker-form input, .tracker-form select, .tracker-form textarea {
  background:var(--bg-card); color:var(--text-main); border:1px solid var(--border);
  border-radius:6px; padding:7px; max-width:100%;
}
.tracker-entry { border-top:1px solid var(--border); padding:16px 0; }
.tracker-entry h2 { font-size:18px; }
.tracker-overview { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(240px,100%),1fr)); gap:20px; }
.table-wrap { max-width: 100%; overflow-x: auto; }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 10px; text-align: left; border-bottom: 1px solid var(--border); }
input:focus-visible + .slider { outline: 2px solid var(--teal-accent); outline-offset: 2px; }
@media (max-width: 768px) {
  header.app-header { position: static; padding: 12px; }
  .container { padding: 20px 12px; }
  .nav-link { padding: 6px 8px; }
  th, td { padding: 7px; }
  .filter-pills { flex-wrap: wrap; }
  .radar-box-header { flex-wrap: wrap; }
}

"""


def _navigation(active, scan=False):
    links = (
        ("dashboard", "/dashboard", "Dashboard"),
        ("tracker", "/tracker", "Tracker"),
        ("excluded", "/dashboard?filter=excluded", "Exam conflicts"),
        ("calendar", "/calendar", "Calendar"),
        ("sources", "/sources", "Sources"),
        ("leads", "/leads", "LinkedIn leads"),
        ("list", "/list", "List view"),
        ("settings", "/settings", "Settings"),
    )
    nav = "".join(
        f'<a class="nav-link" href="{url}" {"aria-current=page" if key == active else ""}>{title}</a>'
        for key, url, title in links
    )
    scan_button = '<button class="btn-scan" id="btnScanNow">Scan Hackathons</button>' if scan else ""
    return f"""<header class="app-header"><div class="header-inner">
      <a class="brand-link" href="/dashboard">Buildathon Radar</a>
      <nav class="nav-links" aria-label="Main navigation">{nav}{scan_button}
        <button class="nav-link" id="themeToggleBtn" type="button">Theme</button>
      </nav>
    </div></header>"""


_THEME_SCRIPT = """<script>
const root = document.documentElement;
const themeButton = document.getElementById('themeToggleBtn');
function applyTheme(theme) {
  root.dataset.theme = theme;
  if (themeButton) {
    themeButton.textContent = theme === 'light' ? 'Dark theme' : 'Light theme';
  }
}
const urlTheme = new URLSearchParams(window.location.search).get('theme');
const activeTheme = urlTheme || localStorage.getItem('radar_theme') || (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
applyTheme(activeTheme);
if (themeButton) {
  themeButton.addEventListener('click', () => {
    const theme = root.dataset.theme === 'light' ? 'dark' : 'light';
    localStorage.setItem('radar_theme', theme);
    applyTheme(theme);
  });
}
</script>"""


def _exam_overlap(details):
    items = "".join(
        f'<li>{_esc(match["title"])} <span>{_esc(match["overlap_dates"])}</span></li>'
        for match in json.loads(details or "[]")
    )
    body = f"<ul>{items}</ul>" if items else "<p>See the calendar for conflicting dates.</p>"
    return f'<div class="exam-overlap"><strong>Exam overlap</strong>{body}</div>'


def _dashboard_page(events, current_filter=None, stats=None, search="", page=1, pages=1, result_count=None):
    today = _datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d")
    if result_count is None:
        result_count = len(events)
    if stats is None:
        conn = _get_conn()
        try:
            stats = tracker_store.get_dashboard_stats(conn)
        finally:
            conn.close()

    total_upcoming = stats["total_upcoming"]
    eligible_count = stats["eligible_count"]
    blackout_excluded = stats["blackout_excluded_count"]
    unverified_count = stats["unverified_count"]
    bangalore_count = stats["bangalore_count"]
    closing_soon_count = stats["closing_soon_count"]
    tracked_count = stats["tracked_count"]
    applied_count = stats["applied_count"]
    next_event = stats["next_eligible_event"] if not current_filter and not search else None
    def filter_url(key, *, keep_search=True):
        params = {} if key in (None, "discover") else {"filter": key}
        if search and keep_search:
            params["search"] = search
        return "/dashboard" + ("?" + _esc(urlencode(params)) if params else "")

    page_links = " ".join(
        f'<a class="nav-link" href="?{_esc(urlencode(dict(filter=current_filter or "discover", search=search, page=i)))}">{label}</a>'
        for i, label in ((page - 1, "Previous"), (page + 1, "Next")) if 1 <= i <= pages
    )

    # Spotlight Hero: Next Eligible Hackathon
    next_event_html = ""
    if next_event:
        ne_id = _esc(next_event["event_id"])
        ne_title = _esc(next_event["title"])
        ne_url = _external_url(next_event["url"])
        ne_host = _esc(next_event["host"] or "Organizer unknown")
        ne_loc = _esc(next_event["location"] or "Location unknown")
        ne_mode = _esc(next_event["mode"] or "unknown")
        ne_start_raw = next_event["event_start"] or ""
        ne_start = _esc(_format_date(ne_start_raw))
        ne_prize = _esc(next_event["prize"] or "Unspecified")
        ne_team = _esc(next_event["team_size"] or "Unknown")
        ne_score = int(next_event["score"]) if next_event["score"] is not None else 0
        ne_token = tracker_store.sign_action("track", next_event["event_id"])

        relative_days_text = ""
        if ne_start_raw:
            try:
                d_start = _datetime.strptime(ne_start_raw[:10], "%Y-%m-%d")
                d_today = _datetime.strptime(today, "%Y-%m-%d")
                delta = (d_start - d_today).days
                if delta == 0:
                    relative_days_text = '<span class="spotlight-days-pill">Starts Today!</span>'
                elif delta == 1:
                    relative_days_text = '<span class="spotlight-days-pill">Starts Tomorrow</span>'
                elif 2 <= delta <= 14:
                    relative_days_text = f'<span class="spotlight-days-pill">Starts in {delta} days</span>'
            except Exception:
                pass

        next_event_html = f"""
        <div class="spotlight-hero" aria-label="Next Eligible Opportunity">
          <div class="spotlight-header">
            <div class="spotlight-tag-row">
              <span class="spotlight-tag">🚀 Next Eligible Hackathon</span>
              {relative_days_text}
              <span class="spotlight-subtag">Zero Exam Conflicts &middot; Class 11/12 Eligible</span>
            </div>
            <div class="spotlight-score">
              Match score: <strong>{ne_score}/100</strong>
            </div>
          </div>
          <div class="spotlight-body">
            <div class="spotlight-info">
              <h2 class="spotlight-title"><a href="{ne_url}" target="_blank" rel="noopener">{ne_title} &rarr;</a></h2>
              <div class="spotlight-meta">
                <span>🏢 {ne_host}</span> &middot;
                <span>📍 {ne_loc} ({ne_mode.title()})</span> &middot;
                <span>📅 Starts: <strong>{ne_start}</strong></span> &middot;
                <span>👥 Team: {ne_team}</span> &middot;
                <span>🏆 Prize: {ne_prize}</span>
              </div>
              <p class="spotlight-why">{_esc(next_event['why'] or '')}</p>
            </div>
            <div class="spotlight-actions">
              <a class="btn-shortlist-action" href="/track?event_id={ne_id}&t={ne_token}" data-event-id="{ne_id}" data-event-action="track" data-token="{ne_token}">Shortlist Opportunity</a>
              <a class="btn-primary-link" href="{ne_url}" target="_blank" rel="noopener">Open Official Page &rarr;</a>
              <button class="btn-shortlist-action" data-copy-url="{ne_url}" aria-label="Copy event link" title="Copy URL">Copy link</button>
            </div>
          </div>
        </div>
        """

    # Generate hackathonradar.com style rows
    rows_html = ""
    cards_html = ""
    date_group = None

    for e in events:
        next_group = e.get("date_group")
        if next_group and next_group != date_group:
            group_heading = f'<h3 class="event-date-group">{_esc(next_group)}</h3>'
            rows_html += group_heading
            cards_html += group_heading
            date_group = next_group
        eid = _esc(e["event_id"])
        detail_url = f'/h/{_esc(e["slug"])}'
        title = _esc(e["title"])
        host = _esc(e["host"] or "Organizer unknown")
        source = _esc(e["source"] or "Discovery")
        loc = _esc(e["location"] or "Location unknown")
        mode = _esc(e["mode"] or "unknown")
        category = _esc(e["category"] or "Hackathon")
        start_raw = e["event_start"] or ""
        end_raw = e["event_end"] or start_raw
        start = _esc(_format_date(start_raw) or "TBD")
        end = _esc(_format_date(end_raw) or "TBD")
        deadline_raw = e["registration_deadline"] or ""
        deadline = _esc(_format_date(deadline_raw) or "Unknown")
        team = _esc(e["team_size"] or "Unknown")
        prize = _esc(e["prize"] or "Unspecified")
        score = int(e["score"]) if e["score"] is not None else 0
        priority = _esc(e["priority"])
        eligibility = _esc(e["eligibility"] or "UNKNOWN")
        why = _esc(e["why"] or "")
        state = _esc(e["state"])
        url = _external_url(e["url"])
        is_conflict = bool(e["blackout_conflict"] if "blackout_conflict" in e.keys() else ("CONFLICT" in priority))
        date_status = str(e["date_status"] if "date_status" in e.keys() else "verified")

        # Duration & Short date string
        short_date = "TBD"
        if start_raw:
            try:
                dt_obj = _datetime.strptime(start_raw[:10], "%Y-%m-%d")
                short_date = dt_obj.strftime("%b %d")
            except Exception:
                short_date = start[:6]

        # Duration computation
        duration_str = "—"
        try:
            if start_raw and end_raw:
                d1 = _datetime.strptime(start_raw[:10], "%Y-%m-%d")
                d2 = _datetime.strptime(end_raw[:10], "%Y-%m-%d")
                days = (d2 - d1).days + 1
                duration_str = f"{days}d" if days > 1 else "1d"
        except Exception:
            pass

        is_bangalore = tracker_store.is_bengaluru_listing(e)

        # Tags
        tags_html = ""
        if e.get("provenance") == "legacy":
            tags_html += '<span class="tag-conflict">Archived discovery</span>'
            eligibility, priority, score = "UNKNOWN", "Archived", 0
        elif is_conflict:
            tags_html += '<span class="tag-conflict">Blackout Conflict</span>'
        elif "HIGH" in priority:
            tags_html += '<span class="tag-featured">🔥 HIGH PRIORITY</span>'

        if e.get("provenance") == "live":
            status = e.get("lifecycle")
            label = {
                "Discovered": "Schedule unconfirmed",
                "Upcoming": "Registration unconfirmed",
                "Registration open": "Registration open",
            }.get(status, status)
            if label:
                tags_html += f'<span class="state-pill">{_esc(label)}</span>'
            if not start_raw and status != "Discovered":
                tags_html += '<span class="state-pill">Schedule unconfirmed</span>'
            if eligibility == "UNKNOWN":
                tags_html += '<span class="state-pill">Eligibility unconfirmed</span>'

        if is_bangalore:
            tags_html += '<span class="tag-bengaluru">Bengaluru</span>'

        if eligibility == "ELIGIBLE":
            tags_html += '<span class="tag-bengaluru">Class 11/12</span>'

        reject_token = tracker_store.sign_action("reject", e["event_id"])

        conflict_note = _exam_overlap(e["conflict_details"]) if is_conflict else ""

        state_label = personal_tracker.STATUSES.get(e.get("tracker_status"), state.title())
        state_pill = f'<span class="state-pill state-{state}">{_esc(state_label)}</span>'

        actions = ""
        if state != "rejected":
            actions = f"""
            <a class="btn-shortlist-action" href="/reject?event_id={eid}&t={reject_token}" data-event-id="{eid}" data-event-action="reject" data-token="{reject_token}">Discard</a>"""

        # HackathonRadar Row
        rows_html += f"""
        <div class="hr-row {'row-conflict' if is_conflict else ''}" data-id="{eid}" data-mode="{mode}" data-bengaluru="{'true' if is_bangalore else 'false'}" data-score="{score}" data-start="{start_raw}" data-title="{title.lower()}">
          <span class="hr-time-pill" title="{start}">{short_date}</span>
          <div class="hr-title-wrap">
            <div class="hr-title-top">
              {tags_html}
              <a href="{detail_url}">{title}</a>
            </div>
            <div class="hr-subtext">
              <span>🏢 {host} via {source}</span> &middot;
              <span>📍 {loc} ({mode.title()})</span> &middot;
              <span>👥 {team}</span> &middot;
              <span class="font-mono">📅 Closes: {deadline}</span>
            </div>
          </div>
          {conflict_note}
          <div class="hr-prize">{prize}</div>
          <div class="hr-score-wrap" title="Match score: {score}/100">
            <span class="hr-score-num">{score}</span>
            <div class="hr-score-bar-bg"><div class="hr-score-bar-fill" style="width: {score}%;"></div></div>
          </div>
          <div class="hr-actions">
            {actions}
            {_tracker_form(e, e.get("tracker_status") or "") if state != "rejected" else ""}
            <button class="btn-shortlist-action" data-copy-url="{detail_url}" aria-label="Copy event link" title="Copy link">Copy</button>
            <a class="btn-shortlist-action" href="{detail_url}">Details</a>
          </div>
        </div>
        """

        # Also support Card view
        cards_html += f"""
        <article class="event-card {'has-conflict' if is_conflict else ''}" data-id="{eid}" data-mode="{mode}" data-bengaluru="{'true' if is_bangalore else 'false'}" data-score="{score}" data-state="{state}" data-start="{start_raw}" data-title="{title.lower()}">
          <div class="card-top">
            <div class="badges-row">
              <span class="hr-time-pill">{short_date}</span>
              {tags_html}
            </div>
            <div class="hr-score-wrap">
              <span class="hr-score-num">{score}</span>
              <div class="hr-score-bar-bg"><div class="hr-score-bar-fill" style="width: {score}%;"></div></div>
            </div>
          </div>
          <h3 class="card-title"><a href="{detail_url}">{title}</a></h3>
          <div class="card-host">🏢 {host} <span class="source-tag">via {source}</span></div>
          <div class="card-specs">
            <div class="spec-item"><span class="spec-k">Dates:</span> <span class="spec-v font-mono">{start} &rarr; {end}</span></div>
            <div class="spec-item"><span class="spec-k">Deadline:</span> <span class="spec-v font-mono">{deadline}</span></div>
            <div class="spec-item"><span class="spec-k">Prize Pool:</span> <span class="spec-v hr-prize">{prize}</span></div>
            <div class="spec-item"><span class="spec-k">Location:</span> <span class="spec-v">{loc} ({mode.title()})</span></div>
          </div>
          {conflict_note if is_conflict else f'<div class="card-why">{why}</div>'}
          <div class="card-footer">
            <div>{state_pill}</div>
            <div class="card-actions">
            {actions}
            {_tracker_form(e, e.get("tracker_status") or "") if state != "rejected" else ""}
              <button class="btn-shortlist-action" data-copy-url="{detail_url}" aria-label="Copy event link" title="Copy link">Copy</button>
              <a class="btn-shortlist-action" href="{detail_url}">Details</a>
            </div>
          </div>
        </article>
        """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Hackathon Radar - Student Opportunity Discovery</title>
<style>
{_SHARED_HEAD_CSS}

/* Hero Section */
.hero-badge {{
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-family: var(--font-mono);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-muted);
  border: 1px solid var(--border-color);
  background: rgba(255, 255, 255, 0.03);
  padding: 4px 12px;
  border-radius: 9999px;
  margin-bottom: 16px;
}}
.live-dot-wrap {{ position: relative; width: 6px; height: 6px; }}
.live-dot {{ position: absolute; inset: 0; border-radius: 50%; background: #4ade80; }}
.live-ping {{
  position: absolute;
  inset: 0;
  border-radius: 50%;
  background: #4ade80;
  animation: hr-live-ping 2s cubic-bezier(0, 0, 0.2, 1) infinite;
}}
@keyframes hr-live-ping {{
  0% {{ opacity: 0.8; transform: scale(1); }}
  100% {{ opacity: 0; transform: scale(2.6); }}
}}

.hero-intro {{
  display: grid;
  grid-template-columns: minmax(0, 1fr) clamp(82px, 24vw, 235px);
  max-width: 885px;
  align-items: center;
  gap: clamp(0px, 1vw, 12px);
}}
.hero-globe {{
  display: block;
  width: 100%;
  height: auto;
  mask-image: linear-gradient(to right, #000 42%, transparent 91%);
}}
@media (max-width: 480px) {{
  .hero-intro .hero-title {{ font-size: clamp(24px, 6vw, 32px); }}
  .hero-intro .hero-subtitle {{ font-size: 14px; }}
}}
.hero-title {{
  font-size: 48px;
  font-weight: 700;
  line-height: 1.05;
  letter-spacing: -0.035em;
  color: var(--text-primary);
  margin: 0 0 16px 0;
  max-width: 640px;
}}
.hero-title .count {{
  font-family: var(--font-mono);
  font-feature-settings: 'cv01';
  color: var(--text-primary);
}}
.hero-subtitle {{
  font-size: 17px;
  line-height: 1.5;
  color: var(--text-muted);
  max-width: 520px;
  margin: 0 0 26px 0;
}}

/* 4 Quick Metric Cards */
.hero-metrics {{
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  max-width: 580px;
  margin-bottom: 32px;
}}
.hero-metric-card {{
  display: block;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 11px;
  padding: 12px 14px;
  text-decoration: none;
  transition: border-color 0.15s ease, background-color 0.15s ease;
}}
.hero-metric-card:hover {{
  border-color: rgba(94, 234, 212, 0.45);
  background: rgba(255, 255, 255, 0.02);
}}
.metric-num {{
  font-family: var(--font-mono);
  font-size: 22px;
  font-weight: 700;
  line-height: 1;
  letter-spacing: -0.02em;
  color: var(--text-primary);
}}
.metric-num.rose {{ color: #fda4af; }}
.metric-num.teal {{ color: var(--teal-accent); }}
.metric-num.gold {{ color: var(--gold-prize); }}
.metric-label {{
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 4px;
}}

/* Spotlight Hero */
.spotlight-hero {{
  background: #0d0d0d;
  border: 1px solid var(--border-color);
  border-left: 4px solid var(--teal-accent);
  border-radius: 14px;
  padding: 20px 24px;
  margin-bottom: 28px;
}}
.spotlight-header {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 12px;
}}
.spotlight-tag-row {{ display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }}
.spotlight-tag {{
  font-family: var(--font-mono);
  font-size: 10.5px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--teal-accent);
  background: rgba(94, 234, 212, 0.1);
  border: 1px solid rgba(94, 234, 212, 0.3);
  padding: 2px 8px;
  border-radius: 4px;
}}
.spotlight-days-pill {{
  font-size: 11px;
  font-weight: 700;
  color: #4ade80;
  background: rgba(74, 222, 128, 0.1);
  padding: 2px 8px;
  border-radius: 4px;
}}
.spotlight-subtag {{ font-size: 12px; color: var(--text-muted); }}
.spotlight-score {{
  font-size: 13px;
  color: var(--text-muted);
  background: rgba(255, 255, 255, 0.04);
  padding: 4px 10px;
  border-radius: 6px;
  border: 1px solid var(--border-color);
}}
.spotlight-score strong {{ color: var(--teal-accent); font-family: var(--font-mono); }}
.spotlight-title {{ font-size: 20px; font-weight: 700; margin: 0 0 8px 0; }}
.spotlight-title a {{ color: var(--text-primary); text-decoration: none; }}
.spotlight-title a:hover {{ color: var(--teal-accent); }}
.spotlight-meta {{ font-size: 13px; color: var(--text-muted); display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 10px; }}
.spotlight-why {{
  font-size: 13px;
  color: var(--text-primary);
  background: rgba(255, 255, 255, 0.03);
  border-left: 3px solid var(--teal-accent);
  padding: 8px 12px;
  border-radius: 0 6px 6px 0;
  margin: 0 0 14px 0;
  line-height: 1.5;
}}
.spotlight-actions {{ display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }}
.btn-primary-link {{
  background: var(--teal-accent);
  color: #0a0a0a;
  font-weight: 700;
  padding: 6px 14px;
  border-radius: 6px;
  text-decoration: none;
  font-size: 12px;
  display: inline-flex;
  align-items: center;
  gap: 5px;
}}
.btn-primary-link:hover {{ opacity: 0.9; }}

/* Radar Box Container */
.radar-box {{
  background: #0d0d0d;
  border: 1px solid var(--border-color);
  border-radius: 14px;
  overflow: hidden;
  margin-bottom: 32px;
}}
.radar-box-header {{
  padding: 14px 18px;
  border-bottom: 1px solid var(--border-color);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  background: rgba(255, 255, 255, 0.015);
}}
.search-controls {{
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  width: 100%;
}}
.search-input-wrap {{
  display: flex;
  flex: 1 1 240px;
  min-width: 0;
  align-items: center;
  gap: 8px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 8px 12px;
}}
.search-input-wrap:focus-within {{ border-color: var(--teal-accent); }}
.search-input-wrap svg {{ flex: none; }}
.search-input-wrap input {{
  background: transparent;
  border: none;
  color: var(--text-primary);
  font: inherit;
  width: 100%;
  min-width: 0;
}}
.kbd {{
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-dim);
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid var(--border-color);
  padding: 2px 5px;
  border-radius: 4px;
}}

/* Filter Pills */
.filter-pills {{
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}}
.filter-pill {{
  font-size: 12px;
  font-weight: 500;
  color: var(--text-muted);
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid transparent;
  padding: 5px 11px;
  border-radius: 6px;
  text-decoration: none;
  transition: all 0.15s ease;
}}
.filter-pill:hover {{ color: var(--text-primary); background: rgba(255, 255, 255, 0.08); }}
.filter-pill.active {{ color: var(--text-primary); background: rgba(255, 255, 255, 0.12); border-color: var(--border-color); font-weight: 600; }}

/* Row Component */
.hr-row {{
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto auto;
  grid-template-areas: "date title prize score" ". actions actions actions";
  align-items: center;
  gap: 14px;
  border-bottom: 1px solid var(--border-subtle);
  padding: 12px 18px;
  text-decoration: none;
  color: inherit;
  transition: background-color 0.15s ease;
}}
.hr-row:last-child {{ border-bottom: none; }}
.hr-row:hover {{ background-color: var(--bg-card-hover); }}
.row-conflict {{ background-color: rgba(244, 63, 94, 0.03); }}

.hr-time-pill {{
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-muted);
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--border-color);
  border-radius: 5px;
  padding: 4px 8px;
  text-align: center;
  min-width: 52px;
}}

.hr-title-wrap {{
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}}
.hr-title-top {{
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}}
.hr-title-top a {{
  color: var(--text-primary);
  text-decoration: none;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}}
.hr-title-top a:hover {{ color: var(--teal-accent); }}

.tag-featured {{
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-family: var(--font-mono);
  font-size: 9.5px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--orange-featured);
  background: rgba(251, 146, 60, 0.1);
  border: 1px solid rgba(251, 146, 60, 0.3);
  padding: 1px 6px;
  border-radius: 4px;
  flex-shrink: 0;
}}
.tag-bengaluru {{
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-family: var(--font-mono);
  font-size: 9.5px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--teal-accent);
  background: rgba(94, 234, 212, 0.1);
  border: 1px solid rgba(94, 234, 212, 0.3);
  padding: 1px 6px;
  border-radius: 4px;
  flex-shrink: 0;
}}
.tag-conflict {{
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-family: var(--font-mono);
  font-size: 9.5px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--rose-conflict);
  background: rgba(244, 63, 94, 0.1);
  border: 1px solid var(--rose-border);
  padding: 1px 6px;
  border-radius: 4px;
  flex-shrink: 0;
}}

.hr-subtext {{
  font-size: 11.5px;
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}}
.row-conflict {{
  grid-template-columns: auto minmax(0, 1fr) auto auto;
  grid-template-areas: "date title prize score" ". overlap overlap overlap" ". actions actions actions";
}}
.hr-row > .hr-time-pill {{ grid-area: date; }}
.hr-row > .hr-title-wrap {{ grid-area: title; }}
.hr-row > .hr-prize {{ grid-area: prize; }}
.hr-row > .hr-score-wrap {{ grid-area: score; }}
.hr-row > .hr-actions {{ grid-area: actions; flex-wrap: wrap; }}
.hr-title-top, .badges-row {{ flex-wrap: wrap; }}
.hr-title-top a {{ flex: 1 0 100%; white-space: normal; overflow-wrap: anywhere; }}
.hr-subtext {{ white-space: normal; }}
.row-conflict > .exam-overlap {{ grid-area: overlap; }}
.card-footer, .card-actions {{ flex-wrap: wrap; gap: 6px; }}

.hr-prize {{
  font-family: var(--font-mono);
  font-size: 13px;
  font-weight: 600;
  color: var(--gold-prize);
  text-align: right;
  min-width: 80px;
}}

.hr-score-wrap {{
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 60px;
}}
.hr-score-num {{
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--green-score);
  font-weight: 600;
}}
.hr-score-bar-bg {{
  width: 32px;
  height: 4px;
  border-radius: 2px;
  background: rgba(255, 255, 255, 0.1);
  overflow: hidden;
}}
.hr-score-bar-fill {{
  height: 100%;
  border-radius: 2px;
  background: var(--green-score);
}}

.hr-actions {{
  display: flex;
  gap: 4px;
  align-items: center;
}}
.btn-shortlist-action {{
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid var(--border-color);
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 600;
  padding: 4px 10px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s ease;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  text-decoration: none;
}}
.btn-shortlist-action:hover, .btn-shortlist-action.btn-active {{
  background: #10b981;
  color: #000;
  border-color: #10b981;
}}

/* Cards View fallback */
.cards-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 360px), 1fr));
  gap: 16px;
  margin-bottom: 24px;
}}
.event-card {{
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 11px;
  padding: 18px;
  display: flex;
  flex-direction: column;
  transition: border-color 0.15s ease, background-color 0.15s ease;
}}
.event-card:hover {{ border-color: rgba(94, 234, 212, 0.45); }}
.event-card.has-conflict {{ border-left: 3px solid var(--rose-conflict); }}
.card-top {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }}
.badges-row {{ display: flex; gap: 6px; align-items: center; }}
.card-title {{ font-size: 15px; font-weight: 600; margin: 0 0 6px 0; }}
.card-title a {{ color: var(--text-primary); text-decoration: none; }}
.card-title a:hover {{ color: var(--teal-accent); }}
.card-host {{ font-size: 12px; color: var(--text-muted); margin-bottom: 12px; }}
.card-specs {{
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  padding: 10px;
  font-size: 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 12px;
}}
.spec-item {{ display: flex; justify-content: space-between; }}
.spec-k {{ color: var(--text-dim); }}
.spec-v {{ color: var(--text-primary); font-weight: 500; }}
.card-why {{ font-size: 12px; color: var(--text-muted); background: rgba(255,255,255,0.03); padding: 8px; border-radius: 4px; margin-bottom: 12px; line-height: 1.4; flex: 1; }}
.card-footer {{ display: flex; justify-content: space-between; align-items: center; padding-top: 10px; border-top: 1px solid var(--border-color); }}
.card-actions {{ display: flex; gap: 4px; }}

.state-pill {{ font-size: 11px; font-family: var(--font-mono); color: var(--text-muted); }}

/* Toast Notice */
.toast-notice {{
  position: fixed;
  bottom: 24px;
  right: 24px;
  background: var(--bg-subtle);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
  border-left: 3px solid var(--teal-accent);
  padding: 12px 18px;
  border-radius: 6px;
  box-shadow: 0 10px 25px -5px rgba(0,0,0,0.5);
  font-size: 13px;
  font-weight: 600;
  z-index: 1000;
  display: none;
}}

@media (max-width: 768px) {{
  .hero-title {{ font-size: 34px; }}
  .hero-metrics {{ grid-template-columns: repeat(2, 1fr); }}
  .hr-row {{
    grid-template-columns: auto minmax(0, 1fr) auto;
    grid-template-areas: "date title score" "actions actions actions";
    gap: 8px;
  }}
  .hr-prize {{ display: none; }}
  .row-conflict {{
    grid-template-columns: auto minmax(0, 1fr) auto;
    grid-template-areas: "date title score" "overlap overlap overlap" "actions actions actions";
  }}
  .radar-box-header {{ flex-direction: column; align-items: stretch; }}
}}

[data-theme="light"] .spotlight-hero,
[data-theme="light"] .hero-metric-card,
[data-theme="light"] .radar-box,
[data-theme="light"] .event-card,
[data-theme="light"] .hr-row {{ background: var(--bg-card); }}
[data-theme="light"] .hr-date-pill {{ color: var(--text-primary); background: var(--bg-subtle); }}
.hero-title, .hero-title .count {{ color: var(--text-primary); }}
.event-date-group {{ grid-column: 1 / -1; margin: 0; padding: 12px; color: var(--text-muted); font-size: 14px; }}
</style>
<script>

function animateGlobe() {{
  const globe = document.querySelector('.hero-globe');
  if (!globe || matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  const land = globe.querySelector('.globe-land');
  const marker = globe.querySelector('.globe-marker');
  const coordinates = land.dataset.land.split(',').map(Number);
  const radians = Math.PI / 180;
  const point = (longitude, latitude) => {{
    const angle = latitude * radians;
    return [longitude * radians, Math.cos(angle), Math.sin(angle)];
  }};
  const points = [];
  for (let i = 0; i < coordinates.length; i += 2) {{
    points.push(point(coordinates[i], coordinates[i + 1]));
  }}
  const bengaluru = point(77.5946, 12.9716);
  const tilt = 19 * radians;
  const tiltSin = Math.sin(tilt);
  const tiltCos = Math.cos(tilt);
  globe.querySelector('.globe-still').setAttribute('display', 'none');
  const start = performance.now();
  let lastFrame = 0;

  function draw(now) {{
    requestAnimationFrame(draw);
    if (document.hidden || now - lastFrame < 40) return;
    lastFrame = now;
    const rotation = (now - start) * 2 * Math.PI / 54000 - 66 * radians;

    function project([longitude, latitudeCos, latitudeSin]) {{
      const east = longitude + rotation;
      const front = latitudeCos * Math.cos(east);
      const depth = tiltSin * latitudeSin + tiltCos * front;
      if (depth <= 0.035) return null;
      const x = 128 + 105 * latitudeCos * Math.sin(east);
      const y = 128 - 105 * (tiltCos * latitudeSin - tiltSin * front);
      return [x, y];
    }}

    let path = '';
    for (const sample of points) {{
      const position = project(sample);
      if (position) path += 'M' + position[0].toFixed(1) + ' ' + position[1].toFixed(1) + 'h.01';
    }}
    land.setAttribute('d', path);

    const position = project(bengaluru);
    marker.setAttribute('visibility', position ? 'visible' : 'hidden');
    if (position) marker.setAttribute('transform', 'translate(' + (position[0] - 148.56) + ' ' + (position[1] - 138.35) + ')');
  }}
  requestAnimationFrame(draw);
}}

function setViewMode(mode) {{
  const list = document.getElementById('hackathonList');
  const grid = document.getElementById('cardsContainer');
  const btnList = document.getElementById('btnViewList');
  const btnGrid = document.getElementById('btnViewGrid');

  if (mode === 'grid') {{
    if (list) list.style.display = 'none';
    if (grid) grid.style.display = 'grid';
    btnGrid?.setAttribute('aria-pressed', 'true');
    btnList?.setAttribute('aria-pressed', 'false');
    if (btnGrid) btnGrid.classList.add('active');
    if (btnList) btnList.classList.remove('active');
    localStorage.setItem('radar_view', 'grid');
  }} else {{
    if (list) list.style.display = 'block';
    if (grid) grid.style.display = 'none';
    btnList?.setAttribute('aria-pressed', 'true');
    btnGrid?.setAttribute('aria-pressed', 'false');
    if (btnList) btnList.classList.add('active');
    if (btnGrid) btnGrid.classList.remove('active');
    localStorage.setItem('radar_view', 'list');
  }}
}}

async function handleAjaxAction(event, eventId, action, token) {{
  if (event) event.preventDefault();
  try {{
    const resp = await fetch('/api/action', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json', 'X-Radar-Request': '1' }},
      body: JSON.stringify({{ event_id: eventId, action: action, token: token }})
    }});
    const data = await resp.json();
    if (resp.status === 401) {{
      window.location.assign('/settings');
      return;
    }}
    if (data.status === 'ok') {{
      if (action === 'reject' && data.state === 'rejected') {{
        window.location.reload();
        return;
      }}
      showToast('✓ ' + action.toUpperCase() + ' recorded');
      document.querySelectorAll("[data-event-action]").forEach(button => {{
        if (button.dataset.eventId === eventId) {{
          button.classList.toggle("btn-active", data.state === (button.dataset.eventAction === "track" ? "tracked" : "applied"));
        }}
      }});
    }} else {{
      showToast("Could not record action. Try again.");
    }}
  }} catch(e) {{
    showToast("Could not record action. Try again.");
  }}
}}

function copyEventLink(url) {{
  navigator.clipboard.writeText(new URL(url, window.location.origin).href).then(() => {{
    showToast('✓ Link copied to clipboard!');
  }}).catch(() => {{
    showToast('Link: ' + url);
  }});
}}

function showToast(msg) {{
  const t = document.getElementById('toastNotice');
  if (t) {{
    t.textContent = msg;
    t.style.display = 'block';
    setTimeout(() => {{ t.style.display = 'none'; }}, 3000);
  }}
}}

async function triggerDiscoveryScan() {{
  const btn = document.getElementById('btnScanNow');
  if (btn) {{
    btn.disabled = true;
    btn.textContent = '⏳ Scanning...';
  }}
  showToast('Running live discovery scan across 51 platforms...');
  try {{
    const resp = await fetch('/api/scan', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json', 'X-Radar-Request': '1' }},
      body: JSON.stringify({{}})
    }});
    const data = await resp.json();
    if (resp.status === 401) {{
      window.location.assign('/settings');
      return;
    }}
    if (data.status === 'ok') {{
      showToast(`Scan complete: ${{data.new_events}} new events found!`);
      setTimeout(() => window.location.reload(), 1200);
    }} else {{
      showToast('Scan error');
      if (btn) {{ btn.disabled = false; btn.textContent = '⚡ Scan Hackathons'; }}
    }}
  }} catch (e) {{
    showToast('Scan failed');
    if (btn) {{ btn.disabled = false; btn.textContent = '⚡ Scan Hackathons'; }}
  }}
}}

window.addEventListener('DOMContentLoaded', () => {{
  const savedView = localStorage.getItem('radar_view') || 'list';
  setViewMode(savedView);
}});

window.addEventListener('keydown', function(e) {{
  const input = document.getElementById('radarSearch');
  if (e.key === '/' && document.activeElement !== input) {{
    e.preventDefault();
    if (input) {{ input.focus(); input.select(); }}
  }} else if (e.key === 'Escape' && document.activeElement === input) {{
    if (input.defaultValue) window.location.href = document.getElementById('clearRadarSearch').href;
    else input.blur();
  }}
}});
const renderedScan = {json.dumps(stats["last_scan_id"])};
let checkingForScan = false;
setInterval(async () => {{
  const input = document.getElementById('radarSearch');
  if (checkingForScan || document.hidden || document.activeElement === input || input.value !== input.defaultValue) return;
  checkingForScan = true;
  try {{
    const response = await fetch('/api/refresh-status');
    if (!response.ok) return;
    const latest = (await response.json()).scan_id;
    if (latest !== renderedScan && document.activeElement !== input && input.value === input.defaultValue) {{
      window.location.reload();
    }}
  }} catch {{
    // The next check retries if the local tracker is restarting.
  }} finally {{
    checkingForScan = false;
  }}
}}, 60000);

document.addEventListener('DOMContentLoaded', () => {{
  animateGlobe();
  document.getElementById('btnScanNow')?.addEventListener('click', triggerDiscoveryScan);

  document.getElementById('btnViewList')?.addEventListener('click', () => setViewMode('list'));
  document.getElementById('btnViewGrid')?.addEventListener('click', () => setViewMode('grid'));
  document.querySelectorAll('[data-event-action]').forEach(button =>
    button.addEventListener('click', event => handleAjaxAction(event, button.dataset.eventId, button.dataset.eventAction, button.dataset.token)));
  document.querySelectorAll('[data-copy-url]').forEach(button =>
    button.addEventListener('click', () => copyEventLink(button.dataset.copyUrl)));
}});
</script>
</head>
<body>
<a href="#main-content" class="skip-link">Skip to main content</a>
{_navigation("excluded" if current_filter == "excluded" else "dashboard", scan=True)}
{_THEME_SCRIPT}

<main id="main-content" role="main" class="container">
  <div class="hero-intro">
    <div>
      <div class="hero-badge">
        <span class="live-dot-wrap"><span class="live-dot"></span><span class="live-ping"></span></span>
        Bengaluru student edition
      </div>

      <h1 class="hero-title">
        <span class="count">{stats["discovered_count"]}</span> hackathon listings to explore
      </h1>
      <p class="hero-subtitle">
        Email notifications are disabled.
        {("Listing data is stale." if stats["stale"] else "Listings last refreshed " + _esc(_format_ts_date(stats["last_success_at"])) + ".") if stats["last_success_at"] else "No live scans recorded."}
      </p>
    </div>
    {_DASHBOARD_GLOBE}
  </div>

  {f'<p class="hero-subtitle">{stats["scan_failures"]} source(s) failed in the last scan. <a href="/sources?health=failed">View source health</a></p>' if stats["scan_failures"] else ""}
  <div class="hero-metrics">
    <a href="{filter_url('open')}" class="hero-metric-card">
      <div class="metric-num">{total_upcoming}</div>
      <div class="metric-label">open now</div>
    </a>
    <a href="{filter_url('bengaluru')}" class="hero-metric-card">
      <div class="metric-num teal">{bangalore_count}</div>
      <div class="metric-label">bengaluru</div>
    </a>
    <a href="{filter_url('closing_soon')}" class="hero-metric-card">
      <div class="metric-num rose">{closing_soon_count}</div>
      <div class="metric-label">closing within 7 days</div>
    </a>
    <a href="{filter_url('tracked')}" class="hero-metric-card">
      <div class="metric-num gold">{tracked_count}</div>
      <div class="metric-label">shortlisted</div>
    </a>
  </div>

  {next_event_html}

  <div class="radar-box">
    <div class="radar-box-header">
      <div class="filter-pills">
        <a href="{filter_url('discover')}" class="filter-pill {'active' if current_filter in (None, 'discover') else ''}">Discover ({stats["discovered_count"]})</a>
        <a href="{filter_url('open')}" class="filter-pill {'active' if current_filter == 'open' else ''}">Open now ({total_upcoming})</a>
        <a href="{filter_url('bengaluru')}" class="filter-pill {'active' if current_filter == 'bengaluru' else ''}">📍 Bengaluru ({bangalore_count})</a>
        <a href="{filter_url('closing_soon')}" class="filter-pill {'active' if current_filter == 'closing_soon' else ''}">Closing soon ({closing_soon_count})</a>
        <a href="{filter_url('upcoming')}" class="filter-pill {'active' if current_filter == 'upcoming' else ''}">Upcoming ({stats["upcoming_count"]})</a>
        <a href="{filter_url('unverified')}" class="filter-pill {'active' if current_filter == 'unverified' else ''}">Needs verification ({unverified_count})</a>
        <a href="{filter_url('history')}" class="filter-pill {'active' if current_filter == 'history' else ''}">History</a>
        <a href="{filter_url('eligible')}" class="filter-pill {'active' if current_filter == 'eligible' else ''}">✓ Student Eligible ({eligible_count})</a>
        <a href="{filter_url('tracked')}" class="filter-pill {'active' if current_filter == 'tracked' else ''}">Shortlisted ({tracked_count})</a>
        <a href="{filter_url('free_weekend')}" class="filter-pill {'active' if current_filter == 'free_weekend' else ''}">⚡ Free &amp; Weekend</a>
        <a href="{filter_url('high')}" class="filter-pill {'active' if current_filter == 'high' else ''}">🔥 High Priority</a>
        <a href="{filter_url('excluded')}" class="filter-pill {'active' if current_filter == 'excluded' else ''}">Exam conflicts ({blackout_excluded} events)</a>
        <a href="{filter_url('discard')}" class="filter-pill {'active' if current_filter == 'discard' else ''}">Discard pile ({stats["discard_count"]})</a>
      </div>
      <div class="search-controls">
        <form action="/dashboard" role="search" class="search-controls">
          <input type="hidden" name="filter" value="{_esc(current_filter or 'discover')}">
          <div class="search-input-wrap">
            <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
            <input type="search" name="search" id="radarSearch" aria-label="Search events" placeholder="Search events, cities, or sources" maxlength="120" value="{_esc(search)}">
            <span class="kbd" aria-hidden="true">/</span>
          </div>
          <button type="submit">Search</button>
          {f'<a id="clearRadarSearch" href="{filter_url(current_filter, keep_search=False)}">Clear search</a>' if search else ''}
        </form>
        <div style="display:inline-flex; border:1px solid var(--border-color); border-radius:6px; overflow:hidden;">
          <button id="btnViewList" class="btn-shortlist-action active" aria-label="List view" style="border:none; border-radius:0;">☰</button>
          <button id="btnViewGrid" class="btn-shortlist-action" aria-label="Grid view" style="border:none; border-radius:0;">▦</button>
        </div>
      </div>
    </div>

    {f'<p class="nav-link">No listings match “{_esc(search)}” in this category. <a href="{filter_url("discover")}">Search all listings</a></p>' if search and not events else ''}
    {'<p class="nav-link">No listings currently match this category.</p>' if not search and not events else ''}
    <div id="hackathonList">
      {rows_html}
    </div>

    <div id="cardsContainer" class="cards-grid" style="display:none; padding:18px;">
      {cards_html}
    </div>
  </div>
  <nav aria-label="Result pages">{result_count} {'result' if result_count == 1 else 'results'} · Page {page} of {pages} {page_links}</nav>
</main>
{_TRACKER_SCRIPT}

<div id="toastNotice" class="toast-notice" role="status"></div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# DEDICATED BLACKOUT CALENDAR MANAGEMENT PAGE
# ---------------------------------------------------------------------------
def _detect_blackout_institution(title: str, reason: str, category: str) -> str:
    t = (title or "").lower()
    r = (reason or "").lower()
    c = (category or "").lower()
    if "allen" in r or "allen" in t or "internal test" in t or "advanced test" in t or "main test" in t:
        return "ALLEN Career Institute (JEE Coaching)"
    if "grade-11" in r or "grade 11" in t or "pre-board" in t or "ct" in t or "mid term" in t or "revision test" in t or "amaatra" in r or "amaatra" in t or "dps" in r or "dps" in t:
        return "The Amaatra Academy (CBSE Grade 11)"
    if "examination" in c or "exam" in t or "board" in t:
        return "CBSE / School Examination Board"
    return "Personal Schedule"


_CALENDAR_CSS = """
/* Hero & Summary */
.calendar-hero {
  background: var(--bg-card);
  border-radius: var(--radius-md);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-sm);
  padding: 24px 28px;
  margin-bottom: 24px;
  border-left: 5px solid var(--rose-primary);
}
.calendar-hero h1 { margin: 0 0 8px 0; font-size: 26px; font-weight: 800; color: #ffffff; }
.calendar-hero p { margin: 0 0 16px 0; font-size: 14px; color: var(--text-muted); line-height: 1.5; }

.cal-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin-bottom: 24px; }
.cal-stat-card { background: var(--bg-card); border-radius: var(--radius-sm); border: 1px solid var(--border); padding: 14px; text-align: left; }
.cal-stat-card .num { font-size: 24px; font-weight: 800; }
.cal-stat-card .lbl { font-size: 11px; text-transform: uppercase; color: var(--text-muted); font-weight: 700; margin-top: 4px; }

/* Visual Calendar Container */
.cal-view-card {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 14px;
  padding: 22px;
  margin-bottom: 28px;
  box-shadow: 0 4px 20px rgba(0,0,0,0.4);
}

.cal-header-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--border-color);
}

.cal-nav-group {
  display: flex;
  align-items: center;
  gap: 8px;
}

.cal-nav-btn {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
  width: 34px;
  height: 34px;
  border-radius: 8px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  cursor: pointer;
  transition: all 0.15s ease;
}
.cal-nav-btn:hover {
  background: rgba(255, 255, 255, 0.1);
  border-color: var(--teal-accent);
  color: var(--teal-accent);
}

.cal-month-title {
  font-size: 20px;
  font-weight: 700;
  font-family: var(--font-sans);
  color: #ffffff;
  min-width: 200px;
  text-align: center;
  letter-spacing: -0.02em;
}

.cal-quick-jumps {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.cal-pill-btn {
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--border-color);
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 600;
  padding: 5px 12px;
  border-radius: 9999px;
  cursor: pointer;
  transition: all 0.15s ease;
}
.cal-pill-btn:hover {
  color: #fff;
  border-color: rgba(255, 255, 255, 0.2);
}
.cal-pill-btn.active {
  background: rgba(94, 234, 212, 0.12);
  color: var(--teal-accent);
  border-color: rgba(94, 234, 212, 0.4);
}

.cal-today-btn {
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
  font-size: 12px;
  font-weight: 600;
  padding: 5px 14px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s ease;
}
.cal-today-btn:hover {
  border-color: var(--teal-accent);
  color: var(--teal-accent);
}

/* Legend */
.cal-legend-bar {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 16px;
  font-size: 12px;
  color: var(--text-muted);
  padding: 0 4px;
}
.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}
.dot-exam { background: #f43f5e; box-shadow: 0 0 6px rgba(244, 63, 94, 0.6); }
.dot-academic { background: #f59e0b; box-shadow: 0 0 6px rgba(245, 158, 11, 0.6); }
.dot-personal { background: #a855f7; box-shadow: 0 0 6px rgba(168, 85, 247, 0.6); }
.dot-free { background: #10b981; }

/* Month Grid */
.cal-grid-wrapper {
  border: 1px solid var(--border-color);
  border-radius: 10px;
  overflow: hidden;
  background: #090909;
}

.cal-weekdays-row {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  background: rgba(255, 255, 255, 0.03);
  border-bottom: 1px solid var(--border-color);
}
.cal-weekday-cell {
  padding: 10px 8px;
  text-align: center;
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-muted);
}

.cal-days-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  background: rgba(255, 255, 255, 0.04);
  gap: 1px;
}

.cal-day-cell {
  background: #0d0d0d;
  min-height: 92px;
  padding: 8px 9px;
  position: relative;
  transition: all 0.15s ease;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 4px;
  overflow: hidden;
}
.cal-day-cell:hover {
  background: #141414;
  outline: 2px solid var(--teal-accent);
  outline-offset: -1px;
  z-index: 10;
}
.cal-day-cell.other-month {
  background: #080808;
  opacity: 0.35;
}
.cal-day-cell.is-today {
  box-shadow: inset 0 0 0 1.5px var(--teal-accent);
}
.cal-day-cell.is-today .cal-num-badge {
  background: var(--teal-accent);
  color: #0a0a0a;
  border-radius: 4px;
  padding: 1px 5px;
}

.cal-day-cell.has-exam {
  background: rgba(244, 63, 94, 0.08);
}
.cal-day-cell.has-academic {
  background: rgba(245, 158, 11, 0.08);
}
.cal-day-cell.has-personal {
  background: rgba(168, 85, 247, 0.08);
}

.cal-cell-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 2px;
}
.cal-num-badge {
  font-family: var(--font-mono);
  font-size: 12.5px;
  font-weight: 700;
  color: #ededed;
}
.cal-dots-row {
  display: flex;
  align-items: center;
  gap: 3px;
}

.cal-event-pills {
  display: flex;
  flex-direction: column;
  gap: 3px;
  overflow: hidden;
}
.cal-mini-pill {
  font-size: 10px;
  font-weight: 600;
  line-height: 1.25;
  padding: 2px 5px;
  border-radius: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  display: block;
}
.mini-exam {
  background: rgba(244, 63, 94, 0.22);
  color: #fda4af;
  border-left: 2px solid #f43f5e;
}
.mini-academic {
  background: rgba(245, 158, 11, 0.22);
  color: #fde68a;
  border-left: 2px solid #f59e0b;
}
.mini-personal {
  background: rgba(168, 85, 247, 0.22);
  color: #e9d5ff;
  border-left: 2px solid #a855f7;
}

.cal-more-tag {
  font-size: 9.5px;
  color: var(--text-muted);
  font-weight: 600;
  padding-left: 4px;
}

/* Hover Tooltip Card */
#calHoverTooltip {
  position: fixed;
  display: none;
  z-index: 99999;
  pointer-events: none;
  width: 330px;
  background: #121212;
  border: 1px solid rgba(255, 255, 255, 0.16);
  border-radius: 12px;
  box-shadow: 0 18px 40px rgba(0, 0, 0, 0.9), 0 0 0 1px rgba(255, 255, 255, 0.05);
  padding: 15px;
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  color: #ededed;
  font-family: var(--font-sans);
  animation: tipFadeIn 0.12s ease-out;
}
@keyframes tipFadeIn {
  from { opacity: 0; transform: scale(0.97); }
  to { opacity: 1; transform: scale(1); }
}

.tip-date-title {
  font-size: 14px;
  font-weight: 700;
  color: #ffffff;
  padding-bottom: 8px;
  margin-bottom: 10px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.tip-date-badge {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--teal-accent);
}

.tip-items-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.tip-item-card {
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  padding: 10px 11px;
}
.tip-badge-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}
.tip-cat-pill {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding: 2px 7px;
  border-radius: 4px;
}
.tip-cat-exam { background: rgba(244, 63, 94, 0.25); color: #fca5a5; }
.tip-cat-academic { background: rgba(245, 158, 11, 0.25); color: #fef08a; }
.tip-cat-personal { background: rgba(168, 85, 247, 0.25); color: #f3e8ff; }

.tip-status-text {
  font-size: 10.5px;
  font-weight: 600;
}
.tip-status-text.active { color: #4ade80; }
.tip-status-text.disabled { color: var(--text-dim); }

.tip-event-name {
  font-size: 13.5px;
  font-weight: 700;
  color: #ffffff;
  margin-bottom: 5px;
  line-height: 1.3;
}

.tip-school-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11.5px;
  font-weight: 600;
  color: var(--teal-accent);
  background: rgba(94, 234, 212, 0.08);
  padding: 3px 8px;
  border-radius: 5px;
  margin-bottom: 6px;
}

.tip-detail-row {
  font-size: 11px;
  color: var(--text-muted);
  line-height: 1.4;
  margin-top: 4px;
}

.tip-free-box {
  padding: 12px 10px;
  text-align: left;
}
.tip-free-header {
  font-size: 13px;
  font-weight: 700;
  color: #4ade80;
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}
.tip-free-text {
  font-size: 11.5px;
  color: var(--text-muted);
  line-height: 1.4;
}

/* Modal styling */
.modal-overlay {
  width: min(500px, calc(100% - 24px)); max-height: calc(100% - 24px);
  padding: 0; border: 1px solid var(--border);
  border-radius: var(--radius-md); background: var(--bg-card); color: var(--text-main);
  overflow: auto;
}
.modal-overlay::backdrop { background: rgba(0,0,0,0.6); }
.modal-card { padding: clamp(14px, 4vw, 28px); }
.modal-card h3 { margin: 0 0 16px 0; font-size: 18px; }
.form-group { margin-bottom: 14px; }
.form-group label { display: block; font-size: 12px; font-weight: 700; margin-bottom: 5px; color: var(--text-muted); }
.form-input {
  width: 100%; padding: 8px 10px; border-radius: var(--radius-sm);
  border: 1px solid var(--border); background: var(--bg-subtle); color: var(--text-main);
  font-family: inherit; font-size: 13px;
}
.form-input:focus { outline: 2px solid var(--teal-primary); background: var(--bg-card); }
.modal-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; margin-top: 20px; }

/* Table Section */
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }
.section-title { font-size: 17px; font-weight: 800; margin: 0; color: #fff; }

.switch { position: relative; display: inline-block; width: 34px; height: 18px; }
.switch input { opacity: 0; width: 0; height: 0; }
.slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: var(--border-subtle); transition: .2s; border-radius: 18px; }
.slider:before { position: absolute; content: ""; height: 12px; width: 12px; left: 3px; bottom: 3px; background-color: white; transition: .2s; border-radius: 50%; }
input:checked + .slider { background-color: var(--emerald-primary); }
input:checked + .slider:before { transform: translateX(16px); }
.row-disabled { opacity: 0.5; }
"""


_CALENDAR_JS = """
const savedTheme = new URLSearchParams(window.location.search).get('theme') || localStorage.getItem('radar_theme') || (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
document.documentElement.setAttribute('data-theme', savedTheme);

let calYear = 2026;
let calMonth = 10; // 0-based: 10 = November

function escHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function formatDateDisplay(iso) {
  if (!iso) return '';
  const parts = iso.split('-');
  if (parts.length !== 3) return iso;
  const d = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function formatFullDate(iso) {
  if (!iso) return '';
  const parts = iso.split('-');
  if (parts.length !== 3) return iso;
  const d = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
  return d.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' });
}

function getMatchingBlackouts(dateStr) {
  return window.ALL_BLACKOUTS.filter(b => dateStr >= b.start_date && dateStr <= b.end_date);
}

function renderVisualCalendar() {
  const container = document.getElementById('calDaysGrid');
  const titleEl = document.getElementById('calMonthTitle');
  if (!container || !titleEl) return;

  const monthNames = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
  ];
  titleEl.textContent = `${monthNames[calMonth]} ${calYear}`;

  // Update quick jump pills active state
  document.querySelectorAll('.cal-pill-btn').forEach(pill => {
    const pY = Number(pill.dataset.year);
    const pM = Number(pill.dataset.month);
    if (pY === calYear && pM === calMonth) {
      pill.classList.add('active');
    } else {
      pill.classList.remove('active');
    }
  });

  const firstDay = new Date(calYear, calMonth, 1);
  const daysInMonth = new Date(calYear, calMonth + 1, 0).getDate();
  const daysInPrevMonth = new Date(calYear, calMonth, 0).getDate();

  // Weekday offset (Monday as first column: Mon=0, Tue=1, ... Sun=6)
  let startCol = (firstDay.getDay() + 6) % 7;

  const now = new Date();
  const todayStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;

  container.innerHTML = '';

  // 1. Previous month days
  for (let i = startCol - 1; i >= 0; i--) {
    const dayNum = daysInPrevMonth - i;
    const prevMonthIdx = calMonth === 0 ? 11 : calMonth - 1;
    const prevYear = calMonth === 0 ? calYear - 1 : calYear;
    const dateStr = `${prevYear}-${String(prevMonthIdx + 1).padStart(2, '0')}-${String(dayNum).padStart(2, '0')}`;
    const cell = createDayCell(dayNum, dateStr, true, todayStr);
    container.appendChild(cell);
  }

  // 2. Current month days
  for (let day = 1; day <= daysInMonth; day++) {
    const dateStr = `${calYear}-${String(calMonth + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
    const cell = createDayCell(day, dateStr, false, todayStr);
    container.appendChild(cell);
  }

  // 3. Next month days to complete 7-day row
  const totalCellsSoFar = startCol + daysInMonth;
  const remainingCells = (7 - (totalCellsSoFar % 7)) % 7;
  for (let day = 1; day <= remainingCells; day++) {
    const nextMonthIdx = calMonth === 11 ? 0 : calMonth + 1;
    const nextYear = calMonth === 11 ? calYear + 1 : calYear;
    const dateStr = `${nextYear}-${String(nextMonthIdx + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
    const cell = createDayCell(day, dateStr, true, todayStr);
    container.appendChild(cell);
  }
}

function createDayCell(dayNum, dateStr, isOtherMonth, todayStr) {
  const cell = document.createElement('div');
  cell.className = 'cal-day-cell';
  cell.dataset.date = dateStr;
  if (isOtherMonth) cell.classList.add('other-month');
  if (dateStr === todayStr) cell.classList.add('is-today');

  const matching = getMatchingBlackouts(dateStr);
  const hasExam = matching.some(b => b.category === 'Examination Period');
  const hasAcademic = matching.some(b => b.category === 'Academic Test');
  const hasPersonal = matching.some(b => b.category === 'Personal');

  if (hasExam) cell.classList.add('has-exam');
  else if (hasAcademic) cell.classList.add('has-academic');
  else if (hasPersonal) cell.classList.add('has-personal');

  // Header row
  const header = document.createElement('div');
  header.className = 'cal-cell-header';

  const numBadge = document.createElement('span');
  numBadge.className = 'cal-num-badge';
  numBadge.textContent = dayNum;
  header.appendChild(numBadge);

  if (matching.length > 0) {
    const dotsRow = document.createElement('div');
    dotsRow.className = 'cal-dots-row';
    if (hasExam) {
      const d = document.createElement('span');
      d.className = 'legend-dot dot-exam';
      dotsRow.appendChild(d);
    }
    if (hasAcademic) {
      const d = document.createElement('span');
      d.className = 'legend-dot dot-academic';
      dotsRow.appendChild(d);
    }
    if (hasPersonal) {
      const d = document.createElement('span');
      d.className = 'legend-dot dot-personal';
      dotsRow.appendChild(d);
    }
    header.appendChild(dotsRow);
  }
  cell.appendChild(header);

  // Mini event pills (up to 2)
  if (matching.length > 0) {
    const pillsWrap = document.createElement('div');
    pillsWrap.className = 'cal-event-pills';

    const maxShow = 2;
    for (let i = 0; i < Math.min(matching.length, maxShow); i++) {
      const ev = matching[i];
      const pill = document.createElement('span');
      pill.className = 'cal-mini-pill';
      if (ev.category === 'Examination Period') pill.classList.add('mini-exam');
      else if (ev.category === 'Academic Test') pill.classList.add('mini-academic');
      else pill.classList.add('mini-personal');

      // Short label
      let label = ev.title;
      if (label.includes('ALLEN JEE')) label = label.replace('ALLEN JEE', '').trim();
      if (label.length > 18) label = label.slice(0, 16) + '…';
      pill.textContent = label;
      pillsWrap.appendChild(pill);
    }

    if (matching.length > maxShow) {
      const more = document.createElement('span');
      more.className = 'cal-more-tag';
      more.textContent = `+${matching.length - maxShow} more`;
      pillsWrap.appendChild(more);
    }
    cell.appendChild(pillsWrap);
  }

  // Hover Tooltip
  cell.addEventListener('mouseenter', e => handleCellHover(e, dateStr, matching));
  cell.addEventListener('mousemove', e => positionTooltip(e));
  cell.addEventListener('mouseleave', hideTooltip);

  // Click to add / filter
  cell.addEventListener('click', () => {
    document.getElementById('inputStart').value = dateStr;
    document.getElementById('inputEnd').value = dateStr;
    openAddModal();
  });

  return cell;
}

function handleCellHover(e, dateStr, matching) {
  const tooltip = document.getElementById('calHoverTooltip');
  if (!tooltip) return;

  let bodyHtml = '';
  if (matching.length > 0) {
    bodyHtml += '<div class="tip-items-list">';
    matching.forEach(ev => {
      let catClass = 'tip-cat-personal';
      if (ev.category === 'Examination Period') catClass = 'tip-cat-exam';
      else if (ev.category === 'Academic Test') catClass = 'tip-cat-academic';

      const statusHtml = ev.enabled
        ? '<span class="tip-status-text active">● Active Conflict</span>'
        : '<span class="tip-status-text disabled">○ Rule Disabled</span>';

      const dateRange = (ev.start_date !== ev.end_date)
        ? `<div class="tip-detail-row"><strong>Dates:</strong> ${formatDateDisplay(ev.start_date)} &rarr; ${formatDateDisplay(ev.end_date)}</div>`
        : '';

      const reasonHtml = ev.reason
        ? `<div class="tip-detail-row"><strong>Details:</strong> ${escHtml(ev.reason)}</div>`
        : '';

      bodyHtml += `
      <div class="tip-item-card">
        <div class="tip-badge-row">
          <span class="tip-cat-pill ${catClass}">${escHtml(ev.category)}</span>
          ${statusHtml}
        </div>
        <div class="tip-event-name">${escHtml(ev.title)}</div>
        <div class="tip-school-badge">
          <span>🏛️</span>
          <span>${escHtml(ev.institution)}</span>
        </div>
        ${dateRange}
        ${reasonHtml}
      </div>`;
    });
    bodyHtml += '</div>';
  } else {
    bodyHtml = `
    <div class="tip-free-box">
      <div class="tip-free-header">🟢 Free Day · Open Schedule</div>
      <div class="tip-free-text">No exams, school tests, or blackout periods scheduled. Ideal day to attend hackathons!</div>
    </div>`;
  }

  tooltip.innerHTML = `
    <div class="tip-date-title">
      <span>${formatFullDate(dateStr)}</span>
      <span class="tip-date-badge">${matching.length ? `${matching.length} Event${matching.length > 1 ? 's' : ''}` : 'Available'}</span>
    </div>
    ${bodyHtml}
  `;

  positionTooltip(e);
  tooltip.style.display = 'block';
}

function positionTooltip(e) {
  const tooltip = document.getElementById('calHoverTooltip');
  if (!tooltip) return;

  const w = 340;
  const h = tooltip.offsetHeight || 180;
  let left = e.clientX + 16;
  let top = e.clientY + 16;

  if (left + w > window.innerWidth - 16) {
    left = e.clientX - w - 16;
  }
  if (top + h > window.innerHeight - 16) {
    top = e.clientY - h - 16;
  }
  tooltip.style.left = Math.max(10, left) + 'px';
  tooltip.style.top = Math.max(10, top) + 'px';
}

function hideTooltip() {
  const tooltip = document.getElementById('calHoverTooltip');
  if (tooltip) tooltip.style.display = 'none';
}

function openAddModal() {
  document.getElementById('modalTitle').textContent = 'Add Blackout Date / Period';
  document.getElementById('blackoutId').value = '';
  document.getElementById('inputTitle').value = '';
  if (!document.getElementById('inputStart').value) {
    document.getElementById('inputStart').value = '';
    document.getElementById('inputEnd').value = '';
  }
  document.getElementById('inputCategory').value = 'Personal';
  document.getElementById('inputReason').value = '';
  document.getElementById('blackoutError').textContent = '';
  document.getElementById('blackoutModal').showModal();
}

function openEditModal(id, title, start, end, cat, reason, enabled) {
  document.getElementById('modalTitle').textContent = 'Edit Blackout Entry';
  document.getElementById('blackoutId').value = id;
  document.getElementById('blackoutId').dataset.enabled = enabled;
  document.getElementById('inputTitle').value = title;
  document.getElementById('inputStart').value = start;
  document.getElementById('inputEnd').value = end;
  document.getElementById('inputCategory').value = cat;
  document.getElementById('inputReason').value = reason;
  document.getElementById('blackoutError').textContent = '';
  document.getElementById('blackoutModal').showModal();
}

function closeModal() {
  document.getElementById('blackoutModal').close();
}

async function saveBlackout(event) {
  event.preventDefault();
  const id = document.getElementById('blackoutId').value;
  const payload = {
    title: document.getElementById('inputTitle').value,
    start_date: document.getElementById('inputStart').value,
    end_date: document.getElementById('inputEnd').value || document.getElementById('inputStart').value,
    category: document.getElementById('inputCategory').value,
    reason: document.getElementById('inputReason').value,
    enabled: !id || document.getElementById('blackoutId').dataset.enabled === '1'
  };

  const url = id ? `/api/blackouts/${id}` : '/api/blackouts';
  const method = id ? 'PUT' : 'POST';

  try {
    const resp = await fetch(url, {
      method: method,
      headers: { 'Content-Type': 'application/json', 'X-Radar-Request': '1' },
      body: JSON.stringify(payload)
    });
    if (resp.ok) {
      closeModal();
      window.location.reload();
    } else {
      document.getElementById('blackoutError').textContent = resp.status === 401 ? 'Unlock writes in Settings.' : 'Check the title and dates. The end must be on or after the start.';
    }
  } catch (e) {
    document.getElementById('blackoutError').textContent = 'Could not reach the tracker. Try again.';
  }
}

async function toggleBlackout(id) {
  try {
    const resp = await fetch(`/api/blackouts/${id}/toggle`, { method: 'POST', headers: { 'X-Radar-Request': '1' } });
    if (resp.ok) {
      window.location.reload();
    }
  } catch(e) {
    alert('Error toggling blackout entry');
  }
}

async function deleteBlackout(id) {
  if (!confirm('Are you sure you want to remove this blackout entry? Event conflicts will be recomputed.')) return;
  try {
    const resp = await fetch(`/api/blackouts/${id}`, { method: 'DELETE', headers: { 'X-Radar-Request': '1' } });
    if (resp.ok) {
      window.location.reload();
    }
  } catch(e) {
    alert('Error deleting blackout entry');
  }
}

document.addEventListener('DOMContentLoaded', () => {
  renderVisualCalendar();

  // Navigation handlers
  const prevBtn = document.getElementById('calPrevMonth');
  if (prevBtn) prevBtn.addEventListener('click', () => {
    if (calMonth === 0) { calMonth = 11; calYear--; }
    else { calMonth--; }
    renderVisualCalendar();
  });

  const nextBtn = document.getElementById('calNextMonth');
  if (nextBtn) nextBtn.addEventListener('click', () => {
    if (calMonth === 11) { calMonth = 0; calYear++; }
    else { calMonth++; }
    renderVisualCalendar();
  });

  const todayBtn = document.getElementById('calTodayBtn');
  if (todayBtn) todayBtn.addEventListener('click', () => {
    const d = new Date();
    calYear = d.getFullYear();
    calMonth = d.getMonth();
    renderVisualCalendar();
  });

  document.querySelectorAll('.cal-pill-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      calYear = Number(btn.dataset.year);
      calMonth = Number(btn.dataset.month);
      renderVisualCalendar();
    });
  });

  // Modal & form handlers
  const addBtn = document.getElementById('addBlackout');
  if (addBtn) addBtn.addEventListener('click', openAddModal);

  const cancelBtn = document.getElementById('cancelBlackout');
  if (cancelBtn) cancelBtn.addEventListener('click', closeModal);

  const form = document.getElementById('blackoutForm');
  if (form) form.addEventListener('submit', saveBlackout);

  document.querySelectorAll('[data-edit]').forEach(button => button.addEventListener('click', () => {
    const data = button.dataset;
    openEditModal(data.edit, data.title, data.start, data.end, data.category, data.reason, data.enabled);
  }));

  document.querySelectorAll('[data-blackout-toggle]').forEach(control =>
    control.addEventListener('change', () => toggleBlackout(control.dataset.blackoutToggle)));

  document.querySelectorAll('[data-blackout-delete]').forEach(button =>
    button.addEventListener('click', () => deleteBlackout(button.dataset.blackoutDelete)));
});
"""


def _calendar_page(blackouts):
    total = len(blackouts)
    days = set()
    for rule in blackouts:
        if rule["enabled"]:
            start, end = map(date.fromisoformat, (rule["start_date"], rule["end_date"]))
            days.update(start + timedelta(days=i) for i in range((end - start).days + 1))
    personal_count = sum(1 for b in blackouts if b["category"] == "Personal")
    academic_count = sum(1 for b in blackouts if b["category"] == "Academic Test")
    exam_count = sum(1 for b in blackouts if b["category"] == "Examination Period")
    enabled_count = sum(1 for b in blackouts if b["enabled"])

    table_rows = ""
    for b in blackouts:
        bid = b["id"]
        title = _esc(b["title"])
        s_date = _esc(b["start_date"])
        e_date = _esc(b["end_date"])
        cat = _esc(b["category"])
        reason = _esc(b.get("reason") or "")
        enabled = bool(b["enabled"])

        # Category Badge
        if cat == "Examination Period":
            cat_badge = '<span class="pill pill-danger">Examination Period</span>'
        elif cat == "Academic Test":
            cat_badge = '<span class="pill pill-warning">Academic Test</span>'
        else:
            cat_badge = '<span class="pill pill-subtle">Personal</span>'

        date_disp = f"{_format_date(s_date)} &rarr; {_format_date(e_date)}" if s_date != e_date else _format_date(s_date)

        table_rows += f"""
        <tr id="blackout-row-{bid}" class="{'row-disabled' if not enabled else ''}">
          <td>{cat_badge}</td>
          <td><strong>{title}</strong></td>
          <td><code>{date_disp}</code></td>
          <td style="color:var(--text-muted);">{reason}</td>
          <td style="text-align:center;">
            <label class="switch">
              <input type="checkbox" {'checked' if enabled else ''} data-blackout-toggle="{bid}" aria-label="Enable blackout rule">
              <span class="slider round"></span>
            </label>
          </td>
          <td style="text-align:right;">
            <button class="btn btn-sm btn-detail" data-edit="{bid}" data-title="{title}" data-start="{s_date}" data-end="{e_date}" data-category="{cat}" data-reason="{reason}" data-enabled="{int(bool(enabled))}">Edit</button>
            <button class="btn btn-sm btn-reject" data-blackout-delete="{bid}" aria-label="Delete blackout rule">✕</button>
          </td>
        </tr>
        """

    blackouts_json = json.dumps([
        {
            "id": b["id"],
            "title": b["title"],
            "start_date": b["start_date"],
            "end_date": b["end_date"],
            "category": b["category"],
            "reason": b.get("reason") or "",
            "enabled": bool(b["enabled"]),
            "institution": _detect_blackout_institution(b["title"], b.get("reason") or "", b["category"])
        }
        for b in blackouts
    ])

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Academic Blackout Calendar - Buildathon Radar</title>
<style>
{_SHARED_HEAD_CSS}
{_CALENDAR_CSS}
</style>
<script>
window.ALL_BLACKOUTS = {blackouts_json};
{_CALENDAR_JS}
</script>
</head>
<body>
{_navigation("calendar")}
{_THEME_SCRIPT}

<main class="container">
  <section class="calendar-hero">
    <h1>Calendar</h1>
    <p>{total} blackout rules &middot; {len(days)} unique blackout days across academic and personal commitments.</p>
    <p>
      Hover over any date on the calendar below to see scheduled examinations, school tests, JEE assessments, and blackout details with their organizing school or institution.
      Hackathons overlapping any active date are automatically excluded from recommendations.
    </p>
    <button class="btn btn-primary-link" id="addBlackout">+ Add New Blackout Date / Period</button>
  </section>

  <div class="cal-stats">
    <div class="cal-stat-card"><div class="num">{total}</div><div class="lbl">Total Rules</div></div>
    <div class="cal-stat-card"><div class="num" style="color:var(--emerald-primary);">{enabled_count}</div><div class="lbl">Active Rules</div></div>
    <div class="cal-stat-card"><div class="num" style="color:var(--purple-primary);">{personal_count}</div><div class="lbl">Personal Commitments</div></div>
    <div class="cal-stat-card"><div class="num" style="color:var(--amber-primary);">{academic_count}</div><div class="lbl">School &amp; JEE Tests</div></div>
    <div class="cal-stat-card"><div class="num" style="color:var(--rose-primary);">{exam_count}</div><div class="lbl">Exam Periods</div></div>
  </div>

  <!-- Interactive Visual Calendar -->
  <section class="cal-view-card" aria-label="Interactive Monthly Calendar Grid">
    <div class="cal-header-bar">
      <div class="cal-nav-group">
        <button id="calPrevMonth" class="cal-nav-btn" aria-label="Previous Month">&lsaquo;</button>
        <span id="calMonthTitle" class="cal-month-title">November 2026</span>
        <button id="calNextMonth" class="cal-nav-btn" aria-label="Next Month">&rsaquo;</button>
        <button id="calTodayBtn" class="cal-today-btn">Jump to Today</button>
      </div>

      <div class="cal-quick-jumps">
        <span style="font-size:11px; text-transform:uppercase; color:var(--text-muted); font-weight:700; margin-right:4px;">Quick Jump:</span>
        <button class="cal-pill-btn active" data-year="2026" data-month="10">Nov 2026</button>
        <button class="cal-pill-btn" data-year="2026" data-month="11">Dec 2026 (Pre-boards)</button>
        <button class="cal-pill-btn" data-year="2027" data-month="0">Jan 2027 (Finals)</button>
        <button class="cal-pill-btn" data-year="2027" data-month="1">Feb 2027 (Exams)</button>
      </div>
    </div>

    <div class="cal-legend-bar">
      <span class="legend-item"><span class="legend-dot dot-exam"></span> Examination Period</span>
      <span class="legend-item"><span class="legend-dot dot-academic"></span> Academic Test (The Amaatra Academy Pre-boards / ALLEN JEE)</span>
      <span class="legend-item"><span class="legend-dot dot-personal"></span> Personal Commitment</span>
      <span class="legend-item"><span class="legend-dot dot-free"></span> Free Day (Open for Hackathons)</span>
    </div>

    <div class="cal-grid-wrapper">
      <div class="cal-weekdays-row">
        <div class="cal-weekday-cell">Mon</div>
        <div class="cal-weekday-cell">Tue</div>
        <div class="cal-weekday-cell">Wed</div>
        <div class="cal-weekday-cell">Thu</div>
        <div class="cal-weekday-cell">Fri</div>
        <div class="cal-weekday-cell">Sat</div>
        <div class="cal-weekday-cell">Sun</div>
      </div>
      <div id="calDaysGrid" class="cal-days-grid">
        <!-- Rendered dynamically by renderVisualCalendar() -->
      </div>
    </div>
  </section>

  <!-- Floating Hover Tooltip -->
  <div id="calHoverTooltip" role="tooltip" aria-hidden="true"></div>

  <div class="section-head">
    <h2 class="section-title">Configured Blackout Dates &amp; Ranges</h2>
  </div>

  <div class="table-wrap" tabindex="0" role="region" aria-label="Scrollable table">
    <table>
      <thead>
        <tr>
          <th width="140">Category</th>
          <th width="220">Title</th>
          <th width="200">Date Range</th>
          <th>Reason &amp; Description</th>
          <th width="80" style="text-align:center;">Status</th>
          <th width="120" style="text-align:right;">Actions</th>
        </tr>
      </thead>
      <tbody>
        {table_rows}
      </tbody>
    </table>
  </div>
</main>

<dialog id="blackoutModal" class="modal-overlay" aria-labelledby="modalTitle">
  <div class="modal-card">
    <h3 id="modalTitle">Add Blackout Date / Period</h3>
    <form id="blackoutForm">
      <input type="hidden" id="blackoutId">
      <div class="form-group">
        <label for="inputTitle">Title / Name *</label>
        <input type="text" id="inputTitle" class="form-input" maxlength="200" required placeholder="e.g. Major Internal Test 2">
      </div>
      <div class="form-group">
        <label for="inputCategory">Category *</label>
        <select id="inputCategory" class="form-input">
          <option value="Personal">Personal</option>
          <option value="Academic Test">Academic Test</option>
          <option value="Examination Period">Examination Period</option>
        </select>
      </div>
      <div style="display:grid; grid-template-columns:1fr 1fr; gap:10px;">
        <div class="form-group">
          <label for="inputStart">Start Date *</label>
          <input type="date" id="inputStart" class="form-input" required>
        </div>
        <div class="form-group">
          <label for="inputEnd">End Date *</label>
          <input type="date" id="inputEnd" class="form-input" required>
        </div>
      </div>
      <div class="form-group">
        <label for="inputReason">Reason / Notes</label>
        <input type="text" id="inputReason" class="form-input" maxlength="2000" placeholder="e.g. ALLEN JEE Test Day">
      </div>
      <p id="blackoutError" role="alert"></p>
      <div class="modal-actions">
        <button type="button" class="btn btn-detail" id="cancelBlackout">Cancel</button>
        <button type="submit" class="btn btn-primary-link">Save Blackout Date</button>
      </div>
    </form>
  </div>
</dialog>
</body>
</html>"""


# ---------------------------------------------------------------------------
# DEDICATED MULTI-PLATFORM DISCOVERY SOURCES MANAGEMENT PAGE
# ---------------------------------------------------------------------------
def _sources_page(sources, last_scan, recent_scans, health=""):
    latest = {}
    source_history = {}
    for scan in recent_scans:
        for key, telemetry in json.loads(scan.get("details") or "{}").get("source_stats", {}).items():
            latest.setdefault(key, telemetry)
            if "outcome" in telemetry:
                source_history.setdefault(key, []).append(telemetry.get("status", "unknown"))
    def status_of(source):
        state = source.get("last_status")
        if state in {"failed", "blocked", "error"}:
            return "failed"
        if state == "degraded":
            return state
        return "ok" if state else "never"
    filters = " ".join(
        f'<a class="btn" href="/sources{("?health=" + key) if key else ""}" {"aria-current=page" if key == health else ""}>{label}</a>'
        for key, label in (("", "All sources"), ("ok", "Healthy"), ("degraded", "Degraded"),
                           ("failed", "Failed"), ("never", "Never scanned"))
    )
    if health:
        sources = [source for source in sources if source["source_key"] in LIVE_SOURCE_KEYS and status_of(source) == health]

    total = len(sources)
    active_count = sum(1 for s in sources if s["enabled"] and s['source_key'] in LIVE_SOURCE_KEYS)

    last_scan_info = "Never scanned"
    if last_scan and any(source.get("last_status") for source in sources):
        dur = last_scan.get("duration_seconds", 0.0)
        ts = _format_date(last_scan.get("timestamp", ""))
        succ = last_scan.get("successful_sources", 0)
        tot = last_scan.get("total_sources", 0)
        new_ev = last_scan.get("new_events", 0)
        last_scan_info = f"{ts} &middot; {dur}s ({succ}/{tot} feeds responded, +{new_ev} new)"

    CATEGORIES = [
        ("Dedicated Hackathon Platforms", "💻 Dedicated Platforms", "Primary global & Indian hackathon directories and challenge portals."),
        ("Professional and Social Networks", "💬 Professional & Social Networks", "Legitimate public posts, organizer updates, DevRel announcements, and Reddit communities."),
        ("Event Discovery Platforms", "🎟️ Event Discovery Platforms", "Ticketing platforms, developer summits, and city-wide tech competitions."),
        ("Developer and Technology Communities", "👥 Developer & Tech Communities", "Grassroots chapters, Google Developer Groups, AWS & Microsoft communities, and FOSS United."),
        ("Indian College and University Sources", "🎓 Indian Colleges & Tech Fests", "Engineering college fests, IIT/NIT/IIIT hackathons, and Bangalore campus challenges."),
        ("Company and Startup Sources", "🏢 Company & Startup Sources", "Corporate challenges, developer challenges, and Indian tech startup hackathons."),
        ("Search Engine-Based Discovery", "🔍 Targeted Search Pipeline", "Multi-query combinatorial web search across Bangalore, student terms, and dates."),
    ]

    source_by_cat = {}
    for s in sources:
        cat = s["category"]
        source_by_cat.setdefault(cat, []).append(s)

    categories_html = ""
    for cat_key, cat_title, cat_desc in CATEGORIES:
        cat_sources = source_by_cat.get(cat_key, [])
        if not cat_sources:
            continue

        rows = ""
        for s in cat_sources:
            s_key = _esc(s["source_key"])
            name = _esc(s["name"])
            method = _esc(ADAPTER_REGISTRY[s["source_key"]].discovery_method) if s["source_key"] in ADAPTER_REGISTRY else _esc(s["discovery_method"])
            conf = s["confidence_level"]
            supported = s["source_key"] in LIVE_SOURCE_KEYS
            enabled = supported and bool(s["enabled"])
            manual_url = MANUAL_SOURCE_URLS.get(s["source_key"])
            telemetry = latest.get(s["source_key"], {})
            state = status_of(s)
            status = _esc((state.upper() if state != "never" else "Never scanned") if supported else "Manual browsing" if manual_url else "Unsupported")
            history = source_history.get(s["source_key"], [])[:5]
            trend = " → ".join(reversed([state.upper() for state in history]))
            outcome = telemetry.get("outcome")
            if outcome:
                status += " · " + _esc({"empty": "valid empty response", "invalid": "no valid records"}.get(outcome, outcome))
            browse = f'<a href="{_external_url(manual_url)}" target="_blank" rel="noopener">Browse {name}</a>' if manual_url else ""
            if s["source_key"] in {"linkedin", "search_discovery"}:
                browse += ' <a href="/leads">View search leads</a>'
            last_success = s.get("last_success_at")
            if supported and last_success and (
                _datetime.now(timezone.utc) - _datetime.fromisoformat(last_success)
            ) > timedelta(days=14):
                status += " · no successful scan in 14 days"
            if not supported:
                method = "Open source in browser" if manual_url else "No reliable feed configured"
            ev_count = s.get("last_valid") or 0
            l_scan = _format_date(s.get("last_scan")) if supported and s.get("last_status") else "—"
            l_err = _esc(s.get("last_error") or "") if supported and s.get("last_status") else ""

            if conf == "High":
                conf_badge = '<span class="pill" style="background:rgba(16,185,129,0.12); color:#059669; font-weight:700;">🛡️ High</span>'
            elif conf == "Medium-High":
                conf_badge = '<span class="pill" style="background:rgba(20,184,166,0.12); color:#0d9488; font-weight:700;">🛡️ Med-High</span>'
            elif conf == "Medium":
                conf_badge = '<span class="pill" style="background:rgba(59,130,246,0.12); color:#2563eb; font-weight:700;">🛡️ Medium</span>'
            else:
                conf_badge = '<span class="pill" style="background:rgba(245,158,11,0.12); color:#d97706; font-weight:700;">🛡️ Low</span>'

            if not supported:
                conf_badge = "—"

            err_html = f'<div style="font-size:11px; color:var(--rose-primary); margin-top:3px;" title="{l_err}">⚠️ {l_err[:60]}...</div>' if l_err else ""

            rows += f"""
            <tr id="source-row-{s_key}" class="{'row-disabled' if supported and not enabled else ''}">
              <td width="50" style="text-align:center;">
                <label class="switch" title="Enable or disable discovery from this source">
                  <input type="checkbox" {'checked' if enabled else ''} {'disabled' if not supported else ''} data-source-toggle="{s_key}" aria-label="Enable source">
                  <span class="slider round"></span>
                </label>
              </td>
              <td>
                <div style="font-weight:700; color:var(--text-main); font-size:14px;">{name}</div>
                <div style="display:flex; align-items:center; gap:6px; margin-top:2px;">
                  <code style="font-size:11px; background:var(--bg-subtle); padding:1px 5px; border-radius:4px; border:1px solid var(--border);">{s_key}</code>
                  <span style="font-size:12px; color:var(--text-muted);">&middot; {method}</span>
                </div>
                {browse}
                {err_html}
              </td>
              <td width="120">{conf_badge}</td>
              <td width="100" style="text-align:center; font-weight:700; font-size:14px;">{ev_count}</td>
              <td width="100" style="text-align:center; font-size:12px;">
                {status}<br>
                Duplicates: {_esc(telemetry.get("duplicates", "—"))} · Duration: {_esc(telemetry.get("duration_seconds", "—"))} s<br>
                Pagination: {_esc(telemetry.get("pagination", "Not reported"))}<br>
                {f'<span title="Oldest to newest">Recent: {_esc(trend)}</span><br>' if trend else ''}
                Last success: {_esc(s.get("last_success_at") or "—")}<br>
                Last failure: {_esc(s.get("last_failed_at") or "—")}<br>
                Retrieved: {_esc(s.get("last_retrieved") or 0)} · Rejected: {_esc(s.get("last_rejected") or 0)}
              </td>
              <td width="130" style="font-size:12px; color:var(--text-muted);">{l_scan}</td>
            </tr>
            """

        categories_html += f"""
        <div class="category-block">
          <div class="cat-head">
            <div>
              <h3 style="margin:0 0 4px 0; font-size:16px; font-weight:800;">{cat_title}</h3>
              <div style="font-size:12px; color:var(--text-muted);">{cat_desc}</div>
            </div>
            <span class="badge badge-high" style="font-size:11px;">{len(cat_sources)} Sources</span>
          </div>
          <div class="table-wrap" tabindex="0" role="region" aria-label="Scrollable table">
            <table role="table">
              <thead>
                <tr>
                  <th scope="col" style="text-align:center;">Active</th>
                  <th scope="col">Source Name &amp; Discovery Method</th>
                  <th scope="col">Confidence</th>
                  <th scope="col" style="text-align:center;">Discovered</th>
                  <th scope="col" style="text-align:center;">Scan status</th>
                  <th scope="col">Last Scanned</th>
                </tr>
              </thead>
              <tbody>
                {rows}
              </tbody>
            </table>
          </div>
        </div>
        """

    # Recent scans history rows
    scans_html = ""
    histories = []
    merge_rows = []
    for sc in (recent_scans or []):
        summary = json.loads(sc.get("details") or "{}")
        if not all("retrieved" in entry for entry in summary.get("source_stats", {}).values()):
            continue
        sid = sc.get("id")
        ts = _format_date(sc.get("timestamp"))
        dur = sc.get("duration_seconds", 0.0)
        tot_s = sc.get("total_sources", 0)
        succ_s = sc.get("successful_sources", 0)
        fail_s = sc.get("failed_sources", 0)
        new_e = sc.get("new_events", 0)
        upd_e = sc.get("updated_events", 0)

        for merge in summary.get("merges", []):
            event_href = "/event/" + quote(merge["event_id"], safe="")
            links = " · ".join(
                f'<a href="{_external_url(link)}">{_esc(urlsplit(link).hostname)}</a>'
                for link in merge.get("urls", [])
            )
            merge_rows.append(f'<li>Scan {int(sid)} · <a href="{event_href}">Event detail</a> · {links}</li>')

        per_source = "".join(
            f'<li>{_esc(key)} · {_esc(info.get("status", "unknown")).upper()} · '
            f'{_esc(info.get("events", 0))} valid · {_esc(info.get("rejected", "—"))} rejected'
            f'{(" · " + _esc(info["error"])) if info.get("error") else ""}</li>'
            for key, info in sorted(summary.get("source_stats", {}).items())
        )
        if per_source:
            histories.append(f'<details><summary>Scan {int(sid)} · {ts}</summary><ul>{per_source}</ul></details>')
        health_pill = f'<span class="pill pill-mode mode-in-person">✓ {succ_s}/{tot_s}</span>' if fail_s == 0 else f'<span class="pill pill-mode mode-online">⚠️ {succ_s}/{tot_s} ({fail_s} err)</span>'

        scans_html += f"""
        <tr>
          <td id="scan-{int(sid)}"><code>#{sid}</code></td>
          <td><strong>{ts}</strong></td>
          <td>{dur}s</td>
          <td>{health_pill}</td>
          <td><span style="color:var(--emerald-primary); font-weight:700;">+{new_e}</span></td>
          <td>{upd_e}</td>
        </tr>
        """

    if not scans_html:
        scans_html = '<tr><td colspan="6" style="text-align:center; padding:24px; color:var(--text-muted);">No discovery scans recorded yet. Click "Scan All Sources Now" to run discovery.</td></tr>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Discovery Sources - Buildathon Radar</title>
<style>
{_SHARED_HEAD_CSS}
.sources-hero {{
  background: var(--bg-card);
  border-radius: var(--radius-md);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-sm);
  padding: 24px 28px;
  margin-bottom: 24px;
  border-left: 5px solid var(--teal-primary);
}}
.sources-hero h2 {{ margin:0 0 8px 0; font-size:22px; font-weight:800; }}
.sources-hero p {{ margin:0 0 16px 0; font-size:14px; color:var(--text-muted); line-height:1.5; }}

.source-stats {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(160px, 1fr)); gap:12px; margin-bottom:24px; }}
.source-stat-card {{ background:var(--bg-card); border-radius:var(--radius-sm); border:1px solid var(--border); padding:14px; text-align:left; }}
.source-stat-card .num {{ font-size:24px; font-weight:800; }}
.source-stat-card .lbl {{ font-size:11px; text-transform:uppercase; color:var(--text-muted); font-weight:700; margin-top:4px; }}

.category-block {{
  background: var(--bg-card);
  border-radius: var(--radius-md);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-sm);
  margin-bottom: 24px;
  overflow: hidden;
}}
.cat-head {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  background: var(--bg-subtle);
  border-bottom: 1px solid var(--border);
}}

/* Toggle Switch */
.switch {{ position: relative; display: inline-block; width: 34px; height: 18px; }}
.switch input {{ opacity: 0; width: 0; height: 0; }}
.slider {{ position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: var(--border-subtle); transition: .2s; border-radius: 18px; }}
.slider:before {{ position: absolute; content: ""; height: 12px; width: 12px; left: 3px; bottom: 3px; background-color: white; transition: .2s; border-radius: 50%; }}
input:checked + .slider {{ background-color: var(--emerald-primary); }}
input:checked + .slider:before {{ transform: translateX(16px); }}
.row-disabled {{ opacity: 0.45; }}
</style>
<script>
const savedTheme = new URLSearchParams(window.location.search).get('theme') || localStorage.getItem('radar_theme') || (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
document.documentElement.setAttribute('data-theme', savedTheme);


async function toggleSource(key) {{
  try {{
    const resp = await fetch(`/api/sources/${{key}}/toggle`, {{ method: 'POST', headers: {{ 'X-Radar-Request': '1' }} }});
    if (resp.ok) {{
      window.location.reload();
    }} else {{
      alert('Error toggling source');
    }}
  }} catch(e) {{
    alert('Network error toggling source');
  }}
}}

async function triggerDiscoveryScan() {{
  const btn = document.getElementById('btnRunScan');
  if (btn) {{
    btn.disabled = true;
    btn.textContent = '⏳ Scanning enabled feeds...';
  }}
  try {{
    const resp = await fetch('/api/scan', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json', 'X-Radar-Request': '1' }},
      body: JSON.stringify({{}})
    }});
    const data = await resp.json();
    if (resp.status === 401) {{
      window.location.assign('/settings');
      return;
    }}
    if (data.status === 'ok') {{
      alert(`Scan complete in ${{data.duration_seconds}}s across ${{data.total_sources}} sources!\\n\\nNew events: ${{data.new_events}}\\nUpdated events: ${{data.updated_events}}\\nFeeds with usable responses: ${{data.successful_sources}}/${{data.total_sources}}`);
      window.location.reload();
    }} else {{
      alert('Discovery scan failed: ' + (data.detail || data.error || 'Unknown error'));
      if (btn) {{ btn.disabled = false; btn.textContent = '⚡ Scan All Sources Now'; }}
    }}
  }} catch(e) {{
    alert('Network error while running scan');
    if (btn) {{ btn.disabled = false; btn.textContent = '⚡ Scan All Sources Now'; }}
  }}
}}
document.addEventListener('DOMContentLoaded', () => {{
  document.getElementById('btnRunScan').addEventListener('click', triggerDiscoveryScan);
  document.querySelectorAll('[data-source-toggle]').forEach(control =>
    control.addEventListener('change', () => toggleSource(control.dataset.sourceToggle)));
}});
</script>
</head>
<body>
{_navigation("sources")}
{_THEME_SCRIPT}

<main class="container">
  <section class="sources-hero">
    <h1>Discovery sources</h1>
    <p>
      View configured discovery feeds, unsupported sources, and the latest scan results.
    </p>
    <div style="display:flex; align-items:center; gap:12px; flex-wrap:wrap;">
      <button id="btnRunScan" class="btn btn-primary-link" style="font-size:13px; font-weight:700;">⚡ Scan All Sources Now</button>
      <span style="font-size:13px; color:var(--text-muted);">Last scan: <strong>{last_scan_info}</strong></span>
    </div>
  </section>

  <div class="source-stats">
    <div class="source-stat-card">
      <div class="num">{total}</div>
      <div class="lbl">Monitored Platforms</div>
    </div>
    <div class="source-stat-card">
      <div class="num" style="color:var(--emerald-primary);">{active_count}</div>
      <div class="lbl">Active Sources</div>
    </div>

  </div>

  <div class="section-head" style="margin-bottom:16px;">
    <h2 class="section-title">Platform Discovery Sources by Category</h2>
  </div>

  <nav class="tracker-form" aria-label="Filter source health">{filters}</nav>
  {categories_html or "<p>No sources match this health filter.</p>"}

  <div class="category-block" style="margin-top:36px;">
    <div class="cat-head">
      <div>
        <h3 style="margin:0 0 4px 0; font-size:16px; font-weight:800;">📜 Recent Discovery Scan Logs</h3>
        <div style="font-size:12px; color:var(--text-muted);">Historical execution runtimes, source response health, and event delta counts.</div>
      </div>
    </div>
    <div class="table-wrap" tabindex="0" role="region" aria-label="Scrollable table">
      <table role="table">
        <thead>
          <tr>
            <th scope="col">Scan ID</th>
            <th scope="col">Timestamp</th>
            <th scope="col">Duration</th>
            <th scope="col">Sources Health</th>
            <th scope="col">New Events</th>
            <th scope="col">Updated Events</th>
          </tr>
        </thead>
        <tbody>
          {scans_html}
        </tbody>
      </table>
    </div>
  </div>
  <section><h2>Source results by scan</h2>{"".join(histories) or "<p>No source results recorded yet.</p>"}</section>
  <section>
    <h2>Recent source merges</h2>
    {('<ul>' + ''.join(merge_rows) + '</ul>') if merge_rows else '<p>No cross-source merges in the recent scans.</p>'}
  </section>
</main>
</body>
</html>"""


def _event_detail_page(row, canonical, tracker_entry=None, show_notes=True):
    title = _esc(row["title"])
    eid = _esc(row["event_id"])
    url = _external_url(row["url"])
    host = _esc(row["host"] or "Community")
    source = _esc(row["source"] or "Unknown")
    summary = _esc(row["summary"] or "No detailed description available.")
    loc = _esc(row["location"] or "Unknown")
    mode = _esc(row["mode"] or "unknown")
    start = _esc(_format_date(row["event_start"]) or "TBD")
    end = _esc(_format_date(row["event_end"]) or "TBD")
    deadline = _esc(_format_date(row["registration_deadline"]) or "Unknown")
    prize = _esc(row["prize"] or "None listed")
    team = _esc(row["team_size"] or "Unknown")
    eligibility = _esc(row["eligibility"] or "UNKNOWN")
    age = _esc(row["age_restrictions"] or "None specified")
    priority = _esc(row["priority"] or "MEDIUM PRIORITY")
    score = _esc(row["score"])
    why = _esc(row["why"] or "")
    state = _esc(row["state"])
    is_conflict = bool(row["blackout_conflict"] if "blackout_conflict" in row.keys() else ("CONFLICT" in priority))

    reject_token = tracker_store.sign_action("reject", row["event_id"])

    status = lifecycle(row, _datetime.now(timezone(timedelta(hours=5, minutes=30))).date().isoformat())
    sources = json.loads(row["discovery_sources"] or "[]")
    lineage_entries = []
    for entry in sources:
        scan_id = entry.get("scan_id")
        scan_link = f' · <a href="/sources#scan-{scan_id}">Scan {scan_id}</a>' if type(scan_id) is int else ""
        lineage_entries.append(
            f'<li><a href="{_external_url(entry.get("announcement_url") or entry.get("url"))}">'
            f'{_esc(entry.get("source") or entry.get("source_name"))}</a> '
            f'{_esc(entry.get("discovered_at"))}{scan_link}</li>'
        )
    lineage = "".join(lineage_entries)
    scores = json.loads(row["scoring"] or "{}")
    factors = "".join(
        f'<li><label>{label} <meter min="0" max="{maximum}" value="{scores[key]}">'
        f'{scores[key]}</meter></label> {scores[key]}/{maximum}</li>'
        for key, label, maximum in (
            ("theme", "Theme", 35), ("geo", "Location", 30), ("host", "Organizer", 20),
            ("format", "Format", 10), ("team", "Team size", 5), ("timing_bonus", "Timing", 15),
        ) if type(scores.get(key)) is int and scores[key] >= 0
    )
    evidence = _esc(row["eligibility_evidence"] or "Eligibility requires verification.")
    restrictions = json.loads(row["restrictions"] or "{}")
    notes_on_eligibility = "".join(f'<li>{_esc(s)} (source restriction)</li>' for s in restrictions.values())
    if notes_on_eligibility:
        notes_on_eligibility = f"<ul>{notes_on_eligibility}</ul>"
    if row["provenance"] != "live":
        priority, eligibility, score, why = "Archived discovery", "UNKNOWN", "—", "This listing predates provenance checks."

    conflict_note = _exam_overlap(row["conflict_details"]) if is_conflict else ""
    if state == "rejected":
        event_actions = '<span role="status">Moved to the Discard pile.</span>'
    else:
        event_actions = f"""
      <button type="button" id="discardDetail" class="btn" data-id="{eid}" data-token="{reject_token}">Discard</button>
      <span id="discardStatus" role="status"></span>"""

    thumbnail_url = f'/event-image/{_esc(row["slug"])}'
    registration_url = _external_url(row["registration_url"])
    description = _esc(" ".join((row["summary"] or row["title"]).split())[:160])
    structured_data = ""
    if row["provenance"] == "live" and row["event_start"] and (row["location"] not in (None, "", "Unknown") or row["mode"] == "online"):
        schema = {"@context": "https://schema.org", "@type": "Event", "name": row["title"],
                  "startDate": row["event_start"], "url": canonical}
        if row["event_end"]:
            schema["endDate"] = row["event_end"]
        if row["mode"] == "online":
            schema["location"] = {"@type": "VirtualLocation", "url": row["url"]}
        else:
            schema["location"] = {"@type": "Place", "name": row["location"]}
        payload = json.dumps(schema).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
        structured_data = f'<script type="application/ld+json">{payload}</script>'
    status_value = tracker_entry["status"] if tracker_entry else ""
    notes = (tracker_entry["notes"] if tracker_entry else "") if show_notes else None

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} - Buildathon Radar</title>
<link rel="canonical" href="{_esc(canonical)}">
<meta name="description" content="{description}">
<meta property="og:type" content="website">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{description}">
<meta property="og:url" content="{_esc(canonical)}">
<meta property="og:image" content="{_esc(canonical.rsplit('/h/', 1)[0] + thumbnail_url)}">
{structured_data}
<style>
{_SHARED_HEAD_CSS}
.detail-card {{
  background: var(--bg-card);
  border-radius: var(--radius-md);
  padding: clamp(16px, 4vw, 32px);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-sm);
  max-width: 860px;
  margin: 30px auto;
}}
.detail-image {{ width:100%; max-height:220px; object-fit:cover; border-radius:var(--radius-sm); }}
.detail-grid {{
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin: 24px 0;
}}
.info-box {{
  background: var(--bg-subtle);
  padding: 12px 16px;
  border-radius: var(--radius-sm);
}}
.info-label {{ font-size: 11px; text-transform: uppercase; color: var(--text-muted); font-weight: 700; }}
.info-val {{ font-size: 14px; font-weight: 700; color: var(--text-main); margin-top: 4px; }}
.detail-heading, .detail-actions {{
  display: flex; flex-wrap: wrap; gap: 10px; align-items: center;
}}
.detail-heading {{ justify-content: space-between; margin-bottom: 12px; }}
.detail-actions {{ padding-top: 20px; border-top: 1px solid var(--border); margin-top: 24px; }}
@media (max-width: 480px) {{
  .detail-grid {{ grid-template-columns: minmax(0, 1fr); }}
}}
</style>
<script>
const savedTheme = new URLSearchParams(window.location.search).get('theme') || localStorage.getItem('radar_theme') || (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
document.documentElement.setAttribute('data-theme', savedTheme);
</script>
</head>
<body>
{_navigation("")}
{_THEME_SCRIPT}
<main class="container">
  <div class="detail-card">
    <div class="detail-heading">
      <span class="badge {'badge-conflict' if is_conflict else 'badge-high'}">{priority}</span>
      <span style="font-weight:700;">Score: {score}/100 &middot; State: {state.upper()}</span>
    </div>
    <h1 style="margin:0 0 8px 0; font-size:24px;">{title}</h1>
    <div style="color:var(--text-muted); font-size:13px; margin-bottom:18px;">Organised by <strong>{host}</strong> &middot; Source: {source}</div>

    <img src="{thumbnail_url}" class="detail-image" alt="" width="480" height="220">
    {conflict_note if is_conflict else f'<p><strong>Why recommended</strong> {why}</p>'}

    <div class="detail-grid">
      <div class="info-box"><div class="info-label">Location &amp; Format</div><div class="info-val">{loc} ({mode.title()}){(" · " + _esc(row["country"])) if row["country"] else ""}</div></div>
      <div class="info-box"><div class="info-label">Event Schedule</div><div class="info-val">{start} &rarr; {end}</div></div>
      <div class="info-box"><div class="info-label">Student Eligibility</div><div class="info-val">{eligibility}</div><p>{evidence}</p>{notes_on_eligibility}</div>
      <div class="info-box"><div class="info-label">Registration Deadline</div><div class="info-val">{deadline}</div></div>
      <div class="info-box"><div class="info-label">Team Requirements</div><div class="info-val">{team}</div></div>
      <div class="info-box"><div class="info-label">Prize Pool</div><div class="info-val">{prize}</div></div>
      <div class="info-box"><div class="info-label">Participation fee</div><div class="info-val">{_esc(row["participation_fee"] or "Unknown")}</div></div>
    </div>

    <div>
      <h3 style="font-size:15px; margin:0 0 8px 0;">Summary</h3>
      <p style="font-size:14px; line-height:1.6; color:var(--text-muted); margin:0;">{summary}</p>
    </div>

    <p>Status: {_esc(status)} · Verification: {_esc(row["verification_status"] if row["provenance"] == "live" else "Unverified history")}</p>
    <p>First discovered: {_esc(_format_ts_date(row["first_seen"]) if row["first_seen"] else "Unknown")} · Last observed: {_esc(_format_ts_date(row["last_observed"]) if row["last_observed"] else "Unknown")} ·
    Last independently verified: {_esc(_format_ts_date(row["last_verified"]) if row["last_verified"] else "Unknown")}</p>
    <h2>Personal tracker</h2>
    {_tracker_form(row, status_value, notes)}
    {'<p><a href="/settings">Unlock in Settings</a> to edit notes.</p>' if not show_notes else ''}
    <p><a href="/tracker">Open personal tracker</a></p>
    <h2>Discovery sources</h2><ul>{lineage}</ul><a href="/sources">View scan history</a>
    <h2>Relevance factors</h2><ul>{factors}</ul>
    <p>{_esc(", ".join(json.loads(row["tech_categories"] or "[]")) or "No themes identified")}</p>
    {'<p>Factor points are normalized to a score out of 100.</p>' if factors else '<p>No factor breakdown is available.</p>'}
    <div class="detail-actions">
      {event_actions}
      <button type="button" id="copyShareLink" class="btn" data-url="{_esc(canonical)}">Copy link</button>
      <button type="button" id="nativeShare" class="btn" hidden>Share</button>
      <span id="shareStatus" role="status"></span>
      {f'<a class="btn" href="{registration_url}" target="_blank" rel="noopener">Registration page</a>' if registration_url != "#" else ""}
      <a class="btn btn-primary-link" href="{url}" target="_blank" rel="noopener" style="margin-left:auto;">Visit Official Page &rarr;</a>
    </div>
  </div>
</main>
{_TRACKER_SCRIPT}
<script>
const copyShareLink = document.getElementById('copyShareLink');
const nativeShare = document.getElementById('nativeShare');
copyShareLink.addEventListener('click', async () => {{
  const result = document.getElementById('shareStatus');
  try {{
    await navigator.clipboard.writeText(copyShareLink.dataset.url);
    result.textContent = 'Link copied.';
  }} catch {{
    result.textContent = copyShareLink.dataset.url;
  }}
}});
if (navigator.share) {{
  nativeShare.hidden = false;
  nativeShare.addEventListener('click', () => {{
    navigator.share({{title: document.title, url: copyShareLink.dataset.url}}).catch(() => {{}});
  }});
}}

const discard = document.getElementById('discardDetail');
discard?.addEventListener('click', async () => {{
  discard.disabled = true;
  try {{
    const response = await fetch('/api/action', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json', 'X-Radar-Request': '1'}},
      body: JSON.stringify({{event_id: discard.dataset.id, action: 'reject', token: discard.dataset.token}})
    }});
    if (response.status === 401) {{
      window.location.assign('/settings');
      return;
    }}
    if (!response.ok) throw new Error();
    window.location.reload();
  }} catch {{
    document.getElementById('discardStatus').textContent = 'Could not discard this listing.';
    discard.disabled = false;
  }}
}});
</script>
</body>
</html>"""


def _handle_action(action, event_id, token):
    if not event_id:
        return HTMLResponse(_malformed_page(), status_code=400)

    if not tracker_store.verify_action(action, event_id, token):
        return HTMLResponse(_invalid_token_page(), status_code=403)

    conn = _get_conn()
    try:
        row = conn.execute("SELECT title, event_start FROM events WHERE event_id = ?", (event_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        return HTMLResponse(_unknown_event_page(), status_code=404)

    return HTMLResponse(f"""<!doctype html>
<html lang="en"><meta charset="utf-8"><title>Confirm event action</title>
<body><main>
<h1>Confirm event action</h1>
<p>{_esc(row["title"])} · {_esc(_format_date(row["event_start"]) or "Date unknown")}</p>
<button id="confirm" data-action="{_esc(action)}" data-id="{_esc(event_id)}" data-token="{_esc(token)}">Confirm</button>
<p id="status" role="status"></p>
<a href="/dashboard">Return to dashboard</a>
</main><script>
const button = document.getElementById('confirm');
button.addEventListener('click', async () => {{
  button.disabled = true;
  try {{
    const response = await fetch('/api/action', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json', 'X-Radar-Request': '1'}},
      body: JSON.stringify({{event_id: button.dataset.id, action: button.dataset.action, token: button.dataset.token}})
    }});
    if (!response.ok) throw new Error();
    document.getElementById('status').textContent = button.dataset.action === 'reject'
      ? 'Moved to the Discard pile.' : 'Action recorded.';
  }} catch {{
    document.getElementById('status').textContent = 'Could not record action.';
    button.disabled = false;
  }}
}});
</script></body></html>""")


# ---------------------------------------------------------------------------
# API & PAGE ROUTES
# ---------------------------------------------------------------------------
@app.get("/")
def root():
    return RedirectResponse("/dashboard")


@app.get("/health")
def health():
    return {"status": "ok", "email_notifications": "disabled"}


@app.get("/dashboard")
def dashboard(filter: Optional[str] = None, search: str = Query("", max_length=120),
              page: int = Query(1, ge=1, le=10000)):
    search = search.strip()
    aliases = {"bangalore": "bengaluru", "bengaluru": "bengaluru"}
    def words(value):
        return {aliases.get(token, token) for token in re.findall(r"\w+", value.casefold())}

    terms = words(search)
    conn = _get_conn()
    try:
        views = tracker_store.dashboard_views(conn)
        if terms:
            matches = {}
            for rows in views.values():
                for row in rows:
                    eid = row["event_id"]
                    if eid not in matches:
                        text = " ".join(str(row.get(field) or "") for field in (
                            "title", "summary", "host", "location", "source", "category", "mode", "tech_categories",
                        ))
                        vocabulary = words(text)
                        matches[eid] = all(any(word.startswith(term) for word in vocabulary) for term in terms)
            views = {key: [row for row in rows if matches[row["event_id"]]] for key, rows in views.items()}
        stats = tracker_store.get_dashboard_stats(conn, views)
        rows = views.get(filter or "discover", views["discover"])
    finally:
        conn.close()
    if filter == "upcoming":
        today = _datetime.now(tracker_store.IST).date()
        week_end = today + timedelta(days=6 - today.weekday())
        month_end = today + timedelta(days=30)
        rows = sorted(rows, key=lambda row: (row["event_start"], -int(row["score"] or 0)))
        rows = [dict(row, date_group=(
            "This week" if row["event_start"] <= week_end.isoformat() else
            "Next 30 days" if row["event_start"] <= month_end.isoformat() else "Later"
        )) for row in rows]
    page_size = 25
    pages = max(1, (len(rows) + page_size - 1) // page_size)
    page = min(page, pages)
    offset = (page - 1) * page_size
    return HTMLResponse(_dashboard_page(rows[offset:offset + page_size], filter, stats, search, page, pages, len(rows)))


def _shared_page(title, active, body, script=""):
    return HTMLResponse(f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)} · Buildathon Radar</title><style>{_SHARED_HEAD_CSS}</style></head>
<body>{_navigation(active)}{_THEME_SCRIPT}<main class="container">{body}</main>{script}</body></html>""")


def _tracker_form(row, current="", notes=None):
    options = "".join(
        f'<option value="{key}" {"selected" if key == current else ""}>{label}</option>'
        for key, label in personal_tracker.STATUSES.items()
    )
    note = "" if notes is None else f'<label>Personal notes <textarea name="notes" maxlength="4000" rows="3">{_esc(notes)}</textarea></label>'
    return f"""<form class="tracker-form" data-event-id="{_esc(row['event_id'])}">
      <label>Status <select name="status">{options}</select></label>{note}
      <button type="submit">{"Add to tracker" if not current else "Save status" if notes is None else "Save tracker entry"}</button>
      <span role="status"></span>
    </form>"""


_TRACKER_SCRIPT = """<script>
document.querySelectorAll('.tracker-form[data-event-id]').forEach(form => {
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const output = form.querySelector('[role=status]');
    const button = form.querySelector('button');
    button.disabled = true;
    try {
      const response = await fetch('/api/tracker/' + encodeURIComponent(form.dataset.eventId), {
        method: 'PUT',
        headers: {'Content-Type': 'application/json', 'X-Radar-Request': '1'},
        body: JSON.stringify(Object.fromEntries(new FormData(form)))
      });
      if (response.status === 401) {
        output.replaceChildren('Unlock writes in ');
        const link = document.createElement('a');
        link.href = '/settings';
        link.textContent = 'Settings';
        output.append(link);
        return;
      }
      if (!response.ok) throw new Error();
      window.location.reload();
    } catch {
      output.textContent = 'Could not save this entry.';
    } finally {
      button.disabled = false;
    }
  });
});
</script>"""


@app.exception_handler(RequestValidationError)
async def safe_validation_error(request, error):
    if request.url.path == "/api/session":
        return JSONResponse({"detail": "Invalid unlock request"}, status_code=422)
    return await request_validation_exception_handler(request, error)


class UnlockRequest(BaseModel):
    password: str = Field(min_length=1, max_length=512)


class TrackerUpdate(BaseModel):
    status: Literal["interested", "registered", "submitted", "won", "not_for_me"] | None = None
    notes: str | None = Field(default=None, max_length=4000)


@app.post("/api/session")
def unlock(data: UnlockRequest, request: Request):
    if not valid_password(data.password):
        raise HTTPException(401, "Incorrect tracker secret")
    response = JSONResponse({"unlocked": True})
    response.set_cookie(SESSION_COOKIE, issue_session(), max_age=SESSION_AGE, httponly=True,
                        samesite="strict", secure=request.url.scheme == "https")
    return response


@app.delete("/api/session")
def lock_session():
    response = JSONResponse({"unlocked": False})
    response.delete_cookie(SESSION_COOKIE)
    return response


@app.get("/settings")
def settings(request: Request):
    unlocked = authenticated(request)
    body = f"""<h1>Settings</h1><h2>Local write access</h2>
      <p>{'Writes are unlocked for this browser.' if unlocked else 'Use the TRACKER_SECRET from your local .env to unlock tracker edits and manual scans.'}</p>
      <form id="write-access" class="tracker-form" data-unlocked="{int(unlocked)}">
        {'' if unlocked else '<label>Tracker secret <input type="password" name="password" required maxlength="512" autocomplete="current-password"></label>'}
        <button type="submit">{'Lock writes' if unlocked else 'Unlock writes'}</button>
        <span role="status"></span>
      </form>
      <h2>Discovery refresh</h2><p>The local launchd job scans on load and every hour by default.
      Its StartInterval setting controls the interval in seconds.</p><p>Email notifications are disabled.</p>"""
    script = """<script>
const accessForm = document.getElementById('write-access');
accessForm.addEventListener('submit', async event => {
  event.preventDefault();
  const locking = accessForm.dataset.unlocked === '1';
  const button = accessForm.querySelector('button');
  button.disabled = true;
  try {
    const response = await fetch('/api/session', {
      method: locking ? 'DELETE' : 'POST',
      headers: {'Content-Type': 'application/json', 'X-Radar-Request': '1'},
      body: locking ? undefined : JSON.stringify(Object.fromEntries(new FormData(accessForm)))
    });
    if (response.ok) window.location.reload();
    else accessForm.querySelector('[role=status]').textContent = 'Could not change write access. Check the tracker secret.';
  } catch {
    accessForm.querySelector('[role=status]').textContent = 'Could not connect to the tracker.';
  } finally {
    button.disabled = false;
  }
});
</script>"""
    return _shared_page("Settings", "settings", body, script)


@app.get("/api/tracker")
def tracker_api():
    conn = _get_conn()
    try:
        return [{key: row[key] for key in ("event_id", "slug", "title", "tracker_status", "notes", "tracker_updated_at")}
                for row in personal_tracker.entries(conn)]
    finally:
        conn.close()


@app.put("/api/tracker/{event_id}")
def tracker_update(event_id: Annotated[str, ApiPath(min_length=1, max_length=300)], data: TrackerUpdate):
    if data.status is None and data.notes is None:
        raise HTTPException(422, "Supply a status or notes")
    conn = _get_conn()
    try:
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            if not conn.execute("SELECT 1 FROM events WHERE event_id = ?", (event_id,)).fetchone():
                raise HTTPException(404, "Unknown event")
            entry = personal_tracker.save_entry(conn, event_id, data.status, data.notes, tracker_store._now_ist())
            return dict(entry)
    finally:
        conn.close()


@app.get("/tracker")
def tracker_page(request: Request, status: str = Query("", max_length=30), location: str = Query("", max_length=120),
                 after: str = Query("", pattern=r"^(?:\d{4}-\d{2}-\d{2})?$"), before: str = Query("", pattern=r"^(?:\d{4}-\d{2}-\d{2})?$"), relevance: int = Query(0, ge=0, le=100)):
    for value in (after, before):
        if value:
            try:
                date.fromisoformat(value)
            except ValueError:
                raise HTTPException(422, "Invalid tracker filter date")
    if after and before and after > before:
        raise HTTPException(422, "The start of the date range must precede its end")
    conn = _get_conn()
    try:
        rows = personal_tracker.entries(conn)
        selected = []
        for row in rows:
            if status and status != row["tracker_status"]:
                continue
            if location.casefold() not in (row["location"] or "").casefold() or (row["score"] or 0) < relevance:
                continue
            start = row["event_start"]
            if (after and (not start or start < after)) or (before and (not start or start > before)):
                continue
            selected.append(row)

        cards = []
        for row in selected:
            history = "".join(
                f'<li>{_esc(item["action"])}{(" · " + _esc(personal_tracker.STATUSES.get(item["status"], ""))) if item["status"] else ""}'
                f' · <time datetime="{_esc(item["occurred_at"])}">{_esc(item["occurred_at"][:16].replace("T", " "))}</time></li>'
                for item in personal_tracker.activity(conn, row["event_id"])
            )
            cards.append(f"""<article class="tracker-entry"><h2><a href="/h/{_esc(row['slug'])}">{_esc(row['title'])}</a></h2>
              <p>{_esc(row['location'] or 'Location unknown')} · {_esc(_format_date(row['event_start']) or 'Date unknown')}
              · Relevance {row['score'] or 0}/100</p>
              {_tracker_form(row, row['tracker_status'], row['notes'])}
              <details><summary>Activity history</summary><ul>{history}</ul></details></article>""")
    finally:
        conn.close()

    totals = " · ".join(
        f'{label} {sum(row["tracker_status"] == key for row in rows)}'
        for key, label in personal_tracker.STATUSES.items()
    )
    today = _datetime.now(tracker_store.IST).date().isoformat()
    deadlines = sorted(
        (row for row in rows if row["tracker_status"] in {"interested", "registered"}
         and (row["registration_deadline"] or "") >= today),
        key=lambda row: row["registration_deadline"],
    )
    def link(row):
        return f'<a href="/h/{_esc(row["slug"])}">{_esc(row["title"])}</a>'
    deadline_list = "".join(f'<li>{link(row)} · {_esc(_format_date(row["registration_deadline"]))}</li>' for row in deadlines[:8])
    recent_list = "".join(f'<li>{link(row)} · {_esc(personal_tracker.STATUSES[row["tracker_status"]])}</li>' for row in rows[:5])
    options = "".join(f'<option value="{key}" {"selected" if key == status else ""}>{label}</option>'
                      for key, label in personal_tracker.STATUSES.items())
    body = f"""<h1>Personal tracker</h1><p>{sum(row['tracker_status'] != 'not_for_me' for row in rows)} shortlisted · {totals}</p>
    <div class="tracker-overview"><section><h2>Upcoming deadlines</h2><ul>{deadline_list or '<li>No upcoming deadlines</li>'}</ul></section>
    <section><h2>Recently updated</h2><ul>{recent_list or '<li>No tracker activity yet</li>'}</ul></section></div>
    <form action="/tracker" class="tracker-form">
      <label>Status <select name="status"><option value="">All statuses</option>{options}</select></label>
      <label>Location <input name="location" value="{_esc(location)}" maxlength="120"></label>
      <label>From <input type="date" name="after" value="{after or ''}"></label>
      <label>Through <input type="date" name="before" value="{before or ''}"></label>
      <label>Minimum relevance <input name="relevance" type="number" min="0" max="100" value="{relevance}"></label>
      <button>Filter</button><a href="/tracker">Clear filters</a>
    </form><p>{len(selected)} tracker entries</p>
    {''.join(cards) or '<p>No tracker entries match these filters.</p>'}"""
    return _shared_page("Personal tracker", "tracker", body, _TRACKER_SCRIPT)


@app.get("/leads")
def linkedin_leads():
    path = Path(__file__).resolve().parent.parent / "config" / "linkedin_leads.json"
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    today = _datetime.now(tracker_store.IST).date().isoformat()
    entries = "".join(
        f"""<article class="lead">
          <h2>{_esc(item["title"])}</h2>
          <p class="publisher">{_esc(item["publisher"])}</p>
          <p>{_esc(item["description"])}</p>
          <a href="{_external_url(item["url"])}" target="_blank" rel="noopener">View LinkedIn source</a>
        </article>"""
        for item in snapshot["leads"] if item["review_until"] >= today
    )
    searches = (
        ("Bengaluru hackathons on Google", 'site:linkedin.com (Bengaluru OR Bangalore) hackathon registration'),
        ("India student hackathons on Google", 'site:linkedin.com India student hackathon registration'),
    )
    search_links = " ".join(
        f'<a class="btn" href="{_external_url("https://www.google.com/search?" + urlencode({"q": query, "tbs": "qdr:m"}))}"'
        f' target="_blank" rel="noopener">{label}</a>'
        for label, query in searches
    )
    return HTMLResponse(f"""<!doctype html><html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>LinkedIn leads · Buildathon Radar</title>
<style>
{_SHARED_HEAD_CSS}
.leads {{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(280px,100%),1fr));gap:16px;margin-top:24px}}
.lead {{background:var(--bg-card);border:1px solid var(--border);border-radius:8px;padding:16px}}
.lead h2 {{margin:0;font-size:1.15rem}}
.publisher {{color:var(--text-muted)}}
.lead-search {{display:flex;gap:8px;flex-wrap:wrap}}
</style></head>
<body>{_navigation("leads")}{_THEME_SCRIPT}
<main class="container">
  <h1>LinkedIn leads</h1>
  <p>Announcements found in public web results on {_esc(_format_date(snapshot["checked_on"]))}. Confirm dates, registration and eligibility with the organizer.</p>
  <nav class="lead-search" aria-label="Search Google for LinkedIn announcements">{search_links}</nav>
  <div class="leads">{entries or "<p>No current leads in the saved snapshot. Try a Google search above.</p>"}</div>
</main></body></html>""")


@app.get("/calendar")
def calendar_view():
    conn = _get_conn()
    try:
        blackouts = tracker_store.get_blackout_dates(conn)
    finally:
        conn.close()
    return HTMLResponse(_calendar_page(blackouts), status_code=200)


@app.get("/sources")
def sources_view(health: Literal["", "ok", "degraded", "failed", "never"] = ""):
    conn = _get_conn()
    try:
        sources = tracker_store.get_discovery_sources(conn)
        last_scan = tracker_store.get_last_discovery_scan(conn)
        recent_scans = tracker_store.get_recent_discovery_scans(conn, limit=10)
    finally:
        conn.close()
    return HTMLResponse(_sources_page(sources, last_scan, recent_scans, health), status_code=200)


@app.get("/track")
def track(event_id: str | None = None, t: str | None = None):
    return _handle_action("track", event_id, t)


@app.get("/applied")
def applied(event_id: str | None = None, t: str | None = None):
    return _handle_action("applied", event_id, t)


@app.get("/reject")
def reject(event_id: str | None = None, t: str | None = None):
    return _handle_action("reject", event_id, t)


@app.get("/list")
def list_view():
    conn = _get_conn()
    try:
        rows = tracker_store.get_all_events(conn)
    finally:
        conn.close()
    return HTMLResponse(_list_page(rows), status_code=200)


@app.get("/event/{event_id}")
def event_detail(request: Request, event_id: str):
    conn = _get_conn()
    try:
        row = conn.execute("SELECT * FROM events WHERE event_id = ?", (event_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        return HTMLResponse(_unknown_event_page(), status_code=404)
    return _event_response(request, row)


# ---------------------------------------------------------------------------
def _event_response(request, row):
    conn = _get_conn()
    try:
        entry = personal_tracker.get_entry(conn, row["event_id"])
    finally:
        conn.close()
    canonical = str(request.base_url).rstrip("/") + "/h/" + row["slug"]
    return HTMLResponse(_event_detail_page(row, canonical=canonical, tracker_entry=entry,
                                          show_notes=True))


@app.get("/h/{slug}")
def event_by_slug(request: Request, slug: str):
    if len(slug) > 80 or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
        return HTMLResponse(_unknown_event_page(), status_code=404)
    conn = _get_conn()
    try:
        row = conn.execute("SELECT * FROM events WHERE slug = ?", (slug,)).fetchone()
    finally:
        conn.close()
    if row is None:
        return HTMLResponse(_unknown_event_page(), status_code=404)
    return _event_response(request, row)


@app.get("/event-image/{slug}")
def event_image(slug: Annotated[str, ApiPath(max_length=80, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")]):
    conn = _get_conn()
    try:
        row = conn.execute("SELECT image_url FROM events WHERE slug = ?", (slug,)).fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(404, "Unknown event")
    image = event_images.thumbnail(row["image_url"])
    if image:
        media_type, data = image
        return Response(data, media_type=media_type)
    return FileResponse(_ASSETS / "event-placeholder.png", media_type="image/png")


# REST JSON APIS
# ---------------------------------------------------------------------------
@app.get("/api/digest")
def api_digest(limit: int = Query(5, ge=1, le=20)):
    from buildathon_radar.digest import generate_digest_data
    conn = _get_conn()
    try:
        return generate_digest_data(conn=conn, limit_featured=limit)
    finally:
        conn.close()


@app.get("/api/events")
def api_events(
    priority: Optional[str] = None,
    state: Optional[str] = None,
    eligibility: Optional[str] = None,
    search: Optional[str] = Query(None, max_length=120),
    mode: Optional[str] = None,
    blackout_conflict: Optional[int] = Query(None, ge=0, le=1),
    date_status: Optional[str] = None,
    location: Optional[str] = Query(None, max_length=100),
    order_by: Optional[str] = None,
):
    conn = _get_conn()
    try:
        rows = tracker_store.get_events_by_filter(
            conn,
            priority=priority,
            state=state,
            eligibility=eligibility,
            search=search,
            mode=mode,
            blackout_conflict=blackout_conflict,
            date_status=date_status,
            location_keyword=location,
            order_by=order_by,
        )
        return [dict(r) for r in rows if r["provenance"] == "live"]
    finally:
        conn.close()


@app.get("/api/deadlines")
def api_deadlines(limit: int = Query(15, ge=1, le=100)):
    conn = _get_conn()
    try:
        rows = [row for row in tracker_store.dashboard_views(conn)["open"] if row["registration_deadline"]]
        return sorted(rows, key=lambda row: (row["registration_deadline"], row["event_id"]))[:limit]
    finally:
        conn.close()


@app.get("/api/dashboard-stats")
def api_dashboard_stats():
    conn = _get_conn()
    try:
        stats = tracker_store.get_dashboard_stats(conn)
        return stats
    finally:
        conn.close()


@app.get("/api/blackouts")
def api_get_blackouts(category: Optional[str] = None, enabled_only: bool = False):
    conn = _get_conn()
    try:
        rows = tracker_store.get_blackout_dates(conn, enabled_only=enabled_only, category=category)
        return rows
    finally:
        conn.close()


@app.post("/api/blackouts")
def api_create_blackout(data: BlackoutCreate):
    conn = _get_conn()
    try:
        new_id = tracker_store.add_blackout_date(
            conn,
            title=data.title,
            start_date=data.start_date.isoformat(),
            end_date=data.end_date.isoformat(),
            category=data.category,
            reason=data.reason,
            enabled=1 if data.enabled else 0,
        )
        return {"status": "ok", "id": new_id}
    finally:
        conn.close()


@app.put("/api/blackouts/{blackout_id}")
def api_update_blackout(blackout_id: int, data: BlackoutUpdate):
    conn = _get_conn()
    try:
        ok = tracker_store.update_blackout_date(
            conn,
            blackout_id=blackout_id,
            title=data.title,
            start_date=data.start_date.isoformat(),
            end_date=data.end_date.isoformat(),
            category=data.category,
            reason=data.reason,
            enabled=1 if data.enabled else 0,
        )
        if not ok:
            raise HTTPException(status_code=404, detail="Blackout date not found")
        return {"status": "ok", "id": blackout_id}
    finally:
        conn.close()


@app.delete("/api/blackouts/{blackout_id}")
def api_delete_blackout(blackout_id: int):
    conn = _get_conn()
    try:
        ok = tracker_store.delete_blackout_date(conn, blackout_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Blackout date not found")
        return {"status": "ok", "deleted_id": blackout_id}
    finally:
        conn.close()


@app.post("/api/blackouts/{blackout_id}/toggle")
def api_toggle_blackout(blackout_id: int):
    conn = _get_conn()
    try:
        ok = tracker_store.toggle_blackout_date(conn, blackout_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Blackout date not found")
        return {"status": "ok", "toggled_id": blackout_id}
    finally:
        conn.close()


@app.post("/api/action")
def api_action(req: ActionRequest):
    if not req.event_id or req.action not in ("track", "applied", "reject"):
        raise HTTPException(status_code=400, detail="Invalid request parameters")

    if not tracker_store.verify_action(req.action, req.event_id, req.token):
        raise HTTPException(status_code=403, detail="Invalid action token")

    conn = _get_conn()
    try:
        result, row = tracker_store.apply_action(conn, req.action, req.event_id)
        if result == "unknown_event":
            raise HTTPException(status_code=404, detail="Unknown event")
        return {
            "status": "ok",
            "result": result,
            "event_id": req.event_id,
            "state": row["state"] if row else None,
        }
    finally:
        conn.close()


@app.get("/api/sources")
def api_get_sources():
    conn = _get_conn()
    try:
        sources = tracker_store.get_discovery_sources(conn)
        for source in sources:
            supported = source["source_key"] in LIVE_SOURCE_KEYS
            source["supported"] = supported
            source["browse_url"] = MANUAL_SOURCE_URLS.get(source["source_key"])
            adapter = ADAPTER_REGISTRY.get(source["source_key"])
            if supported and adapter:
                source["discovery_method"] = adapter.discovery_method
            if not supported or not source["last_status"]:
                source["last_status"] = "unscanned" if supported else "unsupported"
                for key in ("last_scan", "events_discovered", "success_count", "fail_count", "last_error"):
                    source.pop(key, None)
            if not supported:
                source["enabled"] = 0
                source["discovery_method"] = "Manual browsing" if source["browse_url"] else "No reliable feed configured"
        return sources
    finally:
        conn.close()


@app.post("/api/sources/{source_key}/toggle")
def api_toggle_source(source_key: str):
    if source_key not in LIVE_SOURCE_KEYS:
        raise HTTPException(status_code=404, detail="Source feed unavailable")
    conn = _get_conn()
    try:
        new_state = tracker_store.toggle_discovery_source(conn, source_key)
        if new_state is None:
            raise HTTPException(status_code=404, detail="Discovery source not found")
        return {"status": "ok", "source_key": source_key, "enabled": bool(new_state)}
    finally:
        conn.close()


@app.post("/api/scan")
def api_run_scan(req: Optional[ScanRequest] = None):
    if req and req.sources is not None and any(len(key) > 60 for key in req.sources):
        raise HTTPException(status_code=422, detail="Invalid source key")
    if not _scan_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Scan already running")
    try:
        engine = DiscoveryEngine(db_path=DB_PATH)
        source_keys = req.sources if req else None
        force_all = req.force_all if req else False
        result = engine.run_scan(source_keys=source_keys, force_all=force_all)
        return {"status": "ok", **result}
    except ScanInProgress:
        raise HTTPException(status_code=409, detail="Scan already running")
    except Exception:
        raise HTTPException(status_code=500, detail="Discovery scan failed")
    finally:
        _scan_lock.release()


@app.get("/api/refresh-status")
def refresh_status():
    conn = _get_conn()
    try:
        row = conn.execute("SELECT MAX(id) AS scan_id FROM discovery_scans").fetchone()
        return {"scan_id": row["scan_id"]}
    finally:
        conn.close()


@app.get("/api/scans")
def api_get_scans(limit: int = Query(10, ge=1, le=100)):
    conn = _get_conn()
    try:
        scans = tracker_store.get_recent_discovery_scans(conn, limit=limit)
        return scans
    finally:
        conn.close()
