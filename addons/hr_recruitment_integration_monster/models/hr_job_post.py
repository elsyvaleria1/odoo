from odoo import models


class HrJobPost(models.Model):
    _inherit = "hr.job.post"

    def _remove_post(self):
        self.check_singleton()
        if self.platform_id != self.env.ref(
            "hr_recruitment_integration_monster.hr_recruitment_platform_monster"
        ):
            return super()._remove_post()

        if not self.api_data:
            return self.write(
                {
                    "status": "failure",
                    "status_message": self.env._(
                        "This Monster.com job post is not linked to an actual job post."
                    ),
                }
            )

        data = {
            "jobAction": "delete",
            "jobRefCode": self.api_data["jobRefCode"],
        }
        response = self.platform_id._post_api_call(data)
        return self.write(response)
