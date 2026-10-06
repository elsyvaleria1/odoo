from odoo import models


class WizardHelpdeskTicketCreateFsmTask(models.TransientModel):
    _inherit = "wizard.helpdesk.ticket.create.fsm.task"

    def _generate_task_values(self):
        res = super()._generate_task_values()
        if self.helpdesk_ticket_id.sale_line_id:
            res["sale_line_id"] = self.helpdesk_ticket_id.sale_line_id.id
        return res
