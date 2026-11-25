# Buildathon Radar - Google Apps Script Weekly Digest Mailing System

This directory contains the standalone **Google Apps Script (GAS)** email delivery system for **Buildathon Radar**.

It receives structured weekly digest JSON payloads from GitHub Actions via an authenticated Web App webhook (`doPost`), formats them into an accessible, mobile-responsive technology newsletter, and delivers them to your Gmail inbox every Sunday morning at **08:00 AM IST**.

---

## 🏗️ Architecture Overview

```
┌────────────────────────────────────────────────────────┐
│  GitHub Actions (Sundays 02:30 UTC / 08:00 AM IST)     │
│  - Restores state from 'radar-state' branch            │
│  - Runs DiscoveryEngine on multi-platform sources      │
│  - Filters for Bengaluru, high school, exam blackouts  │
│  - Generates and validates weekly digest JSON payload   │
└───────────────────────────┬────────────────────────────┘
                            │
                            │ HTTPS POST (payload.auth.secret)
                            ▼ (Follows 302 Redirect)
┌────────────────────────────────────────────────────────┐
│  Google Apps Script Web App (doPost)                   │
│  - Authenticates shared webhook secret                 │
│  - Enforces duplicate prevention (SHA-256 hash)        │
│  - Renders inline-styled HTML + plaintext email        │
│  - Sends via GmailApp.sendEmail()                      │
│  - Returns JSON delivery confirmation                  │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│  Recipient Gmail Inbox                                 │
│  Sunday 08:00 AM IST                                   │
└────────────────────────────────────────────────────────┘
```

---

## 📁 Directory Contents

- **[`Code.gs`](./Code.gs)** — Full Google Apps Script codebase containing:
  - `doPost(e)`: Webhook entrypoint for GitHub Actions pushes.
  - `doGet(e)`: Lightweight JSON health check endpoint.
  - `renderDigestHtml(data)`: High-fidelity, mobile-responsive HTML newsletter generator.
  - `renderPlainText(data)`: Plain text fallback email renderer.
  - `testDoPostSimulation()`: Zero-dependency test function for in-editor dry-run verification.
  - `testWithSampleData()`: Offline test generator with mocked data.
- **[`DEPLOYMENT.md`](./DEPLOYMENT.md)** — Step-by-step setup guide for creating the Apps Script project, setting Script Properties, deploying as a Web App, and testing.
- **[`sample-digest-response.json`](./sample-digest-response.json)** — 978-line authentic sample payload generated directly from `tracker.db` showcasing all 12 metadata fields per opportunity, blackout notices, and deadlines.

---

## ⚙️ Configuration & Script Properties

Configure these in the Google Apps Script project settings (**Project Settings ⚙️ > Script Properties**):

| Property Name | Required? | Default / Example Value | Description |
|---|---|---|---|
| `WEBHOOK_SECRET` | **Yes** | `whsec_my_secret_token_123` | Shared secret key for authenticating POST payloads from GitHub Actions. |
| `RECIPIENT_EMAIL` | Optional | `your_email@gmail.com` | Target inbox. Defaults to the logged-in Google account email if omitted. |
| `SENDER_NAME` | Optional | `Buildathon Radar` | Display name for outgoing emails in Gmail. |
| `DUPLICATE_PREVENTION_ENABLED` | Optional | `true` | When `true`, avoids re-sending identical digests within 5 days. |
| `FORCE_SEND` | Optional | `false` | Set to `true` to temporarily bypass duplicate prevention during debugging. |

---

## 🧪 Testing In Google Apps Script Editor

To test without deploying or sending real emails:
1. Open `Code.gs` in the Apps Script editor.
2. Select **`testDoPostSimulation`** from the top function dropdown.
3. Click **Run**.
4. Check the **Execution Log** for complete verification output.

For full deployment instructions, see [DEPLOYMENT.md](./DEPLOYMENT.md).
