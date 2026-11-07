# Vibe96 audit-warning resolution — FrontDesk AI v1.0.6

Audit received for v1.0.5: **Passed with warnings, 82/100 overall, 84 security, no failing checks.**
This document maps every warning to the v1.0.6 change (file / function) and the test that proves it.
"Stale" means the v1.0.5 code already satisfied the request; v1.0.6 adds tests/docs so the auditor can verify it.

Test files: app suite `FrontDesk Project/tests/` (new: `test_audit_v106.py`), deployment suite `tests/`.
Run everything from the archive root: `python -m pytest -q` (requires `pip install -r "FrontDesk Project/requirements-dev.txt" -r tests/requirements.txt`).

## Security and secrets

| # | Warning | Status | Resolution (file / function) | Evidence (test) |
|---|---|---|---|---|
| 1 | Placeholder `SECRET_KEY` in root `.env.example` | **Fixed** | `.env.example`: `SECRET_KEY=` blank + comment `python -c "import secrets; print(secrets.token_urlsafe(48))"`. `app/config.py`: default `secret_key = ""`; `enforce_secret_key()` rejects blank, known placeholders and keys < 32 chars in **all** modes incl. demo. Only bypass: `FRONTDESK_TESTING=1`, ignored when Render's `RENDER` variable is present. | `test_env_examples_have_blank_secret_and_generation_comment`, `test_insecure_secret_key_refused_at_startup_in_all_modes` (8 real-startup cases), `test_strong_secret_key_starts`, `test_testing_bypass_is_ignored_on_render`, `test_placeholder_secret_key_refused` |
| 2 | Same placeholder in `FrontDesk Project/.env.example` | **Fixed** | Same blank template. Two **byte-identical** copies are kept on purpose: root copy is for Docker Compose (`cp .env.example .env` at root); nested copy sits next to `main.py` because a local run reads `.env` from its working directory. Neither contains a secret. | same test asserts both are blank and identical; `tests/test_deployment_root.py::verify_archive` |
| 3 | `/admin/demo-login` gives admin with no credentials | **Fixed (hardened)** | One-click demo is the intended reviewer feature, so it stays — but `app/config.py: enforce_demo_isolation()` (called from `app/__init__.py` **before any engine is created**, never bypassed) now **refuses to start** when `DEMO_MODE=true` coexists with a non-demo `DATABASE_URL`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `SETUP_TOKEN`, `AI_BASE_URL` or `AI_API_KEY`. v1.0.5 silently ignored them. Allowed demo DSN: blank, or `sqlite:///./data/demo-<seed>/<name>.db`. Demo login also still requires CSRF, is rate-limited and capped by `DEMO_MAX_SESSIONS`. | `test_demo_mode_refuses_production_configuration` (7 cases, also asserts no DB file is created), `test_demo_mode_starts_with_dedicated_sandbox_only`, existing `test_demo_mode.py` (10 tests) |
| 4 | `/admin/setup` token compare + rate limiting | compare: **stale** (already `secrets.compare_digest` in `app/security.py: require_setup_token`); rate limit: **Fixed** | `app/security.py: rate_limit_setup()` (per client IP, `SETUP_MAX_ATTEMPTS`=5 per `SETUP_WINDOW_SEC`=900) called in `routes/auth.py: do_setup` before the token compare; CSRF verified first. | `test_setup_token_compare_is_constant_time`, `test_setup_post_is_rate_limited` (5×403 then 429), `test_setup_requires_token` |
| 5 | `?q=` search, knowledge update/delete unverified | search: **stale** (ORM `ilike`, bound params) — **improved**; delete: **Fixed/hardened** | `app/web.py: like_term()` escapes `%`, `_`, `\` and all searches use `ilike(term, escape=LIKE_ESCAPE)` (bound parameter). Edits/deletes in `routes/admin/knowledge.py`, `conversations.py`, `appointments.py` load one row with `db.get(Model, pk)`; demo ownership via `app/demo_session.py: demo_blocks_mutation()`; all require `require_admin` + `verify_csrf`. Each demo reviewer also has a private SQLite sandbox. | `test_search_is_bound_and_wildcards_escaped`, `test_mutations_load_single_row_by_primary_key`, `test_demo_can_manage_own_rows_not_seed_or_other_reviewers`, `test_mutating_routes_require_auth_or_are_allowlisted` |
| 6 | `database/schema.sql` FK/index/cascade vs models; FK pragma | FK pragma: **stale** (already in `app/database.py: _create_engine` connect listener); schema: **Fixed** (`id ... NOT NULL PRIMARY KEY` to match SQLAlchemy exactly) | Schema now identical to `Base.metadata` for columns, NOT NULL, defaults, FKs with `ON DELETE CASCADE` (messages) / `SET NULL` (appointments) and every index. | `test_schema_sql_matches_sqlalchemy_models` (builds both DBs and compares PRAGMA table_info / foreign_key_list / index_list), `test_foreign_keys_enabled_on_every_connection`, `test_cascade_delete_messages` |

## Dependencies

| # | Warning | Status | Resolution | Evidence |
|---|---|---|---|---|
| 7 | fastapi / pydantic / sqlalchemy old | **Fixed** | Checked with live `pip index versions` (2026-11-07): fastapi 0.162.0 = latest (kept), pydantic 2.11.4 → **2.14.3**, sqlalchemy 2.0.40 → **2.0.57** (latest 2.0.x; 2.1 is a new minor line, not adopted without a migration review), pydantic-settings → 2.16.2, uvicorn → 0.54.0, python-dotenv → 1.2.4. Hash lock regenerated: `uv pip compile requirements.txt --generate-hashes --universal --python-version 3.12`. bcrypt kept at 4.3.0 (5.0 changes >72-byte password behaviour). | full test suite on the new lock |
| 8 | python-multipart / cryptography "unusual" versions | **Verified / bumped** | python-multipart 0.0.31 → **0.0.33** (latest); cryptography 50.0.2 = latest; jinja2 3.1.6 = latest. `pip-audit -r requirements.txt` and `pip-audit --require-hashes -r requirements.lock`: **No known vulnerabilities found**. | release evidence logs (pip-audit output) |

## Structure and code quality

| # | Warning | Status | Resolution | Evidence |
|---|---|---|---|---|
| 9 | Duplicate trees (app, Dockerfile, requirements, `.env.example`) | app/requirements: **stale** (v1.0.5 had no root `main.py`/`app/`/requirements); Dockerfile: **Fixed** | Exactly **one** runtime source tree (`FrontDesk Project/`) and **one** `Dockerfile` + `.dockerignore` + `.gitignore` at root. Removed `FrontDesk Project/Dockerfile`, `.dockerignore`, `.gitignore`. `.env.example` intentionally kept in both places (see #2). | `test_single_runtime_tree_and_single_dockerfile`, `verify_archive` (exactly one `Dockerfile`, one `main.py`) |
| 10 | Oversized `routes/admin.py` | **Fixed** | Split into `routes/admin/` package: `dashboard.py`, `knowledge.py`, `settings.py`, `appointments.py`, `conversations.py`; each router has `dependencies=[Depends(require_admin)]`. | `test_single_template_context_builder_and_split_admin_router`, `test_admin_router_declares_require_admin_dependency` |
| 11 | Demo helpers in the controller | **Fixed** | Moved to `app/demo_session.py` (`demo_writes`, `demo_created`, `demo_can_mutate`, `demo_blocks_mutation`, `is_demo_session`). | same test |
| 12 | `_tpl()` duplicated in admin and auth | **Fixed** | Single `app/web.py: render()` used by auth and admin routes. | same test |
| 13 | Hard-coded `max_length=2000` in `routes/public.py` | **Fixed** | `Form(..., max_length=settings.chat_message_max_length)`. | `test_chat_max_length_reads_settings`, `test_chat_security.py` length test |

## Setup and build

| # | Warning | Status | Resolution | Evidence |
|---|---|---|---|---|
| 14 | `tests/` referenced but missing | **Stale** (v1.0.5 ZIP shipped both test folders) | Both shipped again: `tests/` (root deployment) and `FrontDesk Project/tests/` (app). | `verify_archive` requires both; `test_docs_state_prerequisites_and_compose_order` |
| 15 | Python 3.12.x / SQLite 3.35+ undocumented | **Fixed** | `HowToSetup.md` "Requirements (prerequisites)" and `README.md` "Requirements". | `test_docs_state_prerequisites_and_compose_order` |
| 16 | Compose env file order | **Fixed** | `HowToSetup.md` section D and `docker-compose.yml` header: 1) `cp .env.example .env` at archive root, 2) set `SECRET_KEY` (+ `SETUP_TOKEN`), 3) `docker compose up --build`. Compose `DATABASE_URL` default is now blank. | `test_docs_state_prerequisites_and_compose_order`, `test_compose_root_and_environment_interpolation` |

## Not verifiable locally

- A real `docker build` / `docker compose up` and a Render deploy were **not** run (no Docker engine on the build machine). The tests instead reproduce the image layout (root Dockerfile COPY semantics) and start the exact Dockerfile CMD (`uvicorn main:app`) over real HTTP.
- Final scoring is Vibe96's decision.
