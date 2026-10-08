import logging
from datetime import timedelta

from odoo import SUPERUSER_ID, api, fields, models
from odoo.exceptions import RetryableJobError
from odoo.libs.json import dumps as json_dumps
from odoo.models import GC_UNLINK_LIMIT
from odoo.tools import frozendict

from ..tools import errors
from ..tools import format as tools_format
from ..tools.authority import operating

_logger = logging.getLogger(__name__)

# Telegram's documented ceiling for one bot: about 30 messages a second.
_BOT_SENDS_PER_SECOND = 30


class TelegramMessage(models.Model):
    _name = "telegram.message"
    _description = "Telegram Message"
    _order = "id desc"

    _ACTIVE_THRESHOLD_DAYS = 15
    _FAILED_THRESHOLD_DAYS = 90
    _access_anchors = frozendict(
        {
            "partner": "chat_id.account_id.partner_id",
        }
    )

    chat_id = fields.Many2one(
        comodel_name="telegram.chat",
        index=True,
        required=True,
        ondelete="cascade",
        help="Chat session this message belongs to",
    )
    bot_id = fields.Many2one(
        comodel_name="telegram.bot",
        index=True,
        required=True,
        help="Bot that sent or received this message",
    )

    display_name = fields.Char(
        compute="_compute_display_name",
        store=True,
        help="Computed display name with message preview",
    )
    msg_uid = fields.Char(
        string="Telegram Message ID",
        index=True,
        help="Unique message ID from Telegram API",
    )

    text = fields.Text(help="Full text content of the message")
    command = fields.Char(help="Command name if message is a command (e.g., /start)")

    message_type = fields.Selection(
        selection=[
            ("outbound", "Outbound"),
            ("inbound", "Inbound"),
        ],
        string="Type",
        default="outbound",
        required=True,
        help="Direction of message flow",
    )
    state = fields.Selection(
        selection=[
            ("outgoing", "In Queue"),
            ("sending", "Sending"),
            ("sent", "Sent"),
            ("uncertain", "Outcome Unknown"),
            ("cancelled", "Not Needed"),
            ("error", "Failed"),
            ("received", "Received"),
        ],
        string="Status",
        default="outgoing",
        help="Delivery status of the message",
    )
    error_message = fields.Char(help="Error details if message failed to send")
    error_class = fields.Char(
        help="What the failure meant: the tools.errors class it was raised as."
    )
    api_method = fields.Char(
        string="Bot API Method",
        help="The Bot API method a queued message is sent with.",
    )
    payload = fields.Json(
        help="The call's parameters, the chat id aside: the chat's current id "
        "is read when it is sent, so a group that became a supergroup is still "
        "reached.",
    )
    attachment_id = fields.Many2one(
        comodel_name="ir.attachment",
        index="btree_not_null",
        ondelete="set null",
        help="The file a queued photo or document sends.",
    )
    attempts = fields.Integer(
        default=0,
        readonly=True,
    )
    reply_to_uid = fields.Char(
        string="Answers Message",
        help="The Telegram message this one answers, in the same chat.",
    )
    thread_uid = fields.Char(
        string="Topic",
        help="The forum topic of a supergroup the message is in.",
    )
    target_id = fields.Many2one(
        comodel_name="telegram.message",
        index="btree_not_null",
        ondelete="cascade",
        help="The message an edit or a deletion applies to.",
    )

    media_type = fields.Selection(
        selection=[
            ("text", "Text"),
            ("photo", "Photo"),
            ("video", "Video"),
            ("audio", "Audio"),
            ("voice", "Voice Note"),
            ("document", "Document"),
        ],
        default="text",
        help="Type of media content in this message",
    )
    caption = fields.Text(help="Caption text for media messages")

    _msg_uid_uniq = models.UniqueIndex(
        "(bot_id, chat_id, msg_uid) WHERE msg_uid IS NOT NULL",
        "Telegram message ID must be unique per chat!",
    )

    @api.depends("text", "caption", "message_type", "media_type")
    def _compute_display_name(self):
        media_icons = {
            "text": "",
            "photo": "📷 ",
            "video": "🎥 ",
            "audio": "🎵 ",
            "voice": "🎤 ",
            "document": "📄 ",
        }

        for message in self:
            icon = media_icons.get(message.media_type, "")

            content = message.caption or message.text

            if content:
                preview = content[:50]
                if len(content) > 50:
                    preview += "..."
                message.display_name = f"{icon}[{message.message_type}] {preview}"
            elif message.media_type and message.media_type != "text":
                media_label = dict(
                    message._fields["media_type"]._description_selection(message.env)
                ).get(message.media_type, message.media_type)
                message.display_name = f"{icon}[{message.message_type}] {media_label}"
            else:
                message.display_name = f"[{message.message_type}] Message {message.id}"

    @api.model
    def _gc_removable_domain(self, now) -> list:
        delivered_before = now - timedelta(days=self._ACTIVE_THRESHOLD_DAYS)
        failed_before = now - timedelta(days=self._FAILED_THRESHOLD_DAYS)
        return [
            "|",
            "&",
            ("create_date", "<", delivered_before),
            ("state", "in", ["sent", "received"]),
            "&",
            ("create_date", "<", failed_before),
            ("state", "in", ["error", "outgoing", "uncertain", "cancelled"]),
        ]

    @api.autovacuum
    def _gc_telegram_messages(self) -> tuple[int, bool]:
        old_messages = self.search(
            self._gc_removable_domain(fields.Datetime.now()),
            limit=GC_UNLINK_LIMIT,
        )

        count = len(old_messages)
        if count > 0:
            _logger.info(
                "Auto-vacuum: Removing %s old telegram messages",
                count,
            )
            old_messages.unlink()
        else:
            _logger.debug("Auto-vacuum: No old messages to remove")

        return count, count == GC_UNLINK_LIMIT

    @api.job(channel="telegram_outbound", max_retries=8, max_defers=200)
    def _deliver(self):
        """Send one queued message, exactly once or visibly not.

        Telegram has no idempotency key, so a message is stamped `sending` on
        a side cursor before the call and its outcome is recorded on another:
        a run that finds it still `sending` cannot know whether Telegram got
        it and marks it `uncertain` for a person to resend, instead of risking
        a duplicate. The job's own transaction writes nothing to the row, so
        it never conflicts with those commits.
        """
        self.check_singleton()
        message = operating(self)
        if message.state != "outgoing":
            if message.state == "sending":
                message._side_write({"state": "uncertain"})
            return
        bot, chat = message.bot_id, message.chat_id
        if not message._still_wanted():
            message._side_write({"state": "cancelled"})
            return
        if chat.bot_blocked:
            message._side_write(
                {
                    "state": "error",
                    "error_class": "TelegramForbidden",
                    "error_message": "The chat blocked the bot.",
                }
            )
            return
        target = message.target_id
        if target and not target.msg_uid:
            if target.state in ("outgoing", "sending"):
                self.env["ir.job"]._defer(
                    2, reason="the message it changes is not sent"
                )
            else:
                message._side_write({"state": "cancelled"})
            return
        if not message._consume_send_budget():
            self.env["ir.job"]._defer(1, reason="rate limit")
            return
        # the client reads the bot's token, which counts a decryption in this
        # transaction: losing that to a concurrent job must happen before the
        # message is stamped `sending`, or the replay finds it `uncertain`
        client = bot._get_telegram_client()
        if not message._side_claim():
            return
        try:
            result = message._call(bot, chat, client)
        except errors.TelegramRetryAfter as error:
            message._side_write({"state": "outgoing"})
            self.env["ir.job"]._defer(error.seconds, reason="flood control")
            return
        except errors.TelegramChatMigrated as error:
            # the history stays with the group; the message goes on to the
            # supergroup as a new row, committed with this job
            supergroup = chat._migrate_to(error.new_chat_id)
            message._side_write(
                {
                    "state": "cancelled",
                    "error_class": type(error).__name__,
                    "error_message": str(error)[:255],
                }
            )
            if supergroup:
                message._requeue_in(supergroup)
            return
        except errors.TelegramParseError:
            payload = dict(message.payload or {})
            for key in ("text", "caption"):
                if key in payload:
                    payload[key] = tools_format.plain(payload[key])
            payload.pop("parse_mode", None)
            message._side_write({"state": "outgoing", "payload": payload})
            self.env["ir.job"]._defer(0, reason="resend as plain text")
            return
        except errors.TelegramUnavailable as error:
            message._side_write(
                {
                    "state": "outgoing",
                    "error_class": type(error).__name__,
                    "error_message": str(error)[:255],
                }
            )
            raise RetryableJobError(
                str(error), seconds=min(300, 5 * 2**message.attempts)
            ) from error
        except errors.TelegramApiError as error:
            vals = {
                "state": "error",
                "error_class": type(error).__name__,
                "error_message": str(error)[:255],
            }
            message._side_write(vals)
            if isinstance(error, errors.TelegramForbidden):
                chat._side_block()
            # a refused edit or deletion ("message is not modified", one too
            # old to delete) says nothing of whether the chat takes messages
            if message.api_method.startswith("send"):
                started = chat._side_update_delivery_failure(vals["error_message"])
                message._on_delivery_failed(vals["error_message"], started)
            return
        # an edit answers with the message it edited, a deletion with True:
        # only a send makes a new Telegram message
        made = message.api_method.startswith("send") and isinstance(result, dict)
        message._side_write(
            {
                "state": "sent",
                "msg_uid": str(result.get("message_id") or "") or False
                if made
                else False,
                "error_class": False,
                "error_message": False,
            }
        )
        if message.api_method.startswith("send"):
            chat._side_remove_delivery_failure()

    def _on_delivery_failed(self, error, started) -> None:
        """Telegram refused this message, a send, for good, saying `error`;
        `started` is True when its chat was delivering until now. Whoever the
        message was for may need to know. The outcome was committed on a side
        cursor this transaction cannot see: read it from the arguments."""

    def _requeue_in(self, chat):
        self.check_singleton()
        return self._queue(
            self.bot_id,
            chat,
            self.api_method,
            self.payload,
            **{
                name: self[name].id
                if self._fields[name].type == "many2one"
                else self[name]
                for name in (
                    "text",
                    "caption",
                    "media_type",
                    "attachment_id",
                    "reply_to_uid",
                    "thread_uid",
                    "target_id",
                )
            },
        )

    def _still_wanted(self) -> bool:
        """Whether a queued message should still go out when it is due: a
        bridge cancels what its reader already saw elsewhere."""
        return True

    def _call(self, bot, chat, client=None):
        client = client or bot._get_telegram_client()
        payload = {**(self.payload or {}), "chat_id": chat.chat_id}
        if self.target_id:
            payload["message_id"] = int(self.target_id.msg_uid)
        if self.thread_uid and self.api_method.startswith("send"):
            payload["message_thread_id"] = int(self.thread_uid)
        if chat.business_connection_id:
            # sent as the business account's owner, in their own chat
            payload["business_connection_id"] = (
                chat.business_connection_id.connection_uid
            )
        if self.reply_to_uid:
            payload["reply_parameters"] = json_dumps(
                {
                    "message_id": int(self.reply_to_uid),
                    "allow_sending_without_reply": True,
                }
            )
        if isinstance(payload.get("reply_markup"), dict):
            payload["reply_markup"] = json_dumps(payload["reply_markup"])
        if self.attachment_id:
            field = {"sendPhoto": "photo", "sendVoice": "voice"}.get(
                self.api_method, "document"
            )
            attachment = self.attachment_id
            files = {
                field: (
                    attachment.name,
                    attachment.raw,
                    attachment.mimetype or "application/octet-stream",
                )
            }
            return client.call(self.api_method, payload, files=files)
        return client.call(self.api_method, payload)

    def _consume_send_budget(self):
        """One token of the chat's and the bot's send budgets, taken on a side
        cursor: a bucket row locked for the job's whole transaction would
        serialise every send of the bot."""
        chat = self.chat_id
        is_group = (chat.chat_type or "private") != "private"
        with self.env.registry.cursor() as cr:
            buckets = self.env(cr=cr, su=True)["rate.limit.bucket"]
            if not buckets.consume_for_key(
                f"telegram.chat.send:{chat.id}",
                subject_model="telegram.chat",
                subject_id=chat.id,
                capacity=20 if is_group else 1,
                window_seconds=60 if is_group else 1,
                strict=True,
            ):
                return False
            return buckets.consume_for_key(
                f"telegram.bot.send:{self.bot_id.id}",
                subject_model="telegram.bot",
                subject_id=self.bot_id.id,
                capacity=_BOT_SENDS_PER_SECOND,
                window_seconds=1,
                strict=True,
            )

    def _side_claim(self):
        self.flush_recordset()
        with self.env.registry.cursor() as cr:
            cr.execute(
                "UPDATE telegram_message SET state = 'sending', "
                "attempts = COALESCE(attempts, 0) + 1 WHERE id = %s AND state = 'outgoing' "
                "RETURNING id",
                (self.id,),
            )
            claimed = bool(cr.fetchone())
        self.invalidate_recordset(["state", "attempts"])
        return claimed

    def _side_write(self, vals) -> None:
        self.flush_recordset()
        with self.env.registry.cursor() as cr:
            side = self.with_env(self.env(cr=cr, su=True))
            side.write(vals)
            side.flush_recordset()
        self.invalidate_recordset(list(vals))

    @api.model
    def _queue(self, bot, chat, api_method, payload, *, eta=None, **vals):
        """Queue a message for the outbox and return its ledger row. It is sent
        by a job after the caller's transaction commits, so a rolled-back
        transaction sends nothing."""
        message = operating(self).create(
            {
                "bot_id": bot.id,
                "chat_id": chat.id,
                "message_type": "outbound",
                "state": "outgoing",
                "api_method": api_method,
                "payload": payload,
                **vals,
            }
        )
        message._get_delivery_runner().delayed(
            identity_key=f"telegram.message:{message.id}", eta=eta
        )._deliver()
        return message

    def _get_delivery_runner(self):
        """This message, as the user its delivery job runs as: whoever queued
        it, unless they can run no job -- a webhook's public user is inactive,
        and the job runner refuses a job of an inactive user, so an answer to
        an update that no Odoo user sent would never go out. That job runs as
        the system user instead, which `_deliver` acts through only by the
        bot's privilege, as it does for anyone."""
        if self.env.user.active:
            return self
        return self.with_user(SUPERUSER_ID)

    def action_resend(self):
        """Send again a message whose outcome is unknown or that failed: a
        person decides, knowing it may arrive twice."""
        self.check_access("write")
        for message in self.filtered(
            lambda m: m.message_type == "outbound" and m.state in ("uncertain", "error")
        ):
            message.write(
                {"state": "outgoing", "error_class": False, "error_message": False}
            )
            message.delayed(identity_key=f"telegram.message:{message.id}")._deliver()
