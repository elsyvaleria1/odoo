import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.libs.datetime import timezone
from odoo.libs.debug_log import DebugLog

if TYPE_CHECKING:
    from vobject.base import Component

    from odoo.addons.base.models.resource_resource import ResourceResource

_debug = DebugLog(__name__)

PAGE_OUTLIVES_SCHEDULE = timedelta(days=30)


class PlanningPlanning(models.Model):
    _name = "planning.planning"
    _description = "Schedule"

    @api.model
    def _default_access_token(self):
        return str(uuid.uuid4())

    start_datetime = fields.Datetime(
        string="Start Date",
        required=True,
    )
    end_datetime = fields.Datetime(
        string="Stop Date",
        required=True,
    )
    include_unassigned = fields.Boolean(
        string="Includes Open Shifts",
        default=True,
    )
    access_token = fields.Char(
        string="Security Token",
        default=lambda self: self._default_access_token(),
        copy=False,
        readonly=True,
        required=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        required=True,
        help="Company linked to the material resource. Leave empty for the resource to be available in every company.",
    )
    date_start = fields.Date(compute="_compute_dates")
    date_end = fields.Date(compute="_compute_dates")
    allow_self_unassign = fields.Boolean(
        string="Let Employee Unassign Themselves",
        compute="_compute_allow_self_unassign",
    )
    self_unassign_days_before = fields.Integer(
        related="company_id.planning_self_unassign_days_before",
        string="Days before shift for unassignment",
        export_string_translation=False,
    )
    is_planning_preview = fields.Boolean()

    @api.depends("start_datetime", "end_datetime")
    @api.depends_context("uid")
    def _compute_dates(self) -> None:
        tz = timezone(self.env.user.tz or "UTC")
        for planning in self:
            planning.date_start = (
                planning.start_datetime.replace(tzinfo=UTC)
                .astimezone(tz)
                .replace(tzinfo=None)
            )
            planning.date_end = (
                planning.end_datetime.replace(tzinfo=UTC)
                .astimezone(tz)
                .replace(tzinfo=None)
            )

    def _compute_display_name(self):
        self.display_name = self.env._("Planning")

    def _compute_allow_self_unassign(self) -> None:
        self.allow_self_unassign = (
            self.company_id.planning_employee_unavailabilities == "unassign"
        )


    def _is_slot_in_planning(self, slot_sudo) -> bool:
        return bool(
            self
            and slot_sudo.start_datetime >= self.start_datetime
            and slot_sudo.end_datetime <= self.end_datetime
            and slot_sudo.state in slot_sudo._get_scheduled_states()
        )

    def _append_ics_events(
        self, calendar: Component, resource: ResourceResource
    ) -> None:
        self.check_singleton()
        slots_in_planning = self.env["planning.slot"].search(
            [
                ("start_datetime", ">=", self.start_datetime),
                ("end_datetime", "<=", self.end_datetime),
                ("state", "in", self.env["planning.slot"]._get_scheduled_states()),
                ("resource_id", "=", resource.id),
            ]
        )
        slots_in_planning._append_ics_events(calendar, resource.tz)

    def _page_token(self, resource) -> str:
        self.check_singleton()
        __, token = self.env["access.link"]._issue(
            self,
            partner=resource.sudo().partner_id,
            role="comment",
            cause="notification",
            cause_record=resource,
        )
        return token

    def _get_link_expiry(self) -> datetime:
        return max(self.end_datetime, fields.Datetime.now()) + PAGE_OUTLIVES_SCHEDULE

    def _send_planning(self, slots, message=None, resources=False) -> bool:
        _debug.pipeline(
            "send_planning", planning=self, slots=slots, resources=resources
        )
        email_from = self.env.user.email or self.env.user.company_id.email or ""
        resources_sudo = resources.sudo()
        resource_url_map = resources_sudo._planning_get_url(
            self.date_start, self.date_end, self
        )
        ics_url_per_resource_id = {
            resource.id: f"/planning/{self.access_token}/{resource.planning_token}.ics"
            for resource in resources_sudo
        }

        template = self.env.ref(
            "planning.email_template_planning_planning", raise_if_not_found=False
        )
        template_context = {
            "slot_unassigned": self.include_unassigned,
            "message": message,
        }
        if template:
            for resource in resources_sudo:
                email = resource._get_planning_email()
                if not email:
                    continue
                template_context["recipient"] = resource
                template_context["start_datetime"] = self.date_start
                template_context["end_datetime"] = self.date_end
                template_context["planning_url"] = resource_url_map[resource.id]
                template_context["planning_url_ics"] = ics_url_per_resource_id[
                    resource.id
                ]
                template_context["assigned_new_shift"] = bool(
                    slots.filtered_domain([("resource_id", "=", resource.id)])
                )
                template.with_context(**template_context).send_mail(
                    self.id,
                    email_values={
                        "email_to": email,
                        "email_from": email_from,
                    },
                    email_layout_xmlid="mail.mail_notification_light",
                )
        slots.write({"publication_warning": False})
        slots.filtered(lambda slot: slot.state == "1_draft").write(
            {"state": "2_published"}
        )
        return True

    def _get_or_create_preview_planning(
        self, start_datetime, end_datetime, include_unassigned
    ):
        Planning = self.env["planning.planning"]
        planning = Planning.search(
            [
                ("start_datetime", "=", start_datetime),
                ("end_datetime", "=", end_datetime),
                ("is_planning_preview", "=", True),
            ],
            limit=1,
        )
        if not planning:
            planning = Planning.create(
                {
                    "start_datetime": start_datetime,
                    "end_datetime": end_datetime,
                    "include_unassigned": include_unassigned,
                }
            )
        return planning

    @api.autovacuum
    def _gc_planning_preview(self) -> None:
        limit_dt = fields.Datetime.subtract(fields.Datetime.now(), months=3)
        plannings = self.env["planning.planning"].search(
            [
                ("is_planning_preview", "=", True),
                ("create_date", "<=", limit_dt),
            ]
        )
        plannings.unlink()
