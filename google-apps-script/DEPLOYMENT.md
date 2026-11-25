# Google Apps Script Web App Deployment Guide (Serverless Push Architecture)

This guide walks you through deploying the Google Apps Script (GAS) email rendering and delivery service for **Buildathon Radar**.

In this architecture, Google Apps Script functions as a **serverless webhook listener (`doPost`)**. Every Sunday morning at 08:00 AM IST, GitHub Actions runs the discovery engine, generates the digest payload, and securely POSTs it to your deployed Web App, which sends the email via `GmailApp` directly to your inbox.

---

## 🚀 Quick Setup (5 Minutes)

### Step 1: Open Google Apps Script
1. Navigate to [https://script.google.com/](https://script.google.com/) and sign in with your Google Account.
2. Click **+ New project**.
3. Rename the project in the top left to **`Buildathon Radar Digest`**.

### Step 2: Paste `Code.gs`
1. Open [`google-apps-script/Code.gs`](./Code.gs) in your editor.
2. Copy the entire file contents.
3. In the Apps Script web editor, replace all existing code in `Code.gs` with the copied content.
4. Click **Save** (💾 icon or `Cmd+S` / `Ctrl+S`).

---

## ⚙️ Step 3: Configure Script Properties

Script Properties securely store your webhook authentication secret and delivery preferences without hardcoding them in code.

1. In the Apps Script left sidebar, click the **Gear icon (Project Settings ⚙️)**.
2. Scroll down to **Script Properties**.
3. Click **Add script property** and configure the following keys:

| Property | Required? | Example Value | Description |
| :--- | :---: | :--- | :--- |
| `WEBHOOK_SECRET` | **Yes** | `whsec_my_super_secret_key_12345` | Secure shared secret key. Must match `GAS_WEBHOOK_SECRET` in GitHub Secrets. |
| `RECIPIENT_EMAIL` | Optional | `student@example.com` | Override recipient email. If omitted, emails are sent to the deploying Google account. |
| `SENDER_NAME` | Optional | `Buildathon Radar` | Display sender name in Gmail. |
| `DUPLICATE_PREVENTION_ENABLED` | Optional | `true` | Set to `true` (default) to prevent re-delivering duplicate digests. |

4. Click **Save script properties**.

---

## 🌐 Step 4: Deploy as a Web App

1. In the top right corner of the Apps Script editor, click **Deploy** > **New deployment**.
2. Click the **Gear icon (Select type)** next to "Select type" and choose **Web app**.
3. Fill in the deployment configuration:
   - **Description:** `Buildathon Radar Webhook Listener v1`
   - **Execute as:** `Me (your_email@gmail.com)` *(Important: allows sending via your Gmail)*
   - **Who has access:** `Anyone` *(Required: GitHub Actions sends unauthenticated HTTP requests that authenticate via the secret in the payload)*
4. Click **Deploy**.
5. **Authorize Permissions:**
   - Google will display an **"Authorization Required"** prompt.
   - Click **Review Permissions**.
   - Select your Google account.
   - Click **Advanced** > **Go to Buildathon Radar Digest (unsafe)** *(standard for personal Apps Script projects)*.
   - Click **Allow** (authorizes `GmailApp` to send emails on your behalf).
6. **Copy Web App URL:**
   - Under **Web app**, copy the **URL** (ends in `/exec`):
     `https://script.google.com/macros/s/AKfycbx.../exec`
   - Save this URL! You will add it as `GAS_WEB_APP_URL` in GitHub Secrets.

> ⚠️ **Important When Making Future Code Edits:**
> Whenever you modify `Code.gs`, you must create a new version:
> Click **Deploy** > **Manage deployments** > **Edit (pencil icon)** > **Version: New version** > **Deploy**.

---

## 🧪 Step 5: Test Your Deployment (Without Sending Emails)

### 1. In-Editor Simulation (Built-in Test Function)
In the Apps Script editor:
1. Select the function **`testDoPostSimulation`** from the function dropdown at the top.
2. Click **Run**.
3. Check the **Execution log** at the bottom:
   - You should see: `=== RUNNING DOPOST WEBHOOK SIMULATION ===`
   - Authentication check passes.
   - Digest is rendered and validated.
   - `Simulation mode (dry_run=true): Skipped real email send.`
   - Output: `{"status":"success","delivery_id":"test-sim-001",...}`

### 2. Browser Health Check (GET Request)
Open your copied Web App URL in any browser tab:
```
https://script.google.com/macros/s/.../exec
```
You should see a clean JSON response:
```json
{
  "status": "healthy",
  "service": "Buildathon Radar Email Delivery Webhook",
  "version": "2.0.0",
  "auth_configured": true,
  "recipient": "your_email@gmail.com"
}
```

---

## 🔒 Security Best Practices

1. **Secret in POST Body & Header:**
   - The webhook secret is passed inside the JSON payload (`payload.auth.secret`) and via `X-Webhook-Secret`.
   - The secret is **never** passed in the URL query string, preventing exposure in browser history or proxy logs.
2. **Redirect Handling:**
   - Google Apps Script 302 redirects return `script.googleusercontent.com`. Passing `payload.auth.secret` inside the body ensures authentication persists safely without header stripping issues.
3. **Execution as "Me":**
   - Web App executes as your account so `GmailApp.sendEmail()` operates with your personal Gmail quota (100–1,500 emails/day, well exceeding the 1 email/week needed).
