from odoo import fields, models
from odoo.tools import frozendict


class SaleTenderLine(models.Model):
    _name = "sale.tender.line"
    _inherit = ["mixin.tender.line"]
    _description = "Sale Tender Need"
    _check_company_auto = True
    _access_anchors = frozendict(
        {
            "owner": "tender_id.user_id",
            "user_or_unset": models.Anchor(
                "tender_id.user_id", kind="owner", shared=True
            ),
        }
    )

    tender_id = fields.Many2one(comodel_name="sale.tender")
