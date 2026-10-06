from odoo import fields, models


class Account_FollowupFollowupLine(models.Model):
    _inherit = "account_followup.followup.line"

    send_letter = fields.Boolean(
        string="Letter",
        default=False,
    )
