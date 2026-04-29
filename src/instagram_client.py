"""Instagram wrapper around instagrapi.

Auth model: the user gets a `sessionid` from their browser cookies on
instagram.com and feeds it via env var (bootstrap) or via Telegram /auth
command. We never see their password. instagrapi calls run in worker
threads via asyncio.to_thread to avoid blocking the event loop.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

from instagrapi import Client
from instagrapi.exceptions import (
    ChallengeRequired,
    LoginRequired,
    PleaseWaitFewMinutes,
)
from instagrapi.types import Media

from .config import Config
from .state import PendingPost

log = logging.getLogger(__name__)

# Media type constants from instagrapi
PHOTO = 1
VIDEO = 2
ALBUM = 8


class IGAuthError(Exception):
    pass


class InstagramClient:
    def __init__(self, cfg: Config):
        self._cfg = cfg
        self._client = Client()
        self._client.delay_range = [2, 5]
        self._target_user_id: Optional[str] = None
        self._target_cache_for: Optional[str] = None
        self._authed = asyncio.Event()
        self._username: Optional[str] = None
        self._auth_lock = asyncio.Lock()

    @property
    def auth_ready(self) -> asyncio.Event:
        """Set when the client has a working session, cleared otherwise."""
        return self._authed

    @property
    def username(self) -> Optional[str]:
        return self._username

    # ---------- auth ----------

    def _verify_sync(self) -> str:
        """Probe the API to confirm the session works. Returns username on success."""
        info = self._client.account_info()
        return info.username

    def _load_session_sync(self) -> bool:
        """Try to revive a previously-saved session. Returns True on success."""
        if not self._cfg.session_file.exists():
            return False
        try:
            self._client.load_settings(self._cfg.session_file)
            self._username = self._verify_sync()
            log.info("Revived session for @%s", self._username)
            return True
        except (LoginRequired, ChallengeRequired, Exception) as e:
            log.warning("Cached session invalid: %s", e)
            self._client = Client()
            self._client.delay_range = [2, 5]
            return False

    def _login_with_sessionid_sync(self, sessionid: str) -> str:
        """Replace the current session with one driven by a fresh browser sessionid."""
        sessionid = sessionid.strip().strip('"').strip("'")
        if not sessionid:
            raise IGAuthError("sessionid vuoto")

        # start clean to avoid mixing state from a stale session
        new_client = Client()
        new_client.delay_range = [2, 5]
        try:
            new_client.login_by_sessionid(sessionid)
            info = new_client.account_info()
        except ChallengeRequired:
            raise IGAuthError(
                "Instagram chiede un challenge. Apri instagram.com nel browser, "
                "completa la verifica, poi prendi un nuovo sessionid e riprova."
            )
        except PleaseWaitFewMinutes as e:
            raise IGAuthError(f"IG ti ha messo in pausa: {e}")
        except Exception as e:
            raise IGAuthError(f"sessionid rifiutato: {e}")

        self._client = new_client
        self._username = info.username
        self._target_user_id = None  # invalidate cache, new client
        self._client.dump_settings(self._cfg.session_file)
        log.info("Authenticated via sessionid as @%s", self._username)
        return self._username

    async def try_load_session(self) -> bool:
        ok = await asyncio.to_thread(self._load_session_sync)
        if ok:
            self._authed.set()
        return ok

    async def login_with_sessionid(self, sessionid: str) -> str:
        async with self._auth_lock:
            username = await asyncio.to_thread(self._login_with_sessionid_sync, sessionid)
            self._authed.set()
            return username

    def mark_auth_invalid(self) -> None:
        """Called when an API call surfaced an auth error mid-runtime."""
        self._authed.clear()
        try:
            if self._cfg.session_file.exists():
                self._cfg.session_file.unlink()
        except Exception:
            pass

    # ---------- pending sessionid (background retry) ----------

    def set_pending_sessionid(self, sessionid: str) -> None:
        sessionid = sessionid.strip().strip('"').strip("'")
        if not sessionid:
            self.clear_pending_sessionid()
            return
        path = self._cfg.pending_session_file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(sessionid)

    def clear_pending_sessionid(self) -> None:
        try:
            if self._cfg.pending_session_file.exists():
                self._cfg.pending_session_file.unlink()
        except Exception as e:
            log.warning("Could not clear pending sessionid: %s", e)

    def read_pending_sessionid(self) -> Optional[str]:
        path = self._cfg.pending_session_file
        if not path.exists():
            return None
        try:
            sid = path.read_text().strip()
            return sid or None
        except Exception:
            return None

    async def try_pending_login(self) -> tuple[bool, str]:
        """Attempt auth using the stored pending sessionid. Never raises auth errors.

        Returns (True, username) on success — pending file is cleared and
        auth_ready event set. Returns (False, error_message) on any failure.
        """
        sid = self.read_pending_sessionid()
        if sid is None:
            return False, "no pending sessionid"
        async with self._auth_lock:
            if self._authed.is_set():
                self.clear_pending_sessionid()
                return True, self._username or ""
            try:
                username = await asyncio.to_thread(self._login_with_sessionid_sync, sid)
            except IGAuthError as e:
                return False, str(e)
            except Exception as e:
                return False, f"errore inatteso: {e}"
            self._authed.set()
            self.clear_pending_sessionid()
            return True, username

    # ---------- target monitoring ----------

    def _resolve_target_sync(self, target: str) -> str:
        if self._target_user_id is None or self._target_cache_for != target:
            uid = self._client.user_id_from_username(target)
            self._target_user_id = str(uid)
            self._target_cache_for = target
            log.info("Resolved target @%s -> id=%s", target, uid)
        return self._target_user_id

    def _fetch_recent_sync(self, target: str, amount: int) -> list[Media]:
        uid = self._resolve_target_sync(target)
        return self._client.user_medias(uid, amount=amount)

    async def fetch_recent(self, target: str, amount: int = 6) -> list[Media]:
        return await asyncio.to_thread(self._fetch_recent_sync, target, amount)

    def reset_target_cache(self) -> None:
        self._target_user_id = None
        self._target_cache_for = None

    # ---------- download ----------

    def _download_sync(self, media: Media) -> list[Path]:
        out_dir = self._cfg.media_dir / str(media.pk)
        out_dir.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []

        if media.media_type == PHOTO:
            paths.append(self._client.photo_download(media.pk, folder=out_dir))
        elif media.media_type == VIDEO:
            paths.append(self._client.video_download(media.pk, folder=out_dir))
        elif media.media_type == ALBUM:
            for resource in media.resources:
                if resource.media_type == PHOTO:
                    paths.append(
                        self._client.photo_download_by_url(
                            resource.thumbnail_url, folder=out_dir
                        )
                    )
                elif resource.media_type == VIDEO:
                    paths.append(
                        self._client.video_download_by_url(
                            resource.video_url, folder=out_dir
                        )
                    )
        else:
            raise ValueError(f"Unsupported media_type: {media.media_type}")

        return paths

    async def download(self, media: Media) -> list[Path]:
        return await asyncio.to_thread(self._download_sync, media)

    # ---------- repost ----------

    def _repost_sync(self, post: PendingPost, caption: str) -> str:
        paths = [Path(p) for p in post.media_paths]
        if post.media_type == PHOTO:
            result = self._client.photo_upload(paths[0], caption=caption)
        elif post.media_type == VIDEO:
            if post.product_type == "clips":
                result = self._client.clip_upload(paths[0], caption=caption)
            else:
                result = self._client.video_upload(paths[0], caption=caption)
        elif post.media_type == ALBUM:
            result = self._client.album_upload(paths, caption=caption)
        else:
            raise ValueError(f"Unsupported media_type: {post.media_type}")
        return str(result.pk)

    async def repost(self, post: PendingPost, caption: str) -> str:
        return await asyncio.to_thread(self._repost_sync, post, caption)
