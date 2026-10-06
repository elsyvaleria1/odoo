from odoo import Command, fields, models


class WizardHrReferralAlertSend(models.TransientModel):
    _name = "wizard.hr.referral.alert.send"
    _description = "Referral Alert Mail Wizard"
    _rec_name = "subject"

    def _get_domain_user(self) -> list:
        return [
            ("share", "=", False),
            ("company_ids", "in", self.env.company.id),
            (
                "all_group_ids",
                "in",
                self.env.ref("hr_referral.group_hr_recruitment_referral_user").id,
            ),
        ]

    def _default_user_ids(self):
        user_ids = self.env["res.users"].search(self._get_domain_user())
        return [Command.set(user_ids.ids)]

    def _default_body(self) -> str:
        url = "/odoo/action-hr_referral.action_hr_referral_welcome_screen"
        return self.env._(
            "A new alert has been added to the Referrals app! Check your <a href=%(url)s>dashboard</a> now!",
            url=url,
        )

    user_ids = fields.Many2many(
        comodel_name="res.users",
        relation="Users",
        default=lambda self: self._default_user_ids(),
        store=False,
        domain=_get_domain_user,
    )
    subject = fields.Char(
        default=lambda self: self.env._("New Alert In Referrals App"),
        required=True,
    )
    body = fields.Html(
        default=lambda self: self._default_body(),
        required=True,
    )

    def action_send(self):
        self.check_singleton()
        self.env["mixin.mail.thread"].message_notify(
            partner_ids=self.user_ids.partner_id.ids,
            model_description="Referral Alerts",
            subject=self.subject,
            body=self.body,
            email_layout_xmlid="mail.mail_notification_light",
        )
        return True
