from odoo import api, fields, models


class IrModelData(models.Model):
    _inherit = "ir.model.data"

    studio = fields.Boolean(help="Checked if it has been edited with Studio.")

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.context.get("studio"):
            for vals in vals_list:
                vals["studio"] = True
        return super().create(vals_list)

    def write(self, vals):
        if self.env.context.get("studio"):
            vals["noupdate"] = True
            vals["studio"] = True
        return super().write(vals)

    def _xmlid_extra_vals(self):
        vals = super()._xmlid_extra_vals()
        if self.env.context.get("studio"):
            vals["studio"] = True
        return vals

    def _xmlid_for_export(self):
        self.check_singleton()
        return self.complete_name.replace("__export__.", "").replace(
            "studio_customization.", ""
        )
