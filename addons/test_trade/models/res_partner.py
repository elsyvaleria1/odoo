from odoo import api, fields, models


class ResPartner(models.Model):

    _inherit = "res.partner"

    test_trade_order_count = fields.Integer(
        string="Test Order Count",
        compute="_compute_test_trade_order_count",
    )

    def _compute_test_trade_order_count(self):
        self._update_order_count(
            "test_trade.order",
            "test_trade_order_count",
            "base.group_user",
            domain=self._get_test_trade_order_domain_count(),
        )

    def _get_test_trade_order_domain_count(self):
        return []

    @api.model
    def _get_order_activity_sources(self):
        return super()._get_order_activity_sources() + [
            ("test_trade.order", [("state", "=", "done")]),
        ]
