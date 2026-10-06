from odoo import api, fields, models

from odoo.addons.device_mobile.models.device_device import mobile_e164


class TelegramAccount(models.Model):
    _inherit = "telegram.account"

    phone_e164 = fields.Char(
        string="Phone (E.164)",
        compute="_compute_phone_e164",
        store=True,
        index="btree_not_null",
        help="The verified number as a company phone's number is written: the "
        "same line whatever prefix Telegram gives it.",
    )

    @api.depends("phone")
    def _compute_phone_e164(self) -> None:
        for account in self:
            account.phone_e164 = mobile_e164(account.phone) or False
