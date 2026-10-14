from odoo import api, fields, models


class StockWarehouse(models.Model):
    _inherit = "stock.warehouse"

    fleet_exit_log = fields.Boolean(
        string="Vehicle Exit Log",
        help="Every vehicle leaving this warehouse goes out on a departed trip: a "
        "delivery trip, or a route its authorisers authorised.",
    )
    fleet_exit_type_id = fields.Many2one(
        comodel_name="stock.picking.type",
        string="Routes Operation Type",
        copy=False,
        readonly=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        warehouses = super().create(vals_list)
        warehouses.filtered("fleet_exit_log")._ensure_fleet_exit_type()
        return warehouses

    def write(self, vals):
        res = super().write(vals)
        if vals.get("fleet_exit_log"):
            self._ensure_fleet_exit_type()
        return res

    def _ensure_fleet_exit_type(self) -> None:
        for warehouse in self.filtered(lambda w: not w.fleet_exit_type_id):
            warehouse.fleet_exit_type_id = self.env["stock.picking.type"].create(
                warehouse._prepare_fleet_exit_type_vals()
            )

    def _prepare_fleet_exit_type_vals(self) -> dict:
        self.check_singleton()
        return {
            "name": self.env._("Routes"),
            "code": "internal",
            "sequence_code": "RUTA",
            "warehouse_id": self.id,
            "company_id": self.company_id.id,
            "default_location_src_id": self.lot_stock_id.id,
            "default_location_dest_id": self.lot_stock_id.id,
            "dispatch_management": True,
            "fleet_exit": True,
        }
