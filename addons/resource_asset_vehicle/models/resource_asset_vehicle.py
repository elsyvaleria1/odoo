from odoo import api, fields, models

from odoo.addons.base.fields import ResourceIdentifier


class ResourceAssetVehicle(models.Model):
    _name = "resource.asset.vehicle"
    _description = "Vehicle"
    _inherit = ["mixin.resource.kind"]
    _table = "resource_asset_vehicle"
    _resource_kind_code = "vehicle"

    license_plate = ResourceIdentifier(
        identifier_code="plate",
        through="resource_id",
        store=True,
    )
    vin_sn = ResourceIdentifier(
        identifier_code="vin",
        through="resource_id",
        store=True,
    )
    engine_sn = ResourceIdentifier(
        identifier_code="engine",
        through="resource_id",
        store=True,
    )

    company_country_code = fields.Char(related="company_id.country_id.code")
    tag_ids = fields.Many2many(
        comodel_name="fleet.vehicle.tag",
        relation="resource_asset_fleet_vehicle_tag_rel",
        column1="asset_id",
        column2="tag_id",
        string="Tags",
        copy=False,
    )
    manufacturer_id = fields.Many2one(
        related="product_id.manufacturer_id",
        string="Manufacturer",
    )
    vehicle_color = fields.Char(related="product_id.vehicle_color")
    seats = fields.Integer(related="product_id.seats")
    doors = fields.Integer(related="product_id.doors")
    trailer_hook = fields.Boolean(related="product_id.trailer_hook")
    transmission = fields.Selection(related="product_id.transmission")
    fuel_type = fields.Selection(related="product_id.fuel_type")
    power = fields.Float(related="product_id.power")
    power_unit = fields.Selection(related="product_id.power_unit")
    horsepower = fields.Float(related="product_id.horsepower")
    co2 = fields.Float(related="product_id.co2")
    co2_emission_unit = fields.Selection(related="product_id.co2_emission_unit")
    vehicle_range = fields.Integer(related="product_id.vehicle_range")
    fuel_tank_capacity = fields.Float(
        related="product_id.fuel_tank_capacity",
        digits=(10, 2),
    )
    range_unit = fields.Selection(related="product_id.range_unit")
    service_count = fields.Integer(compute="_compute_service_count")

    def _compute_service_count(self) -> None:
        counts = self.resource_id._get_log_counts_by_type()
        for vehicle in self:
            vehicle.service_count = counts[vehicle.id]["service"]

    @api.onchange("product_id")
    def _onchange_product_id_model_year(self) -> None:
        if not self.model_year and self.product_id.vehicle_model_year:
            self.model_year = int(self.product_id.vehicle_model_year)

    def action_view_services(self):
        return self.resource_id._action_view_logs(
            [("log_type", "=", "service")],
            {"search_default_groupby_product": 1},
            xml_id="resource_asset_vehicle.fleet_vehicle_service_action",
        )

    def action_view_odometer(self):
        self.check_singleton()
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "resource_asset_vehicle.fleet_vehicle_odometer_action"
        )
        action["domain"] = [
            ("asset_id", "=", self.id),
            ("meter_id.kind", "=", "odometer"),
        ]
        return action

    def action_send_email(self) -> dict:
        return {
            "name": self.env._("Send Email"),
            "type": "ir.actions.act_window",
            "target": "new",
            "view_mode": "form",
            "res_model": "wizard.resource.asset.vehicle.send.mail.driver",
            "context": {"default_vehicle_ids": self.ids},
        }
