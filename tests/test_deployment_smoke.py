"""Exact Linux Docker Uvicorn CMD over real HTTP, local temporary layout only."""
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

import pytest

ROOT = Path(__file__).resolve().parents[1]


def flatten(dest: Path):
    dest.mkdir(parents=True)
    shutil.copytree(
        ROOT / "FrontDesk Project", dest, dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("*.db", "__pycache__", "venv", "tests"),
    )
    assert (dest / "main.py").exists()
    assert not (dest / "FrontDesk Project").exists()


def flatten_from(context: Path, dest: Path):
    dest.mkdir(parents=True)
    shutil.copytree(context, dest, dirs_exist_ok=True)
    assert (dest / "main.py").exists()
    assert (dest / "app" / "__init__.py").exists()
    assert (dest / "templates" / "landing.html").exists()
    assert not (dest / "FrontDesk Project").exists()


def select_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.mark.parametrize("use_default_port", [True, False], ids=["default-10000", "alternate-port"])
def test_exact_docker_cmd_real_http_smoke(tmp_path, use_default_port):
    image = tmp_path / ("app-10000" if use_default_port else "app-alternate")
    flatten(image)
    with socket.socket() as sock:
        default_free = sock.connect_ex(("127.0.0.1", 10000)) != 0
    if use_default_port and not default_free:
        pytest.skip("Local port 10000 is occupied; alternate-port smoke still runs")
    port = 10000 if use_default_port else select_port()
    env = os.environ.copy()
    env.pop("PORT", None)
    env.pop("FRONTDESK_TESTING", None)
    if not use_default_port:
        env["PORT"] = str(port)
    env.update(
        HTTPS_ONLY="false", DEMO_MODE="false",
        SECRET_KEY=secrets.token_urlsafe(48),
        DATABASE_URL=f"sqlite:///{tmp_path / 'temp.db'}",
        PYTHONDONTWRITEBYTECODE="1",
        PATH=f"{Path(sys.executable).parent}{os.pathsep}/usr/bin:/bin",
    )
    command = "uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000}"
    proc = subprocess.Popen(
        ["sh", "-c", command], cwd=image, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            if proc.poll() is not None:
                raise AssertionError(f"Image CMD exited without test bypass: {proc.stdout.read()}")
            try:
                with urlopen(base + "/health", timeout=0.3) as response:
                    assert json.loads(response.read()) == {
                        "status": "ok", "version": "1.0.8", "demo_mode": False,
                    }
                break
            except URLError:
                time.sleep(0.05)
        else:
            raise AssertionError(f"Flattened app failed exact Docker CMD on port {port}")
        for path in ("/", "/admin/login", "/static/app.css", "/static/admin-demo-dashboard.png"):
            with urlopen(base + path, timeout=3) as response:
                assert response.status == 200
                assert response.read()
        assert not (image / "FrontDesk Project").exists()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        if proc.returncode not in (0, -15):
            print(proc.stdout.read())
