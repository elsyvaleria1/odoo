from datetime import timedelta
from urllib.parse import quote_plus

from markupsafe import Markup

from odoo import api, fields, models
from odoo.api import ValuesType
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog
from odoo.tools.authority_keys import declare_authority_keys

_debug = DebugLog(__name__)

FIELD_SERVICE_STATES = ("3_in_progress", "4_completed")
FIELD_SERVICE_TRANSITION = "field_service_transition"
declare_authority_keys("planning_field_service", "field_service_transition")


class PlanningSlot(models.Model):

    _name = "planning.slot"
    _inherit = ["planning.slot", "mixin.mail.thread"]
    _access_verbs = {"manage_visits": models.Verb()}

    state = fields.Selection(
        selection_add=[
            ("3_in_progress", "In Progress"),
            ("4_completed", "Completed"),
        ],
        ondelete={
            "3_in_progress": lambda slots: slots.write({"state": "2_published"}),
            "4_completed": lambda slots: slots.write({"state": "2_published"}),
        },
        tracking=True,
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        related=False,
        string="Customer",
        compute="_compute_partner_id",
        store=True,
        index="btree_not_null",
        readonly=False,
        check_company=True,
        tracking=True,
    )
    partner_city = fields.Char(related="partner_id.city")

    @api.depends("sale_order_id.partner_id")
    def _compute_partner_id(self):
        for slot in self:
            slot.partner_id = slot.sale_order_id.partner_id or slot.partner_id

    @api.model
    def default_get(self, fields: list[str]) -> ValuesType:
        res = super().default_get(fields)
        if self.env.context.get("field_service_declare_visit"):
            res.update(self._get_declared_visit_defaults(fields))
        return res

    @api.model
    def _get_declared_visit_defaults(self, field_names) -> dict:
        resource = self.env.user.employee_id.resource_id
        if not resource:
            raise UserError(
                self.env._(
                    "You have no employee in %(company)s: a visit is made by an employee.",
                    company=self.env.company.name,
                )
            )
        now = fields.Datetime.now().replace(second=0, microsecond=0)
        defaults = {
            "resource_id": resource.id,
            "start_datetime": now,
            "end_datetime": now + timedelta(hours=1),
            "state": "2_published",
        }
        return {key: value for key, value in defaults.items() if key in field_names}

    def write(self, vals):
        if vals.get("state") == "1_draft" and any(
            slot.state in FIELD_SERVICE_STATES for slot in self
        ):
            raise UserError(
                self.env._(
                    "A shift that is in progress or completed cannot go back to draft."
                )
            )
        visits = self if vals.get("partner_id") else self.filtered("partner_id")
        if visits and not self.env.su and not visits.has_access("manage_visits"):
            visits._check_employee_write(vals)
        return super().write(vals)

    def _check_employee_write(self, vals) -> None:
        if "state" in vals and not self.env.context.get(FIELD_SERVICE_TRANSITION):
            raise UserError(
                self.env._("A visit changes status only through Start and Complete.")
            )
        if "resource_id" in vals and any(
            slot.resource_id and slot.resource_id.id != vals["resource_id"]
            for slot in self
        ):
            raise UserError(
                self.env._(
                    "Only a planning manager can hand a visit over to someone else."
                )
            )

    def action_sign_in(self):
        self.check_singleton()
        if self.state != "2_published":
            raise UserError(self.env._("Only a published shift can be started."))
        if not self.resource_id:
            self.action_self_assign()
        now = fields.Datetime.now()
        vals = {"state": "3_in_progress", "start_datetime": now}
        if not self.end_datetime or not now < self.end_datetime <= now + timedelta(
            days=1
        ):
            vals["end_datetime"] = now + timedelta(hours=self.allocated_hours or 1)
        self.with_context(**{FIELD_SERVICE_TRANSITION: True}).write(vals)
        _debug.lifecycle("field_visit_started", slot=self)
        self._send_geolocation()

    def action_complete(self):
        self.check_singleton()
        if self.state not in ("2_published", "3_in_progress"):
            raise UserError(
                self.env._(
                    "Only a shift that is published or in progress can be completed."
                )
            )
        if self.start_datetime > fields.Datetime.now():
            raise UserError(
                self.env._("A visit that has not started yet cannot be completed.")
            )
        self._action_complete()

    def _action_complete(self):
        vals = {"state": "4_completed"}
        now = fields.Datetime.now()
        if self.state == "3_in_progress" and self.start_datetime < now:
            vals["end_datetime"] = now
        self.with_context(**{FIELD_SERVICE_TRANSITION: True}).write(vals)
        _debug.lifecycle("field_visit_completed", slot=self)
        self._send_geolocation()

    def _send_geolocation(self) -> None:
        geolocation = self.env.context.get("geolocation")
        if not geolocation or not self.env["res.groups"]._is_feature_enabled(
            "planning.group_field_service_allow_geolocation"
        ):
            return
        if not geolocation.get("success"):
            self.message_post(
                body=geolocation.get("message") or self.env._("Location error")
            )
            return
        latitude, longitude = geolocation["latitude"], geolocation["longitude"]
        self.message_post(
            body=Markup(
                "{text} <a href='https://maps.google.com?q={latitude},{longitude}'"
                " target='_blank'>{label}</a>"
            ).format(
                text=self.env._(
                    "GPS Coordinates: %(latitude)s, %(longitude)s",
                    latitude=latitude,
                    longitude=longitude,
                ),
                latitude=latitude,
                longitude=longitude,
                label=self.env._("View on Map"),
            )
        )

    def action_open_map_navigation(self) -> dict:
        self.check_singleton()
        partner = self.partner_id
        if partner.partner_latitude and partner.partner_longitude:
            destination = f"{partner.partner_latitude},{partner.partner_longitude}"
        else:
            lines = partner._display_address().splitlines()
            destination = ", ".join(line.strip() for line in lines if line.strip())
        if not destination:
            raise UserError(
                self.env._(
                    "%(customer)s has neither coordinates nor an address to navigate to.",
                    customer=partner.display_name,
                )
            )
        return {
            "type": "ir.actions.act_url",
            "url": "https://www.google.com/maps/dir/?api=1&destination="
            + quote_plus(destination),
            "target": "new",
        }
