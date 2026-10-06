from odoo import api, models


class ResCompany(models.Model):
    _inherit = "res.company"

    @api.model
    def winbooks_import_action(self):
        return self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "account_winbooks_import.winbooks_import_action"
        )
