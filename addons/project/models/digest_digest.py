from typing import Any

from odoo import api, fields, models
from odoo.exceptions import AccessError
from odoo.libs.debug_log import DebugLog

from .project_task import CLOSED_STATES

_debug = DebugLog(__name__)


class DigestDigest(models.Model):
    _inherit = "digest.digest"

    kpi_project_task_opened = fields.Boolean(string="Open Tasks")
    kpi_project_task_opened_value = fields.Integer(
        export_string_translation=False,
        compute="_compute_kpi_project_task_opened_value",
    )

    @_debug.perf.timed
    @api.depends_context("uid")
    def _compute_kpi_project_task_opened_value(self) -> None:
        if not self.env.user.has_group("project.group_project_user"):
            _debug.logic(
                "kpi_task_opened_refused", reason="not_project_user", user=self.env.uid
            )
            raise AccessError(
                self.env._("Do not have access, skip this data for user's digest email")
            )

        self._update_company_based_kpi(
            "project.task",
            "kpi_project_task_opened_value",
            additional_domain=[
                ("state", "not in", list(CLOSED_STATES)),
                ("project_id", "!=", False),
            ],
        )

    def _get_kpi_actions(self, company: Any, user: Any) -> dict:
        res = super()._get_kpi_actions(company, user)
        menu = self.env.ref("project.menu_project_root", raise_if_not_found=False)
        if menu:
            res["kpi_project_task_opened"] = (
                "project.open_view_project_all?menu_id=%s" % menu.id
            )
        return res
