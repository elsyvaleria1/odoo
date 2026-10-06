from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ProductTemplate(models.Model):
    _inherit = "product.template"

    maintenance_ok = fields.Boolean(
        string="Maintenance",
        default=False,
        help="If checked, this product can have recurring maintenance schedules.",
    )

    @api.constrains("maintenance_ok", "tracking")
    def _check_maintenance_tracking(self) -> None:
        for template in self:
            if template.maintenance_ok and template.tracking != "serial":
                raise ValidationError(
                    self.env._(
                        "Products marked for maintenance must have tracking set to 'By Unique Serial Number'."
                    )
                )
