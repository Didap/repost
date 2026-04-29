"""Entrypoint: wire everything together and run."""
from __future__ import annotations

import asyncio
import logging
import signal

from . import config as config_mod
from .auth_retrier import AuthRetrier
from .instagram_client import InstagramClient
from .orchestrator import Orchestrator
from .state import State
from .telegram_bot import TelegramBot

log = logging.getLogger(__name__)


async def _bootstrap_auth(cfg, ig: InstagramClient, tg: TelegramBot) -> None:
    """Establish a session at startup if we can; otherwise ask the user via TG.

    A pending sessionid on disk (or one provided via IG_SESSIONID env) is
    enqueued for the background retrier — we never reject at startup.
    """
    if await ig.try_load_session():
        return

    # honor a sessionid already pending from a previous run / restart
    pending = ig.read_pending_sessionid()
    if pending is None and cfg.bootstrap_sessionid:
        log.info("Seeding pending sessionid from IG_SESSIONID env")
        ig.set_pending_sessionid(cfg.bootstrap_sessionid)
        pending = cfg.bootstrap_sessionid

    if pending is not None:
        success, info = await ig.try_pending_login()
        if success:
            log.info("Bootstrap sessionid accepted (user @%s)", info)
            return
        log.warning("Bootstrap sessionid not accepted yet: %s. Retrier will keep trying.", info)
        await tg.notify(
            "💾 Sessionid pendente in retry automatico in background. "
            "Ti scrivo appena IG lo accetta."
        )
        return

    await tg.request_auth()


async def _run() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)

    cfg = config_mod.load()
    state = State.load(cfg.state_file)
    ig = InstagramClient(cfg)
    tg = TelegramBot(cfg, state, ig)

    await tg.start()
    await tg.notify(
        f"🚀 Repost bot avviato.\n"
        f"Target: @{cfg.ig_target}\n"
        f"Polling ogni {cfg.poll_interval}s"
    )

    await _bootstrap_auth(cfg, ig, tg)

    orchestrator = Orchestrator(cfg, state, ig, tg)
    retrier = AuthRetrier(ig, tg)

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass  # windows

    poll_task = asyncio.create_task(orchestrator.run())
    retrier_task = asyncio.create_task(retrier.run())

    await stop_event.wait()
    log.info("Shutting down…")
    orchestrator.stop()
    retrier.stop()
    await asyncio.wait([poll_task, retrier_task], timeout=5)
    for t in (poll_task, retrier_task):
        if not t.done():
            t.cancel()
    await tg.stop()


def main() -> None:
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
