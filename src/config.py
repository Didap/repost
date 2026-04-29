"""Configuration loaded from .env."""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Config:
    ig_target: str               # default target (seeded into DB on first boot)
    poll_interval: int
    caption_template: str
    data_dir: Path
    skip_initial: bool
    bootstrap_sessionid: str

    admin_email: str
    admin_password: str
    dashboard_host: str
    dashboard_port: int
    cookie_secret: str

    @property
    def session_file(self) -> Path:
        return self.data_dir / "ig_session.json"

    @property
    def pending_session_file(self) -> Path:
        return self.data_dir / "pending_sessionid"

    @property
    def state_file(self) -> Path:
        # legacy JSON file — only consulted for one-shot migration to SQLite
        return self.data_dir / "state.json"

    @property
    def db_file(self) -> Path:
        return self.data_dir / "state.db"

    @property
    def media_dir(self) -> Path:
        return self.data_dir / "media"

    @property
    def web_dist(self) -> Path:
        # static SPA bundle, copied in by the Dockerfile
        return Path(os.getenv("WEB_DIST", "/app/web/dist"))


def _cookie_secret(data_dir: Path) -> str:
    """Stable cookie-signing secret. Use env if provided, otherwise persist a
    random secret next to the data dir so cookies survive restarts."""
    env = os.getenv("COOKIE_SECRET", "").strip()
    if env:
        return env
    secret_file = data_dir / "cookie.secret"
    if secret_file.exists():
        return secret_file.read_text().strip()
    secret = secrets.token_urlsafe(48)
    data_dir.mkdir(parents=True, exist_ok=True)
    secret_file.write_text(secret)
    return secret


def load() -> Config:
    data_dir = Path(os.getenv("DATA_DIR", "./data")).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)

    cfg = Config(
        ig_target=os.getenv("IG_TARGET_USERNAME", "").lstrip("@"),
        poll_interval=int(os.getenv("POLL_INTERVAL_SECONDS", "600")),
        caption_template=os.getenv("CAPTION_TEMPLATE", "{caption}").replace("\\n", "\n"),
        data_dir=data_dir,
        skip_initial=_bool("SKIP_INITIAL", True),
        bootstrap_sessionid=os.getenv("IG_SESSIONID", "").strip(),
        admin_email=_required("ADMIN_EMAIL").strip().lower(),
        admin_password=_required("ADMIN_PASSWORD"),
        dashboard_host=os.getenv("DASHBOARD_HOST", "0.0.0.0"),
        dashboard_port=int(os.getenv("DASHBOARD_PORT", "8000")),
        cookie_secret=_cookie_secret(data_dir),
    )
    cfg.media_dir.mkdir(parents=True, exist_ok=True)
    return cfg
