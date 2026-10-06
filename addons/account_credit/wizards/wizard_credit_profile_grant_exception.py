from datetime import timedelta

from odoo import api, fields, models


class WizardCreditProfileGrantException(models.TransientModel):
    _name = "wizard.credit.profile.grant.exception"
    _description = "Grant a dated credit exception"

    profile_id = fields.Many2one(
        comodel_name="credit.profile",
        required=True,
    )
    max_days = fields.Integer(
        compute="_compute_max_days",
        precompute=True,
        store=True,
    )
    exception_until = fields.Date(
        compute="_compute_max_days",
        precompute=True,
        store=True,
        readonly=False,
        required=True,
    )
    reason = fields.Char(required=True)

    @api.depends("profile_id")
    def _compute_max_days(self) -> None:
        today = fields.Date.today()
        for wizard in self:
            days = (
                wizard.profile_id._config().exception_max_days
                if wizard.profile_id
                else 0
            )
            wizard.max_days = days
            wizard.exception_until = today + timedelta(days=days)

    def action_grant(self) -> None:
        self.check_singleton()
        self.profile_id.write(
            {"exception_until": self.exception_until, "exception_reason": self.reason}
        )
        self.profile_id._open_review("exception")
