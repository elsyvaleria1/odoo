from odoo import api, fields, models


class TelegramBot(models.Model):
    _inherit = "telegram.bot"

    _APPROVAL_COMMANDS = ("/solicitar", "/pago")

    notify_approvals = fields.Boolean(
        string="Notify Approval Requests",
        help="When enabled, this bot pushes a Telegram notification to an "
        "approver whose decision is pending on an approval.request, with "
        "inline buttons to approve, request changes or refuse. The approver "
        "must have a chat linked to this bot.",
    )
    has_approval_command = fields.Boolean(
        compute="_compute_has_approval_command",
        help="Technical: True when the bot runs an approval command "
        "(/solicitar or /pago). Used to surface the approval-notification "
        "settings only on approval bots.",
    )

    @api.depends("command_ids")
    def _compute_has_approval_command(self) -> None:
        approval_commands = set(self._APPROVAL_COMMANDS)
        for bot in self:
            command_names = set(bot.command_ids.mapped("name"))
            bot.has_approval_command = bool(command_names & approval_commands)
