from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ResourceResource(models.Model):
    _inherit = "resource.resource"

    device_ids = fields.One2many(
        comodel_name="device.device",
        inverse_name="resource_id",
        string="Endpoints",
        copy=False,
    )

    @api.constrains("type", "company_id")
    def _check_endpoint_identity(self):
        Device = self.env["device.device"].sudo().with_context(active_test=False)
        non_material = self.filtered(lambda resource: resource.type != "material")
        if non_material and Device.search_count(
            [("resource_id", "in", non_material.ids)], limit=1
        ):
            raise ValidationError(
                self.env._("An endpoint can represent only a material resource.")
            )
        endpoints = Device._read_group(
            [("resource_id", "in", (self - non_material).ids)],
            ["resource_id", "company_id"],
        )
        for resource, company in endpoints:
            if resource.company_id and company != resource.company_id:
                raise ValidationError(
                    self.env._(
                        "A represented resource must remain compatible with its endpoints' companies."
                    )
                )
