from odoo import models


class WizardHelpdeskTicketConvertTask(models.TransientModel):
    _inherit = "wizard.helpdesk.ticket.convert.task"

    def _prepare_task_vals(self, ticket) -> dict:
        return {
            **super()._prepare_task_vals(ticket),
            "sale_line_id": ticket.sale_line_id.id,
        }
