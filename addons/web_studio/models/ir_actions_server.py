from odoo import api, models


class IrActionsServer(models.Model):
    _name = "ir.actions.server"
    _inherit = ["mixin.studio", "ir.actions.server"]

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        if self.env.context.get("web_studio.auto_add_to_context"):
            res.create_action()
        return res
