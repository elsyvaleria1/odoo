from odoo import models


class WizardHrJobCreatePost(models.TransientModel):
    _inherit = "wizard.hr.job.create.post"

    def _prepare_monster_data(self):
        self.check_singleton()
        data = super()._prepare_monster_data()
        if self.job_id.skill_ids:
            data["JobInformation"]["JobSkills"] = {
                "JobSkill": [{"Name": skill.name} for skill in self.job_id.skill_ids],
            }
        return data
