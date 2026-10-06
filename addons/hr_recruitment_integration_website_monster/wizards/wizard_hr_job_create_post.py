from odoo import models


class WizardHrJobCreatePost(models.TransientModel):
    _inherit = "wizard.hr.job.create.post"

    def _prepare_monster_data(self):
        self.check_singleton()
        data = super()._prepare_monster_data()
        data["JobInformation"]["Contact"]["WebSite"] = self.get_base_url()
        if self.apply_method == "redirect":
            data["JobInformation"]["CustomApplyOnlineURL"] = self.job_id.full_url
        return data
