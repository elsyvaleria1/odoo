from odoo import api, fields, models

from odoo.addons.phone_call.models.phone_call import number_key


class TelegramAccount(models.Model):
    _inherit = "telegram.account"

    phone_digits = fields.Char(
        compute="_compute_phone_digits",
        store=True,
        index="btree_not_null",
        help="The verified number's last digits, as a company phone's number is "
        "matched to it whatever prefix either carries.",
    )

    @api.depends("phone")
    def _compute_phone_digits(self) -> None:
        for account in self:
            account.phone_digits = number_key(account.phone) or False
