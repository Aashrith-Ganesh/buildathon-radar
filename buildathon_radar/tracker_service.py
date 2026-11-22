import html as html_lib
import os
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse

from buildathon_radar import tracker_store

load_dotenv()

# Secure fallback for TRACKER_SECRET so local development does not crash
if not os.getenv("TRACKER_SECRET"):
    tracker_store.get_secret()

DB_PATH = tracker_store.DB_FILE
TRACKER_BASE_URL = os.getenv("TRACKER_BASE_URL", "http://127.0.0.1:8015").rstrip("/")

FONT_STACK = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
TEAL_DARK = "#0f4c4c"
PAGE_BG = "#f6f4ef"
CARD_BG = "#ffffff"
ACCENT = "#0d9488"

STATE_ORDER = ["tracked", "applied", "seen", "rejected", "over"]
STATE_LABELS = {
    "tracked": "Tracked",
    "applied": "Applied",
    "seen": "Seen",
    "rejected": "Rejected",
    "over": "Over",
}

app = FastAPI(title="Buildathon Radar Tracker")


def _get_conn():
    return tracker_store.connect(DB_PATH)


def _esc(value):
    return html_lib.escape(str(value or ""))


def _format_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%b %d, %Y")
    except ValueError:
        return value


def _format_ts_date(iso_ts):
    if not iso_ts:
        return "an earlier visit"
    try:
        return datetime.fromisoformat(iso_ts).strftime("%b %d, %Y")
    except ValueError:
        return "an earlier visit"


def _page(headline, lines, event_url=None, accent=ACCENT):
    body_lines = "".join(f'<p style="margin:0 0 10px 0;">{line}</p>' for line in lines)
    link_html = ""
    if event_url:
        link_html = (
            f'<p style="margin:18px 0 0 0;">'
            f'<a href="{_esc(event_url)}" style="color:{accent}; font-weight:bold; '
            f'text-decoration:none;">Open event page &rarr;</a></p>'
        )
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Buildathon Radar</title>
</head>
<body style="margin:0; padding:0; background-color:{PAGE_BG}; font-family:{FONT_STACK};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:{PAGE_BG};">
<tr>
<td align="center" style="background-color:{PAGE_BG}; padding:40px 16px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="width:100%; max-width:480px; background-color:{CARD_BG}; border-radius:6px; overflow:hidden; box-shadow:0 2px 8px rgba(0,0,0,0.06);">
<tr>
<td style="background-color:{accent}; padding:20px 24px;">
<div style="font-family:{FONT_STACK}; font-size:13px; font-weight:bold; color:#ffffff; letter-spacing:0.5px;">BUILDATHON RADAR</div>
</td>
</tr>
<tr>
<td style="background-color:{CARD_BG}; padding:24px; font-family:{FONT_STACK}; color:#2e4243;">
<div style="font-size:20px; font-weight:bold; color:{TEAL_DARK}; margin-bottom:12px; word-break:break-word; overflow-wrap:break-word;">{_esc(headline)}</div>
<div style="font-size:14px; line-height:1.5; word-break:break-word; overflow-wrap:break-word;">{body_lines}</div>
{link_html}
<div style="margin-top:24px; border-top:1px solid #e2ece9; padding-top:12px;">
<a href="/dashboard" style="color:{ACCENT}; font-size:13px; text-decoration:none;">&larr; Return to Dashboard</a>
</div>
</td>
</tr>
</table>
</td>
</tr>
</table>
</body>
</html>"""


def _health_page():
    return _page("Buildathon Radar tracker is running.", [
        "This is a liveness check only. No event data is exposed here.",
        "<br>Access the interactive local dashboard at: <a href='/dashboard' style='color:#0d9488; font-weight:bold;'>Local Dashboard</a> | <a href='/list' style='color:#0d9488;'>Read-only List</a>"
    ])


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


def _dashboard_page(events, current_filter=None):
    def _val(row, k, default=""):
        try:
            v = row[k]
            return default if v is None else v
        except Exception:
            return default

    total = len(events)
    high_count = sum(1 for e in events if "HIGH" in str(_val(e, "priority")))
    free_weekend_count = sum(1 for e in events if "Free & Weekend" in str(_val(e, "why")))
    tracked_count = sum(1 for e in events if _val(e, "state") == "tracked")
    applied_count = sum(1 for e in events if _val(e, "state") == "applied")
    eligible_count = sum(1 for e in events if _val(e, "eligibility") == "ELIGIBLE")
    unverified_count = sum(1 for e in events if _val(e, "eligibility") == "UNKNOWN")

    cards_html = f"""
    <div class="metrics">
      <div class="metric-card"><div class="num">{total}</div><div class="lbl">Active Opportunities</div></div>
      <div class="metric-card highlight-indigo"><div class="num">{free_weekend_count}</div><div class="lbl">Free & Weekend</div></div>
      <div class="metric-card highlight-teal"><div class="num">{high_count}</div><div class="lbl">High Priority</div></div>
      <div class="metric-card"><div class="num">{unverified_count}</div><div class="lbl">Needs Verification</div></div>
      <div class="metric-card highlight-emerald"><div class="num">{tracked_count}</div><div class="lbl">Shortlisted</div></div>
      <div class="metric-card highlight-blue"><div class="num">{applied_count}</div><div class="lbl">Applied</div></div>
    </div>
    """

    rows_html = ""
    for e in events:
        eid = _esc(e["event_id"])
        title = _esc(e["title"])
        host = _esc(e["host"] or "Community")
        loc = _esc(e["location"] or "Online")
        mode = _esc(e["mode"] or "unknown")
        start = _esc(_format_date(e["event_start"]) or "TBD")
        deadline = _esc(_format_date(e["registration_deadline"]) or "Open")
        score = int(e["score"]) if e["score"] is not None else 0
        priority = _esc(e["priority"])
        eligibility = _esc(e["eligibility"])
        why = _esc(e["why"] or "")
        state = _esc(e["state"])
        url = _esc(e["url"])

        # Cost & Timing Badge
        sched_badge = ""
        if "Free & Weekend" in why:
            sched_badge = '<span class="sched-pill sched-fw">Free & Weekend</span>'
        elif "Paid & Weekend" in why:
            sched_badge = '<span class="sched-pill sched-pw">Paid & Weekend</span>'
        elif "Free & Weekday" in why:
            sched_badge = '<span class="sched-pill sched-fwd">Free & Weekday</span>'
        elif "Paid & Weekday" in why:
            sched_badge = '<span class="sched-pill sched-pwd">Paid & Weekday</span>'
        elif "Unavailable" in why or "Blackout" in why:
            sched_badge = '<span class="sched-pill sched-conflict">Blackout Conflict</span>'

        # Priority styling
        if "CONFLICT" in priority or "UNAVAILABLE" in priority:
            p_class = "p-conflict"
        elif "HIGH" in priority:
            p_class = "p-high"
        elif "MEDIUM" in priority:
            p_class = "p-med"
        else:
            p_class = "p-low"

        # Score styling
        if score >= 90:
            score_class = "score-top"
        elif score >= 70:
            score_class = "score-high"
        elif score >= 50:
            score_class = "score-mid"
        else:
            score_class = "score-low"

        s_class = "s-tracked" if state == "tracked" else ("s-applied" if state == "applied" else "s-seen")

        track_token = tracker_store.sign_action("track", e["event_id"])
        applied_token = tracker_store.sign_action("applied", e["event_id"])
        reject_token = tracker_store.sign_action("reject", e["event_id"])

        mode_badge = f'<span class="mode-pill mode-{mode}">{mode.title()}</span>'

        rows_html += f"""
        <tr class="event-item {s_class}">
          <td>
            <div class="priority-wrap">
              <span class="badge {p_class}">{priority}</span>
              {sched_badge}
            </div>
          </td>
          <td>
            <div class="score-circle {score_class}">{score}</div>
          </td>
          <td>
            <div class="title-row">
              <a class="item-title" href="{url}" target="_blank" rel="noopener">{title}</a>
              {mode_badge}
            </div>
            <div class="item-meta">
              <span class="meta-host">🏢 {host}</span> &middot; 
              <span class="meta-loc">📍 {loc}</span> &middot; 
              <span class="meta-date">📅 Starts: {start}</span>
            </div>
            {f'<div class="item-why">{why}</div>' if why else ''}
          </td>
          <td>
            <span class="elig-pill elig-{eligibility.lower()}">
              {'✓ Class 11/12' if eligibility == 'ELIGIBLE' else ('? Verify' if eligibility == 'UNKNOWN' else '✕ Ineligible')}
            </span>
          </td>
          <td>
            <div class="deadline-wrap">
              <span class="deadline-val">{deadline}</span>
            </div>
          </td>
          <td>
            <span class="state-pill state-{state}">{state.title()}</span>
          </td>
          <td class="action-cell">
            <div class="btn-group">
              <a class="btn btn-track" href="/track?event_id={eid}&t={track_token}" title="Shortlist event">📌 Track</a>
              <a class="btn btn-applied" href="/applied?event_id={eid}&t={applied_token}" title="Mark applied">🎯 Applied</a>
              <a class="btn btn-reject" href="/reject?event_id={eid}&t={reject_token}" title="Dismiss event">✕ Reject</a>
              <a class="btn btn-detail" href="/event/{eid}" title="Full details">Details</a>
            </div>
          </td>
        </tr>
        """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Buildathon Radar - Student Opportunity Dashboard</title>
<style>
:root {{
  --bg-canvas: #f8fafc;
  --bg-card: #ffffff;
  --text-main: #0f172a;
  --text-muted: #64748b;
  --border-subtle: #e2e8f0;
  --border-light: #f1f5f9;
  --teal-dark: #082f35;
  --teal-primary: #0d9488;
  --teal-light: #f0fdfa;
  --font-stack: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}}
* {{ box-sizing: border-box; }}
body {{ margin:0; padding:0; background:var(--bg-canvas); font-family:var(--font-stack); color:var(--text-main); -webkit-font-smoothing:antialiased; }}
header {{ background:var(--teal-dark); color:#fff; padding:18px 32px; display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #115e59; }}
.brand {{ display:flex; align-items:center; gap:12px; }}
.brand-title {{ font-size:19px; font-weight:700; letter-spacing:-0.3px; margin:0; }}
.brand-badge {{ font-size:11px; background:#115e59; color:#a7f3d0; padding:3px 8px; border-radius:12px; font-weight:600; display:inline-flex; align-items:center; gap:5px; }}
.brand-badge::before {{ content:""; width:6px; height:6px; background:#10b981; border-radius:50%; display:inline-block; }}
.tagline {{ font-size:12px; color:#99f6e4; margin-top:3px; }}
.header-links a {{ color:#ccfbf1; text-decoration:none; font-size:13px; font-weight:500; margin-left:18px; transition:color 0.15s; }}
.header-links a:hover {{ color:#fff; }}
.container {{ max-width:1280px; margin:24px auto; padding:0 20px; }}

/* Metrics Grid */
.metrics {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(160px, 1fr)); gap:12px; margin-bottom:20px; }}
.metric-card {{ background:var(--bg-card); border-radius:8px; padding:16px 18px; text-align:left; border:1px solid var(--border-subtle); box-shadow:0 1px 2px rgba(0,0,0,0.03); }}
.metric-card .num {{ font-size:28px; font-weight:800; color:var(--text-main); line-height:1.1; letter-spacing:-0.5px; }}
.metric-card .lbl {{ font-size:11px; text-transform:uppercase; color:var(--text-muted); margin-top:6px; letter-spacing:0.5px; font-weight:600; }}
.highlight-indigo {{ border-left:4px solid #6366f1; }}
.highlight-indigo .num {{ color:#4338ca; }}
.highlight-teal {{ border-left:4px solid var(--teal-primary); }}
.highlight-teal .num {{ color:#0f766e; }}
.highlight-emerald {{ border-left:4px solid #10b981; }}
.highlight-blue {{ border-left:4px solid #3b82f6; }}

/* Controls Bar */
.controls {{ background:var(--bg-card); border-radius:8px; padding:12px 18px; margin-bottom:16px; border:1px solid var(--border-subtle); display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px; }}
.tabs {{ display:flex; flex-wrap:wrap; gap:6px; }}
.tabs a {{ display:inline-flex; align-items:center; gap:6px; padding:6px 12px; border-radius:6px; font-size:13px; font-weight:600; text-decoration:none; color:var(--text-muted); background:var(--border-light); transition:all 0.15s; }}
.tabs a:hover {{ background:#e2e8f0; color:var(--text-main); }}
.tabs a.active {{ background:var(--teal-primary); color:#ffffff; }}

/* Live Search Input */
.search-box {{ display:inline-flex; align-items:center; background:var(--border-light); border:1px solid var(--border-subtle); border-radius:6px; padding:6px 12px; min-width:280px; gap:8px; }}
.search-box input {{ border:none; background:transparent; font-size:13px; outline:none; width:100%; font-family:inherit; color:var(--text-main); }}
.search-count {{ font-size:11px; font-weight:600; color:var(--teal-primary); white-space:nowrap; }}

/* Table */
.table-wrap {{ background:var(--bg-card); border-radius:8px; border:1px solid var(--border-subtle); overflow-x:auto; box-shadow:0 1px 3px rgba(0,0,0,0.03); }}
table {{ width:100%; border-collapse:collapse; text-align:left; }}
th {{ background:#f8fafc; padding:12px 16px; font-size:11px; text-transform:uppercase; letter-spacing:0.5px; color:var(--text-muted); font-weight:700; border-bottom:1px solid var(--border-subtle); }}
td {{ padding:14px 16px; border-bottom:1px solid var(--border-light); font-size:13px; vertical-align:top; }}
tr:hover td {{ background:#fbfcfd; }}

/* Score pill */
.score-circle {{ width:38px; height:38px; border-radius:50%; display:inline-flex; align-items:center; justify-content:center; font-size:14px; font-weight:800; }}
.score-top {{ background:#dcfce7; color:#15803d; border:2px solid #86efac; }}
.score-high {{ background:#ccfbf1; color:#0f766e; border:2px solid #5eead4; }}
.score-mid {{ background:#fef3c7; color:#b45309; border:2px solid #fde68a; }}
.score-low {{ background:#f1f5f9; color:#475569; border:2px solid #cbd5e1; }}

/* Priority and Schedule Badges */
.priority-wrap {{ display:flex; flex-direction:column; gap:4px; align-items:flex-start; }}
.badge {{ display:inline-block; padding:3px 8px; border-radius:4px; font-size:11px; font-weight:700; white-space:nowrap; }}
.p-high {{ background:#ecfdf5; color:#065f46; }}
.p-med {{ background:#fffbeb; color:#92400e; }}
.p-low {{ background:#f1f5f9; color:#475569; }}
.p-conflict {{ background:#fef2f2; color:#991b1b; border:1px solid #fecaca; }}

.sched-pill {{ display:inline-block; padding:2px 7px; border-radius:4px; font-size:10px; font-weight:700; text-transform:uppercase; letter-spacing:0.3px; }}
.sched-fw {{ background:#e0e7ff; color:#3730a3; }}
.sched-pw {{ background:#f3e8ff; color:#6b21a8; }}
.sched-fwd {{ background:#e0f2fe; color:#0369a1; }}
.sched-pwd {{ background:#f4f4f5; color:#52525b; }}
.sched-conflict {{ background:#fee2e2; color:#b91c1c; }}

/* Event Content */
.title-row {{ display:flex; align-items:center; gap:8px; flex-wrap:wrap; }}
.item-title {{ font-size:15px; font-weight:700; color:var(--text-main); text-decoration:none; line-height:1.3; }}
.item-title:hover {{ color:var(--teal-primary); text-decoration:underline; }}
.mode-pill {{ font-size:10px; font-weight:700; text-transform:uppercase; padding:2px 6px; border-radius:3px; background:#f1f5f9; color:#475569; }}
.mode-in-person {{ background:#dbeafe; color:#1e40af; }}
.mode-online {{ background:#ede9fe; color:#5b21b6; }}
.item-meta {{ font-size:12px; color:var(--text-muted); margin-top:4px; display:flex; gap:10px; flex-wrap:wrap; }}
.item-why {{ font-size:12px; color:#134e4a; margin-top:6px; background:#f0fdfa; padding:6px 10px; border-left:3px solid var(--teal-primary); border-radius:0 4px 4px 0; font-style:italic; line-height:1.4; }}

/* Eligibility & Status */
.elig-pill {{ display:inline-block; font-size:11px; font-weight:700; padding:3px 8px; border-radius:4px; }}
.elig-eligible {{ background:#dcfce7; color:#166534; }}
.elig-unknown {{ background:#fef3c7; color:#92400e; }}
.elig-ineligible {{ background:#fee2e2; color:#991b1b; }}

.state-pill {{ font-size:11px; font-weight:700; text-transform:uppercase; padding:3px 7px; border-radius:4px; }}
.state-seen {{ background:#f1f5f9; color:#64748b; }}
.state-tracked {{ background:#ecfdf5; color:#059669; border:1px solid #a7f3d0; }}
.state-applied {{ background:#eff6ff; color:#2563eb; border:1px solid #bfdbfe; }}
.state-rejected {{ background:#fef2f2; color:#dc2626; }}

/* Actions */
.btn-group {{ display:flex; gap:4px; align-items:center; justify-content:flex-end; }}
.btn {{ display:inline-flex; align-items:center; justify-content:center; padding:5px 9px; border-radius:5px; font-size:12px; font-weight:600; text-decoration:none; transition:all 0.15s; border:1px solid transparent; }}
.btn-track {{ background:#ecfdf5; color:#065f46; border-color:#a7f3d0; }}
.btn-track:hover {{ background:#059669; color:#fff; }}
.btn-applied {{ background:#eff6ff; color:#1e40af; border-color:#bfdbfe; }}
.btn-applied:hover {{ background:#2563eb; color:#fff; }}
.btn-reject {{ background:#fef2f2; color:#991b1b; border-color:#fecaca; }}
.btn-reject:hover {{ background:#dc2626; color:#fff; }}
.btn-detail {{ background:#f8fafc; color:#475569; border-color:var(--border-subtle); }}
.btn-detail:hover {{ background:#e2e8f0; color:var(--text-main); }}

@media (max-width: 768px) {{
  header {{ padding:14px 18px; }}
  .container {{ padding:0 12px; }}
  .search-box {{ min-width:100%; }}
  .controls {{ flex-direction:column; align-items:stretch; }}
}}
</style>
<script>
function filterTable() {{
  const query = document.getElementById('radarSearch').value.toLowerCase().trim();
  const rows = document.querySelectorAll('tbody tr.event-item');
  let matchCount = 0;
  rows.forEach(r => {{
    const text = r.innerText.toLowerCase();
    if (!query || text.includes(query)) {{
      r.style.display = '';
      matchCount++;
    }} else {{
      r.style.display = 'none';
    }}
  }});
  const countEl = document.getElementById('searchCount');
  if (query) {{
    countEl.textContent = matchCount + ' matching';
  }} else {{
    countEl.textContent = '';
  }}
}}
</script>
</head>
<body>
<header>
  <div class="brand">
    <div>
      <div style="display:flex; align-items:center; gap:8px;">
        <h1 class="brand-title">🛰️ Buildathon Radar</h1>
        <span class="brand-badge">Live Radar</span>
      </div>
      <div class="tagline">Indian High-School Student Edition (Class 11/12) &middot; Bengaluru &middot; Free & Weekend Prioritized</div>
    </div>
  </div>
  <div class="header-links">
    <a href="/list">Read-Only List</a>
    <a href="/api/events" target="_blank">JSON API</a>
  </div>
</header>
<div class="container">
  {cards_html}
  <div class="controls">
    <div class="tabs">
      <a href="/dashboard" class="{'active' if not current_filter else ''}">All Active ({total})</a>
      <a href="/dashboard?filter=free_weekend" class="{'active' if current_filter == 'free_weekend' else ''}">Free &amp; Weekend ({free_weekend_count})</a>
      <a href="/dashboard?filter=high" class="{'active' if current_filter == 'high' else ''}">High Priority ({high_count})</a>
      <a href="/dashboard?filter=unverified" class="{'active' if current_filter == 'unverified' else ''}">Needs Verification ({unverified_count})</a>
      <a href="/dashboard?filter=tracked" class="{'active' if current_filter == 'tracked' else ''}">Shortlisted ({tracked_count})</a>
      <a href="/dashboard?filter=applied" class="{'active' if current_filter == 'applied' else ''}">Applied ({applied_count})</a>
      <a href="/dashboard?filter=deadlines" class="{'active' if current_filter == 'deadlines' else ''}">Deadlines</a>
    </div>
    <div class="search-box">
      <span>🔍</span>
      <input type="search" id="radarSearch" placeholder="Filter by title, AI theme, host, city..." aria-label="Search hackathons" oninput="filterTable()">
      <span id="searchCount" class="search-count"></span>
    </div>
  </div>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th width="150">Priority &amp; Timing</th>
          <th width="50">Score</th>
          <th>Event &amp; Recommendation Rationale</th>
          <th width="110">Eligibility</th>
          <th width="110">Deadline</th>
          <th width="80">State</th>
          <th width="220" style="text-align:right;">Actions</th>
        </tr>
      </thead>
      <tbody>
        {rows_html if rows_html else '<tr><td colspan="7" style="text-align:center; padding:40px; color:#64748b;">No active opportunities match the selected criteria.</td></tr>'}
      </tbody>
    </table>
  </div>
</div>
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

    track_token = tracker_store.sign_action("track", row["event_id"])
    applied_token = tracker_store.sign_action("applied", row["event_id"])
    reject_token = tracker_store.sign_action("reject", row["event_id"])

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} - Buildathon Radar</title>
<style>
body {{ margin:0; padding:0; background:{PAGE_BG}; font-family:{FONT_STACK}; color:#2e4243; }}
header {{ background:{TEAL_DARK}; color:#fff; padding:20px 32px; }}
.container {{ max-width:800px; margin:28px auto; padding:0 20px; }}
.card {{ background:#fff; border-radius:8px; padding:28px; box-shadow:0 1px 4px rgba(0,0,0,0.06); }}
.badge {{ display:inline-block; padding:4px 10px; border-radius:4px; font-size:12px; font-weight:bold; }}
.p-high {{ background:#e6f4f1; color:#0d9488; }}
.p-med {{ background:#fff4e5; color:#d97706; }}
h1 {{ margin:12px 0 6px 0; font-size:24px; color:{TEAL_DARK}; }}
.meta {{ font-size:14px; color:#6b7b7b; margin-bottom:18px; }}
.why-box {{ background:#f2f8f7; border-left:4px solid {ACCENT}; padding:12px 16px; border-radius:0 6px 6px 0; font-style:italic; margin-bottom:24px; font-size:14px; }}
.grid {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-bottom:24px; }}
.info-item {{ background:#faf9f6; padding:12px 14px; border-radius:6px; }}
.info-item .label {{ font-size:11px; text-transform:uppercase; color:#8a9a9a; font-weight:bold; }}
.info-item .val {{ font-size:14px; font-weight:600; color:#2e4243; margin-top:4px; }}
.summary-box {{ margin-bottom:24px; line-height:1.6; font-size:14px; }}
.actions {{ border-top:1px solid #e2ece9; padding-top:18px; display:flex; gap:10px; align-items:center; }}
.btn {{ display:inline-block; padding:9px 16px; border-radius:4px; font-size:13px; font-weight:bold; text-decoration:none; }}
.btn-primary {{ background:{ACCENT}; color:#fff; }}
.btn-blue {{ background:#2563eb; color:#fff; }}
.btn-danger {{ background:#fee2e2; color:#dc2626; }}
.btn-link {{ color:{ACCENT}; margin-left:auto; text-decoration:none; font-weight:bold; }}
</style>
</head>
<body>
<header>
  <a href="/dashboard" style="color:#a2cfcb; text-decoration:none; font-size:13px;">&larr; Back to Dashboard</a>
</header>
<div class="container">
  <div class="card">
    <div><span class="badge p-high">{priority}</span> &middot; Score {score}/100 &middot; State: {state.upper()}</div>
    <h1>{title}</h1>
    <div class="meta">Organised by {host} &middot; Source: {source}</div>
    <div class="why-box"><strong>Why recommended:</strong> {why}</div>
    <div class="grid">
      <div class="info-item"><div class="label">Location & Format</div><div class="val">{loc} ({mode})</div></div>
      <div class="info-item"><div class="label">Event Dates</div><div class="val">{start} &rarr; {end}</div></div>
      <div class="info-item"><div class="label">Student Eligibility</div><div class="val">{eligibility}</div></div>
      <div class="info-item"><div class="label">Age Restrictions</div><div class="val">{age}</div></div>
      <div class="info-item"><div class="label">Registration Deadline</div><div class="val">{deadline}</div></div>
      <div class="info-item"><div class="label">Team Size</div><div class="val">{team}</div></div>
      <div class="info-item"><div class="label">Prizes</div><div class="val">{prize}</div></div>
      <div class="info-item"><div class="label">Official URL</div><div class="val"><a href="{url}" target="_blank">Open Link &rarr;</a></div></div>
    </div>
    <div class="summary-box">
      <strong>Summary:</strong>
      <p>{summary}</p>
    </div>
    <div class="actions">
      <a class="btn btn-primary" href="/track?event_id={eid}&t={track_token}">&#128204; Shortlist / Track</a>
      <a class="btn btn-blue" href="/applied?event_id={eid}&t={applied_token}">&#127919; Mark Applied</a>
      <a class="btn btn-danger" href="/reject?event_id={eid}&t={reject_token}">&#125D1; Dismiss</a>
      <a class="btn-link" href="{url}" target="_blank">Visit Official Page &rarr;</a>
    </div>
  </div>
</div>
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


@app.get("/")
def health():
    return HTMLResponse(_health_page(), status_code=200)


@app.get("/dashboard")
def dashboard(filter: Optional[str] = None):
    conn = _get_conn()
    try:
        if filter == "free_weekend":
            events = [e for e in tracker_store.get_all_events(conn) if "Free & Weekend" in str(e["why"] if "why" in e.keys() else "")]
        elif filter == "high":
            events = tracker_store.get_events_by_filter(conn, priority="HIGH PRIORITY")
        elif filter == "unverified":
            events = tracker_store.get_events_by_filter(conn, eligibility="UNKNOWN")
        elif filter == "tracked":
            events = tracker_store.get_events_by_filter(conn, state="tracked")
        elif filter == "applied":
            events = tracker_store.get_events_by_filter(conn, state="applied")
        elif filter == "deadlines":
            events = tracker_store.get_upcoming_deadlines(conn, limit=50)
        else:
            events = tracker_store.get_all_events(conn)
    finally:
        conn.close()
    return HTMLResponse(_dashboard_page(events, current_filter=filter), status_code=200)


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


@app.get("/api/events")
def api_events(
    priority: Optional[str] = None,
    state: Optional[str] = None,
    eligibility: Optional[str] = None,
    search: Optional[str] = None,
):
    conn = _get_conn()
    try:
        rows = tracker_store.get_events_by_filter(
            conn, priority=priority, state=state, eligibility=eligibility, search=search
        )
        return [dict(r) for r in rows]
    finally:
        conn.close()


@app.get("/api/deadlines")
def api_deadlines(limit: int = 15):
    conn = _get_conn()
    try:
        rows = tracker_store.get_upcoming_deadlines(conn, limit=limit)
        return [dict(r) for r in rows]
    finally:
        conn.close()
