from odoo import models


class ResGroups(models.Model):
    _inherit = "res.groups"

    def write(self, vals):
        result = super().write(vals)
        if vals.keys() & {"user_ids", "implied_ids"}:
            self.all_user_ids._sync_telegram_command_menus()
        return result
