from odoo import api, fields, models
from odoo.exceptions import AccessError

from ..tools.authority import operating


class ResUsers(models.Model):
    _inherit = "res.users"

    telegram_account_ids = fields.One2many(
        related="partner_id.telegram_account_ids",
        string="Telegram Accounts",
    )
    telegram_binding_ids = fields.One2many(
        comodel_name="telegram.binding",
        inverse_name="user_id",
        string="Telegram Bindings",
        readonly=True,
        help="Every binding of a Telegram account straight to this user.",
    )
    telegram_connect_bot_ids = fields.Many2many(
        comodel_name="telegram.bot",
        compute="_compute_telegram_connect_bot_ids",
        help="Bots the user can connect their Telegram account through.",
    )

    @property
    def SELF_READABLE_FIELDS(self):
        return [
            *super().SELF_READABLE_FIELDS,
            "telegram_account_ids",
            "telegram_connect_bot_ids",
        ]

    def write(self, vals):
        result = super().write(vals)
        if vals.keys() & {"group_ids", "company_ids", "active", "lang"}:
            self._sync_telegram_command_menus()
        return result

    @api.depends_context("uid")
    def _compute_telegram_connect_bot_ids(self) -> None:
        bots = operating(self.env["telegram.bot"]).search(
            [("bot_username", "!=", False), ("moved_to_id", "=", False)]
        )
        for user in self:
            # a bot of another company refuses whatever its user writes
            user.telegram_connect_bot_ids = bots.filtered(
                lambda bot, user=user: bot._admits_user(user)
            )

    def _get_telegram_connect_bot(self):
        """The bot Connect Telegram opens: one an extension needs the person
        to talk to comes first."""
        self.check_singleton()
        return self.telegram_connect_bot_ids[:1]

    def action_telegram_connect(self) -> dict | None:
        self.check_singleton()
        bot = self._get_telegram_connect_bot()
        if not bot:
            return None
        return {
            "type": "ir.actions.act_url",
            "url": f"/telegram/connect/{bot.id}",
            "target": "new",
        }

    def action_telegram_disconnect(self) -> None:
        self.check_singleton()
        if self != self.env.user and not self.env.user._is_admin():
            raise AccessError(
                self.env._(
                    "Only its owner or an administrator disconnects a Telegram account."
                )
            )
        operating(self.env["telegram.binding"]).search(
            [("state", "=", "active"), ("partner_id", "=", self.partner_id.id)]
        )._revoke("user")

    def _sync_telegram_command_menus(self) -> None:
        """Bring the command menu of these users' private chats up to date with
        what their groups and companies let them run now."""
        operating(self.env["telegram.chat"]).search(
            [
                ("chat_type", "=", "private"),
                ("account_id.partner_id", "in", self.partner_id.ids),
            ]
        )._sync_command_menu()
