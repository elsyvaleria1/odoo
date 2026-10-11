from odoo import api, fields, models


class MarketingCampaign(models.Model):
    _inherit = "marketing.campaign"

    mailing_sms_count = fields.Integer(
        string="# SMS Mailings",
        compute="_compute_mailing_sms_count",
    )

    @api.depends("marketing_activity_ids.mass_mailing_id.mailing_type")
    def _compute_mailing_sms_count(self) -> None:
        for campaign in self:
            campaign.mailing_sms_count = len(
                campaign.mapped("marketing_activity_ids.mass_mailing_id").filtered(
                    lambda mailing: mailing.mailing_type == "sms"
                )
            )

    def action_view_sms(self):
        self.check_singleton()
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "marketing_automation_sms.mail_mass_mailing_action_marketing_automation_sms"
        )
        action["domain"] = [
            "&",
            ("use_in_marketing_automation", "=", True),
            ("id", "in", self.mapped("marketing_activity_ids.mass_mailing_id").ids),
            ("mailing_type", "=", "sms"),
        ]
        action["context"] = dict(self.env.context)
        action["context"].update(
            {
                "default_mailing_model_id": self.model_id.id,
                "default_campaign_id": self.utm_campaign_id.id,
                "default_use_in_marketing_automation": True,
                "default_mailing_type": "sms",
                "default_state": "done",
                "create": False,
            }
        )
        return action
