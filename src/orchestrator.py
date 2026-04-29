"""Polling loop: fetch each target's recent posts, queue new ones for approval.

Polls only when the IG client is authenticated. Auth-related failures during
a tick mark the session as invalid — the loop will then block on auth_ready
until the user reauths via the dashboard. Per-tick errors are written to the
events log (read by the dashboard) instead of pushed to a Telegram bot.
"""
from __future__ import annotations

import asyncio
import logging
import random

from instagrapi.exceptions import LoginRequired, ChallengeRequired

from .config import Config
from .instagram_client import InstagramClient
from .state import PendingPost, State

log = logging.getLogger(__name__)


class Orchestrator:
    def __init__(
        self,
        cfg: Config,
        state: State,
        ig: InstagramClient,
    ):
        self._cfg = cfg
        self._state = state
        self._ig = ig
        self._stop = asyncio.Event()

    def stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        first_run = True
        while not self._stop.is_set():
            await self._wait_for_auth()
            if self._stop.is_set():
                return

            skip_processing = (
                (first_run and self._cfg.skip_initial)
                or await self._state.should_skip_initial()
            )

            try:
                await self._tick(skip_processing=skip_processing)
                first_run = False
                await self._state.clear_initial_skip()
            except (LoginRequired, ChallengeRequired) as e:
                log.warning("Session no longer valid: %s", e)
                self._ig.mark_auth_invalid()
                await self._state.add_event(
                    "warn",
                    "La sessione Instagram non è più valida. "
                    "Vai su Auth e incolla un nuovo sessionid.",
                )
                continue
            except Exception as e:
                log.exception("Polling tick failed: %s", e)
                await self._state.add_event("error", f"Errore nel polling: {e}")

            jitter = random.randint(-30, 30)
            try:
                await asyncio.wait_for(
                    self._stop.wait(),
                    timeout=max(60, self._cfg.poll_interval + jitter),
                )
            except asyncio.TimeoutError:
                pass

    async def _wait_for_auth(self) -> None:
        if self._ig.auth_ready.is_set():
            return
        log.info("Orchestrator paused: waiting for auth")
        wait_auth = asyncio.create_task(self._ig.auth_ready.wait())
        wait_stop = asyncio.create_task(self._stop.wait())
        try:
            await asyncio.wait(
                [wait_auth, wait_stop], return_when=asyncio.FIRST_COMPLETED
            )
        finally:
            for t in (wait_auth, wait_stop):
                if not t.done():
                    t.cancel()
        if self._ig.auth_ready.is_set() and not self._stop.is_set():
            log.info("Orchestrator resumed: auth ready")

    async def _tick(self, *, skip_processing: bool) -> None:
        targets = await self._state.get_targets()
        if not targets:
            log.info("No targets configured — idle")
            return
        for target in targets:
            if self._stop.is_set():
                return
            await self._tick_one(target, skip_processing=skip_processing)

    async def _tick_one(self, target: str, *, skip_processing: bool) -> None:
        log.info("Polling @%s …", target)
        recent = await self._ig.fetch_recent(target, amount=6)
        # IG returns newest first; reverse so approval messages arrive in order
        recent = list(reversed(recent))

        new_pks: list[str] = []
        for media in recent:
            pk = str(media.pk)
            if await self._state.has_seen(pk):
                continue
            if await self._state.get_pending(pk) is not None:
                continue
            new_pks.append(pk)

            if skip_processing:
                continue

            await self._enqueue(media, target)

        if skip_processing and new_pks:
            await self._state.mark_seen_bulk(new_pks, target)
            log.info(
                "Skipped historical batch on @%s: marked %d posts as seen",
                target,
                len(new_pks),
            )

    async def _enqueue(self, media, target: str) -> None:
        pk = str(media.pk)
        log.info("New post %s on @%s (type=%s), downloading…", pk, target, media.media_type)
        try:
            paths = await self._ig.download(media)
        except Exception as e:
            log.exception("Download failed for %s", pk)
            await self._state.add_event(
                "error", f"Download fallito per post {pk} (@{target}): {e}"
            )
            return

        post = PendingPost(
            pk=pk,
            code=media.code,
            target=target,
            caption=media.caption_text or "",
            media_type=media.media_type,
            product_type=media.product_type or "feed",
            media_paths=[str(p) for p in paths],
        )
        await self._state.add_pending(post)
        await self._state.add_event("info", f"Nuovo post da @{target}: {pk}")
