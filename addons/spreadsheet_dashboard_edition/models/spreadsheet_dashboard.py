import json

from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog
from odoo.libs.json import dumps as json_dumps

_debug = DebugLog(__name__)


class SpreadsheetDashboard(models.Model):
    _name = "spreadsheet.dashboard"
    _inherit = ["spreadsheet.dashboard", "mixin.spreadsheet"]

    is_from_data = fields.Boolean(
        export_string_translation=False,
        compute="_compute_is_from_data",
        compute_sudo=True,
    )

    @api.depends("sample_dashboard_file_path")
    def _compute_is_from_data(self) -> None:
        xml_ids = (
            self.env["ir.model.data"]
            .search(
                [
                    ("model", "=", self._name),
                    ("res_id", "in", self.ids),
                ]
            )
            .grouped("res_id")
        )
        for dashboard in self:
            dashboard.is_from_data = bool(
                xml_ids.get(dashboard.id) and dashboard.sample_dashboard_file_path
            )

    def _get_spreadsheet_metadata(self, *args, **kwargs):
        return dict(
            super()._get_spreadsheet_metadata(*args, **kwargs),
            is_published=self.is_published,
            translation_namespace=self._get_dashboard_translation_namespace(),
        )

    def action_edit_dashboard(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.client",
            "tag": "action_edit_dashboard",
            "params": {
                "spreadsheet_id": self.id,
            },
        }

    def _get_serialized_readonly_dashboard(self):
        self.check_singleton()
        update_locale_command = {
            "type": "UPDATE_LOCALE",
            "locale": self.env["res.lang"]._get_user_spreadsheet_locale(),
        }
        self._check_collaborative_spreadsheet_access("read")
        revisions = self.sudo()._get_spreadsheet_serialized_revisions()
        revisions.append(
            json_dumps(self._prepare_new_revision_data([update_locale_command]))
        )
        serialized_revisions = "[%s]" % ",".join(revisions)
        serialized_snapshot = self._get_spreadsheet_serialized_snapshot()
        metadata = self._get_spreadsheet_metadata()
        default_currency = metadata["default_currency"]
        translation_namespace = metadata["translation_namespace"]
        serialized_default_currency = json.dumps(default_currency, ensure_ascii=False)
        _debug.pipeline(
            "dashboard_readonly_serialized",
            dashboard=self,
            revisions=len(revisions),
            snapshot_chars=len(serialized_snapshot),
            translation_namespace=translation_namespace,
        )
        return (
            '{"snapshot": %s,"revisions": %s,"default_currency": %s,"translation_namespace": "%s"}'
            % (
                serialized_snapshot,
                serialized_revisions,
                serialized_default_currency,
                translation_namespace,
            )
        )

    def _dashboard_is_empty(self):
        self._check_collaborative_spreadsheet_access("read")
        all_revisions = (
            self.sudo().with_context(active_test=False).spreadsheet_revision_ids
        )
        if all_revisions:
            _debug.logic(
                "dashboard_emptiness_checked",
                dashboard=self,
                reason="has_revisions",
                revisions=len(all_revisions),
            )
            return False
        return super()._dashboard_is_empty()

    def action_view_spreadsheet(self):
        self.check_singleton()
        return {
            "type": "ir.actions.client",
            "tag": "action_edit_dashboard",
            "params": {
                "spreadsheet_id": self.id,
            },
        }

    @api.model
    def _get_spreadsheet_selector(self) -> dict | None:
        if self.env.user.has_group("spreadsheet_dashboard.group_dashboard_manager"):
            return {
                "model": self._name,
                "display_name": self.env._("Dashboards"),
                "sequence": 10,
                "allow_create": True,
            }
        return super()._get_spreadsheet_selector()
