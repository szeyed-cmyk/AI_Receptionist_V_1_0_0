# GitHub → Render root-first guide

This guide is an **instruction for your local/repository preparation**, not a deployment already performed with this package. No repository contents are changed by extracting the ZIP and no Render instance is included.

## Upload the unpacked contents, not the ZIP

1. Extract the supplied v1.0.8 ZIP to a new empty directory. The ZIP contains its files at its root; an outer folder named `FrontDesk_AI`, `FrontDesk Project` or `ai-receptionist` must **not** appear above the package root.
2. Open that extracted directory (the one directly containing `Dockerfile`, `render.yaml`, `README.md`, `.env.example`, `docker-compose.yml`, and `FrontDesk Project/`) and upload **its complete contents** into your GitHub repository root.
3. Do not upload the ZIP itself or a directory enclosing the above root. Do not copy `FrontDesk Project/requirements.lock` into the repository root. v1.0.6 has a single root `Dockerfile`; if your repository still contains `FrontDesk Project/Dockerfile`, `FrontDesk Project/.dockerignore` or `FrontDesk Project/routes/admin.py` from v1.0.5, delete them. Those files already have correct relative roles under the nested app directory; keep them where provided.
4. If updating a repository with manually added root `requirements.lock` or another older root Dockerfile/render.yaml, replace or remove those **conflicting deployment files in your own repository update** so only this root-first `Dockerfile` and `render.yaml` are used. Root `requirements.lock` is intentionally absent. Inspect your own existing data, secrets and version-control changes first; do not delete local/production database data.
5. Do not upload `.env`, private keys, DB files, `.git`, `venv`, `.venv`, caches or demo sandbox files. Root `.gitignore` protects these by default; root `.dockerignore` protects the image build context. Both `.env.example` files intentionally remain.

After uploading, the top of your GitHub repository should resemble:

```text
Dockerfile                           # root-first primary container entry
.dockerignore
.gitignore
render.yaml                          # one canonical Render Blueprint
README.md
HowToSetup.md
GITHUB-RENDER.md
CLAUDE.md
CHANGELOG.md
LICENSE-NOTE.md
.env.example                         # placeholders, no real secret
docker-compose.yml
database/
  schema.sql
  seed.sql
docs/
FrontDesk Project/                 # all application code/source/assets/templates/tests
```

That directory has its own `.env.example`, `requirements.lock` and tests (no Dockerfile — the single Dockerfile is at the root). Python runtime source must remain in that single directory at the archive/repo root. Do not flatten `main.py`, `app/`, `templates/`, or `static/` into the archive root. `FrontDesk Project/render.yaml` intentionally does not exist: the root Blueprint is canonical.

### Checklist against the existing upload

- Top-level `main.py` **must not be required** by this package; `main.py` is nested before build and copied to `/app/main.py` by the root Dockerfile.
- Top-level `requirements.lock` is **not needed**; root `Dockerfile` uses `COPY ["FrontDesk Project/requirements.lock", "/app/requirements.lock"]` above `COPY ["FrontDesk Project/", "/app/"]`.
- Do not choose an automatic Python runtime expecting root `main.py` or root `requirements.lock`. Choose the **Docker** runtime described below.

## Exact Render settings

For a new or existing web service linked to the repository:

| Setting | Exact value |
|---|---|
| Runtime / Language | **Docker** |
| Root Directory | **blank** (repository root) |
| Dockerfile Path | **./Dockerfile** |
| Build / Docker Context | **.** (repository root) |
| Docker Command | **blank** (use root Dockerfile CMD) |
| Native Build Command | **blank / not applicable for Docker** |
| Start Command override | **blank / not applicable** |
| Health Check Path | **/health** |
| Number of instances | **1** for SQLite and the demo's per-worker cap |

The root `render.yaml` explicitly records the same root paths (`rootDir: .`, `dockerfilePath: ./Dockerfile`, `dockerContext: .`) and health check. No `startCommand` or `buildCommand` is supplied: its root Dockerfile handles both. Inside the image, `/app` contains `main.py`, `app/`, `routes/`, `static/`, `templates/`, `requirements.lock`, and a runtime-created `data/`; it does **not** need `/app/FrontDesk Project/`. `/app/requirements.lock` is installed before application contents are copied. `CMD` uses `${PORT:-10000}` so Render's port selection is respected.

Alternatively use Render's Blueprint-from-GitHub flow and specify the root `render.yaml` filename in the creation form. You do not need to select a nested project root. Create a separate clean demo service if using the public one-click workflow.

### Deployment-time environment configuration

**Default:** the Blueprint has `DEMO_MODE=false` for normal production. `SECRET_KEY` uses Render's supported `generateValue: true`: if not already set, Render generates a randomized base64-encoded 256-bit value; later syncs preserve an existing value. This value is generated by Render during Blueprint creation when the variable is new, **not** packaged in the repository.

Other sensitive variables use `sync: false`; Render prompts for them during the **initial** Blueprint creation. On subsequent Blueprint syncs, `sync: false` variables are ignored, so add any missing ones manually through the Environment settings. A manually created Docker service uses nothing automatic from the Blueprint: generate your private `SECRET_KEY` yourself in Render Environment and configure the values below directly.

Production minimum:

```text
SECRET_KEY = fresh private random value (Blueprint generates it)
DEMO_MODE = false
HTTPS_ONLY = true
```

Choose `SETUP_TOKEN` for browser setup, or private `ADMIN_USERNAME`/`ADMIN_PASSWORD` bootstrap. Avoid reusing public demo or personal credentials. Set `DEMO_MODE=true` **only on a new dedicated clean review service**, where each signed browser session receives isolated fictional data. Use `DEMO_SEED=review-v1`, `DEMO_MAX_SESSIONS=200`, `HTTPS_ONLY=true`, fresh `SECRET_KEY`, and **leave these absent/unset** in a public review service:

```text
ADMIN_USERNAME
ADMIN_PASSWORD
SETUP_TOKEN
AI_BASE_URL
AI_API_KEY
AI_MODEL
DATABASE_URL  # For this clean demo, leave unset; no real production DSN or private path is used.
```

Do not turn on demo mode on a service containing real customer data, production secrets or a real AI credential, even though the app discards production settings before creating the demo engine. The Blueprint comments describe normal-production tradeoffs, not an invitation to expose any real secrets.

**Do not upload `.env` to GitHub.** Render reads configured environment settings, not the template `.env.example`. Both root and nested `.env.example` files have identical placeholder content and should be kept synchronized if edited later.

### Storage, health and verification

SQLite defaults to `sqlite:///./data/ai_receptionist.db` under `/app/data`. Production data requires a purposefully configured persistent disk (mount `/app/data` if using SQLite) or separately managed persistent DB configuration; free ephemeral demo data can be reset on redeploy/restart. This package does not provision or resize a disk and does not migrate production data.

Use `https://<your-service>.onrender.com/` as the marketplace demo root only after your separate review service has been checked and validated. `/admin/login` hosts the opt-in one-click demo; `/chat` is visitor chat; `/health` should report version `1.0.5`. Validate the built service yourself in Render before public submission. One-click demo sandboxes remain per signed session under `data/demo-<seed>/` and are disposable. They do not automatically purge; the worker's default cap is 200 scopes and one worker is required for that process-local cap. Arrange external cleanup if hosting the demo indefinitely.

## Local verification boundary

The release is checked using static YAML parsing, Docker/Moby ignore matching, flattened-image-equivalent imports and a real local Uvicorn HTTP subprocess. It does not include a deployed service, customer data or marketplace approval. If Docker is unavailable, actual base-image pull, Docker build and container startup are not implied by these filesystem tests; run `docker build -f Dockerfile .` in your own local/CI environment before rollout.


## v1.0.6 strict demo service environment

Set ONLY these on the separate public demo service (Render → Environment):

```text
SECRET_KEY = <Render generateValue, or python -c "import secrets; print(secrets.token_urlsafe(48))">
DEMO_MODE = true
DEMO_SEED = review-v1
DEMO_MAX_SESSIONS = 200
HTTPS_ONLY = true
```

`DATABASE_URL`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `SETUP_TOKEN`, `AI_BASE_URL` and `AI_API_KEY` must be absent or blank: the app now refuses to start if any is set together with `DEMO_MODE=true` (the deploy log shows `DEMO_MODE=true cannot start alongside production configuration: ...`). The Blueprint's `sync: false` prompts for those keys — leave them empty on the demo service.
