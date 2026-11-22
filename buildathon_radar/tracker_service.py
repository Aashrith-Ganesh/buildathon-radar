from __future__ import annotations

import html
import json
import os
import re
from datetime import datetime as _datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from buildathon_radar import tracker_store
from buildathon_radar.discovery.engine import DiscoveryEngine

app = FastAPI(title="Buildathon Radar Tracker & Blackout Manager")
DB_PATH = "tracker.db"

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
    title: str
    start_date: str
    end_date: str
    category: str
    reason: Optional[str] = ""
    enabled: Optional[bool] = True


class BlackoutUpdate(BaseModel):
    title: str
    start_date: str
    end_date: str
    category: str
    reason: Optional[str] = ""
    enabled: Optional[bool] = True


class ActionRequest(BaseModel):
    event_id: str
    action: str
    token: Optional[str] = None


class ScanRequest(BaseModel):
    sources: Optional[List[str]] = None
    force_all: Optional[bool] = False


def _get_conn():
    return tracker_store.connect(DB_PATH)


def _esc(value):
    if value is None:
        return ""
    return html.escape(str(value))


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
        link_html = f'<p class="link-p"><a href="{_esc(event_url)}" class="event-link" target="_blank" rel="noopener">Open event &rarr;</a></p>'

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
const savedTheme = localStorage.getItem('radar_theme') || 'dark';
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
    return _page("Unknown event", [
        "This link may be from a digest sent before tracking existed, or the "
        "event was never in a digest. Nothing was recorded.",
    ])


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
    url = _esc(row["url"])
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
body {{ margin:0; padding:0; background-color:{PAGE_BG}; font-family:{FONT_STACK}; color:#2e4243; }}
header {{ background-color:{TEAL_DARK}; padding:20px 24px; }}
header .title {{ font-size:20px; font-weight:bold; color:#eaf6f4; }}
header .subtitle {{ font-size:12px; color:#8fa6a6; margin-top:4px; }}
main {{ max-width:680px; margin:0 auto; padding:20px 16px; }}
section {{ margin-bottom:24px; }}
h2 {{ font-size:14px; text-transform:uppercase; letter-spacing:0.5px; color:{ACCENT}; margin:0 0 8px 0; }}
h2 .count {{ color:#8a9a9a; font-weight:normal; }}
.event-row {{ background-color:{CARD_BG}; border-radius:6px; padding:12px 16px; margin-bottom:8px; box-shadow:0 1px 3px rgba(0,0,0,0.04); }}
.event-title {{ display:block; font-size:16px; font-weight:bold; color:{TEAL_DARK}; text-decoration:none; word-break:break-word; }}
.event-meta {{ font-size:13px; color:#6b7b7b; margin-top:4px; }}
.empty {{ font-size:14px; color:#6b7b7b; padding:24px 16px; }}
.nav-links {{ margin-bottom:16px; font-size:13px; }}
.nav-links a {{ color:{ACCENT}; font-weight:bold; text-decoration:none; margin-right:12px; }}
</style>
</head>
<body>
<header>
<div class="title">Buildathon Radar Tracker</div>
<div class="subtitle">Personalized Hackathon Tracker for Indian High-School Students</div>
</header>
<main>
<div class="nav-links">
<a href="/dashboard">&larr; Switch to Full Interactive Dashboard</a>
</div>
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
  --teal-accent: #059669;
  --gold-prize: #d97706;
  --green-score: #16a34a;
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

/* Header - Exact hackathonradar.com sticky navbar */
header.app-header {
  position: sticky;
  top: 0;
  z-index: 50;
  border-bottom: 1px solid var(--border-color);
  background: rgba(10, 10, 10, 0.85);
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
  color: #fff;
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
.nav-link:hover { color: #fff; background: rgba(255,255,255,0.06); }
.nav-link.active { color: #fff; background: rgba(255,255,255,0.08); border: 1px solid var(--border-color); }
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
"""


def _dashboard_page(events, current_filter=None):
    today = _datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d")
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
    next_event = stats["next_eligible_event"]

    # Spotlight Hero: Next Eligible Hackathon
    next_event_html = ""
    if next_event:
        ne_id = _esc(next_event["event_id"])
        ne_title = _esc(next_event["title"])
        ne_url = _esc(next_event["url"])
        ne_host = _esc(next_event["host"] or "Community")
        ne_loc = _esc(next_event["location"] or "Online")
        ne_mode = _esc(next_event["mode"] or "unknown")
        ne_start_raw = next_event["event_start"] or ""
        ne_start = _esc(_format_date(ne_start_raw))
        ne_prize = _esc(next_event["prize"] or "Unspecified")
        ne_team = _esc(next_event["team_size"] or "3-5 members")
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
              <span class="spotlight-subtag">Zero Blackout Conflicts &middot; Class 11/12 Eligible</span>
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
              <a class="btn-shortlist-action" href="/track?event_id={ne_id}&t={ne_token}" onclick="handleAjaxAction(event, '{ne_id}', 'track', '{ne_token}')">📌 Shortlist Opportunity</a>
              <a class="btn-primary-link" href="{ne_url}" target="_blank" rel="noopener">Open Official Page &rarr;</a>
              <button class="btn-shortlist-action" onclick="copyEventLink('{ne_url}')" title="Copy URL">🔗 Share</button>
            </div>
          </div>
        </div>
        """

    # Generate hackathonradar.com style rows
    rows_html = ""
    cards_html = ""

    for e in events:
        eid = _esc(e["event_id"])
        title = _esc(e["title"])
        host = _esc(e["host"] or "Community")
        source = _esc(e["source"] or "Discovery")
        loc = _esc(e["location"] or "Online")
        mode = _esc(e["mode"] or "unknown")
        category = _esc(e["category"] or "Hackathon")
        start_raw = e["event_start"] or ""
        end_raw = e["event_end"] or start_raw
        start = _esc(_format_date(start_raw) or "TBD")
        end = _esc(_format_date(end_raw) or "TBD")
        deadline_raw = e["registration_deadline"] or ""
        deadline = _esc(_format_date(deadline_raw) or "Open")
        team = _esc(e["team_size"] or "3-5 members")
        prize = _esc(e["prize"] or "Unspecified")
        score = int(e["score"]) if e["score"] is not None else 0
        priority = _esc(e["priority"])
        eligibility = _esc(e["eligibility"] or "UNKNOWN")
        why = _esc(e["why"] or "")
        state = _esc(e["state"])
        url = _esc(e["url"])
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
        duration_str = "1d"
        try:
            if start_raw and end_raw:
                d1 = _datetime.strptime(start_raw[:10], "%Y-%m-%d")
                d2 = _datetime.strptime(end_raw[:10], "%Y-%m-%d")
                days = (d2 - d1).days + 1
                duration_str = f"{days}d" if days > 1 else "1d"
        except Exception:
            pass

        # Bangalore Indicator
        is_bangalore = any(
            p in loc.lower() or p in title.lower() or p in why.lower()
            for p in ["bengaluru", "bangalore", "koramangala", "indiranagar", "whitefield", "hsr", "electronic city", "hebbal"]
        )

        # Tags
        tags_html = ""
        if is_conflict:
            tags_html += '<span class="tag-conflict">Blackout Conflict</span>'
        elif "HIGH" in priority:
            tags_html += '<span class="tag-featured">🔥 HIGH PRIORITY</span>'
        
        if is_bangalore:
            tags_html += '<span class="tag-bengaluru">Bengaluru</span>'

        if eligibility == "ELIGIBLE":
            tags_html += '<span class="tag-bengaluru">Class 11/12</span>'

        track_token = tracker_store.sign_action("track", e["event_id"])
        applied_token = tracker_store.sign_action("applied", e["event_id"])
        reject_token = tracker_store.sign_action("reject", e["event_id"])

        state_pill = f'<span class="state-pill state-{state}">{state.title()}</span>'

        # HackathonRadar Row
        rows_html += f"""
        <div class="hr-row {'row-conflict' if is_conflict else ''}" data-id="{eid}" data-mode="{mode}" data-bengaluru="{'true' if is_bangalore else 'false'}" data-score="{score}" data-start="{start_raw}" data-title="{title.lower()}">
          <span class="hr-time-pill" title="{start}">{short_date}</span>
          <div class="hr-title-wrap">
            <div class="hr-title-top">
              {tags_html}
              <a href="{url}" target="_blank" rel="noopener">{title}</a>
            </div>
            <div class="hr-subtext">
              <span>🏢 {host} via {source}</span> &middot;
              <span>📍 {loc} ({mode.title()})</span> &middot;
              <span>👥 {team}</span> &middot;
              <span class="font-mono">📅 Closes: {deadline}</span>
              {f'<span class="conflict-inline-warn">⛔ {why}</span>' if is_conflict else ''}
            </div>
          </div>
          <div class="hr-prize">{prize}</div>
          <div class="hr-score-wrap" title="Match score: {score}/100">
            <span class="hr-score-num">{score}</span>
            <div class="hr-score-bar-bg"><div class="hr-score-bar-fill" style="width: {score}%;"></div></div>
          </div>
          <div class="hr-actions">
            <a class="btn-shortlist-action {'btn-active' if state == 'tracked' else ''}" href="/track?event_id={eid}&t={track_token}" onclick="handleAjaxAction(event, '{eid}', 'track', '{track_token}')">📌 Shortlist</a>
            <a class="btn-shortlist-action {'btn-active' if state == 'applied' else ''}" href="/applied?event_id={eid}&t={applied_token}" onclick="handleAjaxAction(event, '{eid}', 'applied', '{applied_token}')">🎯 Applied</a>
            <button class="btn-shortlist-action" onclick="copyEventLink('{url}')" title="Copy link">🔗</button>
            <a class="btn-shortlist-action" href="/event/{eid}">Details</a>
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
          <h3 class="card-title"><a href="{url}" target="_blank" rel="noopener">{title}</a></h3>
          <div class="card-host">🏢 {host} <span class="source-tag">via {source}</span></div>
          <div class="card-specs">
            <div class="spec-item"><span class="spec-k">Dates:</span> <span class="spec-v font-mono">{start} &rarr; {end}</span></div>
            <div class="spec-item"><span class="spec-k">Deadline:</span> <span class="spec-v font-mono">{deadline}</span></div>
            <div class="spec-item"><span class="spec-k">Prize Pool:</span> <span class="spec-v hr-prize">{prize}</span></div>
            <div class="spec-item"><span class="spec-k">Location:</span> <span class="spec-v">{loc} ({mode.title()})</span></div>
          </div>
          <div class="card-why">{why}</div>
          <div class="card-footer">
            <div>{state_pill}</div>
            <div class="card-actions">
              <a class="btn-shortlist-action {'btn-active' if state == 'tracked' else ''}" href="/track?event_id={eid}&t={track_token}" onclick="handleAjaxAction(event, '{eid}', 'track', '{track_token}')">📌 Shortlist</a>
              <a class="btn-shortlist-action {'btn-active' if state == 'applied' else ''}" href="/applied?event_id={eid}&t={applied_token}" onclick="handleAjaxAction(event, '{eid}', 'applied', '{applied_token}')">🎯 Applied</a>
              <button class="btn-shortlist-action" onclick="copyEventLink('{url}')" title="Copy link">🔗</button>
              <a class="btn-shortlist-action" href="/event/{eid}">Details</a>
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

.hero-title {{
  font-size: 48px;
  font-weight: 700;
  line-height: 1.05;
  letter-spacing: -0.035em;
  color: #ffffff;
  margin: 0 0 16px 0;
  max-width: 640px;
}}
.hero-title .count {{
  font-family: var(--font-mono);
  font-feature-settings: 'cv01';
  color: #fff;
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
  color: #fff;
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
.spotlight-title a {{ color: #fff; text-decoration: none; }}
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
.search-input-wrap {{
  display: flex;
  align-items: center;
  gap: 8px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 6px 12px;
  min-width: 280px;
}}
.search-input-wrap input {{
  background: transparent;
  border: none;
  outline: none;
  color: #fff;
  font-size: 13px;
  font-family: inherit;
  width: 100%;
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
.filter-pill:hover {{ color: #fff; background: rgba(255, 255, 255, 0.08); }}
.filter-pill.active {{ color: #fff; background: rgba(255, 255, 255, 0.12); border-color: var(--border-color); font-weight: 600; }}

/* Row Component */
.hr-row {{
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto auto auto;
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
  color: #fff;
}}
.hr-title-top a {{
  color: #fff;
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
.conflict-inline-warn {{ color: var(--rose-conflict); margin-left: 6px; }}

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
.card-title a {{ color: #fff; text-decoration: none; }}
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
.spec-v {{ color: #fff; font-weight: 500; }}
.card-why {{ font-size: 12px; color: var(--text-muted); background: rgba(255,255,255,0.03); padding: 8px; border-radius: 4px; margin-bottom: 12px; line-height: 1.4; flex: 1; }}
.card-footer {{ display: flex; justify-content: space-between; align-items: center; padding-top: 10px; border-top: 1px solid var(--border-color); }}
.card-actions {{ display: flex; gap: 4px; }}

.state-pill {{ font-size: 11px; font-family: var(--font-mono); color: var(--text-muted); }}

/* Toast Notice */
.toast-notice {{
  position: fixed;
  bottom: 24px;
  right: 24px;
  background: #141414;
  color: #fff;
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
  .hr-row {{ grid-template-columns: auto 1fr auto; gap: 8px; }}
  .hr-prize {{ display: none; }}
  .search-input-wrap {{ min-width: 100%; }}
  .radar-box-header {{ flex-direction: column; align-items: stretch; }}
}}
</style>
<script>
function toggleTheme() {{
  const cur = document.documentElement.getAttribute('data-theme') || 'dark';
  const nxt = cur === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', nxt);
  localStorage.setItem('radar_theme', nxt);
  const btn = document.getElementById('themeToggleBtn');
  if (btn) btn.textContent = nxt === 'dark' ? '☀️ Light' : '🌙 Dark';
}}

function setViewMode(mode) {{
  const list = document.getElementById('hackathonList');
  const grid = document.getElementById('cardsContainer');
  const btnList = document.getElementById('btnViewList');
  const btnGrid = document.getElementById('btnViewGrid');

  if (mode === 'grid') {{
    if (list) list.style.display = 'none';
    if (grid) grid.style.display = 'grid';
    if (btnGrid) btnGrid.classList.add('active');
    if (btnList) btnList.classList.remove('active');
    localStorage.setItem('radar_view', 'grid');
  }} else {{
    if (list) list.style.display = 'block';
    if (grid) grid.style.display = 'none';
    if (btnList) btnList.classList.add('active');
    if (btnGrid) btnGrid.classList.remove('active');
    localStorage.setItem('radar_view', 'list');
  }}
}}

function filterEvents() {{
  const query = (document.getElementById('radarSearch').value || '').toLowerCase().trim();
  const rows = Array.from(document.querySelectorAll('.hr-row'));
  const cards = Array.from(document.querySelectorAll('.event-card'));
  let matchCount = 0;

  function matches(el) {{
    const text = el.innerText.toLowerCase();
    if (query && !text.includes(query)) return false;
    return true;
  }}

  rows.forEach(r => {{
    const ok = matches(r);
    r.style.display = ok ? 'grid' : 'none';
    if (ok) matchCount++;
  }});

  cards.forEach(c => {{
    const ok = matches(c);
    c.style.display = ok ? 'flex' : 'none';
  }});

  const countEl = document.getElementById('searchCount');
  if (countEl) {{
    countEl.textContent = query ? matchCount + ' matching' : '';
  }}
}}

async function handleAjaxAction(event, eventId, action, token) {{
  if (event) event.preventDefault();
  try {{
    const resp = await fetch('/api/action', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ event_id: eventId, action: action, token: token }})
    }});
    const data = await resp.json();
    if (data.status === 'ok') {{
      showToast('✓ ' + action.toUpperCase() + ' recorded');
      document.querySelectorAll(`[data-id="${{eventId}}"] .btn-shortlist-action`).forEach(b => {{
        if (b.innerText.toLowerCase().includes(action)) b.classList.add('btn-active');
      }});
    }} else {{
      window.location.href = `/${{action}}?event_id=${{eventId}}&t=${{token}}`;
    }}
  }} catch(e) {{
    window.location.href = `/${{action}}?event_id=${{eventId}}&t=${{token}}`;
  }}
}}

function copyEventLink(url) {{
  navigator.clipboard.writeText(url).then(() => {{
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
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{}})
    }});
    const data = await resp.json();
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
    input.value = '';
    filterEvents();
    input.blur();
  }}
}});
</script>
</head>
<body>
<a href="#main-content" class="skip-link">Skip to main content</a>
<header class="app-header" role="banner">
  <div class="header-inner">
    <a href="/dashboard" class="brand-link">
      <div class="brand-icon">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"></polygon></svg>
      </div>
      <span>HackathonRadar</span>
    </a>
    <div class="nav-links">
      <a href="/dashboard" class="nav-link {'active' if not current_filter or current_filter != 'excluded' else ''}">Dashboard</a>
      <a href="/dashboard?filter=excluded" class="nav-link {'active' if current_filter == 'excluded' else ''}">Blackout Conflicts</a>
      <a href="/calendar" class="nav-link">Personal Calendar</a>
      <a href="/sources" class="nav-link">51 Sources</a>
      <button id="btnScanNow" class="btn-scan" onclick="triggerDiscoveryScan()">⚡ Scan Hackathons</button>
      <a href="/list" class="nav-link">List View</a>
      <button id="themeToggleBtn" class="nav-link" onclick="toggleTheme()" style="cursor:pointer; background:transparent; border:none;">☀️ Light</button>
    </div>
  </div>
</header>

<main id="main-content" role="main" class="container">
  <div class="hero-badge">
    <span class="live-dot-wrap"><span class="live-dot"></span><span class="live-ping"></span></span>
    Live &middot; Refreshed Daily &middot; Bengaluru Student Edition
  </div>

  <h1 class="hero-title">
    <span class="count">{total_upcoming}</span> hackathons are open right now.
  </h1>
  <p class="hero-subtitle">
    Every hackathon worth your time, in one place. We track Bangalore &amp; global student hackathons, quality-score each event, and blackout-filter your exam and test dates.
  </p>

  <div class="hero-metrics">
    <a href="/dashboard" class="hero-metric-card">
      <div class="metric-num">{total_upcoming}</div>
      <div class="metric-label">open now</div>
    </a>
    <a href="/dashboard?filter=bengaluru" class="hero-metric-card">
      <div class="metric-num teal">{bangalore_count}</div>
      <div class="metric-label">bengaluru</div>
    </a>
    <a href="/dashboard?filter=closing_soon" class="hero-metric-card">
      <div class="metric-num rose">{closing_soon_count}</div>
      <div class="metric-label">closing soon</div>
    </a>
    <a href="/dashboard?filter=tracked" class="hero-metric-card">
      <div class="metric-num gold">{tracked_count}</div>
      <div class="metric-label">shortlisted</div>
    </a>
  </div>

  {next_event_html}

  <div class="radar-box">
    <div class="radar-box-header">
      <div class="filter-pills">
        <a href="/dashboard" class="filter-pill {'active' if not current_filter else ''}">All Open ({total_upcoming})</a>
        <a href="/dashboard?filter=bengaluru" class="filter-pill {'active' if current_filter == 'bengaluru' else ''}">📍 Bengaluru ({bangalore_count})</a>
        <a href="/dashboard?filter=eligible" class="filter-pill {'active' if current_filter == 'eligible' else ''}">✓ Student Eligible ({eligible_count})</a>
        <a href="/dashboard?filter=tracked" class="filter-pill {'active' if current_filter == 'tracked' else ''}">📌 Shortlisted ({tracked_count})</a>
        <a href="/dashboard?filter=free_weekend" class="filter-pill {'active' if current_filter == 'free_weekend' else ''}">⚡ Free &amp; Weekend</a>
        <a href="/dashboard?filter=high" class="filter-pill {'active' if current_filter == 'high' else ''}">🔥 High Priority</a>
        <a href="/dashboard?filter=excluded" class="filter-pill {'active' if current_filter == 'excluded' else ''}">⛔ Blackouts ({blackout_excluded})</a>
      </div>
      <div style="display:flex; align-items:center; gap:8px;">
        <div class="search-input-wrap">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
          <input type="text" id="radarSearch" placeholder="Search hackathons, hosts, topics..." oninput="filterEvents()">
          <span class="kbd">/</span>
        </div>
        <div style="display:inline-flex; border:1px solid var(--border-color); border-radius:6px; overflow:hidden;">
          <button id="btnViewList" class="btn-shortlist-action active" onclick="setViewMode('list')" title="List View" style="border:none; border-radius:0;">☰</button>
          <button id="btnViewGrid" class="btn-shortlist-action" onclick="setViewMode('grid')" title="Card Grid View" style="border:none; border-radius:0;">▦</button>
        </div>
      </div>
    </div>

    <div id="hackathonList">
      {rows_html if rows_html else '<div style="padding:40px; text-align:center; color:var(--text-muted);">No hackathons matching this filter.</div>'}
    </div>

    <div id="cardsContainer" class="cards-grid" style="display:none; padding:18px;">
      {cards_html}
    </div>
  </div>
</main>

<div id="toastNotice" class="toast-notice" role="status"></div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# DEDICATED BLACKOUT CALENDAR MANAGEMENT PAGE
# ---------------------------------------------------------------------------
def _calendar_page(blackouts):
    total = len(blackouts)
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
              <input type="checkbox" {'checked' if enabled else ''} onchange="toggleBlackout({bid})">
              <span class="slider round"></span>
            </label>
          </td>
          <td style="text-align:right;">
            <button class="btn btn-sm btn-detail" onclick="openEditModal({bid}, '{title}', '{s_date}', '{e_date}', '{cat}', '{reason}')">Edit</button>
            <button class="btn btn-sm btn-reject" onclick="deleteBlackout({bid})">✕</button>
          </td>
        </tr>
        """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Blackout Calendar &amp; Availability Manager - Buildathon Radar</title>
<style>
{_SHARED_HEAD_CSS}

.calendar-hero {{
  background: var(--bg-card);
  border-radius: var(--radius-md);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-sm);
  padding: 24px 28px;
  margin-bottom: 24px;
  border-left: 5px solid var(--rose-primary);
}}
.calendar-hero h2 {{ margin:0 0 8px 0; font-size:22px; font-weight:800; }}
.calendar-hero p {{ margin:0 0 16px 0; font-size:14px; color:var(--text-muted); line-height:1.5; }}

.cal-stats {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(160px, 1fr)); gap:12px; margin-bottom:24px; }}
.cal-stat-card {{ background:var(--bg-card); border-radius:var(--radius-sm); border:1px solid var(--border); padding:14px; text-align:left; }}
.cal-stat-card .num {{ font-size:24px; font-weight:800; }}
.cal-stat-card .lbl {{ font-size:11px; text-transform:uppercase; color:var(--text-muted); font-weight:700; margin-top:4px; }}

.section-head {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:14px; }}
.section-title {{ font-size:17px; font-weight:800; margin:0; }}

/* Modal */
.modal-overlay {{
  position: fixed; top: 0; left: 0; width: 100%; height: 100%;
  background: rgba(0,0,0,0.5); backdrop-filter: blur(2px);
  display: none; justify-content: center; align-items: center; z-index: 1000;
}}
.modal-card {{
  background: var(--bg-card); border-radius: var(--radius-md);
  border: 1px solid var(--border); padding: 28px; max-width: 500px; width: 90%;
  box-shadow: var(--shadow-lg);
}}
.modal-card h3 {{ margin: 0 0 16px 0; font-size: 18px; }}
.form-group {{ margin-bottom: 14px; }}
.form-group label {{ display: block; font-size: 12px; font-weight: 700; margin-bottom: 5px; color: var(--text-muted); }}
.form-input {{
  width: 100%; padding: 8px 10px; border-radius: var(--radius-sm);
  border: 1px solid var(--border); background: var(--bg-subtle); color: var(--text-main);
  font-family: inherit; font-size: 13px;
}}
.form-input:focus {{ outline: 2px solid var(--teal-primary); background: var(--bg-card); }}
.modal-actions {{ display: flex; justify-content: flex-end; gap: 8px; margin-top: 20px; }}

/* Toggle Switch */
.switch {{ position: relative; display: inline-block; width: 34px; height: 18px; }}
.switch input {{ opacity: 0; width: 0; height: 0; }}
.slider {{ position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: var(--border-subtle); transition: .2s; border-radius: 18px; }}
.slider:before {{ position: absolute; content: ""; height: 12px; width: 12px; left: 3px; bottom: 3px; background-color: white; transition: .2s; border-radius: 50%; }}
input:checked + .slider {{ background-color: var(--emerald-primary); }}
input:checked + .slider:before {{ transform: translateX(16px); }}
.row-disabled {{ opacity: 0.5; }}
</style>
<script>
function toggleTheme() {{
  const cur = document.documentElement.getAttribute('data-theme') || 'dark';
  const nxt = cur === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', nxt);
  localStorage.setItem('radar_theme', nxt);
  updateThemeBtn();
}}
function updateThemeBtn() {{
  const theme = document.documentElement.getAttribute('data-theme') || 'dark';
  const btn = document.getElementById('themeToggleBtn');
  if (btn) btn.innerHTML = theme === 'dark' ? '☀️ Light' : '🌙 Dark';
}}
const savedTheme = localStorage.getItem('radar_theme') || 'dark';
document.documentElement.setAttribute('data-theme', savedTheme);
window.addEventListener('DOMContentLoaded', updateThemeBtn);

function openAddModal() {{
  document.getElementById('modalTitle').textContent = 'Add Blackout Date / Period';
  document.getElementById('blackoutId').value = '';
  document.getElementById('inputTitle').value = '';
  document.getElementById('inputStart').value = '';
  document.getElementById('inputEnd').value = '';
  document.getElementById('inputCategory').value = 'Personal';
  document.getElementById('inputReason').value = '';
  document.getElementById('blackoutModal').style.display = 'flex';
}}

function openEditModal(id, title, start, end, cat, reason) {{
  document.getElementById('modalTitle').textContent = 'Edit Blackout Entry';
  document.getElementById('blackoutId').value = id;
  document.getElementById('inputTitle').value = title;
  document.getElementById('inputStart').value = start;
  document.getElementById('inputEnd').value = end;
  document.getElementById('inputCategory').value = cat;
  document.getElementById('inputReason').value = reason;
  document.getElementById('blackoutModal').style.display = 'flex';
}}

function closeModal() {{
  document.getElementById('blackoutModal').style.display = 'none';
}}

async function saveBlackout(event) {{
  event.preventDefault();
  const id = document.getElementById('blackoutId').value;
  const payload = {{
    title: document.getElementById('inputTitle').value,
    start_date: document.getElementById('inputStart').value,
    end_date: document.getElementById('inputEnd').value || document.getElementById('inputStart').value,
    category: document.getElementById('inputCategory').value,
    reason: document.getElementById('inputReason').value,
    enabled: true
  }};

  const url = id ? `/api/blackouts/${{id}}` : '/api/blackouts';
  const method = id ? 'PUT' : 'POST';

  try {{
    const resp = await fetch(url, {{
      method: method,
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify(payload)
    }});
    if (resp.ok) {{
      closeModal();
      window.location.reload();
    }} else {{
      alert('Error saving blackout date');
    }}
  }} catch (e) {{
    alert('Network error');
  }}
}}

async function toggleBlackout(id) {{
  try {{
    const resp = await fetch(`/api/blackouts/${{id}}/toggle`, {{ method: 'POST' }});
    if (resp.ok) {{
      window.location.reload();
    }}
  }} catch(e) {{
    alert('Error toggling blackout entry');
  }}
}}

async function deleteBlackout(id) {{
  if (!confirm('Are you sure you want to remove this blackout entry? Event conflicts will be recomputed.')) return;
  try {{
    const resp = await fetch(`/api/blackouts/${{id}}`, {{ method: 'DELETE' }});
    if (resp.ok) {{
      window.location.reload();
    }}
  }} catch(e) {{
    alert('Error deleting blackout entry');
  }}
}}
</script>
</head>
<body>
<header class="app-header" role="banner">
  <div class="brand-group">
    <div>
      <div style="display:flex; align-items:center; gap:8px;">
        <a href="/dashboard" class="brand-title">🛰️ Buildathon Radar</a>
        <span class="brand-badge">Blackout System</span>
      </div>
      <div class="brand-sub">Personal Calendar Availability &amp; Examination Hard Exclusions</div>
    </div>
  </div>
  <nav class="nav-toolbar" aria-label="Navigation">
    <a href="/dashboard" class="nav-btn">⚡ Dashboard</a>
    <a href="/dashboard?filter=excluded" class="nav-btn">⛔ Excluded Events</a>
    <a href="/calendar" class="nav-btn active">📅 Blackout Calendar</a>
    <a href="/sources" class="nav-btn">🌐 Sources</a>
    <a href="/list" class="nav-btn">📋 List View</a>
    <button id="themeToggleBtn" class="theme-toggle-btn" onclick="toggleTheme()">🌙 Dark</button>
  </nav>
</header>

<main class="container">
  <section class="calendar-hero">
    <h2>📅 Personal Blackout Calendar Management</h2>
    <p>
      These dates represent your hard commitments. Any hackathon or buildathon whose dates overlap even a single day of an active blackout entry is <strong>strictly excluded</strong> from your primary recommendations.
      Eligibility is automatically recomputed across all stored events whenever you add, edit, toggle, or remove blackout dates.
    </p>
    <button class="btn btn-primary-link" onclick="openAddModal()">+ Add New Blackout Date / Period</button>
  </section>

  <div class="cal-stats">
    <div class="cal-stat-card"><div class="num">{total}</div><div class="lbl">Total Rules</div></div>
    <div class="cal-stat-card"><div class="num" style="color:var(--emerald-primary);">{enabled_count}</div><div class="lbl">Active Rules</div></div>
    <div class="cal-stat-card"><div class="num" style="color:var(--purple-primary);">{personal_count}</div><div class="lbl">Personal Commitments</div></div>
    <div class="cal-stat-card"><div class="num" style="color:var(--amber-primary);">{academic_count}</div><div class="lbl">ALLEN JEE Tests</div></div>
    <div class="cal-stat-card"><div class="num" style="color:var(--rose-primary);">{exam_count}</div><div class="lbl">Exam Periods</div></div>
  </div>

  <div class="section-head">
    <h3 class="section-title">Configured Blackout Dates &amp; Ranges</h3>
  </div>

  <div class="table-wrap">
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

<div id="blackoutModal" class="modal-overlay" onclick="if(event.target === this) closeModal()">
  <div class="modal-card">
    <h3 id="modalTitle">Add Blackout Date / Period</h3>
    <form onsubmit="saveBlackout(event)">
      <input type="hidden" id="blackoutId">
      <div class="form-group">
        <label for="inputTitle">Title / Name *</label>
        <input type="text" id="inputTitle" class="form-input" required placeholder="e.g. Major Internal Test 2">
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
        <input type="text" id="inputReason" class="form-input" placeholder="e.g. ALLEN JEE Test Day">
      </div>
      <div class="modal-actions">
        <button type="button" class="btn btn-detail" onclick="closeModal()">Cancel</button>
        <button type="submit" class="btn btn-primary-link">Save Blackout Date</button>
      </div>
    </form>
  </div>
</div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# DEDICATED MULTI-PLATFORM DISCOVERY SOURCES MANAGEMENT PAGE
# ---------------------------------------------------------------------------
def _sources_page(sources, last_scan, recent_scans):
    total = len(sources)
    active_count = sum(1 for s in sources if s["enabled"])
    total_events_discovered = sum(s.get("events_discovered", 0) for s in sources)
    
    last_scan_info = "Never scanned"
    if last_scan:
        dur = last_scan.get("duration_seconds", 0.0)
        ts = _format_date(last_scan.get("timestamp", ""))
        succ = last_scan.get("successful_sources", 0)
        tot = last_scan.get("total_sources", 0)
        new_ev = last_scan.get("new_events", 0)
        last_scan_info = f"{ts} &middot; {dur}s ({succ}/{tot} healthy, +{new_ev} new)"

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
            method = _esc(s["discovery_method"])
            conf = s["confidence_level"]
            enabled = bool(s["enabled"])
            ev_count = s.get("events_discovered", 0)
            succ = s.get("success_count", 0)
            fail = s.get("fail_count", 0)
            l_scan = _format_date(s.get("last_scan")) if s.get("last_scan") else "Never"
            l_err = _esc(s.get("last_error") or "")

            if conf == "High":
                conf_badge = '<span class="pill" style="background:rgba(16,185,129,0.12); color:#059669; font-weight:700;">🛡️ High</span>'
            elif conf == "Medium-High":
                conf_badge = '<span class="pill" style="background:rgba(20,184,166,0.12); color:#0d9488; font-weight:700;">🛡️ Med-High</span>'
            elif conf == "Medium":
                conf_badge = '<span class="pill" style="background:rgba(59,130,246,0.12); color:#2563eb; font-weight:700;">🛡️ Medium</span>'
            else:
                conf_badge = '<span class="pill" style="background:rgba(245,158,11,0.12); color:#d97706; font-weight:700;">🛡️ Low</span>'

            err_html = f'<div style="font-size:11px; color:var(--rose-primary); margin-top:3px;" title="{l_err}">⚠️ {l_err[:60]}...</div>' if l_err else ""

            rows += f"""
            <tr id="source-row-{s_key}" class="{'row-disabled' if not enabled else ''}">
              <td width="50" style="text-align:center;">
                <label class="switch" title="Enable or disable discovery from this source">
                  <input type="checkbox" {'checked' if enabled else ''} onchange="toggleSource('{s_key}')">
                  <span class="slider round"></span>
                </label>
              </td>
              <td>
                <div style="font-weight:700; color:var(--text-main); font-size:14px;">{name}</div>
                <div style="display:flex; align-items:center; gap:6px; margin-top:2px;">
                  <code style="font-size:11px; background:var(--bg-subtle); padding:1px 5px; border-radius:4px; border:1px solid var(--border);">{s_key}</code>
                  <span style="font-size:12px; color:var(--text-muted);">&middot; {method}</span>
                </div>
                {err_html}
              </td>
              <td width="120">{conf_badge}</td>
              <td width="100" style="text-align:center; font-weight:700; font-size:14px;">{ev_count}</td>
              <td width="100" style="text-align:center; font-size:12px;">
                <span style="color:var(--emerald-primary); font-weight:700;">✓ {succ}</span> / 
                <span style="color:var(--rose-primary); font-weight:700;">✗ {fail}</span>
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
          <div class="table-wrap">
            <table role="table">
              <thead>
                <tr>
                  <th scope="col" style="text-align:center;">Active</th>
                  <th scope="col">Source Name &amp; Discovery Method</th>
                  <th scope="col">Confidence</th>
                  <th scope="col" style="text-align:center;">Discovered</th>
                  <th scope="col" style="text-align:center;">Health (✓/✗)</th>
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
    for sc in (recent_scans or []):
        sid = sc.get("id")
        ts = _format_date(sc.get("timestamp"))
        dur = sc.get("duration_seconds", 0.0)
        tot_s = sc.get("total_sources", 0)
        succ_s = sc.get("successful_sources", 0)
        fail_s = sc.get("failed_sources", 0)
        new_e = sc.get("new_events", 0)
        upd_e = sc.get("updated_events", 0)

        health_pill = f'<span class="pill pill-mode mode-in-person">✓ {succ_s}/{tot_s}</span>' if fail_s == 0 else f'<span class="pill pill-mode mode-online">⚠️ {succ_s}/{tot_s} ({fail_s} err)</span>'

        scans_html += f"""
        <tr>
          <td><code>#{sid}</code></td>
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
function toggleTheme() {{
  const cur = document.documentElement.getAttribute('data-theme') || 'dark';
  const nxt = cur === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', nxt);
  localStorage.setItem('radar_theme', nxt);
  updateThemeBtn();
}}
function updateThemeBtn() {{
  const theme = document.documentElement.getAttribute('data-theme') || 'dark';
  const btn = document.getElementById('themeToggleBtn');
  if (btn) btn.innerHTML = theme === 'dark' ? '☀️ Light' : '🌙 Dark';
}}
const savedTheme = localStorage.getItem('radar_theme') || 'dark';
document.documentElement.setAttribute('data-theme', savedTheme);
window.addEventListener('DOMContentLoaded', updateThemeBtn);

async function toggleSource(key) {{
  try {{
    const resp = await fetch(`/api/sources/${{key}}/toggle`, {{ method: 'POST' }});
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
    btn.textContent = '⏳ Scanning 27 sources...';
  }}
  try {{
    const resp = await fetch('/api/scan', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{}})
    }});
    const data = await resp.json();
    if (data.status === 'ok') {{
      alert(`Scan complete in ${{data.duration_seconds}}s across ${{data.total_sources}} sources!\\n\\nNew events: ${{data.new_events}}\\nUpdated events: ${{data.updated_events}}\\nHealthy sources: ${{data.successful_sources}}/${{data.total_sources}}`);
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
</script>
</head>
<body>
<header class="app-header" role="banner">
  <div class="brand-group">
    <div>
      <div style="display:flex; align-items:center; gap:8px;">
        <a href="/dashboard" class="brand-title">🛰️ Buildathon Radar</a>
        <span class="brand-badge">Multi-Platform Discovery</span>
      </div>
      <div class="brand-sub">Multi-Source Internet Discovery Engine &middot; Dedicated Platforms, Social, Communities &amp; Fests</div>
    </div>
  </div>
  <nav class="nav-toolbar" aria-label="Navigation">
    <a href="/dashboard" class="nav-btn">⚡ Dashboard</a>
    <a href="/dashboard?filter=excluded" class="nav-btn">⛔ Excluded Events</a>
    <a href="/calendar" class="nav-btn">📅 Blackout Calendar</a>
    <a href="/sources" class="nav-btn active">🌐 Sources</a>
    <a href="/list" class="nav-btn">📋 List View</a>
    <button id="themeToggleBtn" class="theme-toggle-btn" onclick="toggleTheme()">🌙 Dark</button>
  </nav>
</header>

<main class="container">
  <section class="sources-hero">
    <h2>🌐 Multi-Platform Hackathon Discovery Engine</h2>
    <p>
      Buildathon Radar continuously discovers student opportunities across <strong>27 integrated platforms and sources</strong>: dedicated hackathon platforms, legitimate LinkedIn &amp; social feeds, ticketing directories, developer communities, Indian college tech fests, corporate challenges, and targeted web search engine queries.
    </p>
    <div style="display:flex; align-items:center; gap:12px; flex-wrap:wrap;">
      <button id="btnRunScan" class="btn btn-primary-link" onclick="triggerDiscoveryScan()" style="font-size:13px; font-weight:700;">⚡ Scan All Sources Now</button>
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
    <div class="source-stat-card">
      <div class="num" style="color:var(--teal-primary);">{total_events_discovered}</div>
      <div class="lbl">Opportunities Discovered</div>
    </div>
    <div class="source-stat-card">
      <div class="num" style="font-size:18px; margin-top:4px;">100%</div>
      <div class="lbl">Fault Isolated</div>
    </div>
  </div>

  <div class="section-head" style="margin-bottom:16px;">
    <h2 class="section-title">Platform Discovery Sources by Category</h2>
  </div>

  {categories_html}

  <div class="category-block" style="margin-top:36px;">
    <div class="cat-head">
      <div>
        <h3 style="margin:0 0 4px 0; font-size:16px; font-weight:800;">📜 Recent Discovery Scan Logs</h3>
        <div style="font-size:12px; color:var(--text-muted);">Historical execution runtimes, source response health, and event delta counts.</div>
      </div>
    </div>
    <div class="table-wrap">
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
</main>
</body>
</html>"""


def _event_detail_page(row):
    title = _esc(row["title"])
    eid = _esc(row["event_id"])
    url = _esc(row["url"])
    host = _esc(row["host"] or "Community")
    source = _esc(row["source"] or "Unknown")
    summary = _esc(row["summary"] or "No detailed description available.")
    loc = _esc(row["location"] or "Unknown")
    mode = _esc(row["mode"] or "unknown")
    start = _esc(_format_date(row["event_start"]) or "TBD")
    end = _esc(_format_date(row["event_end"]) or "TBD")
    deadline = _esc(_format_date(row["registration_deadline"]) or "Open")
    prize = _esc(row["prize"] or "None listed")
    team = _esc(row["team_size"] or "3-5 preferred")
    eligibility = _esc(row["eligibility"] or "UNKNOWN")
    age = _esc(row["age_restrictions"] or "None specified")
    priority = _esc(row["priority"] or "MEDIUM PRIORITY")
    score = _esc(row["score"])
    why = _esc(row["why"] or "")
    state = _esc(row["state"])
    is_conflict = bool(row["blackout_conflict"] if "blackout_conflict" in row.keys() else ("CONFLICT" in priority))

    track_token = tracker_store.sign_action("track", row["event_id"])
    applied_token = tracker_store.sign_action("applied", row["event_id"])
    reject_token = tracker_store.sign_action("reject", row["event_id"])

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} - Buildathon Radar</title>
<style>
{_SHARED_HEAD_CSS}
.detail-card {{
  background: var(--bg-card);
  border-radius: var(--radius-md);
  padding: 32px;
  border: 1px solid var(--border);
  box-shadow: var(--shadow-sm);
  max-width: 860px;
  margin: 30px auto;
}}
.detail-grid {{
  display: grid;
  grid-template-columns: 1fr 1fr;
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
.detail-actions {{
  display: flex; gap: 10px; align-items: center; padding-top: 20px;
  border-top: 1px solid var(--border); margin-top: 24px;
}}
</style>
<script>
const savedTheme = localStorage.getItem('radar_theme') || 'dark';
document.documentElement.setAttribute('data-theme', savedTheme);
</script>
</head>
<body>
<header class="app-header">
  <a href="/dashboard" class="brand-title">&larr; Back to Dashboard</a>
</header>
<main class="container">
  <div class="detail-card">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
      <span class="badge {'badge-conflict' if is_conflict else 'badge-high'}">{priority}</span>
      <span style="font-weight:700;">Score: {score}/100 &middot; State: {state.upper()}</span>
    </div>
    <h1 style="margin:0 0 8px 0; font-size:24px;">{title}</h1>
    <div style="color:var(--text-muted); font-size:13px; margin-bottom:18px;">Organised by <strong>{host}</strong> &middot; Source: {source}</div>

    {'<div class="card-conflict-alert" style="margin-bottom:20px;"><strong>⛔ Blackout Conflict:</strong> ' + why + '</div>' if is_conflict else '<div class="card-why" style="margin-bottom:20px;"><strong>Why recommended:</strong> ' + why + '</div>'}

    <div class="detail-grid">
      <div class="info-box"><div class="info-label">Location &amp; Format</div><div class="info-val">{loc} ({mode.title()})</div></div>
      <div class="info-box"><div class="info-label">Event Schedule</div><div class="info-val">{start} &rarr; {end}</div></div>
      <div class="info-box"><div class="info-label">Student Eligibility</div><div class="info-val">{eligibility}</div></div>
      <div class="info-box"><div class="info-label">Registration Deadline</div><div class="info-val">{deadline}</div></div>
      <div class="info-box"><div class="info-label">Team Requirements</div><div class="info-val">{team}</div></div>
      <div class="info-box"><div class="info-label">Prize Pool</div><div class="info-val">{prize}</div></div>
    </div>

    <div>
      <h3 style="font-size:15px; margin:0 0 8px 0;">Summary</h3>
      <p style="font-size:14px; line-height:1.6; color:var(--text-muted); margin:0;">{summary}</p>
    </div>

    <div class="detail-actions">
      <a class="btn btn-track" href="/track?event_id={eid}&t={track_token}">📌 Shortlist / Track</a>
      <a class="btn btn-applied" href="/applied?event_id={eid}&t={applied_token}">🎯 Mark Applied</a>
      <a class="btn btn-reject" href="/reject?event_id={eid}&t={reject_token}">✕ Dismiss</a>
      <a class="btn btn-primary-link" href="{url}" target="_blank" rel="noopener" style="margin-left:auto;">Visit Official Page &rarr;</a>
    </div>
  </div>
</main>
</body>
</html>"""


def _handle_action(action, event_id, token):
    if not event_id:
        return HTMLResponse(_malformed_page(), status_code=400)

    if not tracker_store.verify_action(action, event_id, token):
        conn = _get_conn()
        try:
            tracker_store.log_action(conn, event_id, action, "bad_token")
        finally:
            conn.close()
        return HTMLResponse(_invalid_token_page(), status_code=403)

    conn = _get_conn()
    try:
        result, row = tracker_store.apply_action(conn, action, event_id)
    finally:
        conn.close()

    if result == "unknown_event":
        return HTMLResponse(_unknown_event_page(), status_code=404)
    if result == "noop":
        return HTMLResponse(_noop_page(action, row), status_code=200)
    return HTMLResponse(_ok_page(action, row), status_code=200)


# ---------------------------------------------------------------------------
# API & PAGE ROUTES
# ---------------------------------------------------------------------------
@app.get("/")
def health():
    return HTMLResponse(_health_page(), status_code=200)


@app.get("/dashboard")
def dashboard(filter: Optional[str] = None):
    conn = _get_conn()
    try:
        if filter == "bengaluru":
            events = tracker_store.get_events_by_filter(
                conn, location_keyword="bengaluru", blackout_conflict=0
            )
            # Fallback if no specific bengaluru keyword in location alone
            if not events:
                all_ev = tracker_store.get_all_events(conn, include_conflicts=False)
                events = [
                    e for e in all_ev
                    if str(e["mode"]).lower() in ("in-person", "hybrid", "offline")
                    and any(
                        p in str(e["location"]).lower()
                        or p in str(e["summary"]).lower()
                        or p in str(e["title"]).lower()
                        for p in ["bengaluru", "bangalore", "koramangala", "indiranagar", "whitefield", "hsr"]
                    )
                ]
        elif filter == "eligible":
            events = tracker_store.get_events_by_filter(
                conn, eligibility="ELIGIBLE", blackout_conflict=0, date_status="verified"
            )
        elif filter == "free_weekend":
            events = [
                e for e in tracker_store.get_all_events(conn, include_conflicts=False)
                if "Free & Weekend" in str(e["why"] or "")
            ]
        elif filter == "high":
            events = tracker_store.get_events_by_filter(
                conn, priority="HIGH PRIORITY", blackout_conflict=0
            )
        elif filter == "unverified":
            events = [
                e for e in tracker_store.get_all_events(conn, include_conflicts=True)
                if e["date_status"] == "uncertain" or str(e["eligibility"]).upper() == "UNKNOWN"
            ]
        elif filter == "tracked":
            events = tracker_store.get_events_by_filter(conn, state="tracked")
        elif filter == "applied":
            events = tracker_store.get_events_by_filter(conn, state="applied")
        elif filter == "excluded":
            events = tracker_store.get_events_by_filter(conn, blackout_conflict=1)
        elif filter == "closing_soon":
            events = tracker_store.get_upcoming_deadlines(conn, limit=50, exclude_conflicts=True)
        else:
            # Default discovery view: eligible/available events (excludes blackout conflicts)
            events = tracker_store.get_all_events(conn, include_conflicts=False)
    finally:
        conn.close()
    return HTMLResponse(_dashboard_page(events, current_filter=filter), status_code=200)


@app.get("/calendar")
def calendar_view():
    conn = _get_conn()
    try:
        blackouts = tracker_store.get_blackout_dates(conn)
    finally:
        conn.close()
    return HTMLResponse(_calendar_page(blackouts), status_code=200)


@app.get("/sources")
def sources_view():
    conn = _get_conn()
    try:
        sources = tracker_store.get_discovery_sources(conn)
        last_scan = tracker_store.get_last_discovery_scan(conn)
        recent_scans = tracker_store.get_recent_discovery_scans(conn, limit=10)
    finally:
        conn.close()
    return HTMLResponse(_sources_page(sources, last_scan, recent_scans), status_code=200)


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
def event_detail(event_id: str):
    conn = _get_conn()
    try:
        row = conn.execute("SELECT * FROM events WHERE event_id = ?", (event_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        return HTMLResponse(_unknown_event_page(), status_code=404)
    return HTMLResponse(_event_detail_page(row), status_code=200)


# ---------------------------------------------------------------------------
# REST JSON APIS
# ---------------------------------------------------------------------------
@app.get("/api/events")
def api_events(
    priority: Optional[str] = None,
    state: Optional[str] = None,
    eligibility: Optional[str] = None,
    search: Optional[str] = None,
    mode: Optional[str] = None,
    blackout_conflict: Optional[int] = None,
    date_status: Optional[str] = None,
    location: Optional[str] = None,
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
        return [dict(r) for r in rows]
    finally:
        conn.close()


@app.get("/api/deadlines")
def api_deadlines(limit: int = 15):
    conn = _get_conn()
    try:
        rows = tracker_store.get_upcoming_deadlines(conn, limit=limit, exclude_conflicts=True)
        return [dict(r) for r in rows]
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
            start_date=data.start_date,
            end_date=data.end_date,
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
            start_date=data.start_date,
            end_date=data.end_date,
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

    if req.token and not tracker_store.verify_action(req.action, req.event_id, req.token):
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
        return sources
    finally:
        conn.close()


@app.post("/api/sources/{source_key}/toggle")
def api_toggle_source(source_key: str):
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
    try:
        engine = DiscoveryEngine(db_path=DB_PATH)
        source_keys = req.sources if req else None
        force_all = req.force_all if req else False
        result = engine.run_scan(source_keys=source_keys, force_all=force_all)
        return {"status": "ok", **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/scans")
def api_get_scans(limit: int = 10):
    conn = _get_conn()
    try:
        scans = tracker_store.get_recent_discovery_scans(conn, limit=limit)
        return scans
    finally:
        conn.close()
