from odoo import models


class IrUiMenu(models.Model):
    _inherit = "ir.ui.menu"

    def _get_account_readonly_menu_ids(self):
        return [
            "account.account_tag_menu",
            "account.menu_account_group",
            "account.menu_action_account_report_multicurrency_revaluation",
            "account.menu_action_account_report_tree",
        ]

    def _get_hidden_menu_ids(self):
        hidden_ids = super()._get_hidden_menu_ids()
        if not self.env.user.has_group("account.group_account_readonly"):
            hidden_ids.update(
                menu_id
                for ref_menu in self._get_account_readonly_menu_ids()
                if (menu_id := self.env["ir.model.data"]._xmlid_to_res_id(ref_menu))
            )
        return hidden_ids
