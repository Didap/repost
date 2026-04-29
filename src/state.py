"""Persistent state — thin async facade over src/db.py (SQLite).

Mantiene il contratto usato dall'orchestrator (has_seen / mark_seen /
add_pending / get_pending / pop_pending / all_pending / get_target / set_target /
should_skip_initial / clear_initial_skip) e aggiunge multi-target.
"""
from __future__ import annotations

import logging
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from .db import Database

log = logging.getLogger(__name__)

# kv keys
KV_SKIP_INITIAL = "pending_initial_skip"


@dataclass
class PendingPost:
    pk: str
    code: str
    target: str
    caption: str
    media_type: int
    product_type: str
    media_paths: list[str]


def _to_pending(d: dict) -> PendingPost:
    return PendingPost(
        pk=d["pk"],
        code=d["code"],
        target=d["target"],
        caption=d["caption"],
        media_type=d["media_type"],
        product_type=d["product_type"],
        media_paths=d["media_paths"],
    )


class State:
    def __init__(self, db: Database):
        self._db = db

    # --- seen ---

    async def has_seen(self, pk: str) -> bool:
        return await self._db.has_seen(pk)

    async def mark_seen(self, pk: str, target: str) -> None:
        await self._db.mark_seen(pk, target)

    async def mark_seen_bulk(self, pks: list[str], target: str) -> None:
        await self._db.mark_seen_bulk(pks, target)

    # --- pending ---

    async def add_pending(self, post: PendingPost) -> None:
        await self._db.add_pending(
            pk=post.pk,
            target=post.target,
            code=post.code,
            caption=post.caption,
            media_type=post.media_type,
            product_type=post.product_type,
            media_paths=post.media_paths,
        )

    async def get_pending(self, pk: str) -> Optional[PendingPost]:
        d = await self._db.get_pending(pk)
        return _to_pending(d) if d else None

    async def pop_pending(self, pk: str) -> Optional[PendingPost]:
        d = await self._db.pop_pending(pk)
        return _to_pending(d) if d else None

    async def all_pending(self) -> list[PendingPost]:
        return [_to_pending(d) for d in await self._db.list_pending()]

    # --- targets ---

    async def get_targets(self) -> list[str]:
        return await self._db.list_targets()

    async def get_targets_detailed(self) -> list[dict]:
        return await self._db.list_targets_detailed()

    async def add_target(self, username: str) -> bool:
        added = await self._db.add_target(username)
        if added:
            await self.set_skip_initial(True)
        return added

    async def remove_target(self, username: str) -> bool:
        return await self._db.remove_target(username)

    # --- skip-initial flag (per next tick after target add) ---

    async def should_skip_initial(self) -> bool:
        v = await self._db.kv_get(KV_SKIP_INITIAL)
        return v == "1"

    async def set_skip_initial(self, value: bool) -> None:
        await self._db.kv_set(KV_SKIP_INITIAL, "1" if value else "0")

    async def clear_initial_skip(self) -> None:
        await self.set_skip_initial(False)

    # --- history & events (used by api / approve flow) ---

    async def add_history(
        self,
        *,
        pk: str,
        target: str,
        code: str,
        action: str,
        new_pk: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        await self._db.add_history(
            pk=pk, target=target, code=code, action=action, new_pk=new_pk, error=error
        )

    async def list_history(self, limit: int = 50) -> list[dict]:
        return await self._db.list_history(limit=limit)

    async def add_event(self, level: str, message: str) -> None:
        await self._db.add_event(level, message)

    async def list_events(self, since: int = 0, limit: int = 50) -> list[dict]:
        return await self._db.list_events(since=since, limit=limit)

    # --- users (delegated unchanged) ---

    @property
    def db(self) -> Database:
        return self._db


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
