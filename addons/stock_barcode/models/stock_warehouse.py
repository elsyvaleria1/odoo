from odoo import models


class StockWarehouse(models.Model):
    _inherit = "stock.warehouse"

    def _prepare_picking_type_create_vals(self):
        # No max_sequence cursor, and no [0]: stock replaced
        # `_prepare_picking_type_create_vals(max_sequence) -> (values, next)` with
        # a plain mapping, allocating `sequence` from the position in
        # `_get_picking_type_codes`. This module adds no picking type, so it
        # extends neither that mapping nor `_get_picking_type_barcode_suffixes`
        # — it only settles how the pick type scans.
        values = super()._prepare_picking_type_create_vals()
        values["pick_type_id"]["restrict_scan_source_location"] = "mandatory"
        values["pick_type_id"]["restrict_scan_dest_location"] = "no"
        return values

    def _prepare_picking_type_update_vals(self):
        values = super()._prepare_picking_type_update_vals()
        # When multi-steps delivery is enabled, the source scan setting for the pick is equal to the
        # delivery type's one, and the scan source for the delivery is disabled (by default).
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
