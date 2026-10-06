from odoo import Command, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardReportFormulaExportAttachmentFormat(models.TransientModel):
    _inherit = "wizard.report.formula.export.attachment.format"

    def _prepare_attachment_vals(
        self, file_name, file_content, mimetype, log_options_dict
    ):
        rslt = super()._prepare_attachment_vals(
            file_name, file_content, mimetype, log_options_dict
        )
        # Setting the folder_id of the attachment will make it appear in Documents
        rslt["folder_id"] = self.export_wizard_id.folder_id.id
        rslt["tag_ids"] = [Command.set(self.export_wizard_id.tag_ids.ids)]
        return rslt
