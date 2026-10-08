from collections import defaultdict
from typing import Self

from odoo import api, fields, models
from odoo.api import ValuesType
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL, frozendict

from odoo.addons.base.models.mixin_access_graph import AccessGrantNames

_debug = DebugLog(__name__)


class ProjectCollaborator(models.Model):
    _name = "project.collaborator"
    _inherit = ["mixin.access.grant"]
    _access_grant_names = AccessGrantNames(resource="project_id", role="access_mode")
    _access_anchors = frozendict(
        {
            "company": "project_id.company_id",
            "partner": "partner_id",
        }
    )
    _description = "Collaborators in project shared"

    project_id = fields.Many2one(
        comodel_name="project.project",
        string="Project Shared",
        export_string_translation=False,
        readonly=True,
        required=True,
        domain=[
            ("privacy_visibility", "in", ["portal", "invited_users"]),
            ("is_template", "=", False),
        ],
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Collaborator",
        export_string_translation=False,
        readonly=True,
    )
    partner_email = fields.Char(
        related="partner_id.email",
        export_string_translation=False,
    )
    access_mode = fields.Selection(
        selection=[
            ("view", "View"),
            ("edit", "Edit"),
            ("advanced_edit", "Advanced Edit"),
        ],
        default="view",
        required=True,
        help="View: read the tasks and write in their chatter.\n"
        "Edit: also create and update tasks.\n"
        "Advanced Edit: also move tasks between steps and change their priority.",
    )
    is_current_user_collaboration = fields.Boolean(
        export_string_translation=False,
        compute="_compute_is_current_user_collaboration",
        search="_search_is_current_user_collaboration",
        compute_sudo=True,
    )

    _unique_collaborator_partner = models.UniqueIndex(
        "(project_id, partner_id) WHERE partner_id IS NOT NULL",
        "A collaborator cannot be selected more than once in the project sharing access. Please remove duplicate(s) and try again.",
    )
    _unique_collaborator_group = models.UniqueIndex(
        "(project_id, group_id, COALESCE(company_id, 0)) WHERE group_id IS NOT NULL",
        "A group cannot be selected more than once in the project sharing access.",
    )

    @api.model
    def _domain_of_user(self, user) -> Domain:
        company_ids = user.with_context(active_test=False).company_ids.ids
        groups = Domain("group_id", "in", user.all_group_ids.ids) & (
            Domain("company_id", "=", False) | Domain("company_id", "in", company_ids)
        )
        return (Domain("partner_id", "=", user.partner_id.id) | groups) & Domain.custom(
            to_sql=self._live_sql
        )

    @staticmethod
    def _live_sql(model, alias: str, query) -> SQL:
        model.flush_model(["date_to"])
        return SQL(
            "(%(date_to)s IS NULL OR %(date_to)s > now() AT TIME ZONE 'UTC')",
            date_to=SQL.identifier(alias, "date_to"),
        )

    @api.depends_context("uid")
    def _compute_is_current_user_collaboration(self) -> None:
        reaching = self.search(
            Domain("id", "in", self.ids) & self._domain_of_user(self.env.user)
        )
        for collaborator in self:
            collaborator.is_current_user_collaboration = collaborator in reaching

    def _search_is_current_user_collaboration(
        self, operator: str, value: bool
    ) -> Domain:
        if operator != "in":
            return NotImplemented
        return self._domain_of_user(self.env.user)

    @api.depends("project_id", "partner_id", "group_id")
    def _compute_display_name(self) -> None:
        for collaborator in self:
            principal = collaborator.partner_id or collaborator.group_id
            collaborator.display_name = (
                f"{collaborator.project_id.display_name} - {principal.display_name}"
            )

    @_debug.perf.timed
    @api.model_create_multi
    def create(self, vals_list: list[ValuesType]) -> Self:
        if _debug.lifecycle.enabled:
            _debug.lifecycle(
                "create",
                count=len(vals_list),
                keys=sorted({k for vals in vals_list for k in vals}),
            )
        return super().create(vals_list)

    @_debug.perf.timed
    def unlink(self) -> bool:
        _debug.lifecycle("unlink", collaborators=self)
        revoked_partners_per_project = defaultdict(lambda: self.env["res.partner"])
        for collaborator in self.sudo():
            if collaborator.partner_id:
                revoked_partners_per_project[collaborator.project_id] |= (
                    collaborator.partner_id
                )
        res = super().unlink()
        for project, partners in revoked_partners_per_project.items():
            project._revoke_collaborator_access(partners)
        return res
