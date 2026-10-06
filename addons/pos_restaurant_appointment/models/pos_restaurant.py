from odoo import api, fields, models


class RestaurantTable(models.Model):
    _inherit = "restaurant.table"

    resource_id = fields.Many2one(
        comodel_name="resource.resource",
        string="Bookable resource",
        index="btree_not_null",
    )

    @api.model
    def _load_pos_data_fields(self, config):
        data = super()._load_pos_data_fields(config)
        data += ["resource_id"]
        return data

    @api.model_create_multi
    def create(self, vals_list):
        tables = super().create(vals_list)

        for table in tables:
            if not table.resource_id:
                table.resource_id = (
                    table.env["resource.resource"]
                    .sudo()
                    .create(
                        {
                            "name": f"Table {table.table_number}",
                            "type": "material",
                            "capacity": table.seats,
                            "pos_table_ids": table,
                            "appointment_type_ids": table.floor_id.pos_config_ids.appointment_type_id,
                        }
                    )
                )

        return tables

    def write(self, vals):
        res = super().write(vals)

        if "active" in vals:
            if not vals["active"]:
                self.resource_id.sudo().active = False
            else:
                for table in self:
                    if not table.resource_id:
                        continue
                    table.resource_id.sudo().write(
                        {
                            "name": f"Table {table.table_number}",
                            "capacity": table.seats,
                        }
                    )

        return res

    def unlink(self):
        for table in self:
            table.resource_id.sudo().unlink()

        return super().unlink()

    @api.ondelete(at_uninstall=True)
    def _remove_linked_resources(self) -> None:
        for table in self:
            table.resource_id.unlink()
