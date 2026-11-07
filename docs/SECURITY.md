# Security, authorization and public demo isolation

## Role model

FrontDesk AI has one privileged role: **admin**. There is no invented reviewer, staff, customer or owner account for which a one-click button could be needed. Visitor chat is intentionally unauthenticated but has narrower ownership controls.

Production sign-in stores `user`, `role=admin` and compatibility flags in a **signed** SessionMiddleware cookie. Every router in the `routes/admin/` package declares `dependencies=[Depends(require_admin)]`; every state-changing handler also declares `Depends(require_admin)` explicitly. The guard rejects absent, invalid, production/demo-crossed cookies with a 303 redirect to admin login. Public `GET /` is a landing page; `GET /chat` is not an admin surface.

## Route map

| Method/path | Guard and behavior |
|---|---|
| `GET /`, `/chat`, `/static/*`, `/health` | Intended public retrieval. `/health` contains liveness/version/demo_status, no key. |
| `POST /chat` | Public visitor conversation creation. Rate limited, input capped 2000, session-bound ownership, 403 for foreign/guessed IDs. Demo: local isolated guide only. |
| `GET/POST /admin/login` | CSRF-protected production credential login; ordinary rate limit by direct client IP. Demo login page presents the separate button instead; ordinary credential login is 403 in demo mode. |
| `POST /admin/demo-login` | CSRF, rate limit, `DEMO_MODE` required (404 otherwise). Server issues sole admin role and a fresh isolated demo scope. |
| `GET/POST /admin/setup` | Existing setup disable rule + private SETUP_TOKEN and CSRF; entirely blocked in demo. Min 8-character strong password. |
| `GET /admin/*` | `require_admin`; all pages require role-signed session. |
| `POST /admin/settings`, `/admin/change-password` | `require_admin` + CSRF. Demo always 403. Production validates hours, holiday dates and password policy. |
| `POST /admin/knowledge`, `/{item_id}/edit`, `/{item_id}/delete` | `require_admin` + CSRF. Demo requires session ownership. Other/seeder records cannot be modified. Empty input rejected. |
| `POST /admin/appointments/{id}/status` | `require_admin` + CSRF; allowed values exactly confirmed/completed/cancelled. Demo DB is isolated fictional data. |
| `POST /admin/conversations/{id}/delete` | `require_admin` + CSRF and cascade delete. Demo must have created this thread through the signed admin-demo scope. |
| `GET /admin/logout` | Clears only that signed browser session. |

## Protection properties preserved from v1.0.3

- bcrypt hash/verify only; legacy plaintext DB values are refused rather than promoted.
- Login and chat limits use `request.client.host` (not arbitrary forwarded headers). Properly restrict `--forwarded-allow-ips` to your proxy for non-Render deployments.
- Per-session random `visitor_token` checks bind conversation to cookie. A supplied chat ID cannot switch to another visitor's stored history.
- Secret/placeholder key refuses startup outside `FRONTDESK_TESTING=1`; tests use temp files only.
- API keys configured in production settings are Fernet-encrypted using a `SECRET_KEY`-derived key. Existing key is never rendered in the form, and blank edit preserves it.
- `SETUP_TOKEN` is never the admin password; setup is unavailable once an account exists or env credential bootstrap is used.
- Local static UI assets eliminate runtime CDN dependencies. `[X-Content-Type-Options, X-Frame-Options, Referrer-Policy, Permissions-Policy]` are set. The bundled developer Tailwind build is used; do not widen browser execution allowances unintentionally.

## Demo boundary (mandatory read before enabling)

`DEMO_MODE` is opt-in and defaults false. It must be **true only on a dedicated public demonstration service** with no production secrets and a fresh `SECRET_KEY`. A separate cookie name and a secret combined with a fixed demo namespace prevent signed cookies being replayed across production/demo salts.

The demo overwrites process startup's DSN and provider configuration before the first engine is constructed. It therefore cannot open production `DATABASE_URL` via ordinary app routes and cannot read the configured production `ADMIN_*`/`AI_*`. No production credentials are evaluated through the demo button and the ordinary login endpoint is blocked.

Each signed random scope maps to an opaque file under `data/demo-<sanitized-seed>/`. Before use, demo tables are created and local fictional fixtures are seeded only once; knowledge presence avoids repeated inserts. Direct browser input never selects the engine path. Reviewer A's FAQs/messages/bookings are not in Reviewer B's database, not merely filtered in the UI. No real production tenant feature is implied.

### Demo edits, not universal delete power

Possible demo changes are deliberately narrow:
- change a fictional appointment into any defined workflow status with CSRF;
- add an FAQ, edit/deactivate it, or delete only when that same signed session owns the creation record;
- start a visitor chat in its own public sandbox;
- delete a conversation only when this admin-demo scope received ownership from chat creation.

Every endpoint checks membership and object existence. Client-provided `role`, `item_id`, `conversation_id`, or path cannot grant additional objects. Seed FAQ changes and another reviewer's addition/delete return **403**. Account password/username, business hours, integration values and key storage mutations are blocked **even with a valid admin demo session and CSRF token**.

No external AI client is constructed in demo mode. Chat responds with deterministic local FAQ and booking logic. The app accepts a documented example-style structured booking request. That local rule engine is not represented as full external generative-AI capability; normal production may still require the operator's configured provider for arbitrary natural-language conversations.

### Capacity, reset and data‑retention compromises

- One uvicorn worker should run SQLite. In-memory scope registry default cap is 200 known demo sessions (`DEMO_MAX_SESSIONS`, clamp 1–1000); existing scope reuse is allowed, new creation beyond cap is refused. It is **not** a distributed/global quota.
- Per-session databases **are not automatically purged** and may outlive the user cookie. Public operator must provide external scheduled reset/cleanup and disk quotas for expiry and abuse mitigation. Users cannot start a privileged system reset.
- Free Render filesystem is ephemeral; restarting/redeploying can reset sandbox files. This is acceptable for a disposable review, not for production.
- Demo session cookies are short-lived (12 hours) but can include a list of small ids/descriptions (not secrets). Cookie size may grow during use; re-login starts a fresh scope. Do not place untrusted secrets in the session.
The package runs no external jobs, emails, SMS, payments or deployments.

## Proxy configuration

For nginx/systemd bound on loopback, use `--proxy-headers --forwarded-allow-ips=127.0.0.1`. Restrict any non-loopback range to motivated proxy CIDRs. The supplied Docker CMD does not add `--proxy-headers` or trust an arbitrary `*`. Follow the hosting platform's documented trusted-proxy configuration; do not expose an origin directly while trusting forwarded headers from everyone. The example nginx deployment restricts its trusted proxy to loopback.


## v1.0.6 hardening

- **Secret key:** `app/config.py: enforce_secret_key` rejects blank, placeholder or <32-character `SECRET_KEY` at startup in production *and* demo mode. The only bypass is `FRONTDESK_TESTING=1` (tests), which is ignored when `RENDER` is set.
- **Demo isolation:** `enforce_demo_isolation` stops startup when `DEMO_MODE=true` coexists with a non-demo `DATABASE_URL`, admin bootstrap credentials, `SETUP_TOKEN` or AI provider credentials. It runs before any engine is created and has no bypass.
- **Setup:** `require_setup_token` uses `secrets.compare_digest`; `POST /admin/setup` is throttled per client IP (`SETUP_MAX_ATTEMPTS`=5 per `SETUP_WINDOW_SEC`=900) before the token is compared.
- **Search:** admin `?q=` filters use SQLAlchemy `ilike(..., escape="\\")` with `%`/`_` escaped; values are bound parameters.
- **Edits/deletes:** load exactly one row with `db.get(Model, pk)`; in demo mode the row must be in the signed session's ownership allowlist (`app/demo_session.py`).
- **Database:** `PRAGMA foreign_keys=ON` on every new SQLite connection; `database/schema.sql` is tested for parity with the SQLAlchemy models.
- **Client IP:** rate limits key on the direct peer (`request.client.host`). Behind Render's proxy Uvicorn's default `--forwarded-allow-ips` (127.0.0.1) applies; see HowToSetup for proxy-header notes.


## v1.0.7 CSRF expired-form handling

Diagnosis and behaviour: see CHANGELOG 1.0.7. Tokens are per session (signed cookie `frontdesk_session` / `frontdesk_demo_session`) and rotate on sign-in. Keep `SECRET_KEY` unchanged across deploys (Render `generateValue` keeps the existing value); changing it invalidates every open session and form, which then shows the "expired" message once.
