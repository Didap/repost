"""Telegram bot: approval requests + remote auth + control."""
from __future__ import annotations

import logging
from pathlib import Path

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    InputMediaVideo,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from .config import Config
from .instagram_client import ALBUM, PHOTO, VIDEO, IGAuthError, InstagramClient
from .state import PendingPost, State, cleanup_media

log = logging.getLogger(__name__)

CB_APPROVE = "ok"
CB_REJECT = "no"
TG_CAPTION_LIMIT = 1000  # leave room for header


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _build_caption(post: PendingPost) -> str:
    url = f"https://www.instagram.com/p/{post.code}/"
    header = f"<b>@{post.target}</b> ha postato — <a href=\"{url}\">vedi originale</a>\n\n"
    body = _truncate(post.caption or "<i>(nessuna caption)</i>", TG_CAPTION_LIMIT)
    return header + body


def _keyboard(pk: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Pubblica", callback_data=f"{CB_APPROVE}:{pk}"),
                InlineKeyboardButton("❌ Scarta", callback_data=f"{CB_REJECT}:{pk}"),
            ]
        ]
    )


AUTH_INSTRUCTIONS = (
    "🔑 <b>Per autenticare il bot serve il tuo sessionid Instagram</b>\n\n"
    "1. Vai su <a href=\"https://www.instagram.com\">instagram.com</a> nel browser e fai login\n"
    "2. Apri DevTools (F12) → tab <b>Application</b> (Chrome) o <b>Storage</b> (Firefox)\n"
    "3. <b>Cookies → instagram.com</b> → trova la riga <code>sessionid</code> → copia il <b>Value</b>\n"
    "4. Mandami: <code>/auth INCOLLA_QUI_IL_SESSIONID</code>\n\n"
    "Il sessionid è privato — non condividerlo con nessun altro."
)


class TelegramBot:
    def __init__(self, cfg: Config, state: State, ig: InstagramClient):
        self._cfg = cfg
        self._state = state
        self._ig = ig
        self._app: Application = (
            Application.builder().token(cfg.tg_token).build()
        )
        self._app.add_handler(CommandHandler("start", self._cmd_start))
        self._app.add_handler(CommandHandler("status", self._cmd_status))
        self._app.add_handler(CommandHandler("pending", self._cmd_pending))
        self._app.add_handler(CommandHandler("auth", self._cmd_auth))
        self._app.add_handler(CallbackQueryHandler(self._on_callback))

    # ---------- public API used by orchestrator ----------

    async def start(self) -> None:
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)
        log.info("Telegram bot started")

    async def stop(self) -> None:
        await self._app.updater.stop()
        await self._app.stop()
        await self._app.shutdown()

    async def send_approval_request(self, post: PendingPost) -> None:
        bot = self._app.bot
        chat_id = self._cfg.tg_chat_id

        try:
            await self._send_media(post)
        except Exception as e:
            log.exception("Failed to send media to Telegram for pk=%s: %s", post.pk, e)
            await bot.send_message(
                chat_id=chat_id,
                text=f"⚠️ Non sono riuscito ad allegare il media del post {post.pk}: {e}",
            )

        msg = await bot.send_message(
            chat_id=chat_id,
            text=_build_caption(post),
            parse_mode=ParseMode.HTML,
            reply_markup=_keyboard(post.pk),
            disable_web_page_preview=True,
        )
        await self._state.update_pending_message(post.pk, msg.message_id)

    async def notify(self, text: str, *, html: bool = True) -> None:
        try:
            await self._app.bot.send_message(
                chat_id=self._cfg.tg_chat_id,
                text=text,
                parse_mode=ParseMode.HTML if html else None,
                disable_web_page_preview=True,
            )
        except Exception as e:
            log.warning("Failed to send notification: %s", e)

    async def request_auth(self) -> None:
        await self.notify(AUTH_INSTRUCTIONS)

    # ---------- internal ----------

    async def _send_media(self, post: PendingPost) -> None:
        bot = self._app.bot
        chat_id = self._cfg.tg_chat_id
        paths = [Path(p) for p in post.media_paths]

        if post.media_type == PHOTO:
            with paths[0].open("rb") as f:
                await bot.send_photo(chat_id=chat_id, photo=f)
        elif post.media_type == VIDEO:
            with paths[0].open("rb") as f:
                await bot.send_video(chat_id=chat_id, video=f)
        elif post.media_type == ALBUM:
            opens = [p.open("rb") for p in paths[:10]]
            try:
                media = []
                for p, fh in zip(paths, opens):
                    if p.suffix.lower() in (".mp4", ".mov"):
                        media.append(InputMediaVideo(fh))
                    else:
                        media.append(InputMediaPhoto(fh))
                await bot.send_media_group(chat_id=chat_id, media=media)
            finally:
                for fh in opens:
                    fh.close()

    async def _on_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query is None or query.data is None:
            return
        await query.answer()

        action, _, pk = query.data.partition(":")
        post = self._state.get_pending(pk)
        if post is None:
            await query.edit_message_text("⚠️ Questa richiesta non è più valida (riavvio?).")
            return

        if action == CB_APPROVE:
            await self._handle_approve(query, post)
        elif action == CB_REJECT:
            await self._handle_reject(query, post)

    async def _handle_approve(self, query, post: PendingPost) -> None:
        if not self._ig.auth_ready.is_set():
            await query.edit_message_text(
                text="⚠️ Sessione Instagram non valida. Manda <code>/auth &lt;sessionid&gt;</code> e riprova.",
                parse_mode=ParseMode.HTML,
            )
            return

        await query.edit_message_text(text=f"⏳ Pubblicazione in corso del post {post.pk}…")
        try:
            caption = self._cfg.caption_template.format(
                caption=post.caption or "", target=post.target
            )
            new_pk = await self._ig.repost(post, caption=caption)
        except Exception as e:
            log.exception("Repost failed for pk=%s", post.pk)
            await query.edit_message_text(
                text=f"❌ Pubblicazione fallita per {post.pk}: <code>{e}</code>",
                parse_mode=ParseMode.HTML,
            )
            return

        await self._state.pop_pending(post.pk)
        await self._state.mark_seen(post.pk)
        cleanup_media(post)
        await query.edit_message_text(
            text=(
                f"✅ Pubblicato come <code>{new_pk}</code>\n"
                f"Originale: @{post.target}/{post.code}"
            ),
            parse_mode=ParseMode.HTML,
        )

    async def _handle_reject(self, query, post: PendingPost) -> None:
        await self._state.pop_pending(post.pk)
        await self._state.mark_seen(post.pk)
        cleanup_media(post)
        await query.edit_message_text(
            text=f"❌ Scartato @{post.target}/{post.code}",
        )

    # ---------- commands ----------

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.id != self._cfg.tg_chat_id:
            return
        if self._ig.auth_ready.is_set():
            await update.message.reply_text(
                f"Bot attivo. Sto monitorando @{self._cfg.ig_target} "
                f"ogni {self._cfg.poll_interval}s e ti scrivo quando vedo un nuovo post."
            )
        else:
            await update.message.reply_text(
                AUTH_INSTRUCTIONS,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.id != self._cfg.tg_chat_id:
            return
        pending = self._state.all_pending()
        auth_status = (
            f"✅ Autenticato come @{self._ig.username}"
            if self._ig.auth_ready.is_set()
            else "⚠️ Non autenticato — manda /auth <sessionid>"
        )
        await update.message.reply_text(
            f"{auth_status}\n"
            f"Target: @{self._cfg.ig_target}\n"
            f"Pending: {len(pending)}\n"
            f"Polling: {self._cfg.poll_interval}s"
        )

    async def _cmd_pending(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.id != self._cfg.tg_chat_id:
            return
        pending = self._state.all_pending()
        if not pending:
            await update.message.reply_text("Nessun post in attesa.")
            return
        for post in pending:
            await self.send_approval_request(post)

    async def _cmd_auth(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.id != self._cfg.tg_chat_id:
            return
        if not context.args:
            await update.message.reply_text(
                AUTH_INSTRUCTIONS,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
            return

        sessionid = " ".join(context.args).strip()
        # try to delete the message so the sessionid doesn't sit visible in the chat
        try:
            await update.message.delete()
        except Exception:
            pass

        progress = await self._app.bot.send_message(
            chat_id=self._cfg.tg_chat_id, text="⏳ Verifico il sessionid…"
        )
        try:
            username = await self._ig.login_with_sessionid(sessionid)
        except IGAuthError as e:
            await progress.edit_text(f"❌ {e}")
            return
        except Exception as e:
            log.exception("Unexpected error during /auth")
            await progress.edit_text(f"❌ Errore inatteso: <code>{e}</code>", parse_mode=ParseMode.HTML)
            return

        await progress.edit_text(
            text=f"✅ Autenticato come <b>@{username}</b>. Polling attivo.",
            parse_mode=ParseMode.HTML,
        )
