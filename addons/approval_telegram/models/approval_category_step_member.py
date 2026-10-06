from odoo import fields, models


class ApprovalCategoryStepMember(models.Model):
    _inherit = "approval.category.step.member"

    notify_telegram = fields.Boolean(
        default=False,
        help="When enabled, this member receives a Telegram push (with "
        "approve / request-changes / refuse buttons) for requests pending on "
        "this step. Opt-in: disabled by default. The bot's global "
        "'Notify Approval Requests' switch must also be on, and the member "
        "must have a chat linked to an approval bot.",
    )
