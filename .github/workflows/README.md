# GitHub Actions Workflows - Buildathon Radar

This directory contains the continuous integration and serverless automation workflows for **Buildathon Radar**.

---

## 1. Workflows Overview

| Workflow | File | Trigger | Purpose |
| :--- | :--- | :--- | :--- |
| **Weekly Buildathon Digest** | [`weekly-digest.yml`](./weekly-digest.yml) | Sunday 02:30 UTC / 08:00 AM IST + Manual Dispatch | Executes the discovery engine, checks student eligibility and exam blackouts, formats the weekly digest, submits via webhook to Google Apps Script Web App, and commits state back to `radar-state`. |
| **Dependency Audit** | [`dependency-audit.yml`](./dependency-audit.yml) | Pull Requests + Monday 04:23 UTC | Scans `requirements.lock` using `pip-audit` for known vulnerabilities. |

---

## 2. Weekly Digest Workflow Details

### 🕒 Schedule
- **Cron:** `30 2 * * 0`
- **Time:** Every Sunday at 02:30 UTC (which corresponds to 08:00 AM IST, safely arriving prior to 09:00 AM IST).

### 🕹️ Manual Dispatch (`workflow_dispatch`)
The workflow can be manually triggered at any time from the **Actions** tab in GitHub with custom parameters:

| Input Parameter | Type | Default | Description |
| :--- | :---: | :---: | :--- |
| `dry_run` | `boolean` | `false` | When `true`, runs discovery, validation, and digest generation, but **does not** call the webhook or commit state to `radar-state`. |
| `force_send` | `boolean` | `false` | Bypasses duplicate detection if you need to re-send a digest within the 5-day deduplication window. |
| `mock_submission` | `boolean` | `false` | Simulates a successful Google Apps Script response without making actual HTTP requests. Ideal for end-to-end CI pipeline validation. |
| `skip_discovery` | `boolean` | `false` | Skips running network adapters and uses the existing cached SQLite store directly. |

---

## 3. Required GitHub Secrets

To enable email delivery, configure these secrets under **Settings > Secrets and variables > Actions**:

| Secret Name | Required? | Example / Value | Description |
| :--- | :---: | :--- | :--- |
| `GAS_WEB_APP_URL` | **Yes** | `https://script.google.com/macros/s/.../exec` | The published deployment URL of the Google Apps Script Web App (`doPost`). |
| `GAS_WEBHOOK_SECRET` | **Yes** | `whsec_abc123...` | Shared secret key that matches `WEBHOOK_SECRET` in Google Apps Script Script Properties. |
| `RECIPIENT_EMAIL` | Optional | `student@example.com` | Override recipient email. If unset, Google Apps Script defaults to the deploying Google account email. |

---

## 4. Runner Architecture & State Persistence

Because GitHub Actions runners are ephemeral (discarded after each run), Buildathon Radar uses an **orphan Git branch (`radar-state`)** for cross-runner persistence:

```
┌────────────────────────────────────────────────────────┐
│ GitHub Actions Runner (Ephemeral Ubuntu VM)           │
│                                                        │
│ 1. actions/checkout (main repo code)                   │
│ 2. Clone state from 'radar-state' branch into state/    │
│    - tracker.db                                        │
│    - delivery_history.json                             │
│    - last_digest.json                                  │
│ 3. Restore state/tracker.db to working tracker.db      │
│ 4. Run Multi-Platform Discovery Engine                 │
│ 5. Filter for Bengaluru / Student / Exam Blackouts     │
│ 6. Duplicate check (delivery_id & SHA256 content hash) │
│ 7. POST payload to GAS Web App (follows 302 redirect)  │
│ 8. Record delivery & checkpoint SQLite WAL             │
│ 9. Commit & push state/ back to 'radar-state' branch   │
│ 10. Upload state/ as 90-day artifact backup            │
└────────────────────────────────────────────────────────┘
```

### Why a dedicated `radar-state` branch?
1. **Zero Polluting Commits on Main:** Keeps `main` Git commit history clean.
2. **Auditability:** Complete history of every weekly state snapshot and delivery log.
3. **No 7-Day Expiry:** Unlike GitHub Actions Cache (which evicts keys after 7 days of inactivity), branch storage is permanent.
4. **Artifact Redundancy:** Every run also uploads an artifact named `radar-state-<run_id>` retained for 90 days.
