"""Persistent JSON state: seen posts + pending approvals."""
from __future__ import annotations

import asyncio
import json
import logging
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class PendingPost:
    pk: str                 # IG post primary key
    code: str               # shortcode (for the URL)
    target: str             # source username
    caption: str            # original caption from target
    media_type: int         # 1 photo, 2 video, 8 album
    product_type: str       # "feed" or "clips" (reels)
    media_paths: list[str]  # local downloaded media files
    tg_message_id: Optional[int] = None  # set after we send to telegram


@dataclass
class _StateData:
    seen_pks: list[str] = field(default_factory=list)
    pending: dict[str, dict] = field(default_factory=dict)
    target: Optional[str] = None  # overrides cfg.ig_target if set
    pending_initial_skip: bool = False  # next tick should mark all as seen


class State:
    def __init__(self, path: Path):
        self._path = path
        self._lock = asyncio.Lock()
        self._data = _StateData()

    @classmethod
    def load(cls, path: Path) -> "State":
        s = cls(path)
        if path.exists():
            try:
                raw = json.loads(path.read_text())
                s._data.seen_pks = list(raw.get("seen_pks", []))
                s._data.pending = dict(raw.get("pending", {}))
                s._data.target = raw.get("target")
                s._data.pending_initial_skip = bool(raw.get("pending_initial_skip", False))
            except Exception as e:
                log.warning("Could not load state, starting fresh: %s", e)
        return s

    def _flush(self) -> None:
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(asdict(self._data), indent=2, ensure_ascii=False))
        tmp.replace(self._path)

    # --- seen posts ---

    def has_seen(self, pk: str) -> bool:
        return pk in self._data.seen_pks

    async def mark_seen(self, pk: str) -> None:
        async with self._lock:
            if pk not in self._data.seen_pks:
                self._data.seen_pks.append(pk)
                # cap to last 1000 to avoid unbounded growth
                self._data.seen_pks = self._data.seen_pks[-1000:]
                self._flush()

    async def mark_seen_bulk(self, pks: list[str]) -> None:
        async with self._lock:
            existing = set(self._data.seen_pks)
            for pk in pks:
                if pk not in existing:
                    self._data.seen_pks.append(pk)
                    existing.add(pk)
            self._data.seen_pks = self._data.seen_pks[-1000:]
            self._flush()

    # --- pending approvals ---

    async def add_pending(self, post: PendingPost) -> None:
        async with self._lock:
            self._data.pending[post.pk] = asdict(post)
            self._flush()

    async def update_pending_message(self, pk: str, message_id: int) -> None:
        async with self._lock:
            if pk in self._data.pending:
                self._data.pending[pk]["tg_message_id"] = message_id
                self._flush()

    async def pop_pending(self, pk: str) -> Optional[PendingPost]:
        async with self._lock:
            raw = self._data.pending.pop(pk, None)
            if raw is None:
                return None
            self._flush()
            return PendingPost(**raw)

    def get_pending(self, pk: str) -> Optional[PendingPost]:
        raw = self._data.pending.get(pk)
        return PendingPost(**raw) if raw else None

    def all_pending(self) -> list[PendingPost]:
        return [PendingPost(**v) for v in self._data.pending.values()]

    # --- target ---

    def get_target(self, default: str) -> str:
        return self._data.target or default

    async def set_target(self, target: str) -> None:
        async with self._lock:
            self._data.target = target
            # changing target: skip current historical batch to avoid flooding
            self._data.pending_initial_skip = True
            self._flush()

    def should_skip_initial(self) -> bool:
        return self._data.pending_initial_skip

    async def clear_initial_skip(self) -> None:
        async with self._lock:
            if self._data.pending_initial_skip:
                self._data.pending_initial_skip = False
                self._flush()


def cleanup_media(post: PendingPost) -> None:
    """Best-effort delete of locally cached media files for a post."""
    parents = set()
    for p in post.media_paths:
        try:
            path = Path(p)
            if path.exists():
                path.unlink()
            parents.add(path.parent)
        except Exception as e:
            log.warning("Could not delete media %s: %s", p, e)
    for parent in parents:
        try:
            if parent.exists() and not any(parent.iterdir()):
                shutil.rmtree(parent)
        except Exception:
            pass
