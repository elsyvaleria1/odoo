import logging
import threading
from datetime import timedelta

import psycopg

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.models import GC_UNLINK_LIMIT
from odoo.tools import frozendict

from ..tools.authority import operating
from odoo.addons.rate_limit.tools import EndpointRateLimiter

_logger = logging.getLogger(__name__)

_pending_activity = threading.local()

_NOTICE_BUCKET_MODEL = "telegram.chat.ratelimit.notice"
_NOTICE_WINDOW_SECONDS = 300


class TelegramChat(models.Model):
    _name = "telegram.chat"
    _description = "Telegram Chat Session"
    _rec_names_search = [
        "title",
        "account_id.name",
        "account_id.phone",
        "bot_id.bot_username",
    ]
    _access_anchors = frozendict(
        {
            "partner": "account_id.partner_id",
        }
    )

    chat_id = fields.Char(
        index=True,
        readonly=True,
        required=True,
    )
    chat_type = fields.Char(
        readonly=True,
        help="Telegram chat type as reported by the API: private, group, "
        "supergroup or channel. Only a private chat has a single speaker, so "
        "only a private chat can carry an identity.",
    )
    bot_id = fields.Many2one(
        comodel_name="telegram.bot",
        index=True,
        readonly=True,
        required=True,
        ondelete="cascade",
    )
    account_id = fields.Many2one(
        comodel_name="telegram.account",
        index="btree_not_null",
        readonly=True,
        ondelete="restrict",
        help="The person on the other end of a private chat. A group has many "
        "speakers and records none.",
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        related="account_id.partner_id",
        help="Who the private chat's person is in Odoo, by their active binding.",
    )
    title = fields.Char(help="A group's name in Telegram.")
    migrated_to_id = fields.Many2one(
        comodel_name="telegram.chat",
        readonly=True,
        ondelete="set null",
        help="The supergroup this group became.",
    )
    business_connection_id = fields.Many2one(
        comodel_name="telegram.business.connection",
        index="btree_not_null",
        readonly=True,
        ondelete="cascade",
        help="Set for a chat of a Telegram Business account the bot manages: "
        "the owner's own private chat with a customer, which shares its id "
        "with the customer's chat with the bot.",
    )
    bot_blocked = fields.Boolean(
        readonly=True,
        help="Telegram refused a message because the person blocked the bot or "
        "removed it: nothing more is sent until they write again.",
    )
    delivery_failed_at = fields.Datetime(
        string="Failing Since",
        readonly=True,
        help="When Telegram started refusing what the bot sends here: set by "
        "the first failed message, cleared by the next one sent.",
    )
    delivery_error = fields.Char(
        string="Last Delivery Error",
        readonly=True,
    )
    message_ids = fields.One2many(
        comodel_name="telegram.message",
        inverse_name="chat_id",
    )
    flow_owner = fields.Char(
        readonly=True,
        help="The handler model whose multi-step flow the chat is in: it gets "
        "the chat's free text until the flow ends.",
    )
    flow_step = fields.Char(readonly=True)
    flow_data = fields.Json(readonly=True)
    flow_expires_at = fields.Datetime(
        readonly=True,
        help="A flow nobody moved since is over.",
    )
    failed_command_count = fields.Integer(
        default=0,
        help="Number of consecutive failed commands. Auto-resets on success.",
    )
    last_error = fields.Char(help="Last error message for debugging.")
    last_message_time = fields.Datetime(
        help="Timestamp of last message sent by user (for cleanup/activity tracking)"
    )

    rate_limit_enabled = fields.Boolean(
        default=True,
        help="Prevent spam with rate limiting (token bucket algorithm)",
    )
    rate_limit_requests = fields.Integer(
        default=20,
        help="Maximum number of messages allowed per time period",
    )
    rate_limit_period = fields.Selection(
        selection=[
            ("minute", "Per Minute"),
            ("hour", "Per Hour"),
        ],
        default="minute",
        help="Time period for rate limiting",
    )

    context_data = fields.Json(
        help="What a handler parks on the chat outside any flow until a button "
        "of its answers it: a reply waiting for its visibility, a draft waiting "
        "for its thread."
    )

    _chat_id_bot_id_uniq = models.Constraint(
        "UNIQUE NULLS NOT DISTINCT (chat_id, bot_id, business_connection_id)",
        "A chat ID must be unique per bot and business connection!",
    )

    @api.depends("account_id.name", "account_id.phone", "title", "bot_id.bot_username")
    @api.depends_context("telegram_show_phone")
    def _compute_display_name(self) -> None:
        # the number tells apart two accounts of one person, where that person
        # chooses between them; anywhere else a name stays a name
        show_phone = self.env.context.get("telegram_show_phone")
        for chat in self:
            who = chat.title or chat.account_id.name or chat.chat_id
            if show_phone and chat.account_id.phone:
                who = f"{who} ({chat.account_id.phone})"
            bot = chat.bot_id
            via = f"@{bot.bot_username}" if bot.bot_username else bot.name
            chat.display_name = f"{who} · {via}" if via else who

    @api.constrains("rate_limit_enabled", "rate_limit_requests")
    def _check_rate_limit_requests(self) -> None:
        for record in self:
            if record.rate_limit_enabled and record.rate_limit_requests <= 0:
                raise ValidationError(
                    self.env._("Rate limit requests must be greater than 0")
                )

    @api.model
    def _acquire_chat(
        self, chat_id, bot_id, chat_type=None, account=None, business_connection=None
    ):
        """The chat `chat_id` of the bot, created on first sight.

        Only a private chat records its person: Telegram gives it the id of
        the one user on the other end, so the account of that chat's sender
        is the chat's, and stays so.
        """
        chat_id_str = str(chat_id)
        is_private = chat_type == "private"
        connection_id = business_connection.id if business_connection else False
        chat = self.search(
            [
                ("chat_id", "=", chat_id_str),
                ("bot_id", "=", bot_id),
                ("business_connection_id", "=", connection_id),
            ],
            limit=1,
        )
        if not chat:
            vals = {
                "chat_id": chat_id_str,
                "bot_id": bot_id,
                "business_connection_id": connection_id,
            }
            if chat_type:
                vals["chat_type"] = chat_type
            if account and is_private:
                vals["account_id"] = account.id
            return self.create(vals)

        if chat_type and chat.chat_type != chat_type:
            chat.chat_type = chat_type
        if chat.bot_blocked and account:
            chat.bot_blocked = False
        # A chat first seen by an outbound message records no person yet.
        if account and is_private and not chat.account_id:
            chat.account_id = account.id
        return chat

    @api.model
    def _for_partner(self, partner, bot=None):
        """The private chats reaching `partner` through a bound account --
        their own with the bot, never a business chat they are the customer
        of."""
        domain = [
            ("chat_type", "=", "private"),
            ("business_connection_id", "=", False),
            ("account_id.partner_id", "in", partner.ids),
        ]
        if bot is not None:
            domain.append(("bot_id", "in", bot.ids))
        return operating(self).search(domain, order="last_message_time desc, id desc")

    @api.model
    def _for_user(self, user, bot=None):
        """The private chats of the Telegram person who may act as `user`."""
        chats = self._for_partner(user.partner_id, bot)
        return chats.filtered(
            lambda chat: chat.account_id._acting_user("portal") == user
        )

    def _side_block(self) -> None:
        self.flush_recordset()
        with self.env.registry.cursor() as cr:
            # one row, raced by any job refused in this chat: wait for the
            # other and write over it, rather than fail serialising
            cr.use_read_committed()
            cr.execute(
                "UPDATE telegram_chat SET bot_blocked = TRUE WHERE id = %s", (self.id,)
            )
        self.invalidate_recordset(["bot_blocked"])

    def _side_update_delivery_failure(self, error) -> bool:
        """Record on a side cursor that a message failed here; True when the
        chat was delivering until now."""
        self.check_singleton()
        self.flush_recordset()
        with self.env.registry.cursor() as cr:
            # read committed: a concurrent failure or success in this chat is
            # waited for and then seen, so exactly one failure starts it
            cr.use_read_committed()
            cr.execute(
                "UPDATE telegram_chat AS chat SET delivery_error = %s, "
                "delivery_failed_at = COALESCE(previous.failed_at, %s) "
                "FROM (SELECT id, delivery_failed_at AS failed_at FROM telegram_chat "
                "WHERE id = %s FOR UPDATE) AS previous "
                "WHERE chat.id = previous.id RETURNING previous.failed_at IS NULL",
                ((error or "")[:255], fields.Datetime.now(), self.id),
            )
            started = bool((cr.fetchone() or [False])[0])
        self.invalidate_recordset(["delivery_error", "delivery_failed_at"])
        return started

    def _side_remove_delivery_failure(self) -> None:
        """A message went through: the chat delivers again. Asked of the
        table, not of this transaction's snapshot, which may predate a
        failure another job recorded."""
        self.check_singleton()
        self.flush_recordset()
        with self.env.registry.cursor() as cr:
            cr.use_read_committed()
            cr.execute(
                "UPDATE telegram_chat SET delivery_failed_at = NULL, "
                "delivery_error = NULL "
                "WHERE id = %s AND delivery_failed_at IS NOT NULL",
                (self.id,),
            )
        self.invalidate_recordset(["delivery_error", "delivery_failed_at"])

    def _migrate_to(self, new_chat_id):
        """The supergroup this group became, recorded once: the group keeps
        its history, what follows happens in the supergroup's own chat."""
        self.check_singleton()
        if not new_chat_id:
            return self.browse()
        chat = operating(self)
        if chat.migrated_to_id:
            return chat.migrated_to_id
        supergroup = chat._acquire_chat(
            new_chat_id, chat.bot_id.id, chat_type="supergroup"
        )
        supergroup.write(
            {
                "rate_limit_enabled": chat.rate_limit_enabled,
                "rate_limit_requests": chat.rate_limit_requests,
                "rate_limit_period": chat.rate_limit_period,
            }
        )
        chat.migrated_to_id = supergroup
        self.env["telegram.router"]._chat_migrated(chat.bot_id, chat, supergroup)
        return supergroup

    def _with_flow_privilege(self):
        return self.with_privilege(
            "telegram.privilege_chat_conversation",
            reason="the bot moves the conversation of the chat it is serving",
        )

    def _increment_failed_state(self, error_msg):
        self.check_singleton()
        self.env.cr.execute(
            """
            UPDATE telegram_chat
               SET failed_command_count = failed_command_count + 1,
                   last_error = %s
             WHERE id = %s
         RETURNING failed_command_count
            """,
            (error_msg[:255] if error_msg else None, self.id),
        )
        row = self.env.cr.fetchone()
        self.invalidate_recordset(["failed_command_count", "last_error"])
        return row[0] if row else 0

    def _reset_failed_state(self) -> None:
        self.check_singleton()
        if not self.failed_command_count and not self.last_error:
            return
        self._with_flow_privilege().write(
            {
                "failed_command_count": 0,
                "last_error": False,
            },
        )

    def _mark_active(self) -> None:
        self.check_singleton()
        pending = getattr(_pending_activity, "ids", None)
        if pending is None:
            pending = _pending_activity.ids = set()
        pending.add(self.id)

    @api.model
    def _flush_activity(self) -> None:
        pending = getattr(_pending_activity, "ids", None)
        if not pending:
            return
        _pending_activity.ids = set()
        try:
            with self.env.cr.savepoint():
                self.env.cr.execute(
                    "UPDATE telegram_chat SET last_message_time = %s WHERE id = ANY(%s)",
                    (fields.Datetime.now(), list(pending)),
                )
        except psycopg.errors.OperationalError as e:
            _logger.info(
                "Skipped the activity stamp for chats %s: %s",
                sorted(pending),
                e.__class__.__name__,
            )
            return
        self.browse(pending).invalidate_recordset(["last_message_time"])

    @api.model
    def _discard_activity(self) -> None:
        _pending_activity.ids = set()

    def _consume_rate_limit_notice(self):
        self.check_singleton()
        return self.env["rate.limit.bucket"].consume_for_key(
            f"{_NOTICE_BUCKET_MODEL}:{self.id}",
            subject_model=_NOTICE_BUCKET_MODEL,
            subject_id=self.id,
            capacity=1,
            window_seconds=_NOTICE_WINDOW_SECONDS,
        )

    def _consume_rate_limit(self) -> bool:
        self.check_singleton()

        if not self.rate_limit_enabled:
            self._mark_active()
            return True

        limiter = EndpointRateLimiter(self.env, self)
        if not limiter.check_limit():
            return False

        self._mark_active()

        return True

    def _get_context(self, key, default=None):
        self.check_singleton()
        return (self.context_data or {}).get(key, default)

    def _set_context(self, key, value) -> None:
        self.check_singleton()
        context = dict(self.context_data or {})
        context[key] = value
        self._with_flow_privilege().write({"context_data": context})

    # -- flows ----------------------------------------------------------------

    def _flow_is_open(self) -> bool:
        self.check_singleton()
        return bool(
            self.flow_owner
            and self.flow_owner in self.env.registry
            and (
                not self.flow_expires_at or self.flow_expires_at > fields.Datetime.now()
            )
        )

    def _flow_expiry(self, owner):
        return fields.Datetime.now() + self.env[owner]._telegram_flow_ttl

    def _flow_start(self, owner, step, data=None) -> None:
        self.check_singleton()
        _logger.info("Chat %s starts flow %s at %s", self.id, owner, step)
        self._with_flow_privilege().write(
            {
                "flow_owner": owner,
                "flow_step": step,
                "flow_data": data or {},
                "flow_expires_at": self._flow_expiry(owner),
            }
        )

    def _flow_advance(self, step=None, data=None) -> None:
        """Move the open flow to `step` (the same one when None), replacing its
        data when given."""
        self.check_singleton()
        if not self.flow_owner:
            raise ValidationError(self.env._("The chat has no flow to move."))
        vals = {"flow_expires_at": self._flow_expiry(self.flow_owner)}
        if step is not None:
            vals["flow_step"] = step
        if data is not None:
            vals["flow_data"] = data
        self._with_flow_privilege().write(vals)

    def _flow_update(self, values) -> None:
        self.check_singleton()
        self._flow_advance(data={**(self.flow_data or {}), **values})

    def _flow_end(self) -> None:
        if not any(self.mapped("flow_owner")):
            return
        _logger.info("Chats %s end their flow", self.ids)
        self._with_flow_privilege().write(
            {
                "flow_owner": False,
                "flow_step": False,
                "flow_data": False,
                "flow_expires_at": False,
            }
        )

    @api.autovacuum
    def _gc_expired_flows(self) -> int:
        expired = self.search(
            [("flow_expires_at", "<", fields.Datetime.now())], limit=GC_UNLINK_LIMIT
        )
        expired._flow_end()
        return len(expired)

    @api.autovacuum
    def _gc_telegram_chats(self):
        threshold_date = fields.Datetime.now() - timedelta(days=90)

        removable = self.search(
            [
                "|",
                ("account_id", "=", False),
                ("account_id.binding_id", "=", False),
                ("flow_owner", "=", False),
                ("message_ids", "=", False),
                "|",
                ("last_message_time", "<", threshold_date),
                ("last_message_time", "=", False),
            ],
            limit=GC_UNLINK_LIMIT,
        )

        count = len(removable)
        if count > 0:
            _logger.info(
                "Auto-vacuum: Removing %s old unlinked telegram chats (inactive for 90+ days, no message history)",
                count,
            )
            removable.unlink()
        else:
            _logger.debug("Auto-vacuum: No old chats to remove")

        return count
