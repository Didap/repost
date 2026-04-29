"""Background loop that periodically retries auth using a pending sessionid.

Soft backoff (10/20/40/60 min, then 60 forever) so we never hammer IG when
it's having a bad day. The user enqueues a sessionid via /auth; this loop
keeps trying until either (a) it succeeds, (b) the user cancels, or
(c) the user replaces it with a fresh sessionid (backoff resets).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from .instagram_client import InstagramClient
from .telegram_bot import TelegramBot

log = logging.getLogger(__name__)

BACKOFF_MINUTES = [10, 20, 40, 60]  # then last value forever
NAG_AFTER_ATTEMPTS = 5  # ~10+20+40+60+60 ≈ 3h


class AuthRetrier:
    def __init__(self, ig: InstagramClient, tg: TelegramBot):
        self._ig = ig
        self._tg = tg
        self._stop = asyncio.Event()

    def stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        last_sid: Optional[str] = None
        attempts = 0
        nagged = False

        while not self._stop.is_set():
            current_sid = self._ig.read_pending_sessionid()

            # nothing to do: poll again in a minute
            if current_sid is None or self._ig.auth_ready.is_set():
                if self._ig.auth_ready.is_set():
                    self._ig.clear_pending_sessionid()
                last_sid = None
                attempts = 0
                nagged = False
                await self._wait(60)
                continue

            # user gave a new sessionid → reset backoff
            if current_sid != last_sid:
                last_sid = current_sid
                attempts = 0
                nagged = False

            delay_min = BACKOFF_MINUTES[min(attempts, len(BACKOFF_MINUTES) - 1)]
            await self._wait(delay_min * 60)
            if self._stop.is_set():
                return

            # state may have changed during the wait
            if self._ig.auth_ready.is_set():
                continue
            if self._ig.read_pending_sessionid() != last_sid:
                continue

            attempts += 1
            log.info("Auth retry attempt #%d (sid …%s)", attempts, last_sid[-6:])
            success, info = await self._ig.try_pending_login()
            if success:
                await self._tg.notify(
                    f"✅ Autenticato come <b>@{info}</b> dopo retry. Polling attivo."
                )
                last_sid = None
                attempts = 0
                nagged = False
            else:
                log.info("Auth retry failed: %s", info)
                if attempts >= NAG_AFTER_ATTEMPTS and not nagged:
                    await self._tg.notify(
                        "⏳ IG continua a rifiutare la sessione (challenge attivo). "
                        "Continuo a riprovare ogni ora in background.\n\n"
                        "Per accelerare:\n"
                        "• Apri "
                        "<a href=\"https://instagram.com/accounts/activity/?type=login_activity\">"
                        "instagram.com/accounts/activity</a> e conferma la sessione dal datacenter\n"
                        "• Oppure manda un nuovo <code>/auth &lt;sessionid&gt;</code>\n"
                        "• Oppure annulla con /cancel_auth"
                    )
                    nagged = True

    async def _wait(self, seconds: int) -> None:
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass
