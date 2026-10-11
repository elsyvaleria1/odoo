from odoo import models


class StockWarehouse(models.Model):
    _inherit = "stock.warehouse"

    def _prepare_picking_type_create_vals(self):
        values = super()._prepare_picking_type_create_vals()
        values["pick_type_id"]["restrict_scan_source_location"] = "mandatory"
        values["pick_type_id"]["restrict_scan_dest_location"] = "no"
        return values

    def _prepare_picking_type_update_vals(self):
        values = super()._prepare_picking_type_update_vals()
        if values["pick_type_id"].get("active"):
            if (
                self.out_type_id.restrict_scan_source_location == "mandatory"
                and self.pick_type_id.restrict_scan_dest_location == "optional"
            ):
                values["out_type_id"]["restrict_scan_source_location"] = "no"
                values["pick_type_id"]["restrict_scan_source_location"] = (
                    self.out_type_id.restrict_scan_source_location
                )
            values["pick_type_id"]["restrict_scan_dest_location"] = "no"
        elif self.pick_type_id.active:
            values["out_type_id"]["restrict_scan_source_location"] = (
                self.pick_type_id.restrict_scan_source_location
            )
        return values
