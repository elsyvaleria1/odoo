from odoo import models


class IrUiMenu(models.Model):
    _inherit = "ir.ui.menu"

    def _get_blacklisted_menu_ids(self):
        res = super()._get_blacklisted_menu_ids()
        res.append(self.env.ref("esg_csrd.menu_esg_csrd_config").id)
        return res
