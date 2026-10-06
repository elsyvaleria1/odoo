from odoo import api, fields, models
from odoo.exceptions import AccessError


class WizardHrJobSendReferralMail(models.TransientModel):
    _name = "wizard.hr.job.send.referral.mail"
    _description = "Referral Send Mail"

    job_id = fields.Many2one(
        comodel_name="hr.job",
        default=lambda self: self.env.context.get("active_id", None),
        readonly=True,
    )
    url = fields.Char(
        compute="_compute_url",
        readonly=True,
    )
    email_to = fields.Char(
        string="Email",
        required=True,
    )
    subject = fields.Char(default="Job for you")
    body_html = fields.Html(
        string="Body",
        compute="_compute_body_html",
        store=True,
        readonly=False,
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
    def _compute_body_html(self) -> None:
        for wizard in self:
            wizard.body_html = self.env["ir.qweb"]._render(
                "hr_referral.referral_email_body_template",
                {
                    "job_id": wizard.job_id,
                    "companies": self.env.companies.filtered(
                        lambda c: c.website_id.domain or c.website
                    ),
                    "url": wizard.url,
                },
            )

    def send_mail_referral(self) -> dict:
        if not self.env.user.has_group(
            "hr_referral.group_hr_recruitment_referral_user"
        ):
            raise AccessError(self.env._("Do not have access"))

        self.env["mail.mail"].sudo().create(
            {
                "body_html": self.body_html,
                "author_id": self.env.user.partner_id.id,
                "email_from": self.env.user.email_formatted,
                "email_to": self.email_to,
                "subject": self.subject,
            }
        ).send()

        return {"type": "ir.actions.act_window_close"}
