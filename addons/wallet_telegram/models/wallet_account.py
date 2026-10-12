from odoo import fields, models
from odoo.tools import frozendict


class WalletAccount(models.Model):
    _inherit = "wallet.account"
    _access_anchors = frozendict({"partner": "card_ids.holder_id"})

    telegram_topup_category_id = fields.Many2one(
        comodel_name="approval.category",
        string="Top-up Approval Category",
        check_company=True,
        help="Category used by /recarga. Configure its approvers and required "
        "amount; leave empty to allow balance consultation only. Approval "
        "does not send money to the issuer.",
    )
