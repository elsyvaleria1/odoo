import hashlib
import logging
import re
from typing import Any, Self

import psycopg

from odoo import Command, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Domain
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
        help="The company that owns this bot: its token, its receivers and the "
        "log of its calls to Telegram are this company's. It is always one of "
        "the companies the bot serves.",
    )
    moved_to_id = fields.Many2one(
        comodel_name="telegram.bot",
        index="btree_not_null",
        ondelete="set null",
        help="A bot its people moved away from: it answers every private "
        "message and button with a link to this one, offers no command and "
        "delivers no notification.",
    )
    company_ids = fields.Many2many(
        comodel_name="res.company",
        relation="telegram_bot_res_company_rel",
        string="Serves Companies",
        help="The companies whose people act through this bot, each in the "
        "company of what they do: a record's own, or the one they choose for "
        "what they start when they belong to several.",
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
    on_air = fields.Boolean(
        compute="_compute_on_air",
        store=True,
        index=True,
        copy=False,
        help="The bot can send: its credential is set and not archived. Archiving "
        "the credential takes a bot off the air on purpose; no notification, "
        "push or connect link is routed to a bot that is off the air.",
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

    @api.constrains("moved_to_id")
    def _check_moved_to(self) -> None:
        for bot in self:
            target = bot.moved_to_id
            if target and (target == bot or target.moved_to_id):
                raise ValidationError(
                    self.env._("A bot moves to a bot that has not moved itself.")
                )

    @api.model_create_multi
    def create(self, vals_list):
        bots = super().create(vals_list)
        bots._serve_own_company()
        return bots

    def write(self, vals):
        moving = (
            keeping(self).filtered(lambda bot: bot.company_ids == bot.company_id)
            if "company_id" in vals and "company_ids" not in vals
            else self.browse()
        )
        result = super().write(vals)
        for bot in moving:
            bot.company_ids = bot.company_id
        if vals.keys() & {"company_id", "company_ids"}:
            self._serve_own_company()
        if "company_id" in vals or "credential_id" in vals:
            for bot in keeping(self):
                if bot.credential_id.company_id != bot.company_id:
                    bot.credential_id.company_id = bot.company_id
        if vals.keys() & self._command_menu_fields():
            operating(self).chat_ids._sync_command_menu()
        return result

    def _serve_own_company(self) -> None:
        for bot in keeping(self):
            if bot.company_id not in bot.company_ids:
                bot.company_ids = [Command.link(bot.company_id.id)]

    @api.model
    def _command_menu_fields(self) -> set:
        return {
            "command_ids",
            "company_id",
            "company_ids",
            "lang",
            "answer_in_bot_lang",
            "moved_to_id",
        }

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
        ids = [record.id for record in self if isinstance(record.id, int)]
        if not ids:
            return {}
        self.env.cr.execute(
            "SELECT id, token_hash FROM telegram_bot WHERE id = ANY(%s)",
            (ids,),
        )
        return dict(self.env.cr.fetchall())

    @api.depends("credential_id", "credential_id.active")
    def _compute_on_air(self) -> None:
        for bot in self:
            bot.on_air = bool(keeping(bot).credential_id.active)

    @api.model
    def _get_delivering_domain(self) -> Domain:
        return Domain("moved_to_id", "=", False) & Domain("on_air", "=", True)

    def _handle_on_air_change(self) -> None:
        return

    @api.depends("credential_id", "credential_id.active", "credential_id.bearer_token")
    def _compute_token_hash(self) -> None:
        stored = None
        for record in self:
            token = record._read_token()
            if token is not _TOKEN_UNREADABLE:
                record.token_hash = self._hash_token(token) if token else False
                continue

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
        self.check_access("write")
        for bot in self:
            bot._update_webhook_secret_if_inactive()
            token = bot._get_bot_token()
            if bot.token_hash != self._hash_token(token):
                self.env.add_to_compute(self._fields["token_hash"], bot)
                bot.flush_recordset(["token_hash"])
            bot._get_telegram_client().set_webhook(
                f"{bot.get_base_url()}/telegram/webhook/{bot.token_hash}",
                bot._webhook_secret(),
            )
            bot.legacy_secretless_webhook = False
            bot._read_identity()
            bot._publish_default_command_menu()
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

    def _publish_default_command_menu(self) -> None:
        self.check_singleton()
        chat = self.env["telegram.chat"]
        lang = self.lang or "en_US"
        menu = [
            {
                "command": command.removeprefix("/"),
                "description": spec.description.translate(lang),
            }
            for command, spec in self.env["telegram.router"]._available_commands(
                self, chat, self.env["res.partner"], self.env["res.users"]
            )
            if spec.description
        ]
        try:
            self._get_telegram_client().call("setMyCommands", {"commands": menu})
        except errors.TelegramApiError as error:
            _logger.warning("setMyCommands failed for bot %s: %s", self.id, error)

    def _is_chat_administrator(self, chat, tg_user_id) -> bool:
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
        self.check_singleton()
        return bool(user.share or self._served_companies(user))

    def _served_companies(self, user):
        self.check_singleton()
        served = keeping(self).company_ids.with_env(self.env)
        if user.share:
            return served
        member_of = set(self.env(user=user.id).user._get_company_ids())
        served = served.filtered(lambda company: company.id in member_of)
        return (served & user.company_id) | served

    def _acting_company(self):
        self.check_singleton()
        served = keeping(self).company_ids
        pinned = self.env.context.get("telegram_company_id")
        if pinned in served.ids:
            return self.env["res.company"].browse(pinned)
        if not self.env.user.share and self.env.company in served:
            return self.env.company
        return self.company_id

    @api.model
    def _serving(self, handler_name) -> Self:
        handler = self.env[handler_name]
        return (
            operating(self)
            .search(self._get_delivering_domain())
            .filtered(handler._feature_enabled)
        )

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
        self.check_singleton()
        base_url = self.get_base_url() or ""
        if not base_url.startswith("https://"):
            _logger.info(
                "Base URL %r is not https: no Mini App button for %s", base_url, path
            )
            return None
        return f"{base_url.rstrip('/')}/{path.lstrip('/')}"

    def _telegram_id(self) -> str:
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

    def _queue_reaction(self, chat, message_id, emoji="👍"):
        self.check_singleton()
        return self.env["telegram.message"]._queue(
            self,
            chat,
            "setMessageReaction",
            {
                "message_id": int(message_id),
                "reaction": json_dumps([{"type": "emoji", "emoji": emoji}]),
            },
        )

    def _queue_phone_request(self, chat, text):
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
        self.check_singleton()
        if self.answer_in_bot_lang and self.lang:
            return self.lang
        app_lang = (
            chat and chat.chat_type == "private" and operating(chat).account_id._lang()
        )
        return app_lang or (chat and chat.partner_id.lang) or self.lang or self.env.lang

    @api.private
    def get_file(self, file_id: str) -> dict[str, Any] | None:
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
            return None

    @api.private
    def get_file_content(self, file_id: str) -> bytes | None:
        self.check_singleton()
        result = self.get_file(file_id)
        return result["content"] if result else None

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
