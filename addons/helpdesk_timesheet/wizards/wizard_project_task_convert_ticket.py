from odoo import models


class WizardProjectTaskConvertTicket(models.TransientModel):
    _inherit = "wizard.project.task.convert.ticket"

    def _get_default_helpdesk_team_id(self):
        tasks_to_convert = self._get_tasks_to_convert()
        teams = tasks_to_convert.project_id.helpdesk_team
        if len(teams) == 1:
            return teams.id
        elif len(teams) > 1:
            return teams.sorted("sequence")[0].id
        else:
            return False
