from odoo import api, models


class ResCompany(models.Model):
    _inherit = "res.company"

    @api.model
    def account_saft_import_action(self):
        return self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "account_saft_import.import_action"
        )
