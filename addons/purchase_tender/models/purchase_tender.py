from odoo import fields, models
from odoo.tools import frozendict

from odoo.addons.trade.tools import PURCHASE


class PurchaseTender(models.Model):
    _name = "purchase.tender"
    _inherit = ["mixin.tender"]
    _description = "Call for Tenders"
    _direction = PURCHASE
    _check_company_auto = True
    _access_anchors = frozendict(
        {
            "owner": "user_id",
            "user_or_unset": models.Anchor("user_id", kind="owner", shared=True),
        }
    )

    order_ids = fields.One2many(comodel_name="purchase.order")
    line_ids = fields.One2many(comodel_name="purchase.tender.line")

    def _get_sequence_code(self):
        return "purchase.tender"

    def action_view_offers(self) -> dict:
        self.check_singleton()
        return {
            "name": self.env._("Offers of %(tender)s", tender=self.name),
            "type": "ir.actions.act_window",
            "res_model": "purchase.order",
            "view_mode": "list,form",
            "domain": [("tender_id", "=", self.id)],
            "context": {"default_tender_id": self.id, "quotation_only": True},
        }

    def action_compare(self):
        self.check_singleton()
        return self.order_ids[:1].action_compare_alternative_lines()
