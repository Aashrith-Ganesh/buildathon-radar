# Buildathon Radar — Security Audit

**Date:** 2026-11-22
**Target:** Local application `http://127.0.0.1:8015` and its source at `/Users/aashrith/Projects/buildathon-radar`
**Authorization:** Owner-requested, local-only, non-destructive assessment.
**Constraints observed:** no denial of service, no data exfiltration, no third-party attacks, no real emails, no credential disclosure, no database writes to the live store.

---

## 1. Threat model and exposure

| Property | Value |
|---|---|
| Listener | `127.0.0.1:8015` (loopback only) |
| Authentication | **None** |
| Authorization | **None** |
| Session/cookies | **None** |
| CSRF tokens | **None** for API mutations; signed query token optional |
| Security headers | **None** |
| CORS headers | **None** (browser default same-origin reading blocked, but writes are possible) |
| Secrets | `.env` with `TRACKER_SECRET`, Gmail app password, optional Anthropic/TypeSafe keys |
| Data sensitivity | Personal calendar (exam/test dates), shortlist history, email address |

Because the service binds to loopback, a remote attacker cannot reach it directly. The realistic threats are:

1. **Any local process or user on the machine** (no auth, no file permissions).
2. **Any website the user visits** (CSRF against localhost).
3. **Injected content from external sources** rendered into HTML/JS (stored XSS).
4. **Credential exposure** via `.env` permissions or accidental commit.
5. **Supply chain** from unpinned dependencies.

---

## 2. Findings

### S-01 — No authentication or authorization on any route

- **Severity:** High (mitigated by loopback binding)
- **Component:** all routes in `buildathon_radar/tracker_service.py`
- **Status:** Confirmed (command-verified)
- **Description:** Read and write endpoints are open. This includes personal blackout CRUD, source enable/disable, event state changes, and `/api/scan` which performs network fetches and writes to SQLite.
- **Reproduction:**
  ```bash
  curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8015/api/events        # 200
  curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8015/api/blackouts     # 200
  curl -s -X POST http://127.0.0.1:8015/api/sources/nope/toggle                   # 404 (auth never checked)
  curl -s -X POST http://127.0.0.1:8015/api/action -H 'Content-Type: application/json' -d '{"event_id":"x","action":"track"}'  # 404
  ```
- **Expected:** A local app holding personal calendar data should at minimum require a local API token or session, especially for mutations; or bind to a Unix socket only.
- **Actual:** Full read/write API available to anything that can reach the port.
- **Evidence:** HTTP status codes above; `/openapi.json` lists every endpoint.
- **Recommended correction:** Generate a local admin token at first run, store it hashed, require it for all mutating routes (header or signed cookie). Keep GET pages read-only public if desired. Alternatively use a Unix domain socket or a per-install secret in a SameSite=Strict cookie.
- **Confidence:** High

### S-02 — Cross-site request forgery against localhost mutations

- **Severity:** Medium–High
- **Component:** `/api/action`, `/api/scan`, `/api/blackouts*`, `/api/sources/*/toggle`
- **Status:** Confirmed (command-verified)
- **Description:** Requests with `Origin: http://evil.example` are processed normally. There is no Origin/Referer check and no CSRF token. A malicious website can issue `fetch('http://127.0.0.1:8015/api/scan', {method:'POST', mode:'no-cors'})` or a form POST; even without reading the response, the side effect occurs.
- **Reproduction:**
  ```bash
  curl -i -X POST http://127.0.0.1:8015/api/action \
    -H 'Origin: http://evil.example' -H 'Content-Type: application/json' \
    -d '{"event_id":"does-not-exist","action":"track"}'
  # HTTP/1.1 404 -> request reached application logic, no origin rejection
  curl -i -X POST http://127.0.0.1:8015/api/blackouts \
    -H 'Origin: http://evil.example' -H 'Content-Type: application/json' -d '{}'
  # HTTP/1.1 422 -> validation reached, no origin rejection
  ```
  Note: `/api/action` accepts a JSON body, which triggers a CORS preflight from a browser; the absence of CORS headers blocks the *read*, but a simple `text/plain` form or `no-cors` POST to endpoints that accept form/empty bodies (toggle, scan) is not preflighted. `POST /api/scan` with no body is the clearest example.
- **Expected:** Reject mutating requests whose `Origin` is not `http://127.0.0.1:8015` (or absent for same-origin fetch), and require a CSRF token.
- **Actual:** Any origin is accepted.
- **Evidence:** status codes above.
- **Recommended correction:** Enforce `Origin`/`Sec-Fetch-Site` checks on all non-GET routes; add a per-session CSRF token to the dashboard; require `Content-Type: application/json` and a custom header for mutations.
- **Confidence:** High

### S-03 — Stored XSS via blackout title/reason in the calendar edit handler

- **Severity:** Medium
- **Component:** `_calendar_page()` → `onclick="openEditModal({bid}, '{title}', ..., '{reason}')"`
- **Status:** Confirmed by code review; **not exploited** (would require writing a test rule)
- **Description:** `_esc()` is `html.escape()`, which converts `'` to `&#x27;`. Browsers HTML-decode attribute values **before** parsing inline JavaScript, so `&#x27;` becomes `'` inside the JS string. A title such as `x');alert(document.domain);//` escapes the string and executes. The same pattern exists for `reason`, `s_date`, `e_date`, and `cat`.
- **Reproduction (safe, code-level):**
  1. `POST /api/blackouts` with `title: "x');alert(1);//"`.
  2. Open `/calendar`.
  3. Click **Edit** on that row.
  4. The inline `onclick` contains `openEditModal(30, 'x&#x27;);alert(1);//', ...)`; after HTML decoding the JS parser sees `'x');alert(1);//'`.
- **Expected:** Values passed via `data-*` attributes and read with `dataset`, or serialized with `JSON.stringify`/`|tojson`; CSP blocks inline script.
- **Actual:** Inline JS string interpolation of user/external text.
- **Evidence:** `_calendar_page` f-string; `html.escape` behavior.
- **Recommended correction:** Remove inline handlers; attach event listeners and read `data-id`; or build the modal from a JSON blob embedded with `json.dumps` and `<script type="application/json">`. Add a strict CSP.
- **Confidence:** High (mechanism), Medium (real-world exploitability, since data is local and user-entered)

### S-04 — Missing security headers / clickjacking

- **Severity:** Medium
- **Component:** all HTML responses
- **Status:** Confirmed (command-verified)
- **Description:** No `Content-Security-Policy`, `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, or `Permissions-Policy`. The app can be framed by a remote site (clickjacking) and inline script is unrestricted (amplifies S-03).
- **Reproduction:** `curl -D - -o /dev/null http://127.0.0.1:8015/dashboard` → no security headers.
- **Expected:** At minimum `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, and a CSP that disallows inline script (after refactoring handlers).
- **Actual:** Headers absent.
- **Evidence:** response headers.
- **Recommended correction:** Add a middleware with these headers; move inline JS/CSS to static files or nonces.
- **Confidence:** High

### S-05 — Action tokens are optional

- **Severity:** Medium
- **Component:** `POST /api/action`
- **Status:** Confirmed (code)
- **Description:** `if req.token and not verify_action(...)` — when `token` is omitted, verification is skipped. The signed-token protection only applies if the caller volunteers a token.
- **Reproduction:** POST `{"event_id":"<real id>","action":"track"}` without `token`; the action is applied (not executed during audit to avoid state change; code path is explicit).
- **Expected:** Token required for every state change, or session-authenticated equivalent.
- **Actual:** Optional token = no protection.
- **Evidence:** `tracker_service.py::api_action`.
- **Recommended correction:** Require and verify the token, or replace it with session auth. Treat missing token as 403.
- **Confidence:** High

### S-06 — API documentation exposed

- **Severity:** Low
- **Component:** `/docs`, `/openapi.json`
- **Status:** Confirmed (command)
- **Description:** FastAPI defaults expose interactive docs and the full schema, including every mutation endpoint.
- **Reproduction:** both return 200.
- **Expected:** Disable in production/local-hardening mode (`docs_url=None`, `openapi_url=None`) or protect them.
- **Actual:** Public.
- **Evidence:** HTTP 200.
- **Recommended correction:** Disable docs unless an explicit debug flag is set.
- **Confidence:** High

### S-07 — `.env` is world-readable and contains high-value secrets

- **Severity:** Medium
- **Component:** `/Users/aashrith/Projects/buildathon-radar/.env`
- **Status:** Confirmed (command); **values not read or disclosed**
- **Description:** File mode is `0644` (owner read/write, group/world read). It contains `TRACKER_SECRET`, a Gmail app password, and the recipient address. It is correctly listed in `.gitignore` (line 151), so it is not tracked.
- **Reproduction:** `ls -l .env` → `-rw-r--r--`.
- **Expected:** `0600`, owned by the user; secrets in Keychain or a secret manager; a dedicated Gmail app password with minimal scope.
- **Actual:** Other local accounts can read the credentials.
- **Evidence:** file mode; `.env` key names only.
- **Recommended correction:** `chmod 600 .env`; rotate the app password if the machine is shared; consider storing the SMTP password in macOS Keychain. Never commit `.env`.
- **Confidence:** High

### S-08 — Unpinned dependencies

- **Severity:** Low–Medium
- **Component:** `requirements.txt`
- **Status:** Confirmed (code)
- **Description:** No version constraints (`anthropic`, `requests`, `python-dotenv`, `markdown`, `pytest`, `fastapi`, `uvicorn`, `httpx`, `typesafe-sdk`). Installs are not reproducible and a compromised/new release is picked up automatically. `pip check` reports no broken requirements in the current venv.
- **Reproduction:** `cat requirements.txt`; `venv/bin/pip check` → "No broken requirements found."
- **Expected:** Pinned versions or a lockfile with hashes; a scheduled audit (`pip-audit`).
- **Actual:** Floating versions.
- **Evidence:** file contents; installed versions (FastAPI 0.165.0, Uvicorn 0.54.0, requests 2.34.2, pytest 9.2.0).
- **Recommended correction:** `pip freeze > requirements.lock`, use `pip-audit` in CI, and pin direct dependencies.
- **Confidence:** High

### S-09 — Excessive local data exposure

- **Severity:** Low
- **Component:** `/api/events`
- **Status:** Confirmed (command)
- **Description:** Returns all 116 rows with internal `why`, `conflict_details`, state, scores and URLs. This is reasonable for a local dashboard but combines badly with S-01 (no auth).
- **Expected:** If auth is added, scope responses; otherwise accept as local-only.
- **Evidence:** 233 KB JSON response.
- **Recommended correction:** Gate behind the local token; omit internal fields from public views.
- **Confidence:** High

---

## 3. Tested and **not** vulnerable

| Test | Payload | Result |
|---|---|---|
| SQL injection (search) | `search=quantum' OR '1'='1` | Parameterised; no change in result count |
| SQL injection (location) | `location=%' OR 1=1--` | 0 rows; query treated as literal (parameterised) |
| SQL injection (path ID) | `/event/..%2F..%2Fetc%2Fpasswd` | 404; no file read |
| Path traversal | `/event/../../etc/passwd` | 404; event lookup only |
| SSRF via API | no user-supplied URL fetch endpoints | Not applicable; adapters use fixed hosts |
| Unauthorised action token | missing token + unknown event | 404, but for unknown event (see S-05) |
| CORS read | no `Access-Control-Allow-Origin` | Cross-origin reads blocked by browser |
| Secret in HTML | grep credentials in pages | Not found |
| Credential in docs | README/CLAUDE | No secret values; `.env.example` placeholders only |

**Dependency audit:** `pip check` clean; no `pip-audit` run (not installed). **Untested:** CVEs in installed packages, OS-level access controls, Gmail account security, and browser extension threats.

---

## 4. Risk summary

| ID | Severity | Exploitability | Impact | Priority |
|---|---|---|---|---|
| S-01 | High | Local process / any local user | Full data + state control | P0 if machine is shared; P1 otherwise |
| S-02 | Medium–High | Any website user visits | State changes, scans, blackout edits | P0 |
| S-03 | Medium | Requires crafted blackout entry | Script execution in local origin | P1 |
| S-04 | Medium | Any framed page | Clickjacking, XSS amplification | P1 |
| S-05 | Medium | Any local caller | Bypass signed links | P1 |
| S-06 | Low | Local/network if bound wider | API discovery | P2 |
| S-07 | Medium | Other local accounts | SMTP + signing secret | P1 |
| S-08 | Low–Medium | Supply chain | Reproducibility, future CVE | P2 |
| S-09 | Low | Local | Data exposure | P2 |

---

## 5. Security verdict

The app is **safe only under the assumption that the machine is single-user and no untrusted website is visited while the service runs**. That assumption is not stated anywhere in the UI or README, and the service holds exam schedules and a Gmail app password.

Minimum bar before sharing the machine or exposing the port:

1. Enforce Origin checks + CSRF token on mutations (S-02).
2. Require a local auth token for writes (S-01, S-05).
3. Remove inline JS string interpolation (S-03) and add CSP/headers (S-04).
4. `chmod 600 .env` (S-07).
5. Disable `/docs` (S-06).

No SQL injection, path traversal, or SSRF was found. The database layer is parameterised and well-structured; the weaknesses are at the HTTP and template boundaries.
