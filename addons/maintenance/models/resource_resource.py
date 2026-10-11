from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

from .maintenance_order import OPEN_STATES

_debug = DebugLog(__name__)

PROFILE_FACTS = (
    "date_in_service",
    "maintenance_team_id",
    "technician_user_id",
    "expected_mtbf",
)
KIND_DEFAULTS = ("technician_user_id", "maintenance_team_id")


class ResourceResource(models.Model):
    _inherit = "resource.resource"

    maintenance_ids = fields.Many2many(
        comodel_name="maintenance.order",
        relation="maintenance_order_resource_rel",
        column1="resource_id",
        column2="order_id",
    )
    maintenance_plan_ids = fields.Many2many(
        comodel_name="maintenance.plan",
        relation="maintenance_plan_resource_rel",
        column1="resource_id",
        column2="plan_id",
    )
    maintenance_profile_id = fields.One2one(
        comodel_name="maintenance.profile",
        inverse_name="resource_id",
    )
    maintenance_team_id = fields.Many2one(
        comodel_name="team.team",
        compute="_compute_profile_facts",
        inverse="_inverse_maintenance_team_id",
        search="_search_maintenance_team_id",
        domain=[("use_maintenance", "=", True)],
        check_company=True,
    )
    technician_user_id = fields.Many2one(
        comodel_name="res.users",
        string="Technician",
        compute="_compute_profile_facts",
        inverse="_inverse_technician_user_id",
        search="_search_technician_user_id",
    )
    date_in_service = fields.Date(
        string="In Service Since",
        compute="_compute_profile_facts",
        inverse="_inverse_date_in_service",
    )
    expected_mtbf = fields.Integer(
        string="Expected MTBF",
        compute="_compute_profile_facts",
        inverse="_inverse_expected_mtbf",
    )
    mtbf = fields.Integer(related="maintenance_profile_id.mtbf")
    mttr = fields.Integer(related="maintenance_profile_id.mttr")
    date_next_failure = fields.Date(related="maintenance_profile_id.date_next_failure")
    date_last_failure = fields.Date(related="maintenance_profile_id.date_last_failure")
    maintenance_count = fields.Count(count_of="maintenance_ids")
    maintenance_open_count = fields.Integer(
        string="Current Maintenance",
        compute="_compute_maintenance_open_count",
    )
    maintenance_plan_count = fields.Count(count_of="maintenance_plan_ids")

    def _get_in_use_resource_ids(self):
        return super()._get_in_use_resource_ids() | set(
            self.sudo().filtered("maintenance_profile_id").ids
        )

    @api.depends(
        "maintenance_profile_id.date_in_service",
        "maintenance_profile_id.maintenance_team_id",
        "maintenance_profile_id.technician_user_id",
        "maintenance_profile_id.expected_mtbf",
    )
    def _compute_profile_facts(self) -> None:
        for resource in self:
            profile = resource.maintenance_profile_id
            for name in PROFILE_FACTS:
                resource[name] = profile[name]

    @api.depends("maintenance_ids.state")
    @_debug.perf.timed
    def _compute_maintenance_open_count(self) -> None:
        for resource in self:
            resource.maintenance_open_count = len(
                resource.maintenance_ids.filtered(
                    lambda order: order.state in OPEN_STATES
                )
            )

    def _get_or_create_maintenance_profile(self):
        self.check_singleton()
        profile = self.maintenance_profile_id
        if not profile:
            profile = (
                self.env["maintenance.profile"].sudo().create({"resource_id": self.id})
            )
            _debug.lifecycle("profile_created", resource=self, profile=profile)
            self.invalidate_recordset(["maintenance_profile_id"])
        return profile.sudo()

    def _inverse_profile_fact(self, name) -> None:
        for resource in self:
            value = resource[name]
            if not resource.maintenance_profile_id and not value:
                continue
            profile = resource._get_or_create_maintenance_profile()
            if profile[name] != value:
                _debug.logic("profile_fact_written", resource=resource, field=name)
                profile[name] = value

    def _inverse_maintenance_team_id(self) -> None:
        self._inverse_profile_fact("maintenance_team_id")

    def _inverse_technician_user_id(self) -> None:
        self._inverse_profile_fact("technician_user_id")

    def _inverse_date_in_service(self) -> None:
        self._inverse_profile_fact("date_in_service")

    def _inverse_expected_mtbf(self) -> None:
        self._inverse_profile_fact("expected_mtbf")

    def _search_maintenance_team_id(self, operator, value) -> list:
        return [("maintenance_profile_id.maintenance_team_id", operator, value)]

    def _search_technician_user_id(self, operator, value) -> list:
        return [("maintenance_profile_id.technician_user_id", operator, value)]

    def _get_maintenance_action(self, xmlid):
        self.check_singleton()
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(xmlid)
        action["domain"] = [("resource_ids", "in", self.ids)]
        action["context"] = {
            "default_resource_ids": self.ids,
            "default_company_id": self.company_id.id,
            "default_maintenance_team_id": self.maintenance_team_id.id,
        }
        return action

    def action_view_maintenance(self):
        return self._get_maintenance_action("maintenance.maintenance_order_action")

    def action_view_maintenance_plans(self):
        return self._get_maintenance_action("maintenance.maintenance_plan_action")

    def _on_kind_changed(self, vals) -> None:
        super()._on_kind_changed(vals)
        for resource in self:
            resource._take_kind_defaults(vals)

    def _take_kind_defaults(self, given) -> None:
        self.check_singleton()
        kind = self.kind_id
        vals = {
            fname: kind[fname].id
            for fname in KIND_DEFAULTS
            if not given.get(fname) and kind[fname]
        }
        if vals:
            _debug.lifecycle("kind_defaults_taken", resource=self, fields=sorted(vals))
            self.sudo().write(vals)

    def _sync_state_from_maintenance(self) -> None:
        if not self:
            return
        in_progress = (
            self.env["maintenance.order"]
            .sudo()
            .search([("resource_ids", "in", self.ids), ("state", "=", "in_progress")])
        )
        busy = in_progress.resource_ids
        _debug.pipeline(
            "state_synced", resources=self, orders=in_progress, busy=len(busy)
        )
        resources = self.sudo()
        resources.filtered(
            lambda resource: (
                resource in busy and resource.state in ("available", "in_service")
            )
        )._transition("maintenance")
        resources.filtered(
            lambda resource: resource not in busy and resource.state == "maintenance"
        )._end_maintenance()
