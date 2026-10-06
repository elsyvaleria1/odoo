import hashlib
import logging
import re
from typing import Any, Self

import psycopg

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.libs.json import dumps as json_dumps

from ..tools import errors, get_telegram_client, replay
from ..tools import format as tools_format
from ..tools import keyboard as kb
from ..tools.authority import keeping, operating
from ..tools.dispatch import translation_env

_logger = logging.getLogger(__name__)

_TOKEN_UNREADABLE = object()

_TOKEN_RE = re.compile(r"^\d+:[A-Za-z0-9_-]+$")


class TelegramBot(models.Model):
    _name = "telegram.bot"
    _description = "Telegram Bot Configuration"
    _inherit = ["mixin.credential.holder"]
    _credential_purpose = "telegram_bot:token"
    _check_company_auto = True

    name = fields.Char(required=True)
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        index=True,
        required=True,
        help="The company this bot speaks for: what it reads and files is that "
        "company's, whoever the update runs as.",
    )
    credential_id = fields.Many2one(
        comodel_name="credential.credential",
        required=True,
        domain="[('endpoint_id.code', '=', 'telegram')]",
        ondelete="restrict",
        help="API Transport credential for Telegram Bot API. "
        "The credential must contain the bot token in the bearer_token field.",
    )
    lang = fields.Selection(
        selection=lambda self: self.env["res.lang"].get_installed(),
        string="Language",
        default=lambda self: self.env.company.partner_id.lang or self.env.lang,
        help="Language the bot answers in when the chat has no linked contact "
        "with a language of its own, or always when Always Answer in the "
        "Bot's Language is set.",
    )
    answer_in_bot_lang = fields.Boolean(
        string="Always Answer in the Bot's Language",
        help="Answer every chat in the bot's language, whatever language its "
        "linked contact has. Off, a linked contact's language comes first.",
    )
    bot_username = fields.Char(
        copy=False,
        readonly=True,
        help="The bot's @username, read from Telegram when the webhook is "
        "registered. A link that opens the bot (t.me) needs it.",
    )
    can_join_groups = fields.Boolean(
        copy=False,
        readonly=True,
    )
    can_read_all_group_messages = fields.Boolean(
        copy=False,
        readonly=True,
        help="Off while the bot's privacy mode is on: in a group it then sees "
        "only commands and replies to it.",
    )
    idle_text_handler = fields.Selection(
        selection=lambda self: self.env["telegram.router"]._intake_selection("text"),
        help="The feature that takes a text message sent outside any flow, when "
        "several could. Empty: the one with the lowest priority.",
    )
    idle_voice_handler = fields.Selection(
        selection=lambda self: self.env["telegram.router"]._intake_selection("voice"),
        help="The feature that takes a voice note sent outside any flow.",
    )
    idle_media_handler = fields.Selection(
        selection=lambda self: self.env["telegram.router"]._intake_selection("photo"),
        help="The feature that takes a photo or document sent outside any flow.",
    )
    legacy_secretless_webhook = fields.Boolean(
        copy=False,
        readonly=True,
        groups="base.group_system",
        help="This bot existed before webhook secrets were enforced and was never "
        "registered with one, so its updates are still accepted without a secret. "
        "Register Webhook gives it a secret and ends that.",
    )
    chat_ids = fields.One2many(
        comodel_name="telegram.chat",
        inverse_name="bot_id",
    )
    command_ids = fields.Many2many(
        comodel_name="telegram.command",
        help="Additional commands that this bot should respond to.",
    )
    token_hash = fields.Char(
        compute="_compute_token_hash",
        store=True,
        index=True,
        copy=False,
        help="SHA256 of the bot token, used to resolve the webhook URL to this bot. "
        "Recomputed whenever the credential or the token behind it changes.",
    )
    token_masked = fields.Char(
        compute="_compute_token_masked",
        groups="base.group_system",
        help="Masked version of the bot token for verification. Shows bot ID and last 4 characters only.",
    )

    _credential_uniq = models.Constraint(
        "UNIQUE (credential_id)",
        "Each credential can only be used by one bot!",
    )
    _token_hash_uniq = models.Constraint(
        "UNIQUE (token_hash)",
        "Token hash must be unique (duplicate bot token detected)!",
    )

    def write(self, vals):
        result = super().write(vals)
        if "company_id" in vals or "credential_id" in vals:
            for bot in keeping(self):
                if bot.credential_id.company_id != bot.company_id:
                    bot.credential_id.company_id = bot.company_id
        return result

    @api.constrains("credential_id")
    def _check_credential_is_for_telegram(self) -> None:
        for bot in self:
            if bot.credential_id.endpoint_id.code != "telegram":
                raise ValidationError(
                    self.env._(
                        "The credential of bot %(bot)s must belong to the "
                        "Telegram service.",
                        bot=bot.name,
                    )
                )

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    @api.private
    @api.model
    def find_by_token(self, token: str) -> Self:
        return self.search([("token_hash", "=", self._hash_token(token))], limit=1)

    def _read_token(self):
        """Return the token, False when there is no token to read, or
        _TOKEN_UNREADABLE when a credential exists but could not be decrypted.

        The caller has to tell those last two apart: "no token" means the hash
        should go, "could not read it" must never be allowed to.

        An archived credential counts as no token: telegram.bot has no active
        field of its own and credential_id is required with ondelete=restrict,
        so archiving the
        credential is the only non-destructive way to take a bot off the air.
        """
        self.check_singleton()
        if not self.credential_id or not keeping(self).credential_id.active:
            return False
        try:
            return self._get_held_main_secret("bearer_token")
        except UserError as e:
            _logger.warning(
                "Could not read the token of bot '%s': %s",
                self.name,
                e,
            )
            return _TOKEN_UNREADABLE

    def _stored_token_hashes(self) -> dict:
        """Read token_hash straight from the table.

        Inside its own compute the field is flagged for recomputation, so
        reading it through the ORM would recurse.
        """
        ids = [record.id for record in self if isinstance(record.id, int)]
        if not ids:
            return {}
        self.env.cr.execute(
            "SELECT id, token_hash FROM telegram_bot WHERE id = ANY(%s)",
            (ids,),
        )
        return dict(self.env.cr.fetchall())

    @api.depends("credential_id", "credential_id.active", "credential_id.bearer_token")
    def _compute_token_hash(self) -> None:
        stored = None
        for record in self:
            token = record._read_token()
            if token is not _TOKEN_UNREADABLE:
                record.token_hash = self._hash_token(token) if token else False
                continue

            # A transient decrypt failure -- a rate limit, a key not in the
            # environment yet -- used to be flattened to False and stored, and
            # find_by_token stopped resolving. The webhook answers 200 to
            # everything, so Telegram never retries and the bot went silently
            # mute until someone wrote to the credential again.
            if stored is None:
                stored = self._stored_token_hashes()
            record.token_hash = stored.get(record.id, False)
            _logger.warning(
                "Keeping the stored token_hash of bot '%s': its credential "
                "could not be read right now",
                record.name,
            )

    @api.depends("credential_id", "credential_id.active", "credential_id.bearer_token")
    def _compute_token_masked(self) -> None:
        for record in self:
            token = record._read_token()
            if not token or token is _TOKEN_UNREADABLE:
                record.token_masked = False
            elif ":" in token:
                bot_id, secret = token.split(":", 1)
                record.token_masked = (
                    f"{bot_id}:***...{secret[-4:]}"
                    if len(secret) > 4
                    else f"{bot_id}:****"
                )
            elif len(token) > 8:
                record.token_masked = f"{token[:4]}***...{token[-4:]}"
            else:
                record.token_masked = "********"

    def action_register_webhook(self) -> dict:
        # Telegram is told the new secret before the bot row is written; a
        # reader refused only at that write would already have replaced it.
        self.check_access("write")
        for bot in self:
            bot._update_webhook_secret_if_inactive()
            # refuses a bot whose credential is archived or holds no token
            token = bot._get_bot_token()
            if bot.token_hash != self._hash_token(token):
                # the URL names the token's hash: one stored before the token
                # was readable would send Telegram's updates to no bot
                self.env.add_to_compute(self._fields["token_hash"], bot)
                bot.flush_recordset(["token_hash"])
            bot._get_telegram_client().set_webhook(
                f"{bot.get_base_url()}/telegram/webhook/{bot.token_hash}",
                bot._webhook_secret(),
            )
            bot.legacy_secretless_webhook = False
            bot._read_identity()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "message": self.env._(
                    "Telegram now delivers updates with the webhook secret."
                ),
            },
        }

    def _read_identity(self) -> None:
        """Store what Telegram says the bot is (getMe)."""
        self.check_singleton()
        response = self._get_telegram_client().get_me()
        me = (
            response.get("result")
            if isinstance(response, dict) and response.get("ok")
            else None
        )
        if not isinstance(me, dict):
            _logger.warning("getMe answered nothing usable for bot %s", self.id)
            return
        self.write(
            {
                "bot_username": me.get("username") or False,
                "can_join_groups": bool(me.get("can_join_groups")),
                "can_read_all_group_messages": bool(
                    me.get("can_read_all_group_messages")
                ),
            }
        )

    def _is_chat_administrator(self, chat, tg_user_id) -> bool:
        """Whether Telegram says the user administers the group."""
        self.check_singleton()
        try:
            member = self._get_telegram_client().call(
                "getChatMember", {"chat_id": chat.chat_id, "user_id": int(tg_user_id)}
            )
        except errors.TelegramApiError as error:
            _logger.info("getChatMember failed in chat %s: %s", chat.id, error)
            return False
        return (member or {}).get("status") in ("creator", "administrator")

    def _admits_user(self, user) -> bool:
        """Whether `user` may act through this bot: an internal user only as a
        member of the company the bot speaks for, a portal or public user
        always, on their own contact's data."""
        self.check_singleton()
        if user.share:
            return True
        return self.company_id.id in self.env(user=user.id).user._get_company_ids()

    @api.model
    def _serving(self, handler_name) -> Self:
        """The bots that run a feature: those its handler is enabled on."""
        handler = self.env[handler_name]
        return operating(self).search([]).filtered(handler._feature_enabled)

    def _idle_handler_name(self, kind):
        self.check_singleton()
        return {
            "text": self.idle_text_handler,
            "voice": self.idle_voice_handler,
            "photo": self.idle_media_handler,
            "document": self.idle_media_handler,
        }.get(kind) or False

    def _deep_link(self, token=None, *, group=False) -> str | None:
        self.check_singleton()
        if not self.bot_username:
            return None
        if not token:
            return f"https://t.me/{self.bot_username}"
        return f"https://t.me/{self.bot_username}?{'startgroup' if group else 'start'}={token}"

    def _mini_app_url(self, path) -> str | None:
        """The absolute URL of a Mini App page, or None off https: Telegram
        refuses a web_app button on http, and the whole message with it."""
        self.check_singleton()
        base_url = self.get_base_url() or ""
        if not base_url.startswith("https://"):
            _logger.info(
                "Base URL %r is not https: no Mini App button for %s", base_url, path
            )
            return None
        return f"{base_url.rstrip('/')}/{path.lstrip('/')}"

    def _telegram_id(self) -> str:
        # the token's public half: who the bot is on Telegram, never its secret
        try:
            return self._get_bot_token().partition(":")[0]
        except ValueError:
            return f"#{self.id}"

    def _get_bot_token(self) -> str:
        self.check_singleton()

        if not keeping(self).credential_id.active:
            raise ValueError(
                f"Bot '{self.name}' has an archived credential: it is off the "
                f"air on purpose. Unarchive the credential to send again."
            )

        token = self._get_held_main_secret("bearer_token")
        if not token:
            raise ValueError(
                f"Bot '{self.name}' credential has no bearer_token configured."
            )

        if not _TOKEN_RE.match(token):
            raise ValueError(
                f"Bot '{self.name}' has invalid Telegram token format. "
                f"Expected format: {{bot_id}}:{{auth_token}} "
                f"(e.g., 123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw)"
            )

        return token

    def _get_telegram_client(self) -> Any:
        self.check_singleton()

        def get_telegram_client_uncached():
            return get_telegram_client(
                self.env,
                bot_token=self._get_bot_token(),
                credential_id=self.credential_id.id,
                company_id=self.company_id.id,
            )

        return replay.memo(
            ("telegram-client", self.id, id(self.env.cr)), get_telegram_client_uncached
        )

    def _track_outbound_message(
        self,
        chat_id: str,
        media_type: str = "text",
        text: str | None = None,
        caption: str | None = None,
    ) -> Any:
        self.check_singleton()

        # Sending knows the chat id and nothing else -- not the chat's type,
        # not who is on the other end -- so a chat first seen here records no
        # identity, and cannot later prove one: `speaks_for_partner` stays
        # False for it forever and `_can_auto_link` never fires. That is the
        # shape every bot-first notification creates.
        #
        # It is deliberate, not an oversight, and the readers are built for
        # it: the webhook serves such a chat as unlinked, and
        # `_mini_app_user` refuses it for the same reason. Anything new that
        # reads an identity off a chat has to keep that bar -- linking a
        # `partner_id` here by hand does not clear it.
        chat = operating(self.env["telegram.chat"])._acquire_chat(chat_id, self.id)

        vals = {
            "bot_id": self.id,
            "chat_id": chat.id,
            "message_type": "outbound",
            "media_type": media_type,
            "state": "outgoing",
        }
        if text:
            vals["text"] = text
        if caption:
            vals["caption"] = caption

        return operating(self.env["telegram.message"]).create(vals)

    def _send_tracked(
        self,
        chat_id: str,
        api_method: str,
        media_type: str,
        tracking: dict,
        call,
    ) -> dict[str, Any] | bool:
        self.check_singleton()
        telegram_message = self._track_outbound_message(chat_id, media_type, **tracking)

        try:
            response = replay.remember(api_method, (str(chat_id), tracking), call)
        except psycopg.Error:
            # The call reaches Telegram through the ORM, so it also touches the
            # rate limit bucket and the credential usage counters. A database
            # error there is never a delivery failure, and the transaction it
            # aborted cannot carry the write below: let it reach the retry loop.
            _logger.warning(
                "Database error while running %s for chat %s, not recording it "
                "as a delivery failure",
                api_method,
                chat_id,
            )
            raise
        except Exception as e:
            telegram_message.write({"state": "error", "error_message": str(e)[:255]})
            _logger.exception("Failed to run %s for chat %s", api_method, chat_id)
            return False

        if response and response.get("ok"):
            self._record_delivery(
                telegram_message,
                {
                    "state": "sent",
                    "msg_uid": str(response.get("result", {}).get("message_id")),
                },
            )
        else:
            error_msg = (
                response.get("description", "Unknown error")
                if response
                else "No response"
            )
            telegram_message.write({"state": "error", "error_message": error_msg[:255]})
            _logger.error(
                "Telegram refused %s for chat %s of bot %s: %s",
                api_method,
                chat_id,
                self._telegram_id(),
                error_msg,
            )
            return False

        return response

    def _record_delivery(self, telegram_message, vals) -> None:
        try:
            with self.env.cr.savepoint():
                telegram_message.write(vals)
        except psycopg.errors.UniqueViolation:
            _logger.warning(
                "Telegram returned message id %s again for chat %s; keeping the "
                "outbound row without it",
                vals.get("msg_uid"),
                telegram_message.chat_id.chat_id,
            )
            telegram_message.write({**vals, "msg_uid": False})

    def _queue_text(
        self,
        chat,
        text,
        *,
        reply_markup=None,
        reply_to=None,
        silent=False,
        eta=None,
        html=True,
        **vals,
    ):
        """Queue Telegram HTML (or, `html=False`, plain text) for `chat` through
        the outbox; the ledger row it returns records what becomes of it."""
        self.check_singleton()
        payload = {
            "text": tools_format.truncate(text)
            if html
            else text[: tools_format.MESSAGE_LIMIT],
            "link_preview_options": json_dumps({"is_disabled": True}),
        }
        if html:
            payload["parse_mode"] = "HTML"
        if reply_markup:
            payload["reply_markup"] = reply_markup
        if silent:
            payload["disable_notification"] = True
        return self.env["telegram.message"]._queue(
            self,
            chat,
            "sendMessage",
            payload,
            eta=eta,
            text=text,
            media_type="text",
            reply_to_uid=reply_to or False,
            **vals,
        )

    def _queue_phone_request(self, chat, text):
        """Ask the person of a private chat to share their own number: `text`
        says why, the keyboard's one button shares it."""
        self.check_singleton()
        button = translation_env(self, chat)._("📱 Share my phone number")
        return self._queue_text(
            chat, text, html=False, reply_markup=kb.share_phone(button)
        )

    def _queue_file(
        self,
        chat,
        attachment,
        *,
        caption=None,
        reply_to=None,
        silent=False,
        eta=None,
        **vals,
    ):
        """Queue an attachment: an image as a photo, anything else as a
        document."""
        self.check_singleton()
        is_photo = (attachment.mimetype or "").startswith(
            "image/"
        ) and attachment.file_size < 10 * 1024 * 1024
        payload = {}
        if caption:
            payload["caption"] = tools_format.truncate(
                caption, tools_format.CAPTION_LIMIT
            )
            payload["parse_mode"] = "HTML"
        if silent:
            payload["disable_notification"] = True
        return self.env["telegram.message"]._queue(
            self,
            chat,
            "sendPhoto" if is_photo else "sendDocument",
            payload,
            eta=eta,
            caption=caption,
            media_type="photo" if is_photo else "document",
            attachment_id=attachment.id,
            reply_to_uid=reply_to or False,
            **vals,
        )

    @api.private
    def send_message(
        self,
        chat_id: str,
        text: str,
        reply_markup: dict | None = None,
        parse_mode: str | None = "HTML",
    ) -> dict[str, Any] | bool:
        self.check_singleton()
        return self._send_tracked(
            chat_id,
            "sendMessage",
            "text",
            {"text": text},
            lambda: self._get_telegram_client().send_message(
                chat_id, text, parse_mode=parse_mode, reply_markup=reply_markup
            ),
        )

    @api.private
    def send_document(
        self,
        chat_id: str,
        document_content: bytes,
        filename: str,
        caption: str | None = None,
        parse_mode: str | None = "HTML",
    ) -> dict[str, Any] | bool:
        self.check_singleton()
        return self._send_tracked(
            chat_id,
            "sendDocument",
            "document",
            {"caption": caption},
            lambda: self._get_telegram_client().send_document(
                chat_id, document_content, filename, caption, parse_mode=parse_mode
            ),
        )

    def get_lang(self, chat=None) -> str:
        """Language to answer ``chat`` in: the bot's when it always answers in
        its own, else the linked contact's, else the bot's, else the current
        environment's."""
        self.check_singleton()
        if self.answer_in_bot_lang and self.lang:
            return self.lang
        return (chat and chat.partner_id.lang) or self.lang or self.env.lang

    @api.private
    def get_file(self, file_id: str) -> dict[str, Any] | bool:
        """``{"content": bytes, "file_path": str}`` for a Telegram file id.

        ``file_path`` is the name Telegram gives the stored file
        (``photos/file_12.jpg``); a message sent as a document carries its
        original name in the message itself, not here.
        """
        self.check_singleton()

        def _download():
            client = self._get_telegram_client()
            file_info = client.get_file(file_id)
            if not file_info or not file_info.get("ok"):
                raise ValueError(f"Could not get file info for file_id: {file_id}")
            file_path = file_info["result"]["file_path"]
            return {"content": client.download_file(file_path), "file_path": file_path}

        try:
            result = replay.remember("getFile", file_id, _download)
            _logger.info(
                "File '%s' downloaded (%d bytes) for bot '%s'.",
                result["file_path"],
                len(result["content"]),
                self.name,
            )
            return result

        except Exception:
            _logger.exception("Failed to download file for bot '%s'", self.name)
            return False

    @api.private
    def get_file_content(self, file_id: str) -> bytes | bool:
        """The bytes of a Telegram file, or False.

        `get_file` already does exactly this and hands back the stored name
        as well; this is that answer without the name. Written the other way
        round, the two downloaded the same file through the same two Telegram
        calls twice over, and recorded the result under the same replay key
        with two different shapes.

        `if result else False` carries the failure contract: `get_file`
        answers False, and subscripting that would raise where this used to
        return False.
        """
        self.check_singleton()
        result = self.get_file(file_id)
        return result["content"] if result else False

    @api.private
    def answer_callback_query(
        self,
        callback_query_id: str,
        text: str | None = None,
        show_alert: bool = False,
    ) -> dict[str, Any] | bool:
        self.check_singleton()
        replay.note_callback_answered(callback_query_id)

        try:
            return replay.remember(
                "answerCallbackQuery",
                (callback_query_id, text, show_alert),
                lambda: self._get_telegram_client().answer_callback_query(
                    callback_query_id, text=text, show_alert=show_alert
                ),
            )

        except Exception:
            _logger.exception(
                "Failed to answer callback query %s",
                callback_query_id,
            )
            return False

    @api.private
    def send_chat_action(self, chat, action="typing", thread_uid=None):
        """Show `action` in the chat (or one forum topic of it) while the bot
        works; ephemeral, so sent now and never queued or ledgered, and a
        failure only logged."""
        self.check_singleton()
        payload = {"chat_id": chat.chat_id, "action": action}
        if thread_uid:
            payload["message_thread_id"] = int(thread_uid)
        try:
            return replay.remember(
                "sendChatAction",
                (str(chat.chat_id), action, thread_uid or ""),
                lambda: self._get_telegram_client().call("sendChatAction", payload),
            )
        except Exception:
            _logger.info("Chat action %s not shown in chat %s", action, chat.id)
            return False

    @api.private
    def edit_message_reply_markup(
        self, chat_id: str, message_id: int, reply_markup: dict | None = None
    ) -> dict[str, Any] | bool:
        self.check_singleton()
        try:
            return replay.remember(
                "editMessageReplyMarkup",
                (str(chat_id), message_id, reply_markup),
                lambda: self._get_telegram_client().edit_message_reply_markup(
                    chat_id, message_id, reply_markup=reply_markup
                ),
            )
        except Exception:
            _logger.exception(
                "Failed to edit message reply markup for chat %s",
                chat_id,
            )
            return False
