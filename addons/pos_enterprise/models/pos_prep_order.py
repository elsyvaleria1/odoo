from datetime import timedelta

from odoo import api, fields, models


class PosPrepOrder(models.Model):
    _name = "pos.prep.order"
    _description = "Pos Preparation Order"
    _inherit = ["mixin.pos.load"]

    pos_order_id = fields.Many2one(
        comodel_name="pos.order",
        string="Order",
        ondelete="cascade",
    )
    prep_line_ids = fields.One2many(
        comodel_name="pos.prep.line",
        inverse_name="prep_order_id",
        string="Preparation Lines",
    )
    order_name = fields.Char(compute="_compute_order_name")
    pdis_general_customer_note = fields.Text(
        string="General Customer Note",
        help="Current general-customer-note displayed on preparation display",
    )
    pdis_internal_note = fields.Text(
        string="General Note",
        help="Current general-note displayed on preparation display",
    )
    completion_time = fields.Integer(
        help="Time in minutes to complete the order (preparation + service time)"
    )

    @api.depends("pos_order_id.floating_order_name")
    def _compute_order_name(self) -> None:
        for order in self:
            order.order_name = (
                order.pos_order_id.floating_order_name
                or order.pos_order_id.tracking_number
            )

    @api.model
    def process_order(self, order_id, options=None):
        if not order_id or not self.env["pos.order"].browse(order_id).exists():
            return None

        order = self.env["pos.order"].browse(order_id)
        data = order._process_preparation_changes(options or {})
        if not data["change"]:
            return None

        for p_dis in self.env["pos.prep.display"]._get_preparation_displays(
            order, data["category_ids"]
        ):
            p_dis._send_load_orders_message(
                data["sound"], data.get("notification"), order_id
            )

        return True

    @api.model
    def _clean_preparation_data(self) -> bool:
        orders = self.env["pos.prep.order"].search(
            [("write_date", "<=", fields.Datetime.now() - timedelta(days=1))]
        )
        orders.unlink()
        return True
