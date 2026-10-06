from odoo import models
from odoo.fields import Domain


class ProjectTask(models.Model):
    _name = "project.task"
    _inherit = "project.task"

    def action_fsm_view_material(self):
        res = super().action_fsm_view_material()
        res["domain"] = Domain.AND([res["domain"], [("recurring_invoice", "=", False)]])
        return res
