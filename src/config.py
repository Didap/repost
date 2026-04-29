"""Configuration loaded from .env."""
from __future__ import annotations

import os
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
    ig_target: str
    tg_token: str
    tg_chat_id: int
    poll_interval: int
    caption_template: str
    data_dir: Path
    skip_initial: bool
    bootstrap_sessionid: str  # only used if no cached session exists yet

    @property
    def session_file(self) -> Path:
        return self.data_dir / "ig_session.json"

    @property
    def pending_session_file(self) -> Path:
        return self.data_dir / "pending_sessionid"

    @property
    def state_file(self) -> Path:
        return self.data_dir / "state.json"

    @property
    def media_dir(self) -> Path:
        return self.data_dir / "media"


def load() -> Config:
    data_dir = Path(os.getenv("DATA_DIR", "./data")).resolve()
    cfg = Config(
        ig_target=_required("IG_TARGET_USERNAME").lstrip("@"),
        tg_token=_required("TELEGRAM_BOT_TOKEN"),
        tg_chat_id=int(_required("TELEGRAM_CHAT_ID")),
        poll_interval=int(os.getenv("POLL_INTERVAL_SECONDS", "600")),
        caption_template=os.getenv("CAPTION_TEMPLATE", "{caption}").replace("\\n", "\n"),
        data_dir=data_dir,
        skip_initial=_bool("SKIP_INITIAL", True),
        bootstrap_sessionid=os.getenv("IG_SESSIONID", "").strip(),
    )
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    cfg.media_dir.mkdir(parents=True, exist_ok=True)
    return cfg
