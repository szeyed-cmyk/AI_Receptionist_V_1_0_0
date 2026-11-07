"""Application settings loaded from environment / .env.

Startup safety (enforced by ``enforce_startup_config`` before any database
engine is created):

* ``SECRET_KEY`` must be set, must not be a known placeholder and must be at
  least 32 characters. This applies to production *and* demo mode. The only
  bypass is ``FRONTDESK_TESTING=1`` for the automated test-suite, and that
  bypass is ignored on Render (``RENDER`` is set by the platform).
* ``DEMO_MODE=true`` refuses to start if production configuration is also
  present: a non-demo ``DATABASE_URL``, ``ADMIN_USERNAME``/``ADMIN_PASSWORD``,
  ``SETUP_TOKEN`` or AI provider credentials. Demo data may only live under the
  dedicated sandbox path ``sqlite:///./data/demo-<seed>/...``.
"""
from __future__ import annotations

import os
import re
import sys
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_DATABASE_URL = "sqlite:///./data/ai_receptionist.db"
# The only DSN shape accepted together with DEMO_MODE=true.
DEMO_DATABASE_PREFIX = "sqlite:///./data/demo-"
MIN_SECRET_KEY_LENGTH = 32

PLACEHOLDER_SECRETS = {
    "",
    "change-this-to-a-long-random-string-in-production",
    "change-me",
    "change_me",
    "changeme",
    "secret",
    "your-secret-key",
    "replace-me",
}


class Settings(BaseSettings):
    database_url: str = DEFAULT_DATABASE_URL
    # Intentionally blank: the app refuses to start until a real key is set.
    secret_key: str = ""
    admin_username: str = ""
    admin_password: str = ""
    https_only: bool = False
    setup_token: str = ""

    # Opt-in public product demo. False unless explicitly enabled.
    demo_mode: bool = False
    demo_seed: str = "review-demo-v1"
    demo_max_sessions: int = 200

    ai_base_url: str = ""
    ai_api_key: Optional[str] = None
    ai_model: str = ""

    business_name: str = "My Business"
    business_timezone: str = "Asia/Dhaka"

    # Rate limits (overridable via env)
    login_max_attempts: int = 10
    login_window_sec: int = 300
    setup_max_attempts: int = 5
    setup_window_sec: int = 900
    chat_max_attempts: int = 30
    chat_window_sec: int = 60
    chat_message_max_length: int = 2000

    # Pagination defaults
    page_size: int = 25

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("database_url", mode="before")
    @classmethod
    def _blank_database_url_uses_default(cls, value):
        # A blank DATABASE_URL (as shipped in .env.example) means "default".
        if value is None or (isinstance(value, str) and not value.strip()):
            return DEFAULT_DATABASE_URL
        return value.strip() if isinstance(value, str) else value


def _testing() -> bool:
    if os.environ.get("RENDER"):
        return False  # never honour the test bypass on a Render service
    return os.environ.get("FRONTDESK_TESTING", "").strip().lower() in {"1", "true", "yes"}


def secret_key_is_placeholder(value: str | None = None) -> bool:
    key = (settings.secret_key if value is None else value) or ""
    key = key.strip()
    return key.lower() in PLACEHOLDER_SECRETS or len(key) < MIN_SECRET_KEY_LENGTH


def admin_password_is_unset() -> bool:
    return not (settings.admin_password or "").strip() or settings.admin_password.strip() in {
        "CHANGE_ME",
        "change-me",
        "admin123",
    }


class StartupConfigError(SystemExit):
    """Raised (as a SystemExit) when configuration is unsafe to start."""


def _fail(msg: str) -> None:
    print(msg, file=sys.stderr)
    raise StartupConfigError(msg)


def enforce_secret_key() -> None:
    """Refuse to start with an empty, placeholder or short SECRET_KEY (all modes)."""
    if _testing():
        return
    if secret_key_is_placeholder():
        _fail(
            "SECRET_KEY is empty, a placeholder, or shorter than "
            f"{MIN_SECRET_KEY_LENGTH} characters. Generate one with:\n"
            '  python -c "import secrets; print(secrets.token_urlsafe(48))"\n'
            "Then set SECRET_KEY in .env (or the platform environment) and restart. "
            "This check also applies when DEMO_MODE=true."
        )


def is_demo_database_url(url: str) -> bool:
    return bool(re.fullmatch(r"sqlite:///\./data/demo-[A-Za-z0-9_-]{1,48}/[A-Za-z0-9_.-]+\.db", url or ""))


def demo_conflicts(cfg: "Settings | None" = None) -> list[str]:
    """Return production settings that must not coexist with DEMO_MODE=true."""
    cfg = cfg or settings
    if not cfg.demo_mode:
        return []
    problems = []
    if cfg.database_url != DEFAULT_DATABASE_URL and not is_demo_database_url(cfg.database_url):
        problems.append("DATABASE_URL (must be blank or a sqlite:///./data/demo-<seed>/<name>.db sandbox path)")
    if cfg.database_url == DEFAULT_DATABASE_URL and "database_url" in cfg.model_fields_set and _explicit_env("DATABASE_URL"):
        problems.append("DATABASE_URL (the production default path was set explicitly; leave it blank in demo)")
    for name in ("admin_username", "admin_password", "setup_token", "ai_api_key", "ai_base_url"):
        if (getattr(cfg, name) or "").strip():
            problems.append(name.upper())
    return problems


def _explicit_env(name: str) -> bool:
    value = os.environ.get(name)
    if value is not None:
        return bool(value.strip())
    # Also inspect a local .env file, which pydantic-settings reads.
    try:
        with open(".env", encoding="utf-8") as fh:
            for line in fh:
                if line.strip().startswith(f"{name}="):
                    return bool(line.split("=", 1)[1].strip().strip('"\''))
    except OSError:
        pass
    return False


def enforce_demo_isolation() -> None:
    """DEMO_MODE must run on a dedicated, credential-free instance. Never bypassed."""
    problems = demo_conflicts()
    if problems:
        _fail(
            "DEMO_MODE=true cannot start alongside production configuration: "
            + ", ".join(problems)
            + ". Run the public demo as a separate service with only SECRET_KEY, "
            "HTTPS_ONLY, DEMO_MODE, DEMO_SEED and DEMO_MAX_SESSIONS set."
        )


def enforce_startup_config() -> None:
    enforce_secret_key()
    enforce_demo_isolation()


settings = Settings()
