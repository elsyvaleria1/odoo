from odoo import api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.telegram.tools.authority import operating

_WHEN = [
    ("always", "Always"),
    ("away", "While I am away from Odoo"),
    ("never", "Never"),
]


class ResUsersSettings(models.Model):
    _inherit = "res.users.settings"

    telegram_notify_inbox = fields.Selection(
        selection=_WHEN,
        string="Telegram: Notifications",
        default="away",
        required=True,
        help="Notifications of records you follow or are mentioned on.",
    )
    telegram_notify_chats = fields.Selection(
        selection=_WHEN,
        string="Telegram: Chats",
        default="away",
        required=True,
        help="Direct messages and group chats.",
    )
    telegram_notify_channels = fields.Selection(
        selection=[
            ("all", "Every message"),
            ("mentions", "Only when I am mentioned"),
            ("never", "Never"),
        ],
        string="Telegram: Channels",
        default="mentions",
        required=True,
        help="Discuss channels. A muted channel sends nothing.",
    )
    telegram_notify_chat_id = fields.Many2one(
        comodel_name="telegram.chat",
        string="Telegram: Deliver To",
        ondelete="set null",
        help="The Telegram chat your notifications go to, when you connected "
        "more than one. Set to the last one you connected through a bot that "
        "delivers them. Empty: the one you used last.",
    )
    telegram_grace_seconds = fields.Integer(
        string="Telegram: Wait Before Sending (seconds)",
        default=60,
        help="How long a message waits before it goes to Telegram. Read in Odoo "
        "meanwhile, or while you are online, it is not sent.",
    )

    @api.constrains("telegram_notify_chat_id")
    def _check_telegram_notify_chat_id(self) -> None:
        for settings in self.filtered("telegram_notify_chat_id"):
            chat = operating(settings.telegram_notify_chat_id)
            if (
                chat.chat_type != "private"
                or chat.business_connection_id
                or not chat.account_id
                or chat.account_id._acting_user("internal") != settings.user_id
            ):
                raise ValidationError(
                    self.env._(
                        "Notifications go only to a Telegram chat of your own "
                        "with a bot."
                    )
                )
