from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import SQL


class DeviceDevice(models.Model):
    _inherit = "device.device"
    _check_company_auto = True
    _resource_owns = False
    _resource_type = "material"

    resource_id = fields.Many2one(
        comodel_name="resource.resource",
        string="Represented Resource",
        index="btree_not_null",
        copy=False,
        domain=[("type", "=", "material")],
        ondelete="restrict",
        check_company=True,
        help="Optional operational identity represented by this endpoint. Several endpoints can represent the same resource. This is distinct from the resource observed by a sensor and does not change endpoint structure or resource containment.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        ids = [
            vals.get("resource_id", self.env.context.get("default_resource_id"))
            for vals in vals_list
        ]
        if resource_ids := [resource_id for resource_id in ids if resource_id]:
            self.check_access("create")
            resources = self.env["resource.resource"].browse(resource_ids)
            resources.check_access("read")
            resources._lock_for_integrity()
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("resource_id"):
            self.check_access("write")
            resources = self.env["resource.resource"].browse(vals["resource_id"])
            resources.check_access("read")
            resources._lock_for_integrity()
        return super().write(vals)

    @api.constrains("resource_id")
    def _check_resource_type(self):
        if any(resource.type != "material" for resource in self.resource_id):
            raise ValidationError(
                self.env._("An endpoint can represent only a material resource.")
            )

    @api.model
    def _get_integrity_checks(self):
        checks = super()._get_integrity_checks()
        checks.update(
            {
                "resource_company_mismatch": (
                    "device_device",
                    SQL(
                        "resource_id IN (SELECT id FROM resource_resource resource WHERE resource.company_id IS NOT NULL AND resource.company_id IS DISTINCT FROM device.company_id)"
                    ),
                ),
                "non_material_resource": (
                    "device_device",
                    SQL(
                        "resource_id IN (SELECT id FROM resource_resource resource WHERE resource.type != 'material')"
                    ),
                ),
            }
        )
        return checks
