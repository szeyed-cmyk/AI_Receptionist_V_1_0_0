# HowToSetup.md

Step-by-step install for v1.0.8. Application code remains in `FrontDesk Project/`; documentation, SQL and deployment configuration stay at the archive root. Read root-first `GITHUB-RENDER.md` when preparing GitHub or Render.

## Archive layout and environment files

The archive root holds deployment files and root documentation. **Python code, source templates, static assets and application tests remain inside the single `FrontDesk Project/` source directory.** It is shipped nested; only the Docker build puts its contents directly in `/app`.

```text
.
├── Dockerfile                       # primary root-first builder
├── .dockerignore
├── .gitignore
├── render.yaml                      # canonical root Docker Blueprint
├── docker-compose.yml               # root .env, root Docker context/file
├── .env.example                     # no private secret values
├── README.md
├── HowToSetup.md
├── GITHUB-RENDER.md
├── CLAUDE.md
├── CHANGELOG.md
├── LICENSE-NOTE.md
├── database/schema.sql
├── database/seed.sql
├── docs/
└── FrontDesk Project/
    ├── .env.example                 # byte-identical to root template
    ├── .env                         # create locally; never in the archive
    ├── main.py
    ├── requirements.lock            # sole lock, copied from nested path
    ├── app/, routes/, templates/, static/, tests/   # the ONLY runtime source tree
    └── data/                        # runtime-created local database path
```

### Working directory / configuration matrix

| Workflow | Working directory | Real private config |
|---|---|---|
| Local Python / Linux / Windows | `FrontDesk Project/` | Adjacent project `.env` |
| Ubuntu VPS/systemd | `/opt/frontdesk/FrontDesk Project` | `/opt/frontdesk/FrontDesk Project/.env` |
| Docker Compose | Complete archive root | Archive-root `.env` |
| GitHub → Render Docker | Repository root holding all extracted contents | Render Environment; no committed `.env` |

Local code loads `env_file=".env"` relative to its process working directory, not its source module and not an automatic parent-directory search. Run local application and initialization from `FrontDesk Project/` whose `main.py` is present. `cp ../.env.example .env` from that directory is equivalent to `cp .env.example .env`; both example copies are synchronized.

Compose is different: root `env_file: .env` and local interpolation (`${SECRET_KEY}`, `${PORT:-10000}`) both source archive-root `.env`. `${PORT:-10000}` controls the **host** port while `PORT=10000` is explicitly given to the container process. Its `context: .` / `dockerfile: Dockerfile` selects the single root Dockerfile (v1.0.6 removed the competing nested Dockerfile/.dockerignore). Compose reads root `.env`; a plain local run reads adjacent project `.env`. Do not assume either searches both locations or has secret values from the other workflow by default.

Render gets exactly the **entire archive root** at repository root; leave Root Directory blank and set Build Context `.`. A root `.env` is neither needed nor safe in GitHub. Blueprint or Environment settings provide runtime variables. `FrontDesk Project/render.yaml` is intentionally absent, so it cannot conflict with root-first Render discovery.

### Lockfile & two-image filesystem layout

The root Dockerfile first installs `COPY ["FrontDesk Project/requirements.lock", "/app/requirements.lock"]`; then the space-quoted nested **contents** go into `/app` with:

```dockerfile
COPY ["FrontDesk Project/", "/app/"]
```

The result has `/app/main.py`, `/app/app`, `/app/routes`, `/app/templates`, `/app/static`, and `/app/requirements.lock`; no `/app/FrontDesk Project` directory or root Python duplicates are needed. No archive root docs, root env, DB, `.git`, user venvs or unnecessary caches are brought into `/app`, because the builder copies only that nested folder after the context ignores private/environment/runtime files.

```bash
# The only Docker builder (Compose, Render and manual builds), with root .dockerignore:
docker build -f Dockerfile .
```

The container runs Uvicorn `main:app` on `${PORT:-10000}` in their Linux shell. Do not append project subdirectory to the primary `dockerContext` or change Root Directory for Render; that prevents correct sources from entering the image. Input contexts and resulting app placement are covered by regression tests.

Root `.dockerignore` excludes private `.env` under directories (except `.env.example` templates), keys/certificates, credentials, DB files/journals, sandbox data, Git metadata, virtual environments, caches/test outputs. Root `.gitignore` similarly prevents accidental Git tracking of private data. **Neither pattern rules replace keeping sensitive content outside a package or scanning a repository before disclosure.**

### Keep both examples synchronized

```bash
# Linux/macOS, archive root
cp .env.example "FrontDesk Project/.env.example"
cmp .env.example "FrontDesk Project/.env.example"
```

```powershell
# PowerShell, archive root
Copy-Item .env.example ".\FrontDesk Project\.env.example"
(Get-FileHash .env.example).Hash -eq (Get-FileHash ".\FrontDesk Project\.env.example").Hash  # True
```

DEMO_MODE remains `false` in the example. For any changed public variables change *the two examples together only with placeholders*, never a filled environment file.


## Requirements (prerequisites)

- **Python 3.12.x** (required; tested with 3.12 — the Docker image uses `python:3.12.7-slim`). Python 3.13+ is not the supported target.
- **SQLite 3.35 or newer** (the version bundled with Python's `sqlite3` module; check with `python -c "import sqlite3; print(sqlite3.sqlite_version)"`). Foreign keys are enabled on every connection by the app.
- pip (installs with `--require-hashes -r requirements.lock`)
- Optional: Docker + Docker Compose, nginx, systemd (VPS)
- Optional: `sqlite3` CLI if you want to load `database/seed.sql` by hand

---

## A. Local install (Linux / macOS) — ordered steps

1. Unzip the archive and enter the project folder:

```bash
cd "FrontDesk Project"
```

2. Create a virtual environment:

```bash
python3.12 -m venv venv  #Windows py -m venv venv
source venv/bin/activate
```

3. Check that `requirements.lock` exists in this directory, then install its pinned dependencies:

```bash
python -m pip install --require-hashes -r requirements.lock
# python comes from the activated venv. Use pip only if you prefer:
# pip install --require-hashes -r requirements.lock
```

If a locked package is unavailable on your platform, troubleshoot the interpreter/platform first rather than silently skipping hash verification. Do not replace pinned security-sensitive versions without testing.

4. Create the private local environment file from the adjacent application template while your working directory is `FrontDesk Project`:

```bash
cp .env.example .env   # windows copy .env.example .env
```

This creates `FrontDesk Project/.env`; the ZIP must contain only `.env.example`, not a filled `.env`. `cp ../.env.example .env` is also correct because both copies are identical. `../.env.example` is **not** loaded automatically by a local app run here.

5. Edit `.env` and set required secrets:

```bash
# Generate SECRET_KEY:
python -c "import secrets; print(secrets.token_urlsafe(48))"
# Generate SETUP_TOKEN:
python -c "import secrets; print(secrets.token_urlsafe(24))"
```

Put both values into `.env`. Optionally set `ADMIN_USERNAME` / `ADMIN_PASSWORD` to skip the setup form (when set, `/admin/setup` is disabled). Set `HTTPS_ONLY=true` behind HTTPS.

6. Create the data directory and initialize the database:

```bash
mkdir -p data
python -m app.init_db
```

Optional demo data (fictional clinic):

```bash
sqlite3 data/ai_receptionist.db < ../database/schema.sql
sqlite3 data/ai_receptionist.db < ../database/seed.sql
```

(The app also creates tables automatically on first start.)

7. Start the server from this `FrontDesk Project` directory:

```bash
python -m uvicorn main:app --host 0.0.0.0 --port 10000
# alternatively: python main.py (uses PORT if supplied)
```

Leave the activated venv and working directory unchanged; do not `cd` to the ZIP root before starting locally.

Behind a reverse proxy, add trusted forwarded headers:

```bash
uvicorn main:app --host 0.0.0.0 --port 10000 \
  --proxy-headers --forwarded-allow-ips='127.0.0.1'
```

8. Open http://localhost:10000

---

## B. Windows PowerShell local install (`py`)

Run **PowerShell**, not Command Prompt. These commands require Python launcher (`py`) 3.12+ and use a project-local venv named `venv`.

1. From the unpacked **archive root**, enter the application folder:

```powershell
py -0p
Set-Location ".\FrontDesk Project"
```

`py -0p` lists installed Python versions/paths. Ensure one is 3.12+ as required. Confirm `Test-Path .env.example`, `Test-Path requirements.lock`, and `Test-Path main.py` each return `$true`; this prevents creating `.env` in the wrong directory.

2. Create and activate the virtual environment:

```powershell
py -3.12 -m venv venv
.\venv\Scripts\Activate.ps1
```

Do not use `source` or Command Prompt's `activate.bat` in PowerShell. `py` creates the requested Python 3.12 venv; after activation, `python` explicitly selects that venv for installation and runtime, so dependencies do not land in the system interpreter. In each new PowerShell session, activate the same `venv` again before running the app.

3. Install dependencies, create `.env`, and generate placeholders for your private values:

```powershell
python -m pip install --require-hashes -r requirements.lock
Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"  # paste as SECRET_KEY
python -c "import secrets; print(secrets.token_urlsafe(24))"  # paste as SETUP_TOKEN
```

This is `FrontDesk Project\.env`, not `..\.env` (the latter is for Compose only). The neighboring `.env.example` was already copied from the ZIP root template and must have the same content. `Copy-Item ..\.env.example .env` is equivalent. After copying, edit `.env` in your preferred editor—for example, `notepad .env`—and paste the generated values. Leave `ADMIN_*` blank to use browser setup, or use explicit private admin bootstrap instead. Set `HTTPS_ONLY=true` only behind HTTPS.

4. Initialize and run using the activated venv:

```powershell
python -c "import sys; assert sys.version_info >= (3, 12)"
New-Item -ItemType Directory -Force data | Out-Null
python -m app.init_db
python -m uvicorn main:app --host 0.0.0.0 --port 10000
```

The `data` folder is created only on your machine; no DB is packaged. Open `http://localhost:10000`; the visitor chat is `/chat` and admin login is `/admin/login`.

Optional PowerShell **local** review settings use separate demo-only data. Keep real admin/AI/bootstrap credentials blank and review `../docs/DEMONSTRATION.md` first:

```powershell
# Optional: from FrontDesk Project for a dedicated local review only.
$env:DEMO_MODE = "true"
$env:DEMO_SEED = "local-review"
$env:HTTPS_ONLY = "false"
# Set a fresh development SECRET_KEY, e.g. a generated value:
$env:SECRET_KEY = python -c "import secrets; print(secrets.token_urlsafe(48))"
python -m uvicorn main:app --host 0.0.0.0 --port 10000
```

These values apply to this PowerShell session only, not to a committed `.env`. Real admin/setup/AI credentials and a real database are not used. Clear the overrides (`Remove-Item Env:DEMO_MODE` and likewise for `DEMO_SEED`, `HTTPS_ONLY`, `SECRET_KEY`) before switching back to ordinary local configuration in that session. Never expose `DEMO_MODE=true` on production data.

## C. First admin login / demo account

### Option 1 — browser setup (requires SETUP_TOKEN)

1. Visit http://localhost:10000/admin/setup
2. Enter username, password (min 8 characters; avoid weak passwords), and the `SETUP_TOKEN` from `.env`.
3. You are redirected to the dashboard.

### Option 2 — environment bootstrap

Set `ADMIN_USERNAME` and `ADMIN_PASSWORD` in `FrontDesk Project/.env` before starting a local/VPS installation, or in archive-root `.env` for supplied Compose. `/admin/setup` is disabled. Log in at `/admin/login`; the password is hashed into the database on first successful login.

### Dedicated public review demo (Vibe96 / Render)

The app contains exactly one role: **admin**. v1.0.6 can issue that role only in the isolated, explicitly enabled sandbox. Do not create public-facing credentials on a production instance.

For a **separate demo-only Render service** (recommended), deploy the complete extracted package root exactly as described in section F and set the following names in **Render → Environment**, not in a committed or uploaded `.env`:

```
SECRET_KEY=<generate-a-fresh-random-value>
DEMO_MODE=true
DEMO_SEED=review-v1
DEMO_MAX_SESSIONS=200
HTTPS_ONLY=true
```

Leave `DATABASE_URL`, `ADMIN_*`, `SETUP_TOKEN` and `AI_*` unset for that public demo. **v1.0.6 enforces this: with `DEMO_MODE=true` the app refuses to start** if any of `DATABASE_URL` (other than a `sqlite:///./data/demo-<seed>/<name>.db` sandbox path), `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `SETUP_TOKEN`, `AI_BASE_URL` or `AI_API_KEY` is set, and it also refuses a blank, placeholder or short `SECRET_KEY`. For a local demo, rename any private `FrontDesk Project/.env` that contains those values first (environment variables set to an empty string in PowerShell are removed, so the `.env` value would be read). Production DSN/AI provider/admin credentials are never used; no AI provider or setup token is required for viewing the sandbox. Use the landing-page root (`https://<service>.onrender.com/`) as the live-demo URL. The Live Demo button opens `/admin/login`, which includes **Enter Admin demo**. Each signed review session starts with independent fictional data and may explore status and own-FAQ/chat changes. The server forbids production login and sensitive settings, keys, setup or account changes in this deployment. `/chat` is the visitor experience.

If you edit an existing Render service already holding customer data or a real AI key, **do not turn on demo mode there**. Deploy a fresh demo service without those secrets instead. For production leave `DEMO_MODE=false`, retain private `ADMIN_USERNAME`/`ADMIN_PASSWORD` or `SETUP_TOKEN`, and mount persistent storage for the chosen SQLite `DATABASE_URL`. Do not copy demo DB files over production.

Demo note: SQLite per-session sandboxes are intentionally disposable. They are not automatically deleted; the worker knows up to `DEMO_MAX_SESSIONS` (default 200) scopes. Single-worker deployment is mandatory for the per-worker cap; extra external disk cleanup is required for a long-running service. Render free's ephemeral filesystem may reset at restart/redeploy. Read `docs/DEMONSTRATION.md` for isolation, capacity and workflow tradeoffs.

### Private password-protected deployment (not the public one-click demo)

1. Deploy with `SECRET_KEY`, `SETUP_TOKEN` (or `ADMIN_USERNAME`/`ADMIN_PASSWORD`), and `HTTPS_ONLY=true`.
2. Optional private `ADMIN_*` bootstrap (avoid reusing real credentials):

```
ADMIN_USERNAME=demo
ADMIN_PASSWORD=<choose-a-strong-demo-password>
```

3. With `DEMO_MODE=false`, confirm `/admin/login` accepts those credentials and the dashboard loads.
4. If you choose that separate private deployment path, provide your newly chosen private review credentials only through the appropriate marketplace review-credentials field. This does not replace or weaken the recommended isolated one-click demo; never reuse personal or production credentials.
5. In **Settings**, add your own AI Base URL / API Key / Model, business name, hours.
6. Add FAQs under **Knowledge**.

Change the password later under **Admin → Settings → Change Admin Password**.

---

## D. Docker Compose (root context and root `.env`)

Compose builds the same single root Dockerfile as Render. Do not copy `requirements.lock` or any app file to the repository root. Run these steps **in this order, at the archive root**:

```bash
# 1. Linux/macOS, extracted archive root: create the private env file
cp .env.example .env
# 2. Edit .env and set (generate each value with the command below):
#      SECRET_KEY=<paste generated value>      (required, >= 32 chars)
#      SETUP_TOKEN=<paste another generated value>  (for first-run /admin/setup)
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
# 3. Build and start
docker compose up --build
```

```powershell
# 1. Windows PowerShell, extracted archive root
Copy-Item .env.example .env
# 2. Generate values and paste them into .env as SECRET_KEY= and SETUP_TOKEN=
py -3.12 -c "import secrets; print(secrets.token_urlsafe(48))"
notepad .env
# 3. Build and start
docker compose up --build
```

If `SECRET_KEY` is missing Compose stops with `Set SECRET_KEY in .env - see .env.example`; if it is a placeholder or shorter than 32 characters the app itself refuses to start.

The app opens at `http://localhost:10000` with default settings. If root `.env` says `PORT=8080`, the host listens on 8080, mapping still goes to internal 10000. Only host-external port changes from the mapping; no source change is necessary.

- Source: root `context: .`, `dockerfile: Dockerfile`; root `.dockerignore` applies.
- Database is bind-mounted at `/app/data` ↔ `./FrontDesk Project/data`; keep actual DBs out of tracked source and image contexts.
- Use ordinary private root `.env` only for local Compose; never treat the root `.env.example` as a filled file or upload private `.env` to GitHub.
- `docker compose --env-file .env config` is a local validation/inspection command. Actual image/network startup/testing depends on available Docker, and static tests alone are not a BuildKit run.
- Manual image run (archive root): `docker build -t frontdesk-ai .` then `docker run --env-file .env -p 10000:10000 frontdesk-ai`. Public demo data only disposable details must align with `docs/DEMONSTRATION.md`.

---

## E. Ubuntu VPS (venv + systemd + nginx)

Assumes Ubuntu 22.04+, a non-root user with sudo, and a domain pointed at the server.

### 1. System packages

```bash
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3-pip nginx sqlite3
```

### 2. App files

```bash
sudo mkdir -p /opt/frontdesk
sudo chown "$USER":"$USER" /opt/frontdesk
# copy the unzipped archive into /opt/frontdesk so that
# /opt/frontdesk/FrontDesk Project/ and /opt/frontdesk/database/ exist
cd "/opt/frontdesk/FrontDesk Project"
python3.12 -m venv venv
source venv/bin/activate
pip install --require-hashes -r requirements.lock
cp .env.example .env
# equivalent: cp ../.env.example .env
# edit .env: SECRET_KEY, SETUP_TOKEN, HTTPS_ONLY=true, optional ADMIN_*
mkdir -p data
python -m app.init_db
```

### 3. systemd unit

Create `/etc/systemd/system/frontdesk.service`:

```ini
[Unit]
Description=FrontDesk AI
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/frontdesk/FrontDesk Project
EnvironmentFile=/opt/frontdesk/FrontDesk Project/.env
ExecStart=/opt/frontdesk/FrontDesk Project/venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips=127.0.0.1
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo chown -R www-data:www-data /opt/frontdesk
sudo systemctl daemon-reload
sudo systemctl enable --now frontdesk
```

### 4. nginx reverse proxy

Create `/etc/nginx/sites-available/frontdesk`:

```nginx
server {
    listen 80;
    server_name your.domain.example;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/frontdesk /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
# then obtain TLS (example): sudo apt install certbot python3-certbot-nginx && sudo certbot --nginx
```

Set `HTTPS_ONLY=true` in `.env` after TLS is active, then `sudo systemctl restart frontdesk`.

---

## F. GitHub → Render hosting

Follow **`GITHUB-RENDER.md`** for complete instructions, exact repository root shape, conflict cleanup by you, notes on the previously copied root lockfile, and how correct Docker COPY sources avoid `uvicorn main:app` import failure.

| Render setting | Exact value |
|---|---|
| Runtime / Language | **Docker** |
| Root Directory | **blank** (repository root) |
| Dockerfile Path | **./Dockerfile** |
| Build / Docker Context | **.** (repository root) |
| Docker Command | **blank** — root Dockerfile CMD |
| Build Command | **blank / not applicable** for Docker |
| Start Command override | **blank / not applicable** |
| Health Check Path | **/health** |
| Instances | **1** while SQLite is used / for demo cap |

The canonical root `render.yaml` sets rootDir `.`, Dockerfile path `./Dockerfile`, context `.`, Docker runtime, single worker and liveness check. It omits native build/start overrides. Repository application stays nested; inside the image `/app/main.py` is valid. Production defaults are explicit `DEMO_MODE=false`, `HTTPS_ONLY=true`.

`SECRET_KEY generateValue: true` supported by Render Blueprint generates a random base64-encoded 256-bit value **when a variable does not already exist**. Later Blueprint syncs preserve existing secrets. `sync: false` variables prompt at first creation, but new entries on later syncs are ignored; manual Docker service configuration requires input through Render Environment instead. Generate a new fresh secret manually outside Blueprint if needed. Nothing secret is committed with this package.

To provision one-click admin review correctly use a **separate, dedicated, clean review service** with:

```text
SECRET_KEY = freshly generated by Render or manually generated securely
DEMO_MODE = true
DEMO_SEED = review-v1
DEMO_MAX_SESSIONS = 200
HTTPS_ONLY = true
```

Leave `ADMIN_*`, `SETUP_TOKEN`, `AI_*` and any unneeded providers blank/unset. Keep production authentication/CSRF/hash config and customer secrets out of it. From v1.0.6 a demo service that still has a production `DATABASE_URL`, admin, setup or AI credential **fails at startup** instead of silently ignoring them; remove those variables from the demo service.

Render can preserve data with a paid persistent disk mounted at `/app/data`, or use an owner-managed persistent DB when configured. This archive does not create disk, credential or database resources. Sandbox SQLite/session files are not automatically deleted; per-worker cap max/default 200 assigned seed `review-v1`. `numInstances=1` avoids implying distributed scope quota. Free demo filesystem resets are expected; other periods require owner external cleanup scheduling.

Before using root `https://<your-service>.onrender.com/` as your separate review URL, verify your own real deployment and app pages. This guide never claims an action outside local source modifications.

---

## G. Branding changes

| What | Where |
|------|--------|
| Business name | Admin → Settings, or `BUSINESS_NAME` in `.env` |
| Avatar image | Replace `FrontDesk Project/static/avatar.jpg` |
| Chat / admin colors and layout | Edit Jinja templates under `FrontDesk Project/templates/` (Tailwind utility classes) |
| Page title | `templates/chat.html`, `templates/admin.html`, etc. |
| Default hours / holidays | Admin → Settings (`opening_hour`, `closing_hour`, `closed_days`, `holiday_dates`) |
| FAQs the AI uses | Admin → Knowledge |

---

## H. Booking rules (buyers)

- Hours and closed weekdays are configurable (defaults: Mon–Sat 09:00–18:00, closed Sunday).
- Holiday dates (`YYYY-MM-DD` list) are rejected by the booking tool.
- Overlapping 60-minute slots are rejected.
- Duplicate phone: one confirmed appointment per phone number.
- Dates: weekday is computed from the real calendar date in `BUSINESS_TIMEZONE`. Accepted: `10th November at 5pm`, `November 10 2pm`, `2026-11-10 17:00`, `day after tomorrow at 5pm`, `next Monday 10am`. Ambiguous (`10/11`), missing date/time, past or conflicting weekday inputs get a clarification question instead of a guess.

## J. Example AI providers

| Provider | AI Base URL | Example Model |
|----------|-----------------------------|-------------------------|
| Groq | https://api.groq.com/openai/v1 | `openai/gpt-oss-20b` |
| OpenAI | https://api.openai.com/v1 | `gpt-4o-mini` |
| OpenRouter | https://openrouter.ai/api/v1 | `google/gemini-flash-1.5` |
| Together AI | https://api.together.xyz/v1 | Various open models |
| Local (Ollama) | http://localhost:11434/v1 | `llama3.2` |

## K. Production notes

- Generate and set `SECRET_KEY` before going live. The app **refuses to start** with the placeholder.
- Set `SETUP_TOKEN` (or use `ADMIN_PASSWORD` bootstrap) before exposing the site.
- Use a reverse proxy and HTTPS; set `HTTPS_ONLY=true`.
- Do not commit or share your real `.env`, API keys, or `*.db` files.
- Admin auth uses a signed session cookie (`frontdesk_session`) with `role=admin`. A plain `admin=true` cookie is rejected.
- AI API keys are encrypted at rest (Fernet derived from `SECRET_KEY`).
- See [docs/SECURITY.md](docs/SECURITY.md) for the full route/guard table.


## L0. Upgrade v1.0.5 → v1.0.6 (existing service)

1. Back up production `.env` and `data/` first. Upload all extracted v1.0.6 root contents to the repository root and **delete** `FrontDesk Project/Dockerfile`, `FrontDesk Project/.dockerignore`, `FrontDesk Project/.gitignore` and `FrontDesk Project/routes/admin.py` from GitHub (replaced by the root Dockerfile/ignore files and the `routes/admin/` package).
2. Render settings are unchanged (Root Directory blank, `./Dockerfile`, context `.`, Docker Command blank, `/health`).
3. Production: make sure `SECRET_KEY` is at least 32 characters (Render `generateValue` already is).
4. Demo service: remove `DATABASE_URL`, `ADMIN_*`, `SETUP_TOKEN`, `AI_BASE_URL`, `AI_API_KEY` from its Environment, otherwise it will refuse to start.
5. Dependencies were re-locked (patch/minor updates); reinstall with `pip install --require-hashes -r requirements.lock` for local runs.

## L. Upgrade v1.0.4 → v1.0.5 (existing service)

1. Back up your production `.env`, configured database and SQLite `data/` files before replacing anything. Test restore separately. This ZIP intentionally contains no live database or private environment.
2. On GitHub upload **all extracted v1.0.5 root contents** to repository root. Replace this release's root `Dockerfile`, `render.yaml`, Compose file and ignore files as needed; remove obsolete manually duplicated root `requirements.lock` and conflicting stale deployment files after reviewing them. Keep production runtime data private and outside that upload.
3. For a manual Render service use Runtime Docker, Root Directory blank, Dockerfile Path `./Dockerfile`, Build Context `.`, Docker Command blank and Health Path `/health`. Do not switch back to the nested Python service or copy the old Dockerfile to the root.
4. For local/VPS upgrades always run from `FrontDesk Project/`, retain its private `.env`, install from the unchanged `requirements.lock`, preserve `SECRET_KEY` for existing sessions and keep `DEMO_MODE=false` for production. Do not overwrite live data files with examples.
5. Test imports, `/health`, login, admin forms, booking and storage on staging before changing a public deployment. Dependencies and runtime functionality have no intended behavior change beyond version identification. Root Docker copies the same nested source into `/app`; it does not require root `main.py`.
6. For a public reviewer use a separate clean service with the opt-in demo values from section C/F. Do not reconfigure production as demo. SQLite requires one process/worker here; enable persistent storage or an owner-managed database for production, and external cleanup for long-running demos.

## M. Render troubleshooting

- **`No module named main` / `uvicorn main:app` failure:** confirm you uploaded every ZIP-root item, not the ZIP or an extra outer directory. Delete only the obsolete manually duplicated root lockfile after review; do not copy the nested app to root. Use `./Dockerfile` and context `.` so `/app/main.py` is built from `FrontDesk Project/main.py`.

- **Root is chat or 404:** verify the v1.0.5 `FrontDesk Project` content and verify `routes/public.py` contains both landing `/` and chat `/chat`. Clear any platform cache only through standard deployment mechanisms.
- **No one-click demo button:** explicitly set `DEMO_MODE=true` on the *dedicated clean review* service and restart. This behaviour is intentionally absent in production.
- **Login redirects to setup:** production DB has no admin hash. Configure `SETUP_TOKEN` or use private `ADMIN_*`; this does not apply to demo mode.
- **App seeded but another reviewer's chat is missing:** intended isolation. Each signed review session has an independent fictional store.
- **AI replies are deterministic:** intended in demo mode to avoid costs and secret exposure. Production uses your own provider settings with the API key encrypted at rest.
- **Dedicated demo on nested-only service:** do not use a nested-only GitHub repository with this root-first package. Deploy full package root so the root Dockerfile correctly produces `/app/main.py`; opt into demo only in the separate clean environment described in section F.
- **Client IP / proxy handling:** the image CMD runs `uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000}`. Its `${PORT}` is expanded by the Linux shell, matching Render-supplied ports. The app reads `request.client.host` for rate limiting. If operating behind a trusted reverse proxy, configure Uvicorn forwarded behavior only at the proxy boundary you trust; the VPS example allows only `127.0.0.1`. Consult Render’s current documentation before changing their trusted-proxy defaults. Do not blindly trust forwarded headers from arbitrary clients.
- **Free filesystem disappears:** demo data is disposable. Use persistent storage for production; do not rely on Render free SQLite persistence.
- **Both examples drifted:** copy either `.env.example` over the other and run the comparison commands in the initial layout section. Never merge a filled `.env` into an example.
- **Local `.env` is not found / placeholder SECRET_KEY is rejected:** run `pwd` / `Get-Location` first. From `FrontDesk Project`, confirm `Test-Path main.py`, `Test-Path .env`, then restart. The dotenv path is resolved against the invocation working directory, not the ZIP-root Compose `.env`. Activating venv does not itself change directory.
- **Render needs secrets:** fill Render Environment settings rather than committing/uploading `.env`. The dedicated demo discards configured production DSN/admin/bootstrap/AI values before engine creation but still requires a fresh secret and clean isolated deployment.
- **Archive contains old screenshots:** `docs/screenshots/` are intentionally marked as v1.0.3 product examples for documentation. The landing page uses the actual new admin demo-dashboard screenshot plus a retained visitor-workflow example. The outdated pricing/duration showcase has been removed.
