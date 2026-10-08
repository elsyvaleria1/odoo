from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class AccountAnalyticAccount(models.Model):
    _inherit = "account.analytic.account"
    _description = "Analytic Account"

    project_ids = fields.One2many(
        comodel_name="project.project",
        inverse_name="account_id",
        string="Projects",
        export_string_translation=False,
    )
    project_count = fields.Integer(
        export_string_translation=False,
        compute="_compute_project_count",
    )

    @_debug.perf.timed
    @api.depends("project_ids")
    def _compute_project_count(self) -> None:
        counts = self._get_project_counts(include_archived=False)
        for account in self:
            account.project_count = counts.get(account.id, 0)

    def _get_project_counts(self, include_archived: bool) -> dict[int, int]:
        counts = dict.fromkeys(self.ids, 0)
        for account, count in (
            self.env["project.project"]
            .with_context(active_test=not include_archived)
            ._read_group([("account_id", "in", self.ids)], ["account_id"], ["__count"])
        ):
            counts[account.id] = count
        return counts

    def _has_analytic_lines(self) -> bool:
        return bool(
            self.env["account.analytic.line"].search_count(
                [("auto_account_id", "in", self.ids)], limit=1
            )
        )

    @api.ondelete(at_uninstall=False)
    def _unlink_except_existing_tasks(self) -> None:
        has_tasks = self.env["project.task"].search_count(
            [("project_id.account_id", "in", self.ids)],
            limit=1,
        )
        _debug.logic("unlink_checked", accounts=self, has_tasks=bool(has_tasks))
        if has_tasks:
            raise UserError(
                self.env._(
                    "Before we can bid farewell to these accounts, you need to tidy up the projects linked to them by removing their existing tasks!"
                )
            )

    def action_view_projects(self) -> dict:
        kanban_view_id = self.env.ref("project.view_project_kanban").id
        result = {
            "type": "ir.actions.act_window",
            "res_model": "project.project",
            "views": [[kanban_view_id, "kanban"], [False, "form"]],
            "domain": [["account_id", "=", self.id]],
            "context": {"create": False},
            "name": self.env._("Projects"),
        }
        if len(self.project_ids) == 1:
            result["views"] = [(False, "form")]
            result["res_id"] = self.project_ids.id
        return result
