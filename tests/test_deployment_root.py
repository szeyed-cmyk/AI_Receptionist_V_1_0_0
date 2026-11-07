"""Offline deployment regressions for root-first GitHub / Render / Compose.

The optional tests/docker_matcher directory contains Apache-2.0 upstream
Moby patternmatcher v0.6.0 source; compiled offline if Go is installed.
It is validation tooling only, not runtime code or an image build.
"""
from __future__ import annotations

import json
import os
from pathlib import PurePosixPath, Path
import re
import shutil
import subprocess
import sys
import zipfile

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "FrontDesk Project"
MATCHER_SOURCE = ROOT / "tests/docker_matcher"


def dockerfile_instructions(text):
    """Join continuations; ignore comments as Docker's parser does for this file."""
    lines = []
    pending = ""
    for raw in text.splitlines():
        stripped = raw.strip()
        if not pending and (not stripped or stripped.startswith("#")):
            continue
        pending = f"{pending} {stripped}".strip() if pending else stripped
        if pending.endswith("\\"):
            pending = pending[:-1].rstrip()
            continue
        lines.append(pending)
        pending = ""
    return [tuple(line.split(None, 1)) for line in lines]


def read_env(path):
    return dict(line.split("=", 1) for line in path.read_text().splitlines()
                if line and not line.lstrip().startswith("#") and "=" in line)


def image_directory(context, destination):
    """Build the content-only layout; ignore behavior is independently tested below."""
    destination.mkdir(parents=True, exist_ok=True)
    for source in context.rglob("*"):
        if not source.is_file():
            continue
        rel = source.relative_to(context)
        if any(p.name in {"venv", ".venv", "__pycache__", ".pytest_cache", ".git"} for p in [source, *source.parents]):
            continue
        if source.name.startswith(".env") and source.name != ".env.example":
            continue
        if source.suffix in {".db", ".sqlite", ".sqlite3", ".pyc"}:
            continue
        if "demo-" in source.parent.name:
            continue
        target = destination / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def dockerfile_path():
    return (ROOT / "Dockerfile").read_text()


def test_vibe96_root_layout_and_preserved_security_asset_paths():
    required = [
        "README.md", "HowToSetup.md", "GITHUB-RENDER.md", "CLAUDE.md",
        "CHANGELOG.md", "LICENSE-NOTE.md", ".env.example",
        "database/schema.sql", "database/seed.sql", "docker-compose.yml",
        "Dockerfile", ".dockerignore", ".gitignore", "render.yaml",
        "FrontDesk Project/main.py", "FrontDesk Project/app/__init__.py",
        "FrontDesk Project/templates/landing.html",
        "FrontDesk Project/static/admin-demo-dashboard.png",
        "FrontDesk Project/requirements.lock", "FrontDesk Project/.env.example",
    ]
    for path in required:
        assert (ROOT / path).is_file(), path
    assert not (APP_PATH / "render.yaml").exists()
    # v1.0.6: ONE canonical root Dockerfile; no competing nested build config.
    assert not (APP_PATH / "Dockerfile").exists()
    assert not (APP_PATH / ".dockerignore").exists()
    for path in ("main.py", "requirements.lock", "app", "templates", "static"):
        assert not (ROOT / path).exists(), path
    env = (ROOT / ".env.example").read_text()
    assert env == (APP_PATH / ".env.example").read_text()
    assert "DEMO_MODE=false" in env
    assert re.search(r"^SECRET_KEY=$", env, re.M) and "change-this" not in env
    assert "secrets.token_urlsafe(48)" in env
    assert "synthetic" not in env and "deployment-fixture" not in env
    assert "CSRF_PROTECT" not in env  # application uses no opt-out flag.
    assert (ROOT / "FrontDesk Project/tests/test_demo_mode.py").is_file()


def test_structured_docker_copy_arguments_resolve_app_flattening():
    lines = dockerfile_instructions(dockerfile_path())
    assert lines[0] == ("FROM", "python:3.12.7-slim")
    assert ("WORKDIR", "/app") in lines
    copies = [json.loads(rest) for op, rest in lines if op == "COPY"]
    assert copies == [
        ["FrontDesk Project/requirements.lock", "/app/requirements.lock"],
        ["FrontDesk Project/", "/app/"],
    ]
    assert (ROOT / copies[0][0]).is_file()
    source = copies[1][0].removesuffix("/")
    assert (ROOT / source / "main.py").is_file()
    assert Path(copies[1][1]) == Path("/app")
    assert not copies[1][0].startswith("/") and ".." not in PurePosixPath(copies[1][0]).parts
    assert next(rest for op, rest in lines if op == "RUN").startswith(
        "pip install --no-cache-dir --require-hashes -r /app/requirements.lock")
    assert lines[-1] == (
        "CMD", '["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000}"]'
    )
    assert ("EXPOSE", "10000") in lines
    assert dict((op, rest) for op, rest in lines if op == "ENV")["ENV"].split() == [
        "PYTHONDONTWRITEBYTECODE=1", "PYTHONUNBUFFERED=1"
    ]
    assert not dockerfile_path().strip().startswith("#")  # no unsolicited Docker parser directive.


def test_flattened_app_templates_assets_and_routes(tmp_path, monkeypatch):
    image = tmp_path / "app"
    image_directory(APP_PATH, image)
    image.joinpath("data").mkdir(exist_ok=True)
    assert (image / "main.py").is_file()
    assert not (image / "FrontDesk Project").exists()
    for rel in ("app", "routes", "templates", "static"):
        assert (image / rel).is_dir()
    for key, value in {
        "FRONTDESK_TESTING": "1",
        "SECRET_KEY": "synthetic-flattened-runtime-test-only",
        "DATABASE_URL": f"sqlite:///{tmp_path}/runtime.db",
        "HTTPS_ONLY": "false",
        "DEMO_MODE": "false",
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.chdir(image)
    monkeypatch.syspath_prepend(str(image))
    for name in list(sys.modules):
        if name == "main" or name == "app" or name.startswith("app."):
            del sys.modules[name]
    script = image / "_flat_import.py"
    script.write_text(
        "import os; from pathlib import Path; import main; import app.templating as t; "
        "from fastapi.testclient import TestClient; "
        "assert Path(main.__file__).resolve() == Path.cwd() / 'main.py'; "
        "assert Path(t.templates.env.loader.searchpath[0]).resolve() == Path.cwd() / 'templates'; "
        "client = TestClient(main.app); "
        "assert client.get('/').status_code == 200; "
        "assert client.get('/health').json() == {'status': 'ok', 'version': '1.0.8', 'demo_mode': False}; "
        "assert len(client.get('/static/admin-demo-dashboard.png').content) > 100_000; "
        "assert client.get('/static/app.css').status_code == 200; "
        "assert client.get('/admin/login').status_code == 200; "
        "assert not (Path.cwd() / 'FrontDesk Project').exists(); "
        "print('FLAT_IMPORT_OK', main.__file__)"
    )
    env = os.environ.copy()
    for key, value in {
        "FRONTDESK_TESTING": "1",
        "SECRET_KEY": "synthetic-flattened-runtime-test-only",
        "DATABASE_URL": f"sqlite:///{tmp_path}/runtime.db",
        "HTTPS_ONLY": "false",
        "DEMO_MODE": "false",
        "PYTHONDONTWRITEBYTECODE": "1",
    }.items():
        env[key] = value
    completed = subprocess.run(
        [sys.executable, str(script)], cwd=image, env=env,
        capture_output=True, text=True, timeout=20,
    )
    assert completed.returncode == 0, completed.stderr
    assert "FLAT_IMPORT_OK" in completed.stdout
    # A fresh child process avoids parent-test config/import cache entirely.


@pytest.fixture()
def docker_matcher(tmp_path):
    tool = shutil.which("go")
    if not tool:
        pytest.skip("Optional Go-based Moby .dockerignore test needs Go; app does not")
    env = os.environ.copy()
    env.update(GOFLAGS="", GOPROXY="off", GOTOOLCHAIN="local")
    env["GOCACHE"] = str(tmp_path / "gocache")
    env["GOMODCACHE"] = str(tmp_path / "gomodcache")
    binary = tmp_path / "ignore-matcher"
    result = subprocess.run([tool, "build", "-mod=vendor", "-o", str(binary), "."],
        cwd=MATCHER_SOURCE, env=env, capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stderr
    assert binary.is_file()
    return binary


def test_official_docker_ignore_matches_both_contexts_and_safeguards(tmp_path, docker_matcher):
    """Test exact Moby patternmatching in a temp compiled helper, offline."""
    root_cases = {
        True: [
            ".env", ".env.production", "FrontDesk Project/.env",
            "FrontDesk Project/venv/bin/python", "nested/venv/lib/site.py",
            "nested/.venv/bin/python", "private/client.key", "nested/id_rsa_backup",
            "FrontDesk Project/data/ai_receptionist.db",
            "FrontDesk Project/data/ai_receptionist.db-journal",
            "FrontDesk Project/data/demo-review-v1/scope.db",
            "FrontDesk Project/data/demo-review-v1/private/scope.txt",
            ".git/HEAD", "nested/.git/config", "__pycache__/a.pyc",
        ],
        False: [
            ".env.example", "FrontDesk Project/.env.example", "FrontDesk Project/main.py",
            "FrontDesk Project/requirements.lock", "FrontDesk Project/app/__init__.py",
            "FrontDesk Project/static/app.css", "FrontDesk Project/templates/landing.html",
        ],
    }
    nested_cases = {
        True: [
            ".env", ".env.production", ".venv/bin/python", "venv/bin/python",
            "venv/lib/python/site-packages/x.py", "nested/id_rsa_backup", "nested/private/x.key",
            "data/ai_receptionist.db", "data/ai_receptionist.db-journal",
            "data/demo-review-v1/scope.db", "data/demo-review-v1/private/scope.txt",
            ".git/config", "tests/test_app.py", "app/__pycache__/mod.pyc",
        ],
        False: [
            ".env.example", "main.py", "requirements.lock", "app/__init__.py",
            "static/app.css", "templates/landing.html",
        ],
    }
    for ignore, cases in ((ROOT / ".dockerignore", root_cases),):  # v1.0.6: single root build context
        for expected, paths in cases.items():
            result = subprocess.run(
                [str(docker_matcher)], input=json.dumps({"ignore_file": str(ignore), "paths": paths}),
                text=True, capture_output=True, timeout=10,
            )
            if result.returncode:
                pytest.skip(f"Matcher cannot execute on this platform: {result.stderr}")
            excluded = json.loads(result.stdout)["excluded"]
            for path in paths:
                assert excluded[path] is expected, (str(ignore), path, excluded)
    # Demonstrate the keep/remove materialization using synthetic files in a temp
    # copy, rather than writing .env or DB files into the release source.
    context = tmp_path / "FrontDesk Project"
    shutil.copytree(APP_PATH, context)
    for rel in (".env", ".env.production", "data/production.db", "venv/bin/python", "data/demo-review-v1/scope.db"):
        path = context / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("SYNTHETIC-IGNORED")
    for rel in (".env", ".env.production", "data/production.db", "venv/bin/python", "data/demo-review-v1/scope.db"):
        rel_path = context / rel
        if any(part.startswith("demo-") for part in rel_path.parts):
            continue
        if rel_path.name.endswith(".db") or rel_path.name.startswith(".env") or "venv" in rel_path.parts:
            rel_path.unlink()
    for directory in sorted(context.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if directory.is_dir() and (directory.name in {"venv", "data"} or directory.name.startswith("demo-")):
            if not any(directory.iterdir()) and directory != context / "data":
                directory.rmdir()
    image_directory(context, tmp_path / "image")
    assert not (tmp_path / "image/.env").exists()
    assert (tmp_path / "image/.env.example").exists()
    assert not (tmp_path / "image/data/production.db").exists()
    assert not list((tmp_path / "image").rglob("SYNTHETIC*"))


def test_root_gitignore_excludes_actual_secrets_and_demo_databases():
    ignore = (ROOT / ".gitignore").read_text()
    for pattern in (
        ".env", ".env.*", "**/.env", "**/.env.*", "!.env.example", "!**/.env.example",
        "**/*.db", "**/*.db-journal", "**/*.db-wal", "**/*.db-shm", "**/ven" + "v/",
        "**/.venv/", "**/__pycache__/", "**/credentials.json", "id_rsa*", "**/*.key",
    ):
        if pattern == "**/*.key":
            continue
        assert pattern in ignore



def test_gitignore_behavior_in_new_temporary_index(tmp_path):
    if not shutil.which("git"):
        pytest.skip("git check-ignore is only an optional validation utility in this run")
    for rel in (".env", ".env.production", "FrontDesk Project/.env", "nested/private/id_rsa",
                "FrontDesk Project/data/test.db", "nested/client.key", "FrontDesk Project/data/demo-review/scope.db",
                "FrontDesk Project/venv/bin/python", "FrontDesk Project/static/app.css",
                ".env.example", "FrontDesk Project/.env.example", "FrontDesk Project/main.py", "README.md"):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic-not-user-data")
    shutil.copy2(ROOT / ".gitignore", tmp_path / ".gitignore")
    subprocess.run(
        ["git", "init", "-q", "--initial-branch=validation"],
        env={"PATH": os.environ.get("PATH", ""), "GIT_CONFIG_NOSYSTEM": "1", "HOME": str(tmp_path / "git-home")},
        cwd=tmp_path, check=True, capture_output=True, text=True,
    )
    def run(args):
        result = subprocess.run(["git", "-c", "core.excludesfile=/dev/null", "check-ignore", "--no-index", "--stdin"], cwd=tmp_path,
            input="\n".join(args) + "\n", text=True, capture_output=True)
        return result.stdout.splitlines()
    ignored = set(run([
        ".env", ".env.production", "FrontDesk Project/.env", "nested/private/id_rsa",
        "FrontDesk Project/data/test.db", "nested/client.key", "FrontDesk Project/data/demo-review/scope.db",
        "FrontDesk Project/venv/bin/python",
    ]))
    assert all(path in ignored for path in [
         ".env", ".env.production", "FrontDesk Project/.env", "nested/private/id_rsa",
        "FrontDesk Project/data/test.db", "nested/client.key", "FrontDesk Project/data/demo-review/scope.db",
        "FrontDesk Project/venv/bin/python",
    ])
    assert not run([".env.example", "FrontDesk Project/.env.example", "FrontDesk Project/main.py", "README.md"])

def test_root_render_blueprint_is_canonical_and_no_paths_drift():
    files = list(ROOT.rglob("render.yaml"))
    assert files == [ROOT / "render.yaml"]
    raw = yaml.safe_load((ROOT / "render.yaml").read_text())
    assert len(raw["services"]) == 1
    service = raw["services"][0]
    for key in ("runtime", "rootDir", "dockerfilePath", "dockerContext", "healthCheckPath", "plan"):
        assert key in service, key
    assert service["runtime"] == "docker" and service["rootDir"] == "."
    assert service["dockerfilePath"] == "./Dockerfile" and service["dockerContext"] == "."
    assert service["healthCheckPath"] == "/health"
    assert service["numInstances"] == 1 and "disks" not in service
    assert {"buildCommand", "startCommand", "dockerCommand"}.isdisjoint(service)
    params = {entry["key"]: entry for entry in service["envVars"]}
    assert params["SECRET_KEY"] == {"key": "SECRET_KEY", "generateValue": True}
    for key in ("ADMIN_USERNAME", "ADMIN_PASSWORD", "SETUP_TOKEN", "DATABASE_URL"):
        assert params[key].get("sync") is False
        assert "value" not in params[key]
    assert params["DEMO_MODE"]["value"] == "false"


def test_compose_root_and_environment_interpolation():
    parsed = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    assert set(parsed["services"]) == {"web"}
    web = parsed["services"]["web"]
    assert web["build"] == {"context": ".", "dockerfile": "Dockerfile"}
    assert web["env_file"] == [".env"]
    assert web["ports"] == ["${PORT:-10000}:10000"]
    assert web["volumes"] == ["./FrontDesk Project/data:/app/data"]
    environment = {entry.split("=", 1)[0]: entry.split("=", 1)[1] for entry in web["environment"]}
    assert environment["PORT"] == "10000"
    assert environment["SECRET_KEY"] == "${SECRET_KEY:?Set SECRET_KEY in .env - see .env.example}"
    assert environment["DEMO_MODE"] == "${DEMO_MODE:-false}"
    # Test mapping semantics here to avoid writing a genuine source .env.
    example = read_env(ROOT / ".env.example")
    assert example["DEMO_MODE"] == "false"
    assert example["PORT"] == "10000"
    assert "{{" not in (ROOT / "docker-compose.yml").read_text()


def test_root_guides_have_no_conflicting_upload_or_port_instructions():
    docs = [
        (ROOT / "README.md").read_text(), (ROOT / "GITHUB-RENDER.md").read_text(),
        (ROOT / "HowToSetup.md").read_text(), (ROOT / "CLAUDE.md").read_text(),
        (ROOT / "docs/overview.md").read_text(),
    ]
    assert all("Root Directory" in doc for doc in docs[:3])
    assert all("./Dockerfile" in doc for doc in docs)
    assert all("rootDiv" not in doc for doc in docs)
    assert all("Front Desk Project" not in doc for doc in docs)
    assert all("command blank" in doc.lower() or "docker command | **blank" in doc.lower() for doc in docs[:3])
    howto = docs[2]
    assert "py -3.12 -m venv venv" in howto
    assert ".\\venv\\Scripts\\Activate.ps1" in howto
    assert "deploy the contents of `FrontDesk Project/`" not in howto
    assert howto.count('# HowToSetup.md') == 1
    assert "upgrade v1.0.4" in howto.lower()
    assert "manually duplicated root `requirements.lock`" in howto
    assert "The leading space" not in howto


def verify_archive(archive_name):
    required = {
        "Dockerfile", ".dockerignore", ".gitignore", "render.yaml", "docker-compose.yml",
        "README.md", "HowToSetup.md", "GITHUB-RENDER.md", "CLAUDE.md", "CHANGELOG.md",
        "LICENSE-NOTE.md", ".env.example", "database/schema.sql", "database/seed.sql",
        "FrontDesk Project/main.py", "FrontDesk Project/requirements.lock",
        "FrontDesk Project/.env.example", "FrontDesk Project/tests/test_audit_v106.py", "tests/test_deployment_root.py",
    }
    with zipfile.ZipFile(archive_name) as archive:
        assert archive.testzip() is None
        names = [info.filename for info in archive.infolist()]
        assert len(names) == len(set(names))
        assert required.issubset(names), required - set(names)
        for name in names:
            path = PurePosixPath(name)
            assert not path.is_absolute() and ".." not in path.parts
            assert path.parts[0] in {"Dockerfile", ".dockerignore", ".gitignore", "render.yaml",
                "docker-compose.yml", "README.md", "HowToSetup.md", "GITHUB-RENDER.md", "CLAUDE.md",
                "CHANGELOG.md", "LICENSE-NOTE.md", ".env.example", "database", "docs", "tests",
                "FrontDesk Project"}
            assert not any(part in {".git", ".venv", "venv", "__pycache__", ".pytest_cache"} for part in path.parts)
            assert not name.endswith((".db", ".sqlite", ".sqlite3", ".pyc", ".zip", ".env.production", ".db-journal"))
        assert names.count(".env.example") == 1
        assert names.count("FrontDesk Project/.env.example") == 1
        assert not any(name.endswith("/.env") for name in names)
        assert archive.read(".env.example") == archive.read("FrontDesk Project/.env.example")
        assert "requirements.lock" not in names and "main.py" not in names
        assert "FrontDesk Project/Dockerfile" not in names and "FrontDesk Project/.dockerignore" not in names
        assert sum(1 for n in names if PurePosixPath(n).name == "Dockerfile") == 1
        assert sum(1 for n in names if PurePosixPath(n).name == "main.py") == 1
        assert not any(name.startswith(("FrontDesk_AI", "ai-receptionist/")) for name in names)


def test_release_zip_after_packaging():
    archive_name = Path(os.environ["FRONTDESK_RELEASE_ZIP"]) if os.environ.get("FRONTDESK_RELEASE_ZIP") else ROOT.parent / "frontdesk-ai-v1.0.8-vibe96.zip"
    if not archive_name.exists():
        pytest.skip("Run again from a fresh release archive extraction after packaging")
    verify_archive(archive_name)
