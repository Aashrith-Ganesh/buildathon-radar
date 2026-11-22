# Buildathon Radar — Remediation Roadmap

**Date:** 2026-11-22
**Basis:** `FREEBUFF-FULL-AUDIT.md`, `FREEBUFF-SECURITY-AUDIT.md`, `FREEBUFF-UX-AI-SLOP-AUDIT.md`, `FREEBUFF-FUNCTIONAL-QA.md`.
**Rule for this document:** no application code, data, blackout dates or configuration was changed during the audit. This is a plan, not a changelog.

---

## 0. The one decision that matters

Do not polish the dashboard until the discovery layer stops inventing events.

A student can forgive a plain interface. They cannot forgive being sent to a 404 registration page for a hackathon that never existed, or planning around a 2014 news article. **Data integrity is the product.** Everything else is secondary.

Recommended sequencing:

```
Phase 0  Stop the bleeding (1–2 days)      -> remove fixtures from user-facing counts
Phase 1  Trustworthy core (1 week)         -> real sources only, date/eligibility provenance
Phase 2  Security baseline (2–3 days)      -> origin checks, local token, headers
Phase 3  Design system + responsive (3–5d) -> one shell, light theme, mobile nav
Phase 4  Student workflow (3–5 days)       -> score breakdown, lineage, grouping, empty states
Phase 5  Hardening (ongoing)               -> dependency pinning, monitoring, tests
```

---

## 1. P0 — Blockers (must ship before any real use)

### R-01 — Remove fixture and news adapters from the opportunity pipeline
**Addresses:** F-01, F-02, F-03, F-10, U-04, U-05
**Why:** 19 of 27 adapters invent data; two more ingest news. These directly create the false "100 open" dashboard.
**Do:**
1. Add `source_kind` to `discovery_sources`: `live | curated | fixture | news`.
2. Mark the 19 literal-list adapters `fixture`, LinkedIn/X/search `news`, and the four real API adapters `live`.
3. Exclude `fixture` and `news` from `/dashboard`, `/api/events`, counts, scoring and the "next eligible" hero by default.
4. Add `ENABLE_DEMO_SOURCES=0` (default) and a visible banner when enabled.
5. Delete the fabricated `verification_status="verified"` from every literal record.
**Acceptance:**
- Default dashboard contains only rows with `source_kind='live'` (or verified curated records with a working URL).
- `/sources` shows "4 live · 0 fixture · 1 blocked" and no "100% fault isolated".
- A source that returns fixtures cannot report `success`.

### R-02 — Enforce future-only listing and expiry
**Addresses:** F-04
**Do:**
1. `get_all_events()` and `/dashboard` require `COALESCE(event_end,event_start) >= today` by default.
2. Add `state='over'`/`verification_status='expired'`; run daily prune via the existing CLI.
3. Never render "Closes: Open" for a missing deadline; render "Unknown".
**Acceptance:**
- Zero rows with an end date before today in any default or filtered view.
- An explicit "Past events" view exists if history is wanted.
- Counts on labels equal rendered rows.

### R-03 — Remove invented dates and eligibility
**Addresses:** F-03, F-05, F-06
**Do:**
1. Delete `"2027-01-23"` fallbacks in `search_engine.py`.
2. Delete `eligibility="ELIGIBLE"` from adapters; default `None`.
3. Remove `item["eligibility"]` from the eligibility text corpus.
4. Add `date_source` (`listing|article|inferred`) and `eligibility_evidence` (quoted snippet) columns.
5. Parse ISO 8601/epoch dates; mark missing dates `uncertain`.
**Acceptance:**
- No event can be `ELIGIBLE` without a stored evidence snippet.
- No event can be `verified` with `date_source='inferred'`.
- News articles cannot produce an event row.

### R-04 — CSRF + local authentication for mutations
**Addresses:** S-01, S-02, S-05
**Do:**
1. Reject non-GET requests whose `Origin` is present and not the app origin; reject `Sec-Fetch-Site: cross-site`.
2. Generate a local admin token at first run; require it (header or HttpOnly SameSite=Strict cookie) for `/api/action`, `/api/scan`, `/api/blackouts*`, `/api/sources/*/toggle`.
3. Make the signed action token mandatory (missing → 403), not optional.
**Acceptance:**
- `curl` without the token → 401/403.
- `Origin: http://evil.example` → 403 on every mutation.
- Dashboard actions still work with the local session.

---

## 2. P1 — Trust and safety

### R-05 — Honest source health
**Addresses:** F-10
**Do:** persist `last_success_at`, `last_status` (`ok|empty|blocked|fixture|error`), `consecutive_failures`, `last_item_at`; compute health from these, not from `err is None`. Surface "no live events in 14 days" as a warning.
**Acceptance:** Reddit's 403 shows as `blocked`; a fixture adapter shows `fixture`, never `healthy`.

### R-06 — Fix deduplication guards
**Addresses:** F-07
**Do:** require URL equality **or** (title similarity ≥0.70 **and** date within 2 days **and** compatible city/host); ignore generic-only titles; keep non-null host/summary during merge; log every merge with both source URLs for review. Add a "merge review" page.
**Acceptance:** synthetic different-city same-title pair is **not** merged; cross-source same-event pair is merged; no `host=None` after merge.

### R-07 — Fix scoring correctness and transparency
**Addresses:** F-06, F-08, U-07
**Do:**
1. Online events cap geography at 14; reason text follows the actual mode.
2. Normalize component maxima to 100 or explain the cap.
3. Persist `scoring` JSON (already returned) and render bars on detail/rows.
4. Enforce `only_in_person` / `target_city_only` from the profile, or remove them.
5. Do not show `HIGH PRIORITY` when eligibility is `UNKNOWN` without a "verify" badge.
**Acceptance:** online Bengaluru event never says "In-person in Bengaluru"; every score has a visible breakdown; hero respects Bengaluru-only preference.

### R-08 — Front-end security hardening
**Addresses:** S-03, S-04, S-06, S-07
**Do:**
1. Remove inline `onclick` string interpolation; use `data-*` + listeners or `JSON.parse` of an escaped JSON block.
2. Add CSP (`default-src 'self'`), `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`.
3. Disable `/docs` and `/openapi.json` unless `DEBUG=1`.
4. `chmod 600 .env`; move the Gmail app password to Keychain if the machine is shared; rotate it if exposure is possible.
**Acceptance:** a blackout title containing `');alert(1);//` renders inert; headers present; docs 404.

### R-09 — Email semantics and reminders
**Addresses:** F-15
**Do:**
1. Return `sent|skipped|failed` instead of bool.
2. Add `--test-email --to <address>` restricted to an explicit test recipient.
3. Map `SMTPAuthenticationError` correctly; log the SMTP stage without secrets.
4. Add a deadline-reminder job with a `notifications` ledger keyed by `(event_id, kind, run_date)` to prevent duplicates.
**Acceptance:** disabled path reports `skipped`; wrong password reports `auth_failed`; one reminder per event per deadline window; no real users contacted in tests.

---

## 3. P2 — Design system, accessibility, workflow

### R-10 — One shell for every page
**Addresses:** U-01, U-10, U-11
**Do:** extract `header`, `nav`, `button`, `table`, `modal`, `empty-state` components; use the same CSS on dashboard, calendar, sources, list, detail, 404. Fix modal sizing (`min(500px, 100vw - 32px)`) and internal scroll.
**Acceptance:** visual diff across pages shows one header and one button style; modal's primary action is fully visible at 1440 and 390.

### R-11 — Light theme and contrast
**Addresses:** U-02, A-01
**Do:** semantic tokens for both themes; H1/card/text pairs audited to ≥4.5:1; add a contrast check to CI; do not ship an incomplete theme.
**Acceptance:** measured H1/body contrast ≥4.5:1 in light and dark; no white-on-white or black-on-black.

### R-12 — Responsive navigation and layout
**Addresses:** U-03, A-03
**Do:** collapse nav below 768 px; horizontally scrollable filter row; no `body` overflow; test 360/390/768/1024/1440.
**Acceptance:** `document.body.scrollWidth <= innerWidth` at every breakpoint; every nav item reachable on mobile.

### R-13 — Accessibility pass
**Addresses:** A-02, A-04, A-05, A-06
**Do:** `aria-label` for all icon-only buttons (125 share buttons, view toggles), `aria-pressed` for toggles, visible `:focus-visible`, 14–16 px body text, decorative emoji `aria-hidden`, keyboard test of filters and modal.
**Acceptance:** axe/Lighthouse accessibility ≥95; zero unnamed buttons; full keyboard traversal.

### R-14 — Student workflow improvements
**Addresses:** U-06, F-12, F-13, U-08
**Do:**
1. Server-side search with an explicit empty state and clear-filters action.
2. Date grouping ("This week", "Next 30 days", "Later") and pagination.
3. "Discovered by" block on detail with every source + announcement URL + scan link.
4. Copy: "Blackouts (53 events excluded)" and "Sources (27)".
**Acceptance:** a student can answer "why this event, where did it come from, can I attend, is it during exams" without leaving the detail page.

### R-15 — Data freshness and scheduling
**Addresses:** F-16
**Do:** load the launchd agents or document a supervisor; add "last refreshed X ago" and a stale warning after 48 h; verify the weekly run.
**Acceptance:** `launchctl list` shows both jobs; dashboard shows freshness; a scheduled dry run completes.

### R-16 — Supply chain and tests
**Addresses:** F-01 (tests enshrine fixtures), S-08
**Do:**
1. Replace the test that asserts "every adapter returns ≥1 event" with assertions about provenance (`live` vs `fixture`) and URL validity.
2. Add regression tests for: no expired rows in default view; count == rendered rows; online Bengaluru geography; self-certified eligibility rejection; dedup different-city non-merge; CSRF rejection; contrast tokens.
3. Pin dependencies and run `pip-audit` in CI.
4. Update README test count (398) and the "27 live sources" claim.
**Acceptance:** tests fail if fixtures leak into default views or counts drift; `pip-audit` clean or triaged.

---

## 4. Effort and ordering

| Phase | Items | Effort | Exit criterion |
|---|---|---|---|
| 0 | R-01, R-02 | 1–2 days | Dashboard shows only future, live events |
| 1 | R-03, R-05, R-06, R-07 | 4–6 days | Every row has provenance, dates, and a defensible score |
| 2 | R-04, R-08, R-09 | 2–3 days | Mutations authenticated; no inline-XSS; email semantics correct |
| 3 | R-10, R-11, R-12, R-13 | 3–5 days | One design system; light/mobile/accessible |
| 4 | R-14, R-15 | 2–3 days | Complete student workflow; scheduled freshness |
| 5 | R-16 | ongoing | Regression coverage and pinned supply chain |

**Total to a defensible v1: roughly 2–3 focused weeks.**

---

## 5. What not to do

- **Do not add more sources** until the existing four live sources are trustworthy and the fixture pipeline is removed. More adapters multiply the problem.
- **Do not add visual effects, gradients, or animation** to compensate for the design inconsistency. The issue is system coherence, not decoration.
- **Do not "fix" the count mismatch by hardcoding the displayed numbers**; derive every label from the same query as the list.
- **Do not delete blackout dates or user shortlist data** while refactoring. The 29 rules / 54 days are correct and should be preserved.
- **Do not enable the fixture adapters behind a flag and leave the flag on.** If demo mode exists, it must be visible and excluded from counts.
- **Do not treat "398 tests pass" as evidence of correctness.** The suite asserts that every adapter returns at least one event, which is exactly the bug.

---

## 6. Definition of done for "ready for a student"

A release is ready when all of the following are true on a clean install:

1. Default dashboard contains only future events, each with a working registration URL and a stated source.
2. No fixture or news adapter contributes to counts, ranking or the hero.
3. Every eligibility label has stored evidence; unknown is the default.
4. Every score has a visible component breakdown and respects Bengaluru-only/in-person preferences.
5. Blackout conflicts are correct at boundaries, persisted, and labelled unambiguously.
6. Light and dark themes both pass 4.5:1; mobile navigation is complete; `body` does not overflow.
7. All mutating endpoints reject cross-origin and unauthenticated requests.
8. `.env` is `0600`; no secret appears in HTML, logs or git.
9. A scheduled run refreshes data and the dashboard shows its freshness.
10. Regression tests cover each of the above and fail when the behaviour regresses.

---

## 7. Adversarial close-out

```markdown
## Adversarial verdict
Claims reviewed: all nine audit areas plus the five required reports.
Evidence: source reads, 398-test run, live DB queries, 27-adapter probe,
browser screenshots at two viewports, contrast measurement, unauthenticated
and cross-origin probes, disposable-DB CRUD.
Confirmed: solid FastAPI/SQLite foundation; correct 29-rule/54-day blackout
engine; working CRUD and conflict recomputation; four genuine live sources;
no SQL injection/path traversal/SSRF.
Refuted: "27 live sources"; "100 open now"; "verified" eligibility;
"100% fault isolated"; multi-source deduplication working in production;
"next eligible" respecting Bengaluru-only preference; complete frontend.
Risk: high (data trust), medium (local security), high (design consistency).
Decision: fix-required. Follow Phase 0 before any further feature work.
```
