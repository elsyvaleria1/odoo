from odoo import fields, models
from odoo.tools import frozendict

from odoo.addons.trade.tools import SALE


class SaleTender(models.Model):
    _name = "sale.tender"
    _inherit = ["mixin.tender"]
    _description = "Sale Tender"
    _direction = SALE
    _check_company_auto = True
    _access_anchors = frozendict(
        {
            "owner": "user_id",
            "user_or_unset": models.Anchor("user_id", kind="owner", shared=True),
        }
    )

    order_ids = fields.One2many(comodel_name="sale.order")
    line_ids = fields.One2many(comodel_name="sale.tender.line")

    def _get_sequence_code(self):
        return "sale.tender"

    def action_view_offers(self) -> dict:
        self.check_singleton()
        return {
            "name": self.env._("Bids of %(tender)s", tender=self.name),
            "type": "ir.actions.act_window",
            "res_model": "sale.order",
            "view_mode": "list,form",
            "domain": [("tender_id", "=", self.id)],
            "context": {"default_tender_id": self.id},
        }

    def action_compare(self):
        self.check_singleton()
        return {
            "name": self.env._("Compare the bids of %(tender)s", tender=self.name),
            "type": "ir.actions.act_window",
            "res_model": "sale.order.line",
            "view_mode": "list",
            "views": [
                (self.env.ref("sale_tender.sale_order_line_compare_list").id, "list")
            ],
            "domain": [
                ("order_id", "in", self.order_ids.ids),
                ("display_type", "=", False),
            ],
            "context": {"search_default_groupby_product": True},
        }
