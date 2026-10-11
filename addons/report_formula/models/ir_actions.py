from odoo import models


class Ir_Actions_Account_Report_Download(models.AbstractModel):
    _name = "ir_actions_account_report_download"

    _description = "Technical model for report downloads"

    def _get_fields_readable(self):
        return self.env["ir.actions.actions"]._get_fields_readable() | {"data"}
