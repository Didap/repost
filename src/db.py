"""SQLite-backed persistence (replaces the legacy JSON state.json).

Schema is intentionally flat. Single-tenant, single-process — no migrations
framework needed. On first boot we one-shot create tables and migrate any
legacy state.json sitting on the data volume.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Optional

import aiosqlite

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS targets (
    username TEXT PRIMARY KEY,
    added_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS seen_pks (
    pk TEXT PRIMARY KEY,
    target TEXT NOT NULL,
    seen_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS pending (
    pk TEXT PRIMARY KEY,
    target TEXT NOT NULL,
    code TEXT NOT NULL,
    caption TEXT NOT NULL,
    media_type INTEGER NOT NULL,
    product_type TEXT NOT NULL,
    media_paths TEXT NOT NULL,  -- JSON array
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pk TEXT NOT NULL,
    target TEXT NOT NULL,
    code TEXT NOT NULL,
    action TEXT NOT NULL,           -- approved | rejected | published | failed
    new_pk TEXT,                    -- IG primary key of the republished post
    error TEXT,
    ts INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    level TEXT NOT NULL,            -- info | warn | error
    message TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_seen_target ON seen_pks(target);
CREATE INDEX IF NOT EXISTS idx_history_ts ON history(ts DESC);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts DESC);
"""


def _now() -> int:
    return int(time.time())


class Database:
    def __init__(self, path: Path):
        self._path = path
        self._conn: Optional[aiosqlite.Connection] = None

    async def open(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        assert self._conn is not None, "Database.open() not called"
        return self._conn

    # ---- targets ----

    async def list_targets(self) -> list[str]:
        async with self.conn.execute(
            "SELECT username FROM targets ORDER BY added_at ASC"
        ) as cur:
            return [r["username"] for r in await cur.fetchall()]

    async def list_targets_detailed(self) -> list[dict]:
        async with self.conn.execute(
            """
            SELECT
                t.username,
                t.added_at,
                (SELECT COUNT(*) FROM pending p WHERE p.target = t.username) AS pending_count,
                (SELECT MAX(s.seen_at) FROM seen_pks s WHERE s.target = t.username) AS last_seen_at
            FROM targets t
            ORDER BY t.added_at ASC
            """
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def add_target(self, username: str) -> bool:
        try:
            await self.conn.execute(
                "INSERT INTO targets(username, added_at) VALUES (?, ?)",
                (username, _now()),
            )
            await self.conn.commit()
            return True
        except aiosqlite.IntegrityError:
            return False

    async def remove_target(self, username: str) -> bool:
        cur = await self.conn.execute(
            "DELETE FROM targets WHERE username = ?", (username,)
        )
        await self.conn.commit()
        return cur.rowcount > 0

    # ---- seen ----

    async def has_seen(self, pk: str) -> bool:
        async with self.conn.execute(
            "SELECT 1 FROM seen_pks WHERE pk = ?", (pk,)
        ) as cur:
            return (await cur.fetchone()) is not None

    async def mark_seen(self, pk: str, target: str) -> None:
        await self.conn.execute(
            "INSERT OR IGNORE INTO seen_pks(pk, target, seen_at) VALUES (?, ?, ?)",
            (pk, target, _now()),
        )
        await self.conn.commit()

    async def mark_seen_bulk(self, pks: list[str], target: str) -> None:
        if not pks:
            return
        ts = _now()
        await self.conn.executemany(
            "INSERT OR IGNORE INTO seen_pks(pk, target, seen_at) VALUES (?, ?, ?)",
            [(pk, target, ts) for pk in pks],
        )
        await self.conn.commit()

    # ---- pending ----

    async def add_pending(
        self,
        *,
        pk: str,
        target: str,
        code: str,
        caption: str,
        media_type: int,
        product_type: str,
        media_paths: list[str],
    ) -> None:
        await self.conn.execute(
            """
            INSERT OR REPLACE INTO pending
              (pk, target, code, caption, media_type, product_type, media_paths, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pk,
                target,
                code,
                caption,
                media_type,
                product_type,
                json.dumps(media_paths),
                _now(),
            ),
        )
        await self.conn.commit()

    async def get_pending(self, pk: str) -> Optional[dict]:
        async with self.conn.execute(
            "SELECT * FROM pending WHERE pk = ?", (pk,)
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        d = dict(row)
        d["media_paths"] = json.loads(d["media_paths"])
        return d

    async def list_pending(self) -> list[dict]:
        async with self.conn.execute(
            "SELECT * FROM pending ORDER BY created_at ASC"
        ) as cur:
            rows = await cur.fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["media_paths"] = json.loads(d["media_paths"])
            out.append(d)
        return out

    async def pop_pending(self, pk: str) -> Optional[dict]:
        post = await self.get_pending(pk)
        if post is None:
            return None
        await self.conn.execute("DELETE FROM pending WHERE pk = ?", (pk,))
        await self.conn.commit()
        return post

    # ---- history ----

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
        await self.conn.execute(
            """
            INSERT INTO history(pk, target, code, action, new_pk, error, ts)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (pk, target, code, action, new_pk, error, _now()),
        )
        await self.conn.commit()

    async def list_history(self, limit: int = 50) -> list[dict]:
        async with self.conn.execute(
            "SELECT * FROM history ORDER BY ts DESC LIMIT ?", (limit,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    # ---- events (auth retrier nags, errors) ----

    async def add_event(self, level: str, message: str) -> None:
        await self.conn.execute(
            "INSERT INTO events(ts, level, message) VALUES (?, ?, ?)",
            (_now(), level, message),
        )
        await self.conn.commit()

    async def list_events(self, since: int = 0, limit: int = 50) -> list[dict]:
        async with self.conn.execute(
            "SELECT * FROM events WHERE ts >= ? ORDER BY ts DESC LIMIT ?",
            (since, limit),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    # ---- kv (small flags) ----

    async def kv_get(self, key: str) -> Optional[str]:
        async with self.conn.execute(
            "SELECT value FROM kv WHERE key = ?", (key,)
        ) as cur:
            row = await cur.fetchone()
        return row["value"] if row else None

    async def kv_set(self, key: str, value: str) -> None:
        await self.conn.execute(
            "INSERT OR REPLACE INTO kv(key, value) VALUES (?, ?)", (key, value)
        )
        await self.conn.commit()

    # ---- users ----

    async def count_users(self) -> int:
        async with self.conn.execute("SELECT COUNT(*) AS n FROM users") as cur:
            row = await cur.fetchone()
        return int(row["n"]) if row else 0

    async def list_users(self) -> list[dict]:
        async with self.conn.execute(
            "SELECT id, email, created_at FROM users ORDER BY created_at ASC"
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def get_user_by_email(self, email: str) -> Optional[dict]:
        async with self.conn.execute(
            "SELECT id, email, password_hash, created_at FROM users WHERE LOWER(email) = LOWER(?)",
            (email,),
        ) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None

    async def get_user(self, user_id: int) -> Optional[dict]:
        async with self.conn.execute(
            "SELECT id, email, created_at FROM users WHERE id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None

    async def create_user(self, email: str, password_hash: str) -> Optional[int]:
        try:
            cur = await self.conn.execute(
                "INSERT INTO users(email, password_hash, created_at) VALUES (?, ?, ?)",
                (email, password_hash, _now()),
            )
            await self.conn.commit()
            return cur.lastrowid
        except aiosqlite.IntegrityError:
            return None

    async def delete_user(self, user_id: int) -> bool:
        cur = await self.conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        await self.conn.commit()
        return cur.rowcount > 0


async def migrate_from_json(db: Database, json_path: Path, default_target: str) -> None:
    """Move a legacy state.json into the new SQLite schema. Idempotent."""
    if not json_path.exists():
        # still need to seed the default target if no targets exist yet
        if not await db.list_targets() and default_target:
            await db.add_target(default_target)
        return

    marker = json_path.with_suffix(".json.migrated")
    try:
        raw = json.loads(json_path.read_text())
    except Exception as e:
        log.warning("Could not parse legacy state.json (%s) — skipping migration", e)
        json_path.rename(marker)
        return

    targets_existing = set(await db.list_targets())

    legacy_target = raw.get("target") or default_target
    if legacy_target and legacy_target not in targets_existing:
        await db.add_target(legacy_target)

    seen = raw.get("seen_pks") or []
    if seen and legacy_target:
        await db.mark_seen_bulk(seen, legacy_target)

    pending = raw.get("pending") or {}
    for pk, p in pending.items():
        try:
            await db.add_pending(
                pk=str(p.get("pk", pk)),
                target=p.get("target", legacy_target),
                code=p.get("code", ""),
                caption=p.get("caption", ""),
                media_type=int(p.get("media_type", 1)),
                product_type=p.get("product_type", "feed"),
                media_paths=list(p.get("media_paths", [])),
            )
        except Exception as e:
            log.warning("Skipping legacy pending pk=%s: %s", pk, e)

    json_path.rename(marker)
    log.info("Migrated legacy state.json → SQLite (%d seen, %d pending)", len(seen), len(pending))
