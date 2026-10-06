from odoo import models


class WizardHelpdeskTicketConvertTask(models.TransientModel):
    _inherit = "wizard.helpdesk.ticket.convert.task"

    def _get_default_project_id(self):
        tickets_to_convert = self._get_tickets_to_convert()
        projects = tickets_to_convert.project_id
        if len(projects) == 1:
            return projects.id
        elif len(projects) > 1:
            return projects.sorted("sequence")[0].id
        else:
            return False
