"""Background loop that periodically retries auth using a pending sessionid.

Soft backoff (10/20/40/60 min, then 60 forever). Notifications go into the
events log, surfaced by the dashboard.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from .instagram_client import InstagramClient
from .state import State

log = logging.getLogger(__name__)

BACKOFF_MINUTES = [10, 20, 40, 60]
NAG_AFTER_ATTEMPTS = 5


class AuthRetrier:
    def __init__(self, ig: InstagramClient, state: State):
        self._ig = ig
        self._state = state
        self._stop = asyncio.Event()

    def stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        last_sid: Optional[str] = None
        attempts = 0
        nagged = False

        while not self._stop.is_set():
            current_sid = self._ig.read_pending_sessionid()

            if current_sid is None or self._ig.auth_ready.is_set():
                if self._ig.auth_ready.is_set():
                    self._ig.clear_pending_sessionid()
                last_sid = None
                attempts = 0
                nagged = False
                await self._wait(60)
                continue

            if current_sid != last_sid:
                last_sid = current_sid
                attempts = 0
                nagged = False

            delay_min = BACKOFF_MINUTES[min(attempts, len(BACKOFF_MINUTES) - 1)]
            await self._wait(delay_min * 60)
            if self._stop.is_set():
                return

            if self._ig.auth_ready.is_set():
                continue
            if self._ig.read_pending_sessionid() != last_sid:
                continue

            attempts += 1
            log.info("Auth retry attempt #%d", attempts)
            success, info = await self._ig.try_pending_login()
            if success:
                await self._state.add_event(
                    "info", f"Autenticato come @{info} dopo retry."
                )
                last_sid = None
                attempts = 0
                nagged = False
            else:
                log.info("Auth retry failed: %s", info)
                if attempts >= NAG_AFTER_ATTEMPTS and not nagged:
                    await self._state.add_event(
                        "warn",
                        "IG continua a rifiutare la sessione (challenge attivo). "
                        "Continuo a riprovare ogni ora — sblocca la sessione su "
                        "instagram.com/accounts/activity per accelerare.",
                    )
                    nagged = True

    async def _wait(self, seconds: int) -> None:
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass
