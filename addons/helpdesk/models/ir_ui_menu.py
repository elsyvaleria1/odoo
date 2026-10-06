from odoo import models


class IrUiMenu(models.Model):
    _inherit = "ir.ui.menu"

    def _get_blacklisted_menu_ids(self):
        res = super()._get_blacklisted_menu_ids()
        if not self.env.user.has_group("helpdesk.group_helpdesk_manager"):
            res.append(self.env.ref("helpdesk.helpdesk_ticket_report_menu_ratings").id)
        return res
