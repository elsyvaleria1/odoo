from odoo import api, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class SpreadsheetDashboard(models.Model):
    _inherit = "spreadsheet.dashboard"

    def action_add_document_spreadsheet_to_dashboard(self) -> dict:
        return {
            "type": "ir.actions.client",
            "tag": "action_dashboard_add_spreadsheet",
            "params": {
                "dashboardGroupId": self.env.context.get("dashboard_group_id"),
            },
        }

    @api.model
    def add_document_spreadsheet_to_dashboard(
        self, dashboard_group_id, document_id
    ) -> None:
        document = self.env["document.document"].browse(document_id)
        dashboard = self.create(
            {
                "name": document.name,
                "dashboard_group_id": dashboard_group_id,
                "spreadsheet_snapshot": document.spreadsheet_snapshot,
                "spreadsheet_binary_data": document.datas,
            }
        )
        document._copy_revisions_to(dashboard)
        document.action_archive()
        dashboard._remove_comments_from_data()
        _debug.lifecycle(
            "dashboard_created_from_document",
            document=document,
            dashboard=dashboard,
            group_id=dashboard_group_id,
        )

    @api.model
    def action_view_new_dashboard(self, dashboard_group_id) -> dict:
        dashboard = self.create(
            {
                "name": self.env._("Untitled dashboard"),
                "dashboard_group_id": dashboard_group_id,
            }
        )
        _debug.lifecycle(
            "dashboard_created_empty", dashboard=dashboard, group_id=dashboard_group_id
        )
        return {
            "type": "ir.actions.client",
            "tag": "action_edit_dashboard",
            "params": {
                "spreadsheet_id": dashboard.id,
            },
        }
