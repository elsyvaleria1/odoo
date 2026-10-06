from markupsafe import Markup

from odoo import fields, models


class WizardPhoneBlacklistArchive(models.TransientModel):
    _name = "wizard.phone.blacklist.archive"
    _description = "Remove phone from blacklist"

    phone = fields.Char(
        string="Phone Number",
        readonly=True,
        required=True,
    )
    reason = fields.Char()

    def action_unblacklist_apply(self):
        if self.reason:
            message = Markup("<p>%s</p>") % self.env._(
                "Unblock Reason: %(reason)s", reason=self.reason
            )
        else:
            message = None
        return self.env["phone.blacklist"]._remove(
            [self.phone],
            message=message,
        )
