from odoo import api, fields, models
from odoo.exceptions import AccessError


class WizardHrJobSendReferralSms(models.TransientModel):
    _name = "wizard.hr.job.send.referral.sms"
    _description = "Referral Send sms"

    job_id = fields.Many2one(
        comodel_name="hr.job",
        default=lambda self: self.env.context.get("active_id", None),
        readonly=True,
    )
    url = fields.Char(
        compute="_compute_url",
        readonly=True,
    )
    recipient = fields.Char(required=True)
    body_plaintext = fields.Text(
        string="Body",
        compute="_compute_body_plaintext",
        readonly=False,
        required=True,
    )

    @api.depends("job_id")
    def _compute_url(self) -> None:
        link_wizards = self.env["wizard.hr.job.share.referral.link"].create(
            [
                {
                    "job_id": wizard.job_id.id,
                    "channel": "direct",
                }
                for wizard in self
            ]
        )
        for wizard, link_wizard in zip(self, link_wizards, strict=True):
            wizard.url = link_wizard.url

    @api.depends("job_id", "url")
    def _compute_body_plaintext(self) -> None:
        for wizard in self:
            if not wizard.body_plaintext:
                wizard.body_plaintext = self.env._(
                    "Hello! There is an amazing job offer for %(job_name)s in my company!"
                    " It will be a fit for you %(referral_url)s",
                    job_name=wizard.job_id.name,
                    referral_url=wizard.url,
                )

    def send_sms_referral(self) -> dict:
        if not self.env.user.has_group(
            "hr_referral.group_hr_recruitment_referral_user"
        ):
            raise AccessError(
                self.env._("You do not have the required access rights to send SMS.")
            )

        self.env["sms.sms"].create(
            [
                {
                    "number": wizard.recipient,
                    "body": wizard.body_plaintext,
                }
                for wizard in self
            ]
        ).send()

        return {"type": "ir.actions.act_window_close"}
