# Feature expansion

## Implementation checklist

- [x] Read the five original Freebuff reports and inspect the current FastAPI, SQLite, discovery and launchd entry points.
- [x] Inspect reference source at commit `53a8a09`, covering tracker schema and API, client state, event rendering, discovery and pagination, refresh workflow and image endpoint.
- [x] Capture the 431-test baseline and take a private SQLite online backup before migrations.
- [x] Add tracker records, activity history, and authenticated writes.
- [x] Extend existing event details with stable shareable slugs and provenance.
- [x] Add source health, enrichment, refresh locking and settings.
- [x] Verify runtime and capture screenshots.

## Reference review

The reference tracker persists status and notes under an event ID in D1, mirrors entries and the API key in browser storage, and resolves concurrent writes by client timestamps. Its Pages Function injects per-slug metadata over the SPA shell. Its scanner tracks partial pagination warnings, derives fields from dates and runs on GitHub Actions. The workflow preserves the previously committed dataset when the entire new output is empty. The image endpoint follows redirects and relies on a declared content length, so its allowlist and byte checks are insufficient for this tracker.

Buildathon Radar already has a server-rendered event page, parameterized sqlite3 store, stable event IDs, per-scan JSON history, transactional upserts, and a loaded hourly launchd agent. The new features extend those paths. The current store uses Python's sqlite3 directly, with schema versions and no SQLAlchemy dependency.

## Implemented behavior

- **Personal tracker** at `/tracker` with Interested, Registered, Submitted, Won and Not for me. The dashboard and event pages provide the same status control. Tracker and event detail pages expose editable notes after unlock. The tracker lists deadlines, recent activity and immutable history entries for additions, status changes and note updates. Its status, location, date and relevance filters run against tracked rows independently of discovery.
- **Individual listings** at `/h/{slug}`. A readable slug with a stable ID suffix is allocated once. Existing `/event/{id}` links still work and resolve to pages with canonical slug metadata. Pages include copy and native share controls, Open Graph fields, Event JSON-LD when dates and location support it, source lineage, scoring, eligibility evidence, exam overlaps, and timestamps. Unknown fields stay labelled unknown.
- **Source health** at `/sources`. Adapter reports distinguish OK, degraded and failed, with separate valid-empty and invalid outcomes. Filters, recent trends, per-scan historical detail, duration, pagination scope, valid and rejected records, and duplicate counts are available. These counts measure records handed from the adapter to the discovery engine. Rows filtered inside an adapter are outside those counts. Sources without an automated feed remain identified separately.
- **Discovery pipeline** normalizes source fields before validation and deduplication, then enriches them before eligibility evaluation, scoring and SQLite blackout checks. Enrichment keeps the original prize text and extracts an amount and currency where explicit. It adds themes and explicit restrictions without converting currencies or guessing missing fields. Every successful scan records source sightings and their retrieval timestamps, while the event retains the latest source metadata and first observation per reference.
- **Refresh and retention** use the existing hourly launchd agent. The interval is configurable through the installed plist. A SQLite-path-specific process lock covers both web and scheduled runs. A transaction commits scan history, health and event updates together. Partial valid batches can update existing data. Failed or valid-empty sources never erase previously retained events. The app links to failure details after a scan with failed sources.
- **Thumbnails** are fetched by stored event slug, from exact allowed CDN hostnames. Fetching rejects credentials, query strings, redirects, private IP addresses, invalid raster signatures and bodies over 1 MB. A public address is pinned for the connection while TLS checks the hostname. A bounded in-process cache and local PNG fallback keep the page usable after failed requests.

## Database migration and preservation

Migration 2 adds event slugs, explicit registration URL, country, image URL, prize amount and currency, participation fee, restrictions and last-observed fields. It creates `personal_tracker` and `tracker_activity` with foreign keys and indexes. The single local user is represented by an explicit user ID. Existing tracked, applied and rejected states are backfilled. Older observation timestamps are distinguished from independent verification. The prune operation preserves tracked events and their action logs.

The private pre-expansion online backup is at `~/.local/state/buildathon-radar/pre-feature-expansion-eqyeaf53/tracker.db`. It is the rollback point for the schema change. Restoring the backup also rolls back writes made after it, so export later changes before restoring if those records are needed.

After migration, SQLite integrity and foreign-key checks passed. All 177 baseline event IDs and all 46 then-current blackout rows were retained. The 46 rows cover 69 enabled dates and include the 29 original audit rules. Scan history, source records and profile configuration were preserved. The migration backfilled 20 personal tracker entries.

## Routes and authorization

| Route | Behavior |
|---|---|
| GET /tracker | Tracker and notes after local unlock |
| GET /settings | Local write unlock and refresh information |
| POST /api/session | Issue an eight-hour HttpOnly, SameSite Strict cookie |
| DELETE /api/session | Lock this browser |
| GET /api/tracker | Read personal tracker entries with an unlocked session |
| PUT /api/tracker/{event_id} | Save status or notes in one transaction |
| GET /h/{slug} | Render a retained event and its share metadata |
| GET /event-image/{slug} | Serve its cached thumbnail or a local placeholder |
| GET /api/refresh-status | Lightweight latest scan ID for dashboard polling |

Dashboard browsing remains available without login. Mutations require the signed session and the existing same-origin write header. The secret comes from the local `.env` and is never embedded in generated pages. Email remains disabled. The automation runs locally and does not require paid services.

## Verification and screenshots

The full suite passed with **444 tests**. Added tests cover v1 migration, status and note persistence, expiry and pruning, stable slugs and metadata, partial and empty scans, scanner locking, enrichment, access control, CORS, escaped notes, unsafe image destinations, redirects, content filtering, byte limits and cache hits.

A live scan completed through 11 configured adapters, retained 61 valid listings, and reported incomplete coverage and invalid source data independently. The launchd service remains loaded. Live requests confirmed dashboard, calendar, sources, settings, tracker, canonical event and thumbnail routes. Chromium exercised tracker save and reload, mobile tracker and event layouts at 390 px, and theme switching.

The tracker and event screenshots use demonstration data in a disposable database. The Sources screenshot uses the live local tracker.

- [Personal tracker](feature-expansion-assets/tracker.png)
- [Event page](feature-expansion-assets/event.png)
- [Event page on mobile](feature-expansion-assets/event-mobile.png)
- [Source health](feature-expansion-assets/sources.png)

## Remaining limitations

- Source pagination coverage remains bounded. First-page-only adapters are reported as degraded when they return listings. Some public sources do not expose pagination metadata. Public search leads and unsupported feeds are still excluded from automated event totals.
- Feed observations and conservative enrichment do not constitute independent organizer verification. The app leaves that timestamp unknown if no such verification exists. It does not attempt automated eligibility confirmation from ambiguous source text.
- Canonical URLs use the loopback origin. Copy and native sharing work on the device, while external preview crawlers and other devices cannot fetch localhost content.
- Thumbnail support covers the existing allowlisted public CDNs only. Unavailable images, unapproved hosts and signed links use the placeholder. The cache is per process and does not persist across restarts.
- The write session is for one local owner. There is no cross-device sync or per-user account management.
