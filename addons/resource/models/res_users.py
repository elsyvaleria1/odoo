from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog
from odoo.models import ValuesType

_debug = DebugLog(__name__)


class ResUsers(models.Model):
    _inherit = "res.users"

    resource_ids = fields.One2many(
        comodel_name="resource.resource",
        inverse_name="user_id",
        string="Resources",
    )
    resource_calendar_id = fields.Many2one(
        comodel_name="resource.calendar",
        string="Default Working Hours",
        compute="_compute_resource_calendar_id",
        inverse="_inverse_resource_calendar_id",
    )

    @api.depends("resource_ids.calendar_id", "resource_ids.company_id")
    @api.depends_context("company")
    def _compute_resource_calendar_id(self) -> None:
        for user in self:
            user.resource_calendar_id = user._get_company_resource().calendar_id

    def _inverse_resource_calendar_id(self) -> None:
        for user in self:
            if resource := user._get_company_resource():
                resource.calendar_id = user.resource_calendar_id

    def _get_company_resource(self):
        self.check_singleton()
        resources = self.resource_ids
        return (
            resources.filtered(
                lambda resource: (
                    not resource.company_id or resource.company_id == self.env.company
                )
            )[:1]
            or resources[:1]
        )

    def write(self, vals: ValuesType) -> bool:
        rslt = super().write(vals)

        if (
            vals.get("tz")
            and len(self) == 1
            and not self.env.user.login_date
            and self.env.user == self.env.ref("base.user_admin", False)
            and self == self.env.user
        ):
            if self.resource_calendar_id:
                self.resource_calendar_id.tz = vals["tz"]
            elif default_calendar := self.env.ref(
                "resource.resource_calendar_std", False
            ):
                default_calendar.tz = vals["tz"]

        return rslt

    def _get_asset_kinds_gated(self):
        return self.env["resource.kind"].sudo().search([("group_id", "!=", False)])

    def _get_enabled_asset_kinds(self):
        self.check_singleton()
        kinds = self.env["resource.kind"].sudo().search([])
        if self.has_group("resource.group_asset_manager"):
            return kinds.ids
        enabled = [
            kind.id
            for kind in kinds
            if not kind.group_id or self.has_any_group_id([kind.group_id.id])
        ]
        _debug.logic("kinds_enabled", user=self, kinds=len(kinds), enabled=len(enabled))
        return enabled

    def _get_hidden_asset_kinds(self):
        self.check_singleton()
        if self.has_group("resource.group_asset_manager"):
            return []
        hidden = [
            kind.id
            for kind in self._get_asset_kinds_gated()
            if not self.has_any_group_id([kind.group_id.id])
        ]
        _debug.logic("kinds_hidden", user=self, hidden=len(hidden))
        return hidden
