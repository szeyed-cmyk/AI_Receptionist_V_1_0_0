# CLAUDE.md

Guide for AI coding tools working on this codebase.

## Project

FrontDesk AI — self-hosted AI receptionist. Visitors chat, get answers from a knowledge base, and book 60-minute appointments. Admins manage knowledge, settings, conversations, and appointments.

## Stack

- Python 3.12+
- FastAPI + Uvicorn
- SQLAlchemy 2.0 + SQLite
- Jinja2 templates
- Starlette SessionMiddleware (signed admin session, role=`admin`)
- OpenAI-compatible AI providers (configured in Admin → Settings)
- bcrypt for password hashes; cryptography (Fernet) for AI key at rest

## Folder and deployment map

```text
Repository / archive root
├── Dockerfile                       # primary; sees nested requirements.lock
├── .dockerignore, .gitignore
├── render.yaml                      # canonical root Docker Blueprint
├── docker-compose.yml               # same root Docker context/file
├── README.md, HowToSetup.md, GITHUB-RENDER.md
├── CLAUDE.md, CHANGELOG.md, LICENSE-NOTE.md, .env.example
├── database/schema.sql, database/seed.sql
├── docs/                            # overview, SECURITY, demo, historical screenshots
├── tests/                           # root deployment regression tests
└── FrontDesk Project/               # all application source stays nested
    ├── main.py                      # ASGI entry, root image copies it to /app/main.py
    ├── requirements.lock            # sole lock
    ├── requirements.txt
    ├── requirements-dev.txt
    ├── .env.example
    ├── routes/{public,auth}.py, routes/admin/{dashboard,knowledge,settings,appointments,conversations}.py
    ├── app/{config,database,models,security,auth,web,demo_session,demo,demo_ai,...}.py
    ├── templates/, static/, tests/, data/
    └── runtime.txt
```

Primary root builder installs `FrontDesk Project/requirements.lock` then runs `COPY ["FrontDesk Project/", "/app/"]` with space-quoted source. Root Blueprint `dockerContext: .`, `dockerfilePath: ./Dockerfile`, `rootDir: .`. Start by Dockerfile CMD `uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000}`, not root `main.py`. There is exactly one Dockerfile and one `.dockerignore` (root). Nested root render.yaml intentionally absent; no contradictory native process model.

No actual `.env`, `requirements.lock` or `main.py` copy at package root; `app/`, `static/`, `templates/` are also not mirrored here. Do not flatten source to accommodate previous incorrect Docker image.

## Conventions

- Working directory for local initialisation/runtime and the original app-only test selection is `FrontDesk Project/`; aggregate app/root deployment tests run from archive root. Each mode has its documented private `.env` file.
- Start: `uvicorn main:app --host 0.0.0.0 --port 10000`
- AI Base URL / API Key / Model are stored in the `settings` table via Admin → Settings.
- Do not hardcode API keys or personal contact details.
- Default hours: Mon–Sat 09:00–18:00; closed Sunday; holidays configurable.
- Appointments are 60-minute slots; overlap and duplicate phone numbers are rejected.
- Admin auth is a signed session with `role=admin` — never a plain `admin=true` cookie.
- Public mutating allowlist includes `POST /chat` plus CSRF-guarded login/setup/demo login. Chat is session-bound + rate-limited. Setup needs SETUP_TOKEN. Setup is also rate-limited per client IP. Everything else that mutates data goes through the `routes/admin/` package (dashboard, knowledge, settings, appointments, conversations), each router guarded by `require_admin`.

## How to run tests

```bash
cd "FrontDesk Project"
python -m venv venv && source venv/bin/activate   # PowerShell: py -3.12 -m venv venv; .\venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m pytest -q
# For aggregate deployment + app coverage, instead activate the venv
# from archive root and run: python -m pytest -q
```

## Environment template synchronization

Keep root `.env.example` and `FrontDesk Project/.env.example` byte-for-byte identical (`cmp` from the ZIP root). Root `.env` is for Compose; project `.env` is local/VPS; Render uses Environment settings. `app/config.py` resolves relative `env_file=".env"` against the process working directory. See `HowToSetup.md` tree and Linux/PowerShell commands. Render Environment uses no `.env` commit. Primary Docker works from complete root upload, not copying nested Docker or lockfiles to Git root. Read root `GITHUB-RENDER.md` for exact settings.

## Do not

- Ship `.env` or `*.db` with real keys.
- Include `venv`, `__pycache__`, `.git`, `build`, or `dist` in the release ZIP.
- Put personal contact emails, phones, or developer names in the package.

## Version 1.0.4 additions

- Shared responsive `base.html`/`static/app.css`; Tailwind browser JS is a local MIT distribution in `static/vendor/` (no runtime CDN).
- Public `/` landing; visitor `/chat`; admin management pages use the same shell. Never restore a root alias to chat if you add routes.
- Database registry produces one production engine or scoped demo SQLite files. Demo settings are blanked before engine construction. Keep this ordering.
- `DEMO_MODE` defaults false and must never point to production data. One-click sign-in is CSRF-protected and generates the only existing role, admin, with an isolated synthetic sandbox.
- Demo knowledge/chat mutations are limited to per-signed-session ownership. `block_demo_sensitive_action` always prevents provider, hours, account and setup changes. Never introduce a generic demo admin credential or generic delete shortcut.
- Use only per-worker explicit demo login scope. Do not pass user filename paths or accept role parameters from the request.
- Existing documented images under `docs/screenshots/` are v1.0.3 examples, not new v1.0.4 admin UI screenshots. The current landing admin demo dashboard is `FrontDesk Project/static/admin-demo-dashboard.png`, a supplied browser-QA capture labelled as fictional demonstration data. Add future current screenshots only after visual browser verification of the new screens.

## Version 1.0.6 audit release

- `SECRET_KEY` blank in templates; startup refuses blank/placeholder/<32 chars in all modes (only `FRONTDESK_TESTING=1` bypasses, ignored when `RENDER` is set).
- `DEMO_MODE=true` refuses to start with non-demo `DATABASE_URL`, `ADMIN_*`, `SETUP_TOKEN`, `AI_BASE_URL`, `AI_API_KEY` (`app/config.py: enforce_demo_isolation`, never bypassed).
- Shared helpers: `app/web.py` (`render`, pagination, escaped LIKE search), `app/demo_session.py` (demo ownership allowlist). Do not reintroduce per-router `_tpl`.
- Tests: `FrontDesk Project/tests/` (app) and root `tests/` (deployment); see `docs/AUDIT-RESOLUTION-v1.0.6.md`.

## Version 1.0.5 root release changes

- Keep root deployment configuration primary. Do not resolve Render errors by adding a root Python source/lockfile copy or changing the Render context to the nested folder.
- Use `python -m pytest -q` from archive root to run both original application and root deployment tests. Temp-only secret and test settings are valid only under `FRONTDESK_TESTING=1`; retain production secret enforcement.
- Root Docker `COPY ["FrontDesk Project/", "/app/"]` must retain the trailing source slash and exact space. Nested `COPY . /app/` is not interchangeable with root context.
