from odoo import fields, models

_SETTINGS = (
    "telegram_notify_inbox",
    "telegram_notify_chats",
    "telegram_notify_channels",
    "telegram_grace_seconds",
)


class ResUsers(models.Model):
    _inherit = "res.users"

    telegram_notify_inbox = fields.Selection(
        related="res_users_settings_id.telegram_notify_inbox",
        string="Telegram: Notifications",
        readonly=False,
    )
    telegram_notify_chats = fields.Selection(
        related="res_users_settings_id.telegram_notify_chats",
        string="Telegram: Chats",
        readonly=False,
    )
    telegram_notify_channels = fields.Selection(
        related="res_users_settings_id.telegram_notify_channels",
        string="Telegram: Channels",
        readonly=False,
    )
    telegram_grace_seconds = fields.Integer(
        related="res_users_settings_id.telegram_grace_seconds",
        string="Telegram: Wait Before Sending (seconds)",
        readonly=False,
    )

    @property
    def SELF_READABLE_FIELDS(self):
        return [*super().SELF_READABLE_FIELDS, *_SETTINGS]

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return [*super().SELF_WRITEABLE_FIELDS, *_SETTINGS]

    def _telegram_settings(self):
        self.check_singleton()
        # a user's preferences, read as that user: everyone keeps their own
        return (
            self.env["res.users.settings"].with_user(self)._get_or_create_for_user(self)
        )
