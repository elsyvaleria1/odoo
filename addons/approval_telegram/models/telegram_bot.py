from odoo import fields, models


class TelegramBot(models.Model):
    _inherit = "telegram.bot"

    notify_approvals = fields.Boolean(
        string="Notify Approval Requests",
        help="When enabled, this bot pushes a Telegram notification to an "
        "approver whose decision is pending on an approval.request, with "
        "inline buttons to approve, request changes or refuse. The approver "
        "must have a chat linked to this bot.",
    )
