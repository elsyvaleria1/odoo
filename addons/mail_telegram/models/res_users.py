from markupsafe import Markup

from odoo import api, fields, models

from odoo.addons.telegram.tools.authority import operating
from odoo.addons.telegram.tools.dispatch import translation_env

_SETTINGS = (
    "telegram_notify_inbox",
    "telegram_notify_chats",
    "telegram_notify_channels",
    "telegram_grace_seconds",
    "telegram_notify_chat_id",
)
_STATUS = (
    "telegram_notify_chat_ids",
    "telegram_notify_state",
    "telegram_notify_detail",
)
_STATES = [
    ("ready", "Delivering"),
    ("failing", "Failing"),
    ("blocked", "Bot blocked"),
    ("verify_phone", "Phone number needed"),
    ("refused", "Not allowed here"),
    ("start_bot", "Bot not started"),
    ("unconnected", "Not connected"),
    ("no_bot", "No bot delivers notifications"),
]


class ResUsers(models.Model):
    _inherit = "res.users"

    telegram_notify_inbox = fields.Selection(
        related="res_users_settings_id.telegram_notify_inbox",
        string="Telegram: Notifications",
        readonly=False,
    )
    telegram_notify_chats = fields.Selection(
        related="res_users_settings_id.telegram_notify_chats",
        string="Telegram: Chats",
        readonly=False,
    )
    telegram_notify_channels = fields.Selection(
        related="res_users_settings_id.telegram_notify_channels",
        string="Telegram: Channels",
        readonly=False,
    )
    telegram_grace_seconds = fields.Integer(
        related="res_users_settings_id.telegram_grace_seconds",
        string="Telegram: Wait Before Sending (seconds)",
        readonly=False,
    )
    telegram_notify_chat_id = fields.Many2one(
        related="res_users_settings_id.telegram_notify_chat_id",
        string="Telegram: Deliver To",
        readonly=False,
        domain="[('id', 'in', telegram_notify_chat_ids)]",
    )
    telegram_notify_chat_ids = fields.Many2many(
        comodel_name="telegram.chat",
        string="Telegram: Possible Destinations",
        compute="_compute_telegram_notify_status",
    )
    telegram_notify_state = fields.Selection(
        selection=_STATES,
        string="Telegram: Delivery",
        compute="_compute_telegram_notify_status",
    )
    telegram_notify_detail = fields.Char(
        string="Telegram: Delivery Detail",
        compute="_compute_telegram_notify_status",
    )

    @property
    def SELF_READABLE_FIELDS(self):
        return [*super().SELF_READABLE_FIELDS, *_SETTINGS, *_STATUS]

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return [*super().SELF_WRITEABLE_FIELDS, *_SETTINGS]

    def _telegram_settings(self):
        self.check_singleton()
        # a user's preferences, read as that user: everyone keeps their own
        return (
            self.env["res.users.settings"].with_user(self)._get_or_create_for_user(self)
        )

    def _telegram_self(self):
        """This user, as themselves in all their companies: where their
        notifications go is theirs to know, whoever asks -- a poster of
        another company, the outbox, the webhook's public user, an
        administrator -- and what is queued from here is sent as them."""
        self.check_singleton()
        return self.with_user(self).with_context(
            allowed_company_ids=self.company_ids.ids
        )

    def _get_telegram_connect_bot(self):
        # connecting through the bot that delivers the notifications opens
        # the chat they need; any other bot leaves it to the person to find
        bots = self.telegram_connect_bot_ids
        notifying = self.env["telegram.bot"]._get_notifying_bots(self)
        return (bots & notifying)[:1] or super()._get_telegram_connect_bot()

    # -- where notifications go -----------------------------------------------

    def _get_telegram_notify_chats(self):
        """The private chats that may carry this user's Odoo notifications:
        theirs, with a bot that delivers them and is allowed to deliver to
        that Telegram account. Most recently used first, as the user."""
        me = self._telegram_self()
        chats = operating(me.env["telegram.chat"])
        bots = chats.env["telegram.bot"]._get_notifying_bots(me)
        if not bots:
            return chats
        return chats._for_user(me, bots).filtered(
            lambda chat: chat.bot_id._can_deliver_mail(chat.account_id, me)
        )

    def _get_telegram_notify_chat(self, company=None):
        """The one chat this user's notifications go to: the one they chose
        while it may still carry them, else the last one they used that does
        not refuse the bot. About a record of `company`, only a chat with that
        company's bot: a bot speaks for one company, or the reply lands where
        the bot does not act."""
        self.check_singleton()
        chats = self._get_telegram_notify_chats()
        if company:
            chats = chats.filtered(lambda chat: chat.bot_id.company_id == company)
        chosen = self._telegram_settings().telegram_notify_chat_id
        if chosen and chosen.id in chats.ids:
            return chats.browse(chosen.id)
        return chats.filtered(lambda chat: not chat.bot_blocked)[:1]

    def _update_telegram_notify_chat(self, chat) -> None:
        """Make `chat` where this user's notifications go."""
        self.check_singleton()
        self._telegram_settings().telegram_notify_chat_id = chat

    @api.depends_context("uid", "lang")
    def _compute_telegram_notify_status(self) -> None:
        for user in self:
            state, detail, chats = user._get_telegram_notify_status()
            user.telegram_notify_chat_ids = chats
            user.telegram_notify_state = state
            user.telegram_notify_detail = detail

    def _get_telegram_notify_status(self) -> tuple:
        """`(state, detail, chats)`: whether this user's notifications reach
        Telegram, why not in the reader's words, and where they may go."""
        self.check_singleton()
        me = self._telegram_self()
        chats = me._get_telegram_notify_chats()
        # with every chat refusing the bot, the one to unblock is the last used
        target = me._get_telegram_notify_chat() or chats[:1]
        if target and target.bot_blocked:
            return (
                "blocked",
                self.env._(
                    "You blocked %(bot)s in Telegram: open it and press Start.",
                    bot=target.bot_id.display_name,
                ),
                chats,
            )
        if target and target.delivery_failed_at:
            return (
                "failing",
                self.env._(
                    "Telegram refuses what Odoo sends to %(chat)s: %(error)s",
                    chat=target.display_name,
                    error=target.delivery_error or "",
                ),
                chats,
            )
        if target:
            shown = target.with_context(telegram_show_phone=True)
            return "ready", shown.display_name, chats
        bots = me.env["telegram.bot"]._get_notifying_bots(me)
        if not bots:
            return (
                "no_bot",
                self.env._(
                    "No Telegram bot of your companies delivers Odoo notifications."
                ),
                chats,
            )
        accounts = operating(me.env["telegram.account"]).search(
            [("partner_id", "=", self.partner_id.id)]
        )
        accounts = accounts.filtered(
            lambda account: account._acting_user("internal") == self
        )
        if not accounts:
            return "unconnected", self.env._("Press Connect Telegram."), chats
        own = operating(me.env["telegram.chat"])._for_user(me, bots)
        if not own:
            return (
                "start_bot",
                self.env._(
                    "Your Odoo notifications come from %(bot)s: press Connect "
                    "Telegram to open it.",
                    bot=bots[:1].display_name,
                ),
                chats,
            )
        chat = own[:1]
        bot = chat.bot_id.with_context(lang=self.env.lang)
        refusal = bot._get_mail_refusal(chat.account_id, me) or ""
        if bot._is_phone_needed_for_mail(chat.account_id, me):
            return "verify_phone", refusal, chats
        return "refused", refusal, chats

    # -- actions --------------------------------------------------------------

    def action_telegram_request_phone(self) -> dict | None:
        """Ask, in each chat this user has with a bot delivering notifications,
        for the phone number of that Telegram account."""
        self.check_singleton()
        me = self._telegram_self()
        bots = me.env["telegram.bot"]._get_notifying_bots(me)
        chats = operating(me.env["telegram.chat"])._for_user(me, bots)
        for chat in chats.filtered(lambda chat: not chat.bot_blocked):
            tr = translation_env(chat.bot_id, chat)
            chat.bot_id._queue_phone_request(
                chat,
                tr._(
                    "Odoo asks for the phone number of this Telegram account: "
                    "press the button below to share it."
                ),
            )
        if not chats:
            return None
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "info",
                "message": self.env._(
                    "Open Telegram: the bot asks for your phone number."
                ),
            },
        }

    # -- alerts ---------------------------------------------------------------

    def _notify_telegram_unreachable(self, chat, reason) -> None:
        """Tell this user in Odoo that their notifications stopped reaching
        `chat` in Telegram, and what to do. Whoever noticed -- the outbox, the
        webhook's public user -- only queues it: the notice is the user's
        own, posted in a transaction of theirs."""
        self.check_singleton()
        self._telegram_self().delayed(
            identity_key=f"mail_telegram.unreachable:{self.id}:{chat.id}"
        )._send_telegram_unreachable_notice(chat.id, reason)

    @api.job
    def _send_telegram_unreachable_notice(self, chat_id, reason) -> None:
        """The notice itself, to this user from OdooBot, run as this user."""
        self.check_singleton()
        me = self._telegram_self().with_context(lang=self.lang)
        chat = operating(me.env["telegram.chat"]).browse(chat_id).exists()
        if not chat:
            return
        body = Markup("<p>%s</p><p>%s</p>") % (
            me.env._(
                "Your Odoo notifications no longer reach %(chat)s in Telegram: "
                "%(reason)s",
                chat=chat.display_name,
                reason=reason,
            ),
            me.env._(
                "They stay in Odoo. See My Preferences, Telegram, for what to do."
            ),
        )
        thread = me.env["mixin.mail.thread"].with_context(mail_telegram_skip=True)
        thread.with_privilege(
            "mail.privilege_post_as_author",
            reason="Odoo tells a user that Telegram stopped taking their notifications",
        ).message_notify(
            subject=me.env._("Telegram is not delivering your notifications"),
            body=body,
            author_id=self.env.ref("base.partner_root").id,
            partner_ids=self.partner_id.ids,
        )
