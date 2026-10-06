from odoo import api, fields, models


class WizardStockWarehouseOrderpointUpdateReplenishment(models.TransientModel):
    _inherit = "wizard.stock.warehouse.orderpoint.update.replenishment"
    _description = "Stock supplier replenishment information"

    supplierinfo_id = fields.Many2one(related="orderpoint_id.supplier_id")
    supplierinfo_ids = fields.Many2many(
        comodel_name="product.supplierinfo",
        relation="product_supplierinfo_stock_replenishment_info_rel",
        compute="_compute_supplierinfo_ids",
        store=True,
    )
    show_vendor_tab = fields.Boolean(compute="_compute_show_vendor_tab")

    @api.depends("orderpoint_id", "orderpoint_id.product_id.seller_ids")
    def _compute_supplierinfo_ids(self) -> None:
        for replenishment_info in self:
            replenishment_info.supplierinfo_ids = (
                replenishment_info.product_id.seller_ids
            )

    @api.depends("orderpoint_id")
    def _compute_show_vendor_tab(self) -> None:
        for replenishment_info in self:
            orderpoint = replenishment_info.orderpoint_id
            replenishment_info.show_vendor_tab = (
                not orderpoint.route_id or orderpoint.rule_ids._has_buy_action()
            )
