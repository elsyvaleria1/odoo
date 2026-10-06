from odoo import models


class HrJob(models.Model):
    _inherit = "hr.job"

    def action_view_whatsapp_composer(self) -> dict:
        self.check_singleton()
        link_to_share_wizard = self.env["wizard.hr.job.share.referral.link"].create(
            {
                "job_id": self.id,
                "channel": "direct",
            }
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": "wizard.whatsapp.message.send",
            "view_mode": "form",
            "name": self.env._("Share Job By WhatsApp"),
            "target": "new",
            "context": {
                "active_id": link_to_share_wizard.id,
                "active_model": link_to_share_wizard._name,
            },
        }
