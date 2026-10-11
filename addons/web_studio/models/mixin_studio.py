from odoo import api, models


class MixinStudio(models.AbstractModel):

    _name = "mixin.studio"
    _description = "Studio Mixin"

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        if self.env.context.get("studio") and not self.env.context.get("install_mode"):
            for ob in res:
                ob.create_studio_model_data(ob.display_name)
        return res

    def write(self, vals):
        res = super().write(vals)

        if self.env.context.get("studio") and not self.env.context.get("install_mode"):
            for record in self:
                record.create_studio_model_data(record.display_name)

        return res
