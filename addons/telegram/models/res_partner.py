from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    telegram_account_ids = fields.One2many(
        comodel_name="telegram.account",
        inverse_name="partner_id",
        string="Telegram Accounts",
        readonly=True,
        help="The Telegram accounts whose active binding says they are this contact.",
    )
    telegram_account_count = fields.Integer(compute="_compute_telegram_account_count")
    telegram_binding_ids = fields.One2many(
        comodel_name="telegram.binding",
        inverse_name="partner_id",
        string="Telegram Bindings",
        readonly=True,
        help="Every binding of a Telegram account to this contact, past ones included.",
    )

    @api.depends("telegram_account_ids")
    def _compute_telegram_account_count(self) -> None:
        for partner in self:
            partner.telegram_account_count = len(partner.telegram_account_ids)

    def action_telegram_invite(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "res_model": "wizard.telegram.invite",
            "view_mode": "form",
            "target": "new",
            "context": {"default_partner_id": self.id},
        }
