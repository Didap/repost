"""Entrypoint: bring up DB, IG client, FastAPI app + background tasks."""
from __future__ import annotations

import asyncio
import logging
import signal

import uvicorn

from . import config as config_mod
from .api import bootstrap_admin, create_app
from .auth_retrier import AuthRetrier
from .db import Database, migrate_from_json
from .instagram_client import InstagramClient
from .orchestrator import Orchestrator
from .state import State

log = logging.getLogger(__name__)


async def _bootstrap_auth(cfg, ig: InstagramClient, state: State) -> None:
    if await ig.try_load_session():
        return

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
        log.warning("Bootstrap sessionid pending: %s", info)
        await state.add_event(
            "warn", "Sessionid in retry automatico. Apri Auth nella dashboard."
        )


async def _run() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    cfg = config_mod.load()

    db = Database(cfg.db_file)
    await db.open()
    await migrate_from_json(db, cfg.state_file, cfg.ig_target)
    state = State(db)
    await bootstrap_admin(cfg, state)

    ig = InstagramClient(cfg)
    await _bootstrap_auth(cfg, ig, state)

    orchestrator = Orchestrator(cfg, state, ig)
    retrier = AuthRetrier(ig, state)
    app = create_app(cfg, state, ig)

    config = uvicorn.Config(
        app,
        host=cfg.dashboard_host,
        port=cfg.dashboard_port,
        log_level="info",
        access_log=False,
    )
    server = uvicorn.Server(config)

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass

    poll_task = asyncio.create_task(orchestrator.run(), name="orchestrator")
    retrier_task = asyncio.create_task(retrier.run(), name="auth_retrier")
    server_task = asyncio.create_task(server.serve(), name="uvicorn")
    stop_task = asyncio.create_task(stop_event.wait(), name="stop")

    done, pending = await asyncio.wait(
        [poll_task, retrier_task, server_task, stop_task],
        return_when=asyncio.FIRST_COMPLETED,
    )

    log.info("Shutting down…")
    orchestrator.stop()
    retrier.stop()
    server.should_exit = True

    for t in (poll_task, retrier_task, server_task):
        if not t.done():
            try:
                await asyncio.wait_for(t, timeout=5)
            except asyncio.TimeoutError:
                t.cancel()
    await db.close()


def main() -> None:
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
