# Release Notes — Buildathon Radar v0.2-Beta

- **Release Version:** `v0.2-Beta`
- **Previous Release:** `v0.1.0-alpha`
- **Release Date:** November 25, 2026
- **Target Audience:** Indian High School Student Builders (The Amaatra Academy, Bengaluru)
- **Git Tag:** `v0.2-Beta`

---

## Executive Summary

Buildathon Radar `v0.2-Beta` introduces fully serverless automated weekly delivery, universal emoji-free clean typography, dual dark/light mode visual galleries, complete repository-wide AI configuration cleanup and neutralisation, and a consolidated master audit and remediation report.

---

## Key Highlights & Feature Deliverables

### 1. Serverless Push Email Digest (GitHub Actions + Google Apps Script)
- **Autonomous Sunday Pipeline:** Scheduled GitHub Actions runner executes weekly at 02:30 UTC / 08:00 AM IST.
- **Cross-Runner State Persistence:** Ephemeral runners clone, restore, checkpoint, and commit SQLite state (`tracker.db`, `delivery_history.json`, `last_digest.json`) using a dedicated orphan Git branch (`radar-state`).
- **Google Apps Script Web App:** Formats digest JSON payloads into clean, responsive HTML newsletters dispatched via `GmailApp.sendEmail()`.
- **Zero Local Daemon Dependency:** The user's Mac no longer needs local wakeups or background servers for weekly delivery.

### 2. Clean Typography & Universal Emoji Sanitization
- **Universal Emoji Purging (`stripEmojis`):** Dynamic regex sanitization strips broken surrogate pairs, unaligned glyph boxes (`️`), and decorative emojis from email subjects, section headings, metadata badges, and descriptions.
- **Accessible HTML Badges:** Clean, high-contrast text badges (`ELIGIBLE`, `BENGALURU`, `TEAM`) replace decorative icon clutter.
- **Unthreaded Subject Pattern:** Refreshed weekly email subject lines ensure Gmail creates independent conversation threads.

### 3. Dual Theme Visual Galleries (Dark & Light Mode)
- **Full Visual Coverage:** Captured high-resolution screenshots across all views in both dark and light modes:
  - Main Dashboard
  - Monthly Academic Blackout Calendar
  - Personal Student Tracker
  - Event Detail & Scoring Breakdown
  - Discovery Sources & Diagnostics
  - Mobile Viewports (320px/390px)

### 4. Repository-Wide AI Configuration Cleanup & Neutralisation
- **Removed Assistant Instruction Files:** Obsolete assistant instruction files (`CLAUDE.md`, `ANTIGRAVITY.md`) removed and consolidated into standard neutral documentation (`CONTRIBUTING.md` and `docs/CLI-AND-DATABASE-REFERENCE.md`).
- **Brand-Neutral Interfaces:** Added `radar_cli.py` and `buildathon_radar.analysis` as standard engineering entrypoints while retaining backward-compatible aliases.
- **Consolidated Master Audit Report:** Unified seven previous audit files into a single master document: [`docs/AUDIT-AND-REMEDIATION-REPORT.md`](AUDIT-AND-REMEDIATION-REPORT.md).

---

## Verification & Quality Gates

- **Test Suite:** 461 passing unit and integration tests (`pytest tests/`).
- **Packaging:** `pip check` verified clean dependency trees.
- **Formatting:** `git diff --check` verified clean whitespace.
- **Dry-Run Pipeline:** End-to-end multi-source discovery validated via `scripts/run_weekly_digest.py`.
