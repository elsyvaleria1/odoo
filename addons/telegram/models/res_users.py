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

    @api.depends_context("uid")
    def _compute_telegram_connect_bot_ids(self) -> None:
        bots = operating(self.env["telegram.bot"]).search(
            [("bot_username", "!=", False)]
        )
        for user in self:
            user.telegram_connect_bot_ids = bots

    def action_telegram_connect(self) -> dict | None:
        self.check_singleton()
        bot = self.telegram_connect_bot_ids[:1]
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
