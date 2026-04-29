"""FastAPI app: multi-user auth + JSON endpoints + static SPA serving."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

import bcrypt
from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    FastAPI,
    HTTPException,
    Response,
)
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from itsdangerous import BadSignature, URLSafeSerializer
from pydantic import BaseModel, EmailStr

from .config import Config
from .instagram_client import InstagramClient
from .state import State, cleanup_media

log = logging.getLogger(__name__)

COOKIE_NAME = "repost_session"
COOKIE_MAX_AGE = 60 * 60 * 24 * 30


# ------------------------------------------------------------------ schemas

class LoginIn(BaseModel):
    email: EmailStr
    password: str


class CreateUserIn(BaseModel):
    email: EmailStr
    password: str


class IGAuthIn(BaseModel):
    sessionid: str


class TargetIn(BaseModel):
    username: str


# ------------------------------------------------------------------ helpers

def _serializer(secret: str) -> URLSafeSerializer:
    return URLSafeSerializer(secret, salt="repost-session")


def _user_from_cookie(serializer: URLSafeSerializer, cookie: Optional[str]) -> Optional[int]:
    if not cookie:
        return None
    try:
        data = serializer.loads(cookie)
    except BadSignature:
        return None
    uid = data.get("uid")
    return int(uid) if isinstance(uid, int) else None


def _hash(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# ------------------------------------------------------------------ app factory

def create_app(
    cfg: Config,
    state: State,
    ig: InstagramClient,
) -> FastAPI:
    app = FastAPI(title="Repost", docs_url=None, redoc_url=None, openapi_url=None)
    serializer = _serializer(cfg.cookie_secret)

    async def require_auth(
        repost_session: Optional[str] = Cookie(default=None, alias=COOKIE_NAME),
    ) -> dict:
        uid = _user_from_cookie(serializer, repost_session)
        if uid is None:
            raise HTTPException(status_code=401, detail="auth required")
        user = await state.db.get_user(uid)
        if user is None:
            raise HTTPException(status_code=401, detail="user no longer exists")
        return user

    api = APIRouter(prefix="/api")

    # ---- session ---------------------------------------------------------

    @api.get("/session")
    async def session(
        repost_session: Optional[str] = Cookie(default=None, alias=COOKIE_NAME),
    ):
        uid = _user_from_cookie(serializer, repost_session)
        if uid is None:
            return {"authed": False}
        user = await state.db.get_user(uid)
        if user is None:
            return {"authed": False}
        return {"authed": True, "user": {"id": user["id"], "email": user["email"]}}

    @api.post("/login")
    async def login(payload: LoginIn, response: Response):
        user = await state.db.get_user_by_email(payload.email)
        if user is None or not _verify(payload.password, user["password_hash"]):
            await asyncio.sleep(0.4)
            raise HTTPException(status_code=401, detail="credenziali errate")
        cookie = serializer.dumps({"uid": user["id"]})
        response.set_cookie(
            key=COOKIE_NAME,
            value=cookie,
            max_age=COOKIE_MAX_AGE,
            httponly=True,
            samesite="lax",
            secure=False,
        )
        return {"ok": True, "user": {"id": user["id"], "email": user["email"]}}

    @api.post("/logout")
    async def logout(response: Response, _=Depends(require_auth)):
        response.delete_cookie(key=COOKIE_NAME)
        return {"ok": True}

    # ---- users ---------------------------------------------------------

    @api.get("/users")
    async def list_users(_=Depends(require_auth)):
        return await state.db.list_users()

    @api.post("/users", status_code=201)
    async def create_user(payload: CreateUserIn, _=Depends(require_auth)):
        if len(payload.password) < 8:
            raise HTTPException(status_code=400, detail="password troppo corta (min 8)")
        uid = await state.db.create_user(payload.email.lower(), _hash(payload.password))
        if uid is None:
            raise HTTPException(status_code=409, detail="email già registrata")
        return {"id": uid, "email": payload.email.lower()}

    @api.delete("/users/{user_id}", status_code=204)
    async def delete_user(user_id: int, me: dict = Depends(require_auth)):
        if user_id == me["id"]:
            raise HTTPException(status_code=400, detail="non puoi eliminare il tuo account")
        if await state.db.count_users() <= 1:
            raise HTTPException(status_code=400, detail="non posso lasciare la dashboard senza utenti")
        ok = await state.db.delete_user(user_id)
        if not ok:
            raise HTTPException(status_code=404)
        return Response(status_code=204)

    # ---- IG auth --------------------------------------------------------

    def _ig_auth_payload() -> dict:
        if ig.auth_ready.is_set():
            return {"state": "authed", "username": ig.username}
        if ig.read_pending_sessionid() is not None:
            return {"state": "pending"}
        return {"state": "none"}

    @api.get("/auth/ig")
    async def get_ig_auth(_=Depends(require_auth)):
        return _ig_auth_payload()

    @api.post("/auth/ig")
    async def post_ig_auth(payload: IGAuthIn, _=Depends(require_auth)):
        sid = payload.sessionid.strip()
        if not sid:
            raise HTTPException(status_code=400, detail="sessionid vuoto")
        ig.set_pending_sessionid(sid)
        success, info = await ig.try_pending_login()
        if success:
            await state.add_event("info", f"Autenticato come @{info}")
            return {"state": "authed", "username": info}
        await state.add_event(
            "warn",
            f"Sessionid in retry (IG ha rifiutato adesso: {info}). Continuo in background.",
        )
        return {"state": "pending", "last_attempt_error": info}

    @api.delete("/auth/ig/pending")
    async def delete_ig_pending(_=Depends(require_auth)):
        ig.clear_pending_sessionid()
        return {"ok": True}

    # ---- targets --------------------------------------------------------

    @api.get("/targets")
    async def list_targets(_=Depends(require_auth)):
        return await state.get_targets_detailed()

    @api.post("/targets", status_code=201)
    async def add_target(payload: TargetIn, _=Depends(require_auth)):
        username = payload.username.strip().lstrip("@")
        if not username or " " in username or "/" in username:
            raise HTTPException(status_code=400, detail="username non valido")
        added = await state.add_target(username)
        if not added:
            raise HTTPException(status_code=409, detail="già presente")
        ig.reset_target_cache()
        return {"username": username}

    @api.delete("/targets/{username}", status_code=204)
    async def remove_target(username: str, _=Depends(require_auth)):
        ok = await state.remove_target(username.lstrip("@"))
        if not ok:
            raise HTTPException(status_code=404)
        return Response(status_code=204)

    # ---- pending posts --------------------------------------------------

    @api.get("/pending")
    async def list_pending(_=Depends(require_auth)):
        items = []
        for p in await state.all_pending():
            items.append({
                "pk": p.pk,
                "code": p.code,
                "target": p.target,
                "caption": p.caption,
                "media_type": p.media_type,
                "product_type": p.product_type,
                "media_urls": [_media_url(cfg, path) for path in p.media_paths],
                "instagram_url": f"https://www.instagram.com/p/{p.code}/",
            })
        return items

    @api.post("/pending/{pk}/approve")
    async def approve(pk: str, _=Depends(require_auth)):
        if not ig.auth_ready.is_set():
            raise HTTPException(
                status_code=409,
                detail="non autenticato su Instagram",
            )
        post = await state.get_pending(pk)
        if post is None:
            raise HTTPException(status_code=404)

        await state.add_history(
            pk=post.pk, target=post.target, code=post.code, action="approved"
        )

        async def _publish():
            try:
                caption = cfg.caption_template.format(
                    caption=post.caption or "", target=post.target
                )
                new_pk = await ig.repost(post, caption=caption)
            except Exception as e:
                log.exception("Repost failed for pk=%s", post.pk)
                await state.add_history(
                    pk=post.pk,
                    target=post.target,
                    code=post.code,
                    action="failed",
                    error=str(e),
                )
                await state.add_event(
                    "error", f"Pubblicazione fallita per {post.pk}: {e}"
                )
                return
            popped = await state.pop_pending(post.pk)
            await state.mark_seen(post.pk, post.target)
            if popped is not None:
                cleanup_media(popped)
            await state.add_history(
                pk=post.pk,
                target=post.target,
                code=post.code,
                action="published",
                new_pk=new_pk,
            )
            await state.add_event(
                "info", f"Pubblicato @{post.target}/{post.code} → {new_pk}"
            )

        asyncio.create_task(_publish())
        return {"status": "publishing"}

    @api.post("/pending/{pk}/reject", status_code=204)
    async def reject(pk: str, _=Depends(require_auth)):
        post = await state.pop_pending(pk)
        if post is None:
            raise HTTPException(status_code=404)
        await state.mark_seen(post.pk, post.target)
        cleanup_media(post)
        await state.add_history(
            pk=post.pk, target=post.target, code=post.code, action="rejected"
        )
        return Response(status_code=204)

    # ---- history & events ----------------------------------------------

    @api.get("/history")
    async def history(limit: int = 50, _=Depends(require_auth)):
        return await state.list_history(limit=min(max(limit, 1), 200))

    @api.get("/events")
    async def events(since: int = 0, _=Depends(require_auth)):
        return await state.list_events(since=since, limit=50)

    # ---- aggregate status ----------------------------------------------

    @api.get("/status")
    async def status_(_=Depends(require_auth)):
        targets = await state.get_targets_detailed()
        pending = await state.all_pending()
        return {
            "ig": _ig_auth_payload(),
            "target_count": len(targets),
            "pending_count": len(pending),
            "polling_interval": cfg.poll_interval,
        }

    # ---- media -----------------------------------------------------------

    @api.get("/media/{pk}/{filename}")
    async def media(pk: str, filename: str, _=Depends(require_auth)):
        base = cfg.media_dir / pk
        candidate = (base / filename).resolve()
        if not str(candidate).startswith(str(cfg.media_dir.resolve())):
            raise HTTPException(status_code=400)
        if not candidate.exists() or not candidate.is_file():
            raise HTTPException(status_code=404)
        return FileResponse(candidate)

    app.include_router(api)

    # ---- static SPA ------------------------------------------------------

    dist = cfg.web_dist
    assets_dir = dist / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(status_code=404)
        index = dist / "index.html"
        if not index.exists():
            return JSONResponse(
                status_code=503,
                content={
                    "error": "frontend not built",
                    "hint": f"web build missing at {dist}",
                },
            )
        return FileResponse(index)

    return app


async def bootstrap_admin(cfg: Config, state: State) -> None:
    """If no users exist yet, create the admin from env. Idempotent."""
    if await state.db.count_users() > 0:
        return
    uid = await state.db.create_user(cfg.admin_email, _hash(cfg.admin_password))
    if uid:
        log.info("Bootstrap admin user created: %s", cfg.admin_email)


def _media_url(cfg: Config, abs_path: str) -> str:
    p = Path(abs_path)
    try:
        rel = p.resolve().relative_to(cfg.media_dir.resolve())
    except ValueError:
        return ""
    parts = rel.parts
    if len(parts) < 2:
        return ""
    pk, filename = parts[0], parts[-1]
    return f"/api/media/{pk}/{filename}"
