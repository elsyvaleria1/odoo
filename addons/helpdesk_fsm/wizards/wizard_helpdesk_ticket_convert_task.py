from odoo import models


class WizardHelpdeskTicketConvertTask(models.TransientModel):
    _inherit = "wizard.helpdesk.ticket.convert.task"

    def _get_default_project_id(self):
        default_project_id = super()._get_default_project_id()
        if default_project_id:
            return default_project_id

        tickets_to_convert = self._get_tickets_to_convert()
        projects = tickets_to_convert.team_id.filtered(
            lambda team: team.helpdesk_use_fsm
        ).fsm_project_id
        if len(projects) == 1:
            return projects.id
        elif len(projects) > 1:
            return projects.sorted("sequence")[0].id
        else:
            return False
