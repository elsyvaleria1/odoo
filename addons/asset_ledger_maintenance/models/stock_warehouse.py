from odoo import fields, models


class StockWarehouse(models.Model):
    _inherit = "stock.warehouse"

    allow_deployment = fields.Boolean(
        default=False,
        tracking=True,
        help="Enable this warehouse for equipment deployment tracking. "
        "Creates a default deployed location for tracking operational assets.",
    )
    wh_deployed_stock_loc_id = fields.Many2one(
        comodel_name="stock.location",
        string="Deployed Location",
        copy=False,
        check_company=True,
        tracking=True,
        help="Default location for deployed/operational assets",
    )
    deployment_type_id = fields.Many2one(
        comodel_name="stock.picking.type",
        copy=False,
        check_company=True,
        tracking=True,
        help="Operation type for deploying equipment to field/operations",
    )
    deployment_return_type_id = fields.Many2one(
        comodel_name="stock.picking.type",
        copy=False,
        check_company=True,
        tracking=True,
        help="Operation type for returning equipment from deployment",
    )

    def write(self, vals):
        res = super().write(vals)

        if vals.get("allow_deployment"):
            for warehouse in self:
                warehouse._create_missing_locations(vals)

                picking_type_vals = warehouse._create_or_update_picking_types()
                if picking_type_vals:
                    warehouse.write(picking_type_vals)

        return res

    def _get_fields_location_step(self):
        return [*super()._get_fields_location_step(), "allow_deployment"]

    def _prepare_sub_location_vals(self, vals, code=False):
        sub_locations = super()._prepare_sub_location_vals(vals, code=code)

        def_values = self._get_location_step_values(vals, code)
        code = def_values["code"]

        sub_locations["wh_deployed_stock_loc_id"] = {
            "name": self.env._("Deployed"),
            "active": def_values["allow_deployment"],
            "usage": "internal",
            "barcode": code + "-DPLY",
            "deployed_location": True,
        }

        return sub_locations

    def _get_picking_type_codes(self):
        codes = super()._get_picking_type_codes()
        codes.update(
            {
                "deployment_type_id": "DPLY",
                "deployment_return_type_id": "DRTN",
            }
        )
        return codes

    def _get_picking_type_barcode_suffixes(self, codes=None):
        suffixes = super()._get_picking_type_barcode_suffixes(codes)
        suffixes.update(
            {
                field: "-" + code
                for field, code in (
                    ("deployment_type_id", "DPLY"),
                    ("deployment_return_type_id", "DRTN"),
                )
            }
        )
        return suffixes

    def _prepare_picking_type_create_vals(self):
        data = super()._prepare_picking_type_create_vals()

        data["deployment_type_id"] = {
            "name": self.env._("Deployment"),
            "code": "internal",
            "use_create_lots": False,
            "use_existing_lots": True,
            "default_location_src_id": self.lot_stock_id.id,
            "default_location_dest_id": self.wh_deployed_stock_loc_id.id,
            "company_id": self.company_id.id,
        }

        data["deployment_return_type_id"] = {
            "name": self.env._("Deployment Return"),
            "code": "internal",
            "use_create_lots": False,
            "use_existing_lots": True,
            "default_location_src_id": self.wh_deployed_stock_loc_id.id,
            "default_location_dest_id": self.lot_stock_id.id,
            "company_id": self.company_id.id,
        }

        return data

    def _prepare_picking_type_update_vals(self):
        data = super()._prepare_picking_type_update_vals()

        data["deployment_type_id"] = {
            "active": self.allow_deployment and self.active,
            "default_location_src_id": self.lot_stock_id.id,
            "default_location_dest_id": self.wh_deployed_stock_loc_id.id,
        }

        data["deployment_return_type_id"] = {
            "active": self.allow_deployment and self.active,
            "default_location_src_id": self.wh_deployed_stock_loc_id.id,
            "default_location_dest_id": self.lot_stock_id.id,
        }

        return data

    def _create_or_update_picking_types(self):
        self._create_missing_locations({})

        warehouse_data = super()._create_or_update_picking_types()

        picking_type = self.env["stock.picking.type"]

        if (
            "deployment_type_id" in warehouse_data
            and "deployment_return_type_id" in warehouse_data
        ):
            picking_type.browse(warehouse_data["deployment_type_id"]).write(
                {"return_picking_type_id": warehouse_data["deployment_return_type_id"]}
            )
            picking_type.browse(warehouse_data["deployment_return_type_id"]).write(
                {"return_picking_type_id": warehouse_data["deployment_type_id"]}
            )

        return warehouse_data
