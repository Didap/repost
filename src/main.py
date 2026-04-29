"""Entrypoint: wire everything together and run."""
from __future__ import annotations

import asyncio
import logging
import signal

from . import config as config_mod
from .instagram_client import IGAuthError, InstagramClient
from .orchestrator import Orchestrator
from .state import State
from .telegram_bot import TelegramBot

log = logging.getLogger(__name__)


async def _bootstrap_auth(cfg, ig: InstagramClient, tg: TelegramBot) -> None:
    """Establish a session at startup if we can; otherwise ask the user via TG."""
    if await ig.try_load_session():
        return

    if cfg.bootstrap_sessionid:
        log.info("Trying bootstrap sessionid from env")
        try:
            await ig.login_with_sessionid(cfg.bootstrap_sessionid)
            return
        except IGAuthError as e:
            log.error("Bootstrap sessionid rejected: %s", e)
            await tg.notify(f"⚠️ <code>IG_SESSIONID</code> nell'env è invalido: <code>{e}</code>")

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

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass  # windows

    poll_task = asyncio.create_task(orchestrator.run())

    await stop_event.wait()
    log.info("Shutting down…")
    orchestrator.stop()
    await asyncio.wait([poll_task], timeout=5)
    if not poll_task.done():
        poll_task.cancel()
    await tg.stop()


def main() -> None:
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
