from odoo import fields, models

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
    telegram_grace_seconds = fields.Integer(
        string="Telegram: Wait Before Sending (seconds)",
        default=60,
        help="How long a message waits before it goes to Telegram. Read in Odoo "
        "meanwhile, or while you are online, it is not sent.",
    )
