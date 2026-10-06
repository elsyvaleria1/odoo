from odoo import api, fields, models


class DeviceDevice(models.Model):
    _inherit = "device.device"

    telegram_account_id = fields.Many2one(
        comodel_name="telegram.account",
        string="Telegram Account",
        compute="_compute_telegram_account_id",
        classification="device_mobile_telegram.phone_telegram",
        groups="base.group_system",
        help="The Telegram account whose shared number is this phone's.",
    )
    telegram_user_id = fields.Many2one(
        comodel_name="res.users",
        string="Telegram Acts As",
        compute="_compute_telegram_account_id",
        classification="device_mobile_telegram.phone_telegram",
        groups="base.group_system",
        help="The Odoo user that Telegram account is connected to.",
    )

    @api.depends("line_number_e164")
    def _compute_telegram_account_id(self) -> None:
        numbers = [number for number in self.mapped("line_number_e164") if number]
        accounts = self.env["telegram.account"].search(
            [("phone_e164", "in", numbers)], order="phone_verified_at desc"
        )
        by_number = {}
        for account in accounts:
            by_number.setdefault(account.phone_e164, account)
        for device in self:
            account = by_number.get(
                device.line_number_e164, self.env["telegram.account"]
            )
            device.telegram_account_id = account
            device.telegram_user_id = (
                account._acting_user("internal") if account else False
            )
