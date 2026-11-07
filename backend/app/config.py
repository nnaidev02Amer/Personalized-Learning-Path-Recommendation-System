"""Backend settings, read from environment variables (or a ``.env`` file).

See ``.env.example`` in the repository root for every supported variable.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")


def _bool(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _default_db_url() -> str:
    path = ROOT_DIR / "data" / "app.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path.as_posix()}"


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default_factory=lambda: os.environ.get("DATABASE_URL") or _default_db_url())
    cors_origins: tuple[str, ...] = field(default_factory=lambda: tuple(
        o.strip() for o in os.environ.get(
            "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()))
    # Create tables and load the sample data automatically when the DB is empty.
    seed_on_startup: bool = field(default_factory=lambda: _bool("SEED_ON_STARTUP", True))
    seed_random_state: int = field(default_factory=lambda: int(os.environ.get("SEED_RANDOM_STATE", "42")))
    # Train the ML models in a background thread at startup (otherwise on first ML request).
    ml_train_on_startup: bool = field(default_factory=lambda: _bool("ML_TRAIN_ON_STARTUP", True))

    # ---- authentication (see docs/AUTHENTICATION.md)
    environment: str = field(default_factory=lambda: os.environ.get("APP_ENV", "development").strip().lower())
    # Students can register themselves (an administrator can never be created this way). Set false to close sign-up.
    allow_self_registration: bool = field(default_factory=lambda: _bool("ALLOW_SELF_REGISTRATION", True))
    session_ttl_hours: float = field(default_factory=lambda: float(os.environ.get("SESSION_TTL_HOURS", "8")))
    # None = decide from APP_ENV (Secure cookies in production, so local http://localhost keeps working).
    cookie_secure_override: bool | None = field(default_factory=lambda: (
        _bool("COOKIE_SECURE", False) if os.environ.get("COOKIE_SECURE") not in (None, "") else None))
    max_failed_logins: int = field(default_factory=lambda: int(os.environ.get("MAX_FAILED_LOGINS", "5")))
    lockout_minutes: float = field(default_factory=lambda: float(os.environ.get("LOCKOUT_MINUTES", "15")))
    @property
    def is_production(self) -> bool:
        return self.environment in {"production", "prod"}

    @property
    def cookie_secure(self) -> bool:
        return self.is_production if self.cookie_secure_override is None else self.cookie_secure_override


def get_settings() -> Settings:
    settings = Settings()
    if "*" in settings.cors_origins:
        raise ValueError("CORS_ORIGINS must list explicit origins: '*' cannot be combined with cookie sessions")
    return settings
