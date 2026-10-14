from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardStockWarehouseOrderpointUpdateReplenishmentOption(models.TransientModel):
    _name = "wizard.stock.warehouse.orderpoint.update.replenishment.option"
    _description = "Stock warehouse replenishment option"

    route_id = fields.Many2one(comodel_name="stock.route")
    product_id = fields.Many2one(comodel_name="product.product")
    replenishment_info_id = fields.Many2one(
        comodel_name="wizard.stock.warehouse.orderpoint.update.replenishment"
    )
    location_id = fields.Many2one(
        comodel_name="stock.location",
        related="warehouse_id.lot_stock_id",
    )
    warehouse_id = fields.Many2one(
        comodel_name="stock.warehouse",
        related="route_id.supplier_wh_id",
    )
    uom = fields.Char(related="product_id.uom_name")
    qty_to_order = fields.Float(related="replenishment_info_id.qty_to_order")
    qty_free = fields.Float(compute="_compute_qty_free")
    trigger = fields.Selection(
        related="replenishment_info_id.orderpoint_id.trigger",
    )
    lead_time = fields.Char(compute="_compute_lead_time")
    warning_message = fields.Char(compute="_compute_warning_message")

    @api.depends("product_id", "route_id")
    def _compute_qty_free(self) -> None:
        for record in self:
            record.qty_free = record.product_id.with_context(
                location=record.location_id.id
            ).qty_free

    @api.depends("replenishment_info_id.orderpoint_id.location_id", "route_id")
    def _compute_lead_time(self):
        for record in self:
            rules = record.product_id._get_rules_from_location(
                record.replenishment_info_id.orderpoint_id.location_id,
                route_ids=record.route_id,
            )
            delay = (
                rules.with_context(bypass_delay_description=True)._get_lead_days(
                    record.product_id
                )[0]["total_delay"]
                if rules
                else 0
            )
            record.lead_time = self.env._("%s days", delay)

    @api.depends("warehouse_id", "qty_free", "uom", "qty_to_order")
    def _compute_warning_message(self) -> None:
        self.warning_message = ""
        for record in self:
            if (
                record.product_id.uom_id.compare(record.qty_free, record.qty_to_order)
                < 0
            ):
                record.warning_message = self.env._(
                    "%(warehouse)s can only provide %(free_qty)s %(uom)s, while the quantity to order is %(qty_to_order)s %(uom)s.",
                    warehouse=record.warehouse_id.name,
                    free_qty=record.qty_free,
                    uom=record.uom,
                    qty_to_order=record.qty_to_order,
                )

    def action_select_route(self):
        if self.product_id.uom_id.compare(self.qty_free, self.qty_to_order) < 0:
            _debug.logic(
                "select_route_warning",
                qty_free=self.qty_free,
                qty_to_order=self.qty_to_order,
                route=self.route_id.id,
            )
            return {
                "type": "ir.actions.act_window",
                "res_model": "wizard.stock.warehouse.orderpoint.update.replenishment.option",
                "res_id": self.id,
                "views": [
                    [
                        self.env.ref("stock.replenishment_option_warning_view").id,
                        "form",
                    ],
                ],
                "target": "new",
                "name": self.env._("Quantity available too low"),
            }
        return self.action_order_full_quantity()

    def action_order_available_quantity(self) -> dict:
        _debug.lifecycle(
            "route_capped_to_free",
            orderpoint=self.replenishment_info_id.orderpoint_id.id,
            route=self.route_id.id,
            qty_free=self.qty_free,
        )
        self.replenishment_info_id.orderpoint_id.route_id = self.route_id
        self.replenishment_info_id.orderpoint_id.qty_to_order = self.qty_free
        return {"type": "ir.actions.act_window_close"}

    def action_order_full_quantity(self) -> dict:
        _debug.lifecycle(
            "route_full_quantity",
            orderpoint=self.replenishment_info_id.orderpoint_id.id,
            route=self.route_id.id,
        )
        self.replenishment_info_id.orderpoint_id.route_id = self.route_id
        return {"type": "ir.actions.act_window_close"}
