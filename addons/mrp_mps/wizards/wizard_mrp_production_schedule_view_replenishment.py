from odoo import api, fields, models


class WizardMrpProductionScheduleViewReplenishment(models.TransientModel):
    _name = "wizard.mrp.production.schedule.view.replenishment"
    _description = "Forecast Demand Details"

    move_ids = fields.Many2many(
        comodel_name="stock.move",
        relation="mrp_mps_forecast_details_stock_move_rel",
        readonly=True,
    )
    purchase_order_line_ids = fields.Many2many(
        comodel_name="purchase.order.line",
        relation="mrp_mps_forecast_details_purchase_order_line_rel",
        readonly=True,
    )

    rfq_qty = fields.Integer(
        string="Quantity from RFQ",
        compute="_compute_quantity_and_label",
    )
    moves_qty = fields.Integer(
        string="Quantity from Incoming Moves",
        compute="_compute_quantity_and_label",
    )
    manufacture_qty = fields.Integer(
        string="Quantity from Manufacturing Order",
        compute="_compute_quantity_and_label",
    )
    total_qty = fields.Integer(
        string="Actual Replenishment",
        compute="_compute_quantity_and_label",
    )

    rfq_string = fields.Char(compute="_compute_quantity_and_label")
    moves_string = fields.Char(compute="_compute_quantity_and_label")
    manufacture_string = fields.Char(compute="_compute_quantity_and_label")

    @api.depends("move_ids", "purchase_order_line_ids")
    def _compute_quantity_and_label(self) -> None:
        for mps in self:
            mps.moves_qty = sum(
                mps.move_ids.filtered(lambda m: m.picking_id).mapped("product_qty")
            )
            mps.moves_string = (
                "%(record_count)s %(record_name)s (%(product_qty)s %(product_uom_id)s)"
                % {
                    "record_count": len(mps.move_ids.picking_id),
                    "record_name": self.env._("Receipts")
                    if len(mps.move_ids.picking_id) > 1
                    else self.env._("Receipt"),
                    "product_qty": mps.moves_qty,
                    "product_uom_id": mps.move_ids.product_id.uom_id.name,
                }
            )
            mps.manufacture_qty = sum(
                mps.move_ids.filtered(lambda m: m.production_id).mapped("product_qty")
            )
            mps.manufacture_string = (
                "%(record_count)s %(record_name)s (%(product_qty)s %(product_uom_id)s)"
                % {
                    "record_count": len(mps.move_ids.production_id),
                    "record_name": self.env._("Manufacturing Orders")
                    if len(mps.move_ids.production_id) > 1
                    else self.env._("Manufacturing Order"),
                    "product_qty": mps.manufacture_qty,
                    "product_uom_id": mps.move_ids.product_id.uom_id.name,
                }
            )
            mps.rfq_qty = sum(mps.purchase_order_line_ids.mapped("product_uom_qty"))
            mps.rfq_string = (
                "%(record_count)s %(record_name)s (%(product_qty)s %(product_uom_id)s)"
                % {
                    "record_count": len(mps.purchase_order_line_ids.order_id),
                    "record_name": self.env._("Requests for quotation")
                    if len(mps.purchase_order_line_ids.order_id) > 1
                    else self.env._("Request for quotation"),
                    "product_qty": mps.rfq_qty,
                    "product_uom_id": mps.purchase_order_line_ids.product_id.uom_id.name,
                }
            )
            mps.total_qty = mps.moves_qty + mps.manufacture_qty + mps.rfq_qty

    def action_view_rfq_details(self) -> dict:
        return {
            "type": "ir.actions.act_window",
            "res_model": "purchase.order",
            "views": [(False, "list"), (False, "form")],
            "view_mode": "list,form",
            "target": "current",
            "name": self.env.context.get("action_name"),
            "domain": [
                ("id", "in", self.purchase_order_line_ids.mapped("order_id").ids)
            ],
            "context": {
                "quotation_only": True,
            },
        }

    def action_view_mo_details(self) -> dict:
        return {
            "type": "ir.actions.act_window",
            "res_model": "mrp.production",
            "views": [(False, "list"), (False, "form")],
            "view_mode": "list,form",
            "target": "current",
            "name": self.env.context.get("action_name"),
            "domain": [("id", "in", self.move_ids.mapped("production_id").ids)],
        }

    def action_view_incoming_moves_details(self) -> dict:
        return {
            "type": "ir.actions.act_window",
            "res_model": "stock.picking",
            "views": [(False, "list"), (False, "form")],
            "view_mode": "list,form",
            "target": "current",
            "name": self.env.context.get("action_name"),
            "domain": [("id", "in", self.move_ids.mapped("picking_id").ids)],
        }
