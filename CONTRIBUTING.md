# CONTRIBUTING.md

Engineering standards and development workflows for working on Buildathon Radar.

---

## 1. Documentation Structure

All primary project documentation files at the repository root are UPPERCASE: `README.md`, `SPEC.md`, `ROADMAP.md`, `LEARNINGS.md`, `CONTRIBUTING.md`. Archived or reference materials live under `docs/`.

Each document serves a defined purpose:

- **README.md**: Public overview. What this is, setup instructions, architecture, and verification.
- **SPEC.md**: Technical specifications, architecture, endpoints, and data contracts.
- **ROADMAP.md**: Forward-looking tracking. Shipped milestones and planned capabilities.
- **LEARNINGS.md**: Technical post-mortems, edge cases, and engineering rationales.
- **CONTRIBUTING.md**: Engineering standards, workflow rules, and contributor guide (this file).

---

## 2. Prose & Code Style

- **Clarity & Directness**: Write concise, unambiguous technical documentation.
- **Clean Typography**: Avoid unnecessary decorative emojis in system logs, email subjects, and formal documentation.
- **Deterministic Logic**: Prioritize explicit, testable rule engines over opaque or non-deterministic assumptions.

---

## 3. Development Workflow

- **Pre-Implementation Verification**: Settle design, schemas, and security boundaries before writing code.
- **Surgical Edits**: Prefer focused, minimal, and reversible modifications. Avoid sweeping reformatting or unnecessary dependency additions.
- **Safety Invariants**:
  - The weekly email delivery path and Google Apps Script webhook integration must remain reliable and duplicate-proof.
  - Never commit real secrets, API keys, or `.env` files.
  - The local SQLite store (`tracker.db`) uses WAL mode; transactions must be committed cleanly without leaking locks.

---

## 4. Testing & Verification Requirements

Before submitting changes, all checks must pass:

```bash
# 1. Run full automated test suite (must be 100% green with mocked network)
venv/bin/pytest tests/

# 2. Verify clean packaging dependencies
venv/bin/pip check

# 3. Check for trailing whitespace and syntax errors
git diff --check

# 4. Dry-run pipeline validation (no state mutation, no webhook dispatch)
python scripts/run_weekly_digest.py --dry-run --mock-webhook
```

---

## 5. Useful Operational Commands

```bash
# Start local development dashboard
venv/bin/uvicorn buildathon_radar.tracker_service:app --host 127.0.0.1 --port 8015

# Run a local discovery scan
venv/bin/python main.py --dry-run

# Run discovery without discovery scraping (using existing database)
python scripts/run_weekly_digest.py --mock-webhook --skip-discovery

# Execute database opportunity inspection CLI
venv/bin/python radar_cli.py summary
```
