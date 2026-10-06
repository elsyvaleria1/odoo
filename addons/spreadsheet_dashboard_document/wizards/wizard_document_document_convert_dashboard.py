from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardDocumentDocumentConvertDashboard(models.TransientModel):
    _name = "wizard.document.document.convert.dashboard"
    _description = "Create a dashboard from a spreadsheet document"

    name = fields.Char(
        string="Dashboard Name",
        compute="_compute_name",
        precompute=True,
        store=True,
        readonly=False,
        required=True,
    )
    document_id = fields.Many2one(
        comodel_name="document.document",
        readonly=True,
        required=True,
        domain=[("handler", "=", "spreadsheet")],
    )
    dashboard_group_id = fields.Many2one(
        comodel_name="spreadsheet.dashboard.group",
        string="Dashboard Section",
        required=True,
    )
    group_ids = fields.Many2many(
        comodel_name="res.groups",
        string="Access Groups",
        default=lambda self: self._default_group_ids(),
    )

    def _default_group_ids(self):
        return self.env["spreadsheet.dashboard"].default_get(["group_ids"])["group_ids"]

    @api.depends("document_id.name")
    def _compute_name(self):
        for wizard in self:
            wizard.name = wizard.document_id.name

    def create_dashboard(self) -> dict:
        self.check_singleton()
        dashboard = self.env["spreadsheet.dashboard"].create(
            {
                "name": self.name,
                "dashboard_group_id": self.dashboard_group_id.id,
                "group_ids": self.group_ids.ids,
                "spreadsheet_data": self.document_id._get_spreadsheet_serialized_snapshot(),
            }
        )
        # transfer the comments to the dashboard
        threads = (
            self.env["spreadsheet.cell.thread"]
            .sudo()
            .search([("document_id", "=", self.document_id.id)])
        )
        threads.write({"dashboard_id": dashboard.id, "document_id": False})
        _debug.lifecycle(
            "dashboard_created_from_document",
            wizard=self,
            document=self.document_id,
            dashboard=dashboard,
            threads_moved=len(threads),
        )
        self.document_id._remove_comments_from_data()

        # move the document to the archive
        self.document_id.action_archive()
        return {
            "type": "ir.actions.client",
            "tag": "action_spreadsheet_dashboard",
            "name": self.name,
            "target": "main",
            "params": {
                "dashboard_id": dashboard.id,
            },
        }
