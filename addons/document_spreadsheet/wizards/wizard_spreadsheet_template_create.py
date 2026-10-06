from odoo import fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardSpreadsheetTemplateCreate(models.TransientModel):
    _name = "wizard.spreadsheet.template.create"
    _inherit = ["mixin.spreadsheet"]
    _description = "Spreadsheet Template Save Wizard"

    template_name = fields.Char(required=True)

    def save_template(self) -> dict:
        self.check_singleton()
        template = self.env["spreadsheet.template"].create(
            {
                "name": self.template_name,
                "spreadsheet_data": self.spreadsheet_data,
                "thumbnail": self.thumbnail,
            }
        )
        template._remove_comments_from_data()
        _debug.lifecycle("spreadsheet_template_saved", wizard=self, template=template)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "message": self.env._('"%s" saved as template', self.template_name),
                "sticky": False,
                "type": "info",
            },
        }
