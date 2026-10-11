from urllib.parse import quote

from odoo import api, fields, models
from odoo.exceptions import UserError


class WizardTelegramInvite(models.TransientModel):

    _name = "wizard.telegram.invite"
    _description = "Invite a Contact to Telegram"

    partner_id = fields.Many2one(
        comodel_name="res.partner",
        required=True,
    )
    bot_id = fields.Many2one(
        comodel_name="telegram.bot",
        default=lambda self: self.env["telegram.bot"].search(
            [("bot_username", "!=", False)], limit=1
        ),
        required=True,
        domain="[('bot_username', '!=', False)]",
    )
    link = fields.Char(readonly=True)
    qr_url = fields.Char(compute="_compute_qr_url")

    @api.depends("link")
    def _compute_qr_url(self) -> None:
        for wizard in self:
            wizard.qr_url = (
                wizard.link
                and f"/report/barcode/?barcode_type=QR&value={quote(wizard.link)}&width=300&height=300"
            )

    def action_issue(self) -> dict:
        self.check_singleton()
        self.env["telegram.link.token"].check_access("create")
        if not self.bot_id.bot_username:
            raise UserError(
                self.env._(
                    "Register the bot's webhook first: Telegram then tells Odoo "
                    "the bot's username, which the link needs."
                )
            )
        token = self.env["telegram.link.token"]._issue_invitation(
            self.bot_id, self.partner_id
        )
        self.link = self.bot_id._deep_link(token)
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }
