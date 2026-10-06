from odoo import models


class WizardProjectTaskConvertTicket(models.TransientModel):
    _inherit = "wizard.project.task.convert.ticket"

    def _prepare_ticket_vals(self, task) -> dict:
        return {
            **super()._prepare_ticket_vals(task),
            "sale_line_id": task.sale_line_id.id,
        }
