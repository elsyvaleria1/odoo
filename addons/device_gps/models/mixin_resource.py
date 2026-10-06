from odoo import fields, models


class MixinResource(models.AbstractModel):
    _name = "mixin.resource"
    _inherit = ["mixin.resource", "mixin.gps"]

    gps_device_id = fields.Many2one(
        related="resource_id.gps_device_id",
        copy=False,
        readonly=False,
    )

    gps_observation_id = fields.Many2one(
        related="resource_id.gps_observation_id",
        compute_sudo=False,
        groups="device_gps.group_device_gps_user",
    )

    def _gps_resource(self):
        self.check_singleton()
        return self.resource_id

    def _prepare_resource_values(self, vals, tz):
        resource_vals = super()._prepare_resource_values(vals, tz)
        if "gps_device_id" in vals:
            resource_vals["gps_device_id"] = vals.pop("gps_device_id")
        return resource_vals
