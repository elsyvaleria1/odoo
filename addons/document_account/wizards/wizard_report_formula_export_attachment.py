from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardReportFormulaExportAttachment(models.TransientModel):
    """Extends the report export wizard to give it the ability to save the
    attachments it generates as documents, in a folder of the Documents app.
    """

    _inherit = "wizard.report.formula.export.attachment"

    def _get_default_folder(self):
        return self.env.company.account_folder_id or self.env.ref(
            "document.document_finance_folder", raise_if_not_found=False
        )

    folder_id = fields.Many2one(
        comodel_name="document.document",
        default=lambda self: self._get_default_folder(),
        required=True,
        domain=[("type", "=", "folder"), ("shortcut_document_id", "=", False)],
        help="Folder where to save the generated file",
    )
    tag_ids = fields.Many2many(
        comodel_name="document.tag",
        relation="export_wiz_document_tag_rel",
        string="Tags",
    )

    @api.onchange("folder_id")
    def on_folder_id_change(self) -> None:
        self.tag_ids = False

    def export_report(self):
        # When making the export with Documents app installed, we want the resulting action to open the folder of Documents where
        # the attachments were saved, with the folder/tags pre-selected in the search panel, instead of the regular ir.attachment objects.
        self.check_singleton()
        with _debug.perf(
            "report_export_to_documents", cr=self.env.cr, folder=self.folder_id
        ) as span:
            created_attachments = self.env["document.document"].create(
                list(self._get_attachments_to_save())
            )
            span.set(created=len(created_attachments))
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Generated Documents"),
            "view_mode": "kanban",
            "res_model": "document.document",
            "domain": [],
            "context": {
                "searchpanel_default_user_folder_id": str(self.folder_id.id),
                "searchpanel_default_tag_ids": self.tag_ids.ids,
            },
            "view_id": self.env.ref("document.document_view_kanban").id,
        }
