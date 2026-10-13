from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from typing import TYPE_CHECKING, Self
from zoneinfo import ZoneInfo

from odoo import api, fields, models, tools
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Domain
from odoo.libs.datetime import timezone
from odoo.libs.debug_log import DebugLog
from odoo.libs.intervals import Intervals
from odoo.models import ValuesType
from odoo.tools import SQL, Query
from odoo.tools.date_utils import get_intervals_hours, localized, to_timezone
from odoo.tools.translate import html_translate

from ..fields import ResourceIdentifier
from .resource_utils import (
    ASSET_INITIAL_STATE,
    CUSTODY_ROLE_BY_FIELD,
    CUSTODY_SYNC,
    DEFAULT_HANDOVER_DELAY,
    KIND_MODEL_CREATING,
    MANAGER_ROLE,
    OPERATOR_ROLE,
    SKIP_IDENTITY_CHECK,
    ResourceSchedule,
    SlotIntervals,
    changed_vals,
    hours_by_day,
    last_day_of,
    saturated_spans,
    week_of,
)
from odoo.addons.base.models.res_partner import _selection_timezones

if TYPE_CHECKING:
    from odoo.addons.base.models.res_company import ResCompany

_debug = DebugLog(__name__)

RESOURCE_STATES = [
    ("draft", "Draft"),
    ("available", "Available"),
    ("in_service", "In Service"),
    ("maintenance", "Under Maintenance"),
    ("out_of_service", "Out of Service"),
    ("disposed", "Disposed"),
]


class ResourceResource(models.Model):
    _name = "resource.resource"
    _inherit = ["mixin.color", "mixin.image"]
    _description = "Resources"
    _order = "name"
    _check_company_auto = True

    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
    )
    name = fields.Char(
        compute="_compute_name",
        inverse="_inverse_name",
        precompute=True,
        store=True,
        readonly=False,
        required=True,
    )
    active = fields.Boolean(
        default=True,
        help="If the active field is set to False, it will allow you to hide the resource record without removing it.",
    )
    color = fields.Integer(default=lambda self: self._default_color())
    type = fields.Selection(
        selection=[
            ("human", "Human"),
            ("material", "Material"),
            ("intangible", "Intangible"),
        ],
        default="human",
        required=True,
        help="Human: a person, who has a party. Material: a physical thing, such as a machine, a vehicle or a room. Intangible: a capacity with no body, such as electricity, sunlight or time.",
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Party",
        index="btree_not_null",
        copy=False,
        ondelete="restrict",
        help="The person this resource is. A material resource has none.",
    )
    phone_ids = fields.Many2many(
        related="partner_id.phone_ids",
    )
    email = fields.Char(
        compute="_compute_email",
        inverse="_inverse_email",
        search="_search_email",
    )

    user_id = fields.Many2one(
        comodel_name="res.users",
        compute="_compute_user_id",
        precompute=True,
        store=True,
        index="btree_not_null",
        copy=False,
        readonly=False,
        help="The login of the person this resource is: their party's internal user. Choosing another user makes the resource that user's person.",
    )
    share = fields.Boolean(related="user_id.share")
    avatar_128 = fields.Image(compute="_compute_avatar_128")

    calendar_id = fields.Many2one(
        comodel_name="resource.calendar",
        string="Working Time",
        default=lambda self: self._default_calendar_id(),
        index=True,
        required=True,
        domain="[('company_id', 'in', [company_id, False])]",
        ondelete="restrict",
        help="The working schedule of the resource. A Fully Flexible schedule lets it work any hour.",
    )
    tz = fields.Selection(
        selection=_selection_timezones,
        string="Timezone",
        compute="_compute_tz",
        precompute=True,
        store=True,
        readonly=False,
        required=True,
        help="The time zone where this resource works. Its working schedule is read in this zone: an 08:00-17:00 schedule means 08:00-17:00 here, whatever zone the schedule names. For an employee deployed away from the corporate office, set the zone of the place of work.",
    )
    time_efficiency = fields.Float(
        string="Efficiency Factor",
        default=100,
        required=True,
        help="How quickly this resource performs work compared with the reference duration. At 100%, one reference hour requires one hour; at 200%, it requires 30 minutes.",
    )
    capacity = fields.Integer(
        default=1,
        required=True,
        help="How many claims the resource can hold at once: seats at a table, concurrent users of a machine. A reservation's allocated percentage is a share of this.",
    )

    role_ids = fields.Many2many(
        comodel_name="resource.role",
        relation="resource_resource_role_rel",
        column1="resource_resource_id",
        column2="role_id",
        string="Roles",
    )
    default_role_id = fields.Many2one(
        comodel_name="resource.role",
        compute="_compute_default_role_id",
        inverse="_inverse_default_role_id",
        store=True,
        readonly=False,
        help="Preferred role when assigning this resource. The default is always included in its roles.",
    )

    holder_id = fields.Many2one(
        comodel_name="resource.resource",
        string="Current Holder",
        compute="_compute_holder_id",
        search="_search_holder_id",
        help="Who has it now: the live operator, else the live custodian.",
    )
    operator_id = fields.Many2one(
        comodel_name="resource.resource",
        compute="_compute_custody",
        inverse="_inverse_operator_id",
        search="_search_operator_id",
        domain="[('type', '=', 'human'), '|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        help="Who operates the resource now: the live operator assignment.",
    )
    manager_id = fields.Many2one(
        comodel_name="resource.resource",
        compute="_compute_custody",
        inverse="_inverse_manager_id",
        search="_search_manager_id",
        domain="[('type', '=', 'human'), '|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        help="Who answers for the resource: the live manager assignment.",
    )

    assignment_ids = fields.One2many(
        comodel_name="resource.assignment",
        inverse_name="resource_id",
        string="Assignments",
    )
    future_operator_id = fields.Many2one(
        comodel_name="resource.resource",
        compute="_compute_future_operator",
        inverse="_inverse_future_operator",
        search="_search_future_operator_id",
        domain="[('type', '=', 'human'), '|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        help="Who takes the resource over next: the planned operator assignment.",
    )
    date_future_operator = fields.Datetime(
        string="Hand-over Date",
        compute="_compute_future_operator",
        inverse="_inverse_future_operator",
        help="When the next operator takes over. A hand-over without a date takes effect in a week unless accepted before.",
    )

    relation_ids = fields.One2many(
        comodel_name="resource.relation",
        inverse_name="parent_id",
        string="Members and Dependencies",
        copy=False,
    )
    membership_ids = fields.One2many(
        comodel_name="resource.relation",
        inverse_name="member_id",
        string="Memberships",
        copy=False,
    )

    reservation_ids = fields.One2many(
        comodel_name="resource.reservation",
        inverse_name="resource_id",
        string="Reservations",
    )

    booking_limit_percentage = fields.Float(
        string="Booking Ceiling %",
        default=100.0,
        required=True,
        help="Maximum simultaneous allocation for enforced bookings. 100% permits full booking; 120% permits 20% overbooking. Warning-only reservations can exceed this ceiling when resource enforcement is disabled.",
    )
    enforce_booking_limit = fields.Boolean(
        string="Enforce Booking Ceiling",
        help="Reject any reservation that exceeds this resource's booking ceiling, including manual meetings and shifts. Individual bookings may enforce the ceiling even when this option is disabled.",
    )

    state = fields.Selection(
        selection=RESOURCE_STATES,
        default="available",
        index=True,
        required=True,
        help="Where the resource is in its life: draft, available (ready, idle), in service, under maintenance, out of service or disposed.",
    )
    state_before_maintenance = fields.Selection(
        selection=[state for state in RESOURCE_STATES if state[0] != "maintenance"],
        copy=False,
        readonly=True,
        help="The state the resource returns to when its maintenance ends.",
    )
    date_acquisition = fields.Date(
        help="When the resource was acquired.",
    )
    date_disposal = fields.Date(
        help="When the resource was disposed of.",
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        compute="_compute_currency_id",
        value_sql="_value_sql_currency_id",
    )
    value_original = fields.Monetary(
        string="Original Value",
        copy=False,
    )

    date_built = fields.Date(
        help="When a thing was made or commissioned. A person's birth is their party's.",
    )
    country_built_id = fields.Many2one(
        comodel_name="res.country",
        help="The country a thing was produced in.",
    )
    place_built = fields.Char(
        help="The place within that country: a plant, a workshop.",
    )
    date_origin = fields.Date(
        compute="_compute_origin",
        inverse="_inverse_origin",
        search="_search_date_origin",
        help="When the resource came to be: a person's birth, a thing's manufacture or commissioning.",
    )
    year_origin = fields.Integer(compute="_compute_year_origin")
    origin_country_id = fields.Many2one(
        comodel_name="res.country",
        compute="_compute_origin",
        inverse="_inverse_origin",
        search="_search_origin_country_id",
        help="Where it came to be: a person's country of birth, a thing's country of production.",
    )
    place_origin = fields.Char(
        compute="_compute_origin",
        inverse="_inverse_origin",
        help="The place within that country: a city of birth, a plant.",
    )
    nationality_ids = fields.One2many(
        comodel_name="resource.nationality",
        inverse_name="resource_id",
        string="Nationalities",
        help="A thing's nationalities. A person's are their party's.",
    )
    nationality_country_ids = fields.Many2many(
        comodel_name="res.country",
        compute="_compute_nationality_country_ids",
        search="_search_nationality_country_ids",
        help="The countries it holds a nationality of now, a person's from their party.",
    )

    identifier_ids = fields.One2many(
        comodel_name="resource.identifier",
        inverse_name="resource_id",
        string="Identifiers",
    )
    meter_ids = fields.One2many(
        comodel_name="resource.meter",
        inverse_name="resource_id",
        string="Meters",
    )

    kind_id = fields.Many2one(
        comodel_name="resource.kind",
        index="btree_not_null",
        ondelete="restrict",
    )
    kind_code = fields.Char(related="kind_id.code")
    properties = fields.Properties(
        definition="kind_id.properties_definition",
        copy=True,
    )
    description = fields.Html(translate=html_translate)
    model = fields.Char(string="Model Name")
    model_year = fields.Integer(
        help="The commercial model year, which may differ from the year it was built.",
    )
    brand_new = fields.Boolean(default=True)
    vendor_id = fields.Many2one(
        comodel_name="res.partner",
        index="btree_not_null",
        check_company=True,
    )
    vendor_ref = fields.Char(string="Vendor Reference")
    warranty_date = fields.Date(string="Warranty Expiration Date")
    address_id = fields.Many2one(
        comodel_name="res.partner",
        string="Location",
        help="Where the resource normally is, when no inventory location tracks it.",
    )
    odometer = fields.Float(
        compute="_compute_odometer",
        inverse="_inverse_odometer",
        store=True,
        readonly=False,
    )
    odometer_uom_id = fields.Many2one(
        comodel_name="uom.uom",
        help="Unit of measurement for the odometer readings",
    )
    odometer_uom_name = fields.Char(
        related="odometer_uom_id.display_name",
        string="Odometer Unit",
    )
    odometer_meter_id = fields.Many2one(
        comodel_name="resource.meter",
        compute="_compute_odometer_meter_id",
        store=True,
    )

    license_plate = ResourceIdentifier(
        identifier_code="plate",
        store=False,
        help="License plate number of the asset (eg plate number for a car)",
    )
    vin_sn = ResourceIdentifier(
        identifier_code="vin",
        string="Serial Number / VIN",
        store=False,
        help="Unique number written on an asset's chassis (VIN/SN number).",
    )
    engine_sn = ResourceIdentifier(
        identifier_code="engine",
        string="Engine Serial Number",
        store=False,
        help="Unique number written on the asset's engine.",
    )
    serial_number = ResourceIdentifier(identifier_code="serial", store=False)
    imei = ResourceIdentifier(
        identifier_code="imei",
        string="IMEI",
        store=False,
        help="International Mobile Equipment Identity of a cellular-capable asset.",
    )
    inventory_tag = ResourceIdentifier(identifier_code="inventory", store=False)
    cadastral_id = ResourceIdentifier(
        identifier_code="cadastral",
        string="Cadastral ID",
        store=False,
        help="Government-assigned parcel identifier for real estate assets.",
    )
    missing_identifier_type_ids = fields.Many2many(
        comodel_name="resource.identifier.type",
        compute="_compute_missing_identifier_type_ids",
        search="_search_missing_identifier_type_ids",
    )
    operator_history_count = fields.Integer(compute="_compute_operator_history_count")
    parent_id = fields.Many2one(
        comodel_name="resource.resource",
        string="Part Of",
        compute="_compute_parent_id",
        inverse="_inverse_parent_id",
        search="_search_parent_id",
        compute_sudo=False,
        copy=False,
        readonly=False,
        value_sql="_parent_id_sql",
        help="Current physical parent from the resource membership timeline.",
    )
    child_ids = fields.One2many(
        comodel_name="resource.resource",
        inverse_name="parent_id",
        string="Components",
    )

    _party_company_uniq = models.UniqueIndex(
        "(partner_id, company_id) NULLS NOT DISTINCT WHERE type = 'human'",
        "A person is one human resource per company.",
    )
    _check_booking_limit = models.Constraint(
        "CHECK(booking_limit_percentage >= 0 AND booking_limit_percentage < 'Infinity'::float8)",
        "The booking ceiling must be finite and nonnegative.",
    )
    _check_time_efficiency = models.Constraint(
        "CHECK(time_efficiency>0)",
        "Time efficiency must be strictly positive",
    )
    _check_capacity = models.Constraint(
        "CHECK(capacity>0)",
        "Capacity must be strictly positive",
    )
    _check_human_has_party = models.Constraint(
        "CHECK(type != 'human' OR partner_id IS NOT NULL)",
        "A human resource is a person: it needs a party.",
    )
    _check_dates = models.Constraint(
        "CHECK(date_disposal IS NULL OR date_acquisition IS NULL OR date_disposal >= date_acquisition)",
        "A resource cannot be disposed of before it was acquired.",
    )

    @api.constrains("company_id")
    def _check_links_companies(self):
        for model, ends in (
            ("resource.relation", ("parent_id", "member_id")),
            ("resource.assignment", ("resource_id", "assignee_id")),
        ):
            self.env[model].sudo().with_context(active_test=False).search(  # noqa: E8507 -- one query per link model, two of them
                Domain.OR(Domain(end, "in", self.ids) for end in ends)
            )._check_company()

    @api.constrains("booking_limit_percentage", "enforce_booking_limit")
    def _check_booking_limit_reservations(self) -> None:
        self._lock_for_integrity()
        Reservation = self.env["resource.reservation"]
        Reservation.sudo().search(
            Reservation._get_domain_occupancy(self, since=fields.Datetime.now())
        )._check_hard_overlap()

    @api.constrains("type")
    def _check_host_types(self):
        for name in self._get_host_model_names():
            owner = self.env[name].sudo().with_context(active_test=False)
            resource_type = getattr(owner, "_resource_type", None)
            if resource_type is None:
                continue
            incompatible = self.filtered(
                lambda resource, resource_type=resource_type: (
                    resource.type != resource_type
                )
            )
            if incompatible and owner.search_count(  # noqa: E8507 -- one query per host model, not per resource
                [("resource_id", "in", incompatible.ids)], limit=1
            ):
                incompatible._check_host_type(resource_type)

    @api.constrains("state", "date_disposal")
    def _check_disposal(self) -> None:
        for resource in self:
            if resource.state == "disposed" and not resource.date_disposal:
                raise ValidationError(
                    self.env._(
                        "%(name)s: a disposed resource needs its disposal date.",
                        name=resource.name,
                    )
                )

    @api.constrains("tz")
    def _check_tz(self) -> None:
        for resource in self:
            if not resource.tz:
                raise ValidationError(
                    self.env._(
                        "A resource needs a timezone: %s has none.", resource.name
                    )
                )

    @api.model_create_multi
    def create(self, vals_list: list[ValuesType]) -> Self:
        dispatched = self._create_in_kind_models(vals_list)
        if dispatched is not None:
            return dispatched
        parent_values = [vals.pop("parent_id", None) for vals in vals_list]
        given = [dict(vals) for vals in vals_list]
        for vals in vals_list:
            if not vals.get("kind_id"):
                continue
            vals["type"] = "material"
            vals.setdefault("state", ASSET_INITIAL_STATE)
            if self._around_the_clock(vals):
                vals["calendar_id"] = (
                    self.env["resource.calendar"]._get_fully_flexible_calendar().id
                )
        self._update_party_vals(vals_list)
        named_party_ids = {
            party.id
            for party in self.env["res.partner"]
            .sudo()
            .browse(
                {
                    values["partner_id"]
                    for values in vals_list
                    if values.get("partner_id")
                }
            )
            if party.name
        }
        calendar_by_company = {
            company.id: company.resource_calendar_id.id
            for company in self.env["res.company"].browse(
                {
                    values["company_id"]
                    for values in vals_list
                    if values.get("company_id") and "calendar_id" not in values
                }
            )
        }
        for values in vals_list:
            if "tz" in values and not values["tz"]:
                del values["tz"]
            if values.get("partner_id") in named_party_ids:
                values.pop("name", None)
            if (
                values.get("company_id") in calendar_by_company
                and "calendar_id" not in values
            ):
                values["calendar_id"] = calendar_by_company[values["company_id"]]
        vals_list = [self._normalize_calendar_vals(values) for values in vals_list]
        resources = super().create(vals_list)
        for resource, vals in zip(resources, given, strict=True):
            if resource.kind_id:
                resource._on_kind_changed(vals)
        for resource, parent_id in zip(resources, parent_values, strict=True):
            if parent_id:
                resource._set_parent(self.browse(parent_id), operation="create")
        return resources

    def write(self, vals: ValuesType) -> bool:
        if vals.keys() - self._fields.keys():
            return self._write_in_kind_models(vals)
        if "kind_id" in vals:
            self._check_kind_keeps_its_model(vals["kind_id"])
        if "odometer_uom_id" in vals:
            self._check_odometer_uom_is_not_reinterpreted(vals["odometer_uom_id"])
        vals = self._get_vals_to_write(self._normalize_calendar_vals(vals))
        if not vals:
            return True
        if "state" in vals and "state_before_maintenance" not in vals:
            self._check_transition(vals["state"])
            if vals["state"] == "maintenance":
                return self._write_entering_maintenance(vals)
            vals = {**vals, "state_before_maintenance": False}
        if "active" in vals and not vals["active"]:
            self._end_custody()
        if vals.get("active") and (
            archived := self.filtered(lambda resource: not resource.active)
        ):
            archived._check_reactivation()
            disposed = archived.filtered(lambda resource: resource.state == "disposed")
            if disposed and "state" not in vals:
                disposed.write(
                    {**vals, "state": "out_of_service", "date_disposal": False}
                )
                return (self - disposed).write(vals)
        if "company_id" in vals:
            self.check_access("write")
            self.env["resource.relation"]._lock_graph(self.ids)
            if "calendar_id" not in vals and vals["company_id"]:
                company = self.env["res.company"].browse(vals["company_id"])
                foreign = self.filtered(
                    lambda resource: (
                        resource.calendar_id.company_id
                        and resource.calendar_id.company_id != company
                    )
                )
                if foreign:
                    calendar = self.env["resource.calendar"]._get_company_calendar(
                        company
                    )
                    foreign.write({**vals, "calendar_id": calendar.id})
                    return (self - foreign).write(vals)
        if vals.get("user_id") and "partner_id" not in vals:
            humans = self.filtered(lambda resource: resource.type == "human")
            if humans:
                party = self.env["res.users"].sudo().browse(vals["user_id"]).partner_id
                humans.write({**vals, "partner_id": party.id})
                return (self - humans).write(vals)
        result = super().write(vals)
        self._sync_reservations_for_changed_fields(vals)
        things = self.filtered("kind_id")
        if "kind_id" in vals:
            things._on_kind_changed(vals)
        elif vals.keys() & {"identifier_ids", *self._get_identifier_field_names()}:
            things._check_required_identifiers()
        things._notify_kind_models(vals)
        return result

    def _sync_reservations_for_changed_fields(self, vals: ValuesType) -> None:
        if "calendar_id" in vals:
            self.env["resource.reservation"]._recompute_reservations_field(
                Domain("resource_id", "in", self.ids)
                & Domain("date_end", ">", fields.Datetime.now()),
                "resource_calendar_id",
            )
        if "tz" in vals:
            self.env["resource.reservation"]._recompute_allocated_hours(
                Domain("resource_id", "in", self.ids)
                & Domain("date_end", ">", fields.Datetime.now())
            )
        if "capacity" in vals:
            reservations = (
                self.env["resource.reservation"]
                .sudo()
                .search(
                    Domain("resource_id", "in", self.ids)
                    & Domain("res_model", "!=", False)
                    & (
                        Domain("date_end", "=", False)
                        | Domain("date_end", ">", fields.Datetime.now())
                    )
                )
            )
            for model_name, rows in reservations.grouped("res_model").items():
                if (
                    model_name in self.env
                    and "reservation_ids" in self.env[model_name]._fields
                ):
                    self.env[model_name].sudo().browse(
                        rows.mapped("res_id")
                    ).exists()._active_for_sync()._sync_reservations()

    def _write_entering_maintenance(self, vals: ValuesType) -> bool:
        by_state_before = self.grouped(
            lambda resource: (
                resource.state_before_maintenance
                if resource.state == "maintenance"
                else resource.state
            )
        )
        result = True
        for state_before, resources in by_state_before.items():
            result = (
                resources.write({**vals, "state_before_maintenance": state_before})
                and result
            )
        return result

    def copy_data(self, default: ValuesType | None = None) -> list[ValuesType]:
        vals_list = super().copy_data(default=default)
        given = set(default or ())
        copies = []
        for resource, vals in zip(self, vals_list, strict=True):
            if "name" not in given:
                vals = dict(vals, name=self.env._("%s (copy)", resource.name))
            company = self.env["res.company"].browse(
                vals.get("company_id") or resource.company_id.id
            )
            calendar_company = resource.calendar_id.company_id
            if (
                "calendar_id" not in given
                and calendar_company
                and calendar_company != company
            ):
                vals["calendar_id"] = company.resource_calendar_id.id
            copies.append(vals)
        return copies

    @api.ondelete(at_uninstall=False)
    def _unlink_except_operational_history(self):
        history = (
            self.env["resource.reservation"]
            .sudo()
            .with_context(active_test=False)
            .search_count([("resource_id", "in", self.ids)], limit=1)
            or self.env["resource.assignment"]
            .sudo()
            .with_context(active_test=False)
            .search_count(
                ["|", ("resource_id", "in", self.ids), ("assignee_id", "in", self.ids)],
                limit=1,
            )
            or self.env["resource.relation"]
            .sudo()
            .with_context(active_test=False)
            .search_count(
                ["|", ("parent_id", "in", self.ids), ("member_id", "in", self.ids)],
                limit=1,
            )
        )
        if history:
            raise UserError(
                self.env._(
                    "This resource has operational history. Archive it instead of deleting it."
                )
            )

    @api.model
    def _default_calendar_id(self):
        company = (
            self.env["res.company"].browse(self.env.context.get("default_company_id"))
            or self.env.company
        )
        return self.env["resource.calendar"]._get_company_calendar(company)

    @api.depends("calendar_id", "company_id", "partner_id", "user_id")
    def _compute_tz(self) -> None:
        for resource in self:
            resource.tz = (
                resource.tz
                or resource.calendar_id.tz
                or resource.company_id.resource_calendar_id.tz
                or resource.partner_id.sudo().tz
                or resource.user_id.sudo().tz
                or self.env.context.get("tz")
                or self.env.user.tz
                or "UTC"
            )

    @api.depends("role_ids")
    def _compute_default_role_id(self) -> None:
        for resource in self:
            if resource.default_role_id not in resource.role_ids:
                resource.default_role_id = resource.role_ids[:1]

    @api.depends(
        "assignment_ids.assignee_id",
        "assignment_ids.date_start",
        "assignment_ids.date_end",
        "assignment_ids.active",
        "assignment_ids.custody_role",
    )
    def _compute_holder_id(self) -> None:
        Assignment = self.env["resource.assignment"]
        winners = Assignment._get_custody_winners(
            self, Assignment._get_holding_custody_roles()
        )
        for resource in self:
            resource.holder_id = winners.get(resource._origin.id, (False,))[0]

    @api.depends(
        "assignment_ids.assignee_id",
        "assignment_ids.custody_role",
        "assignment_ids.date_start",
        "assignment_ids.date_end",
        "assignment_ids.active",
    )
    def _compute_custody(self) -> None:
        Assignment = self.env["resource.assignment"]
        for field_name, role in CUSTODY_ROLE_BY_FIELD.items():
            winners = Assignment._get_custody_winners(self, (role,))
            for resource in self:
                resource[field_name] = winners.get(resource._origin.id, (False,))[0]

    @api.depends(
        "assignment_ids.assignee_id",
        "assignment_ids.custody_role",
        "assignment_ids.date_start",
        "assignment_ids.date_end",
        "assignment_ids.active",
    )
    def _compute_future_operator(self) -> None:
        winners = self.env["resource.assignment"]._get_custody_winners(
            self, (OPERATOR_ROLE,), when="planned"
        )
        for resource in self:
            assignee_id, start = winners.get(resource._origin.id, (False, False))
            resource.future_operator_id = assignee_id
            resource.date_future_operator = start

    @api.depends("partner_id.name")
    def _compute_name(self):
        for resource in self:
            resource.name = resource.partner_id.name or resource.name

    @api.depends("type", "partner_id.user_ids.active", "partner_id.user_ids.share")
    def _compute_user_id(self) -> None:
        for resource in self:
            if resource.type != "human":
                resource.user_id = resource.user_id
                continue
            users = resource.partner_id.sudo().with_context(active_test=False).user_ids
            if resource.user_id in users:
                resource.user_id = resource.user_id
                continue
            logins = users.filtered(lambda user: user.active and not user.share)
            resource.user_id = logins.id if len(logins) == 1 else False

    @api.depends("partner_id.email")
    def _compute_email(self) -> None:
        for resource in self:
            resource.email = resource.partner_id.sudo().email

    @api.depends(
        "type",
        "date_built",
        "country_built_id",
        "place_built",
        "partner_id.child_ids.birthdate",
        "partner_id.child_ids.country_of_birth",
        "partner_id.child_ids.place_of_birth",
    )
    @api.depends_context("uid")
    def _compute_origin(self) -> None:
        facets = self.filtered(
            lambda resource: resource.type == "human"
        ).partner_id._get_private_facets()
        for resource in self:
            if resource.type == "human":
                facet = facets.get(resource.partner_id, self.env["res.partner"])
                resource.date_origin = facet.birthdate
                resource.origin_country_id = facet.country_of_birth
                resource.place_origin = facet.place_of_birth
            else:
                resource.date_origin = resource.date_built
                resource.origin_country_id = resource.country_built_id
                resource.place_origin = resource.place_built

    def _inverse_origin(self) -> None:
        for resource in self:
            if resource.type == "human":
                if resource.partner_id:
                    resource.partner_id._get_or_create_private_facet().write(
                        {
                            "birthdate": resource.date_origin,
                            "country_of_birth": resource.origin_country_id.id,
                            "place_of_birth": resource.place_origin,
                        }
                    )
                continue
            resource.write(
                {
                    "date_built": resource.date_origin,
                    "country_built_id": resource.origin_country_id.id,
                    "place_built": resource.place_origin,
                }
            )

    def _get_domain_by_holder(self, thing_domain, facet_domain):
        return (Domain("type", "!=", "human") & thing_domain) | (
            Domain("type", "=", "human")
            & Domain(
                "partner_id.child_ids",
                "any",
                Domain("type", "=", "private") & facet_domain,
            )
        )

    def _search_date_origin(self, operator, value):
        return self._get_domain_by_holder(
            Domain("date_built", operator, value), Domain("birthdate", operator, value)
        )

    def _search_origin_country_id(self, operator, value):
        return self._get_domain_by_holder(
            Domain("country_built_id", operator, value),
            Domain("country_of_birth", operator, value),
        )

    @api.depends("date_origin")
    def _compute_year_origin(self) -> None:
        for resource in self:
            resource.year_origin = (
                resource.date_origin.year if resource.date_origin else 0
            )

    def _get_nationalities(self):
        self.check_singleton()
        if self.type == "human":
            return self.partner_id._get_private_facet().nationality_ids
        return self.nationality_ids

    @api.depends_context("uid")
    def _compute_nationality_country_ids(self) -> None:
        for resource in self:
            resource.nationality_country_ids = (
                resource._get_nationalities()._filter_held().country_id
            )

    def _search_nationality_country_ids(self, operator, value):
        held = self.env["resource.nationality"]._get_held_domain()
        countries = Domain(
            "nationality_ids", "any", held & Domain("country_id", operator, value)
        )
        return self._get_domain_by_holder(countries, countries)

    @api.depends("company_id")
    def _compute_currency_id(self) -> None:
        fallback = self.env.company.currency_id
        for resource in self:
            resource.currency_id = resource.company_id.currency_id or fallback

    def _value_sql_currency_id(self, field, alias, query=None):
        return SQL(
            "COALESCE((SELECT currency_id FROM res_company WHERE id = %s), %s)",
            self._field_to_sql(alias, "company_id", query),
            self.env.company.currency_id.id,
        )

    @api.depends("partner_id.avatar_128", "user_id.avatar_128", "image_128")
    def _compute_avatar_128(self) -> None:
        for resource in self:
            resource.avatar_128 = (
                resource.partner_id.avatar_128
                or resource.user_id.avatar_128
                or resource.image_128
            )

    def _inverse_operator_id(self) -> None:
        self._sync_custody("operator_id")

    def _inverse_manager_id(self) -> None:
        self._sync_custody("manager_id")

    def _inverse_future_operator(self) -> None:
        now = fields.Datetime.now()
        Assignment = self.env["resource.assignment"]
        planned = Assignment._get_custody_assignments(
            self, roles=(OPERATOR_ROLE,), when="planned"
        )
        planned_by_resource = defaultdict(planned.browse)
        for assignment in planned:
            planned_by_resource[assignment.resource_id.id] |= assignment
        holder_field = self._fields["future_operator_id"]
        date_field = self._fields["date_future_operator"]
        cache = self.env.cache
        new_vals_list = []
        changes = {}
        for resource in self:
            current = planned_by_resource[resource.id].sorted("date_start")[:1]
            holder = (
                resource.future_operator_id
                if cache.contains(resource, holder_field)
                else current.assignee_id
            )
            date_start = (
                resource.date_future_operator
                if cache.contains(resource, date_field)
                else current.date_start
            ) or now + DEFAULT_HANDOVER_DELAY
            if (
                holder
                and current.assignee_id == holder
                and current.date_start == date_start
            ):
                continue
            planned_by_resource[resource.id]._end(now)
            if holder:
                if date_start <= now:
                    raise UserError(
                        self.env._("A scheduled hand-over must start in the future.")
                    )
                new_vals_list.append(
                    {
                        "resource_id": resource.id,
                        "assignee_id": holder.id,
                        "custody_role": OPERATOR_ROLE,
                        "date_start": date_start,
                    }
                )
            changes[resource.id] = (current.assignee_id[:1], holder)
            if holder:
                resource.future_operator_id = holder
                resource.date_future_operator = date_start
        if new_vals_list:
            Assignment.sudo().create(new_vals_list)
        self.browse(changes)._on_custody_changed(OPERATOR_ROLE, changes, planned=True)

    def _inverse_default_role_id(self) -> None:
        for resource in self:
            if resource.default_role_id:
                resource.role_ids |= resource.default_role_id
            else:
                resource.default_role_id = resource.role_ids[:1]

    def _inverse_email(self) -> None:
        for resource in self.filtered("partner_id"):
            if resource.partner_id.sudo().email != resource.email:
                resource.partner_id.email = resource.email

    def _inverse_name(self) -> None:
        for resource in self.filtered("partner_id"):
            if resource.partner_id.sudo().name != resource.name:
                resource.partner_id.name = resource.name

    def _search_operator_id(self, operator, value):
        return self._get_domain_custody_winner((OPERATOR_ROLE,), operator, value)

    def _search_manager_id(self, operator, value):
        return self._get_domain_custody_winner((MANAGER_ROLE,), operator, value)

    def _search_future_operator_id(self, operator, value):
        return self._get_domain_custody_winner(
            (OPERATOR_ROLE,), operator, value, when="planned"
        )

    def _search_email(self, operator, value):
        return Domain("partner_id.email", operator, value)

    def _search_holder_id(self, operator, value):
        return self._get_domain_custody_winner(
            self.env["resource.assignment"]._get_holding_custody_roles(),
            operator,
            value,
        )

    @api.onchange("company_id")
    def _onchange_company_id(self):
        if self.company_id:
            self.calendar_id = self.env["resource.calendar"]._get_company_calendar(
                self.company_id
            )

    def _archive_if_unused(self) -> None:
        if not self:
            return
        self.check_access("write")
        self._lock_for_integrity()
        used = self._get_in_use_resource_ids()
        unused = self.filtered(lambda resource: resource.id not in used)
        if unused:
            unused.action_archive()

    def _end_custody(self, at=None) -> None:
        self.env["resource.assignment"]._get_custody_assignments(
            self, when="open", archived=True
        )._end(at)

    def _get_window_free(
        self,
        start: datetime,
        hours: float,
        horizon_days: int = 700,
    ) -> tuple[datetime, datetime] | None:
        revert = to_timezone(start.tzinfo)
        window_start = to_timezone(None)(start)
        length = timedelta(hours=hours or 1)
        limit = window_start + timedelta(days=horizon_days)
        bookings = self.env["resource.reservation"]._get_occupancy(
            self, window_start, limit + length
        )
        busy = Intervals(
            [
                (left, right, bookings.browse())
                for resource, booked in bookings.grouped("resource_id").items()
                for left, right in saturated_spans(
                    [
                        (
                            booking.date_start,
                            booking.date_end,
                            booking.allocated_percentage,
                        )
                        for booking in booked
                    ],
                    window_start,
                    limit + length,
                    resource.booking_limit_percentage,
                )
            ]
        )
        for left, right, _bookings in busy:
            if left >= window_start + length:
                break
            window_start = max(window_start, right)
        if window_start > limit:
            return None
        return revert(window_start), revert(window_start + length)

    def _get_domain_custody_winner(self, roles, operator, value, when="live"):
        if operator in ("in", "not in"):
            ids = [value] if isinstance(value, (int, bool)) else list(value)
            assignee_ids = [i for i in ids if i]
            wanted = SQL("assignee_id = ANY(%s)", assignee_ids)
            wants_empty = len(assignee_ids) < len(ids)
        elif operator in ("any", "not any"):
            assignees = self.with_context(active_test=False)._search(value)
            wanted = SQL("assignee_id IN %s", assignees.subselect())
            wants_empty = False
        else:
            return NotImplemented
        Assignment = self.env["resource.assignment"]

        def to_sql(model, alias, query):
            winners = Assignment._get_sql_custody_winners(roles, when)
            resource_id = model._field_to_sql(alias, "id", query)
            condition = SQL(
                "%s IN (SELECT resource_id FROM (%s) winners WHERE %s)",
                resource_id,
                winners,
                wanted,
            )
            if wants_empty:
                condition = SQL(
                    "(%s OR %s NOT IN (SELECT resource_id FROM (%s) winners))",
                    condition,
                    resource_id,
                    winners,
                )
            return condition

        domain = Domain.custom(to_sql=to_sql)
        return ~domain if operator.startswith("not") else domain

    @api.model
    @tools.ormcache("owns", cache="stable")
    def _get_host_model_names(self, owns=None) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    self.env[name]._get_root_model_name()
                    for name, model in self.env.registry.items()
                    if not model._abstract
                    and not model._transient
                    and isinstance(getattr(model, "_resource_owns", None), bool)
                    and (owns is None or model._resource_owns == owns)
                    and "resource_id" in model._fields
                    and model._fields["resource_id"].comodel_name == "resource.resource"
                }
            )
        )

    @api.model
    def _get_owner_model_names(self) -> tuple[str, ...]:
        return self._get_host_model_names(True)

    def _get_in_use_resource_ids(self) -> set[int]:
        used = set(self._get_owners())
        for name in self._get_host_model_names(False):
            hosts = (
                self.env[name]
                .sudo()
                .with_context(active_test=False)
                .search(  # noqa: E8507 -- one query per host model, not per resource
                    [
                        ("resource_id", "in", self.ids),
                    ]
                )
            )
            used.update(hosts.resource_id.ids)
        now = fields.Datetime.now()
        live = [
            "|",
            ("date_end", "=", False),
            ("date_end", ">", now),
            ("active", "=", True),
        ]
        relations = (
            self.env["resource.relation"]
            .sudo()
            .search(
                live
                + [
                    "|",
                    ("parent_id", "in", self.ids),
                    ("member_id", "in", self.ids),
                ]
            )
        )
        used.update(relations.parent_id.ids)
        used.update(relations.member_id.ids)
        Reservation = self.env["resource.reservation"]
        claims = Reservation.sudo().search(
            Reservation._get_domain_occupancy(self, since=now)
        )
        used.update(claims.resource_id.ids)
        Assignment = self.env["resource.assignment"]
        assignments = Assignment.sudo().search(
            Domain(live)
            & ~Assignment._get_domain_cancelled()
            & (
                Domain("resource_id", "in", self.ids)
                | Domain("assignee_id", "in", self.ids)
            )
        )
        used.update(assignments.resource_id.ids)
        used.update(assignments.assignee_id.ids)
        return used.intersection(self.ids)

    def _get_reservation_status(self, at=None):
        if not self:
            return {}
        self.check_access("read")
        at = fields.Datetime.to_datetime(at or fields.Datetime.now())
        if at.tzinfo is not None:
            at = at.astimezone(UTC).replace(tzinfo=None)
        status = {
            resource.id: {"is_reserved": False, "next_reservation_start": None}
            for resource in self
        }
        reservations = (
            self.env["resource.reservation"]
            .sudo()
            .search_fetch(
                self.env["resource.reservation"]._get_domain_occupancy(self, since=at),
                ["resource_id", "date_start"],
                order="date_start",
            )
        )
        for reservation in reservations:
            item = status[reservation.resource_id.id]
            if reservation.date_start <= at:
                item["is_reserved"] = True
            elif item["next_reservation_start"] is None:
                item["next_reservation_start"] = reservation.date_start
        return status

    def _get_unavailable_intervals(
        self, start: datetime, end: datetime, exclude_bookings: bool = True
    ) -> dict[int, Intervals]:
        start_datetime = localized(start)
        end_datetime = localized(end)
        resource_mapping = {}
        for calendar, resources in self.grouped("calendar_id").items():
            resources_unavailable_intervals = calendar._unavailable_intervals_batch(
                start_datetime,
                end_datetime,
                resources,
                exclude_bookings=exclude_bookings,
            )
            resource_mapping.update(resources_unavailable_intervals)
        return resource_mapping

    def _get_calendars_validity_within_period(
        self,
        start: datetime,
        end: datetime,
        default_company: ResCompany | None = None,
    ) -> dict[int | bool, dict]:
        if not (start.tzinfo and end.tzinfo):
            raise ValueError("start and end datetimes must be timezone-aware")
        resource_calendars_within_period = defaultdict(lambda: defaultdict(Intervals))
        default_calendar = (
            default_company and default_company.resource_calendar_id
        ) or self.env.company.resource_calendar_id
        if not self:
            resource_calendars_within_period[False][default_calendar] = Intervals(
                [(start, end, self.env["resource.calendar.attendance"])]
            )
        for resource in self:
            resource_calendars_within_period[resource.id][resource.calendar_id] = (
                Intervals([(start, end, self.env["resource.calendar.attendance"])])
            )
        return resource_calendars_within_period

    def _get_owners(self) -> dict[int, models.BaseModel]:
        owners: dict[int, models.BaseModel] = {}
        for model_name in self._get_owner_model_names():
            records = (
                self.env[model_name]
                .sudo()
                .with_context(active_test=False)
                .search([("resource_id", "in", self.ids)])  # noqa: E8507 -- one query per owner model, not per resource
            )
            for record in records:
                owners.setdefault(record.resource_id.id, record)
        return owners

    def _get_slot_intervals_batch(
        self, start: datetime, stop: datetime, *, reservations_to_ignore=None
    ) -> SlotIntervals:
        self.check_access("read")
        start, stop = localized(start).astimezone(UTC), localized(stop).astimezone(UTC)
        if stop <= start:
            raise ValueError("slot interval bounds must be increasing")
        occupied = self.env["resource.reservation"]._get_reservation_intervals_batch(
            start,
            stop,
            self,
            domain=[("id", "not in", reservations_to_ignore.ids)]
            if reservations_to_ignore
            else [],
        )
        result = SlotIntervals(
            {
                (resource.id, resource.calendar_id.id): (
                    start,
                    stop,
                    Intervals(),
                    Intervals(
                        [
                            (begin, end, self.env["resource.calendar.attendance"])
                            for begin, end, _claims in occupied[resource.id]
                        ]
                    ),
                )
                for resource in self
            }
        )
        for calendar, resources in self.grouped("calendar_id").items():
            available = calendar._work_intervals_batch(start, stop, resources=resources)
            for resource in resources:
                key = (resource.id, calendar.id)
                result[key] = (
                    start,
                    stop,
                    available.get(resource.id, Intervals()),
                    result[key][3],
                )
        return result

    def _get_slot_intervals(
        self,
        start: datetime,
        stop: datetime,
        *,
        reservations_to_ignore=None,
        snapshot: SlotIntervals | None = None,
    ) -> tuple[Intervals, Intervals]:
        self.check_singleton()
        self.check_access("read")
        start, stop = localized(start).astimezone(UTC), localized(stop).astimezone(UTC)
        if stop <= start:
            raise ValueError("slot interval bounds must be increasing")
        key = (self.id, self.calendar_id.id)
        window = snapshot.get(key) if snapshot is not None else None
        if (
            not window
            or reservations_to_ignore
            or start < window[0]
            or stop > window[1]
        ):
            window = self._get_slot_intervals_batch(
                start, stop, reservations_to_ignore=reservations_to_ignore
            ).get(key)
        if not window:
            return Intervals(), Intervals()
        _start, _stop, available, occupied = window
        bounds = Intervals([(start, stop, self.env["resource.calendar.attendance"])])
        return available & bounds, occupied & bounds

    def _get_work_schedule(
        self,
        start: datetime,
        end: datetime,
        calendars: tuple | None = None,
        compute_leaves: bool = True,
        leave_domain: list | None = None,
    ) -> ResourceSchedule:
        flexible = self.filtered(lambda resource: resource._is_flexible())
        intervals, calendar_intervals = (self - flexible)._get_valid_work_intervals(
            start,
            end,
            calendars=calendars,
            compute_leaves=compute_leaves,
            domain=leave_domain,
        )
        flexible_intervals, hours_per_day, hours_per_week = (
            flexible._get_flexible_resource_valid_work_intervals(
                start, end, compute_leaves=compute_leaves, leave_domain=leave_domain
            )
        )
        intervals.update(flexible_intervals)
        return ResourceSchedule(
            intervals=defaultdict(Intervals, intervals),
            calendar_intervals=calendar_intervals,
            hours_per_day=defaultdict(dict, hours_per_day),
            hours_per_week=defaultdict(dict, hours_per_week),
            flexible_ids=frozenset(flexible.ids),
        )

    def _get_valid_work_intervals(
        self,
        start: datetime,
        end: datetime,
        calendars: tuple | None = None,
        compute_leaves: bool = True,
        domain: list | None = None,
    ) -> tuple[dict[int, Intervals], dict[int, Intervals]]:
        if not (start.tzinfo and end.tzinfo):
            raise ValueError("start and end datetimes must be timezone-aware")
        calendar_resources = defaultdict(lambda: self.env["resource.resource"])
        resource_work_intervals = defaultdict(Intervals)
        calendar_work_intervals = {}

        resource_calendar_validity_intervals = (
            self.sudo()._get_calendars_validity_within_period(start, end)
        )
        for resource in self:
            for calendar in resource_calendar_validity_intervals[resource.id]:
                calendar_resources[calendar] |= resource
        for calendar in filter(None, calendars or ()):
            calendar_resources[calendar] |= self.env["resource.resource"]
        for calendar, resources in calendar_resources.items():
            work_intervals_batch = calendar._work_intervals_batch(
                start,
                end,
                resources=resources,
                domain=domain,
                compute_leaves=compute_leaves,
            )
            for resource in resources:
                resource_work_intervals[resource.id] |= (
                    work_intervals_batch[resource.id]
                    & resource_calendar_validity_intervals[resource.id][calendar]
                )
            calendar_work_intervals[calendar.id] = work_intervals_batch[False]

        return resource_work_intervals, calendar_work_intervals

    def _get_flexible_resources_default_work_intervals(
        self,
        start: datetime,
        end: datetime,
    ) -> dict[int, Intervals]:
        if not (start.tzinfo and end.tzinfo):
            raise ValueError("start and end datetimes must be timezone-aware")

        res = {}

        resources_per_tz = defaultdict(list)
        for resource in self:
            resources_per_tz[timezone(resource.tz)].append(resource)

        for tz, resources in resources_per_tz.items():
            whole_days = (
                datetime.combine(start.astimezone(tz).date(), time.min, tz),
                datetime.combine(
                    end.astimezone(tz).date() + timedelta(days=1), time.min, tz
                ),
                self.env["resource.calendar.attendance"],
            )
            for resource in resources:
                res[resource.id] = Intervals([whole_days])

        return res

    def _get_flexible_resources_calendars_validity_within_period(
        self,
        start: datetime,
        end: datetime,
    ) -> dict[int, dict]:
        if not (start.tzinfo and end.tzinfo):
            raise ValueError("start and end datetimes must be timezone-aware")
        resource_default_work_intervals = (
            self._get_flexible_resources_default_work_intervals(start, end)
        )

        calendars_within_period_per_resource = defaultdict(
            lambda: defaultdict(Intervals)
        )
        for resource in self:
            calendars_within_period_per_resource[resource.id][resource.calendar_id] = (
                resource_default_work_intervals[resource.id]
            )

        return calendars_within_period_per_resource

    def _get_week_of(self, day: date) -> date:
        return week_of(day, self.company_id._get_resource_week_start())

    def _get_flexible_week_bounds(self, start, end) -> tuple:
        if not (start.tzinfo and end.tzinfo):
            raise ValueError("start and end datetimes must be timezone-aware")
        starts, stops = [], []
        for resource in self:
            tz = timezone(resource.tz)
            local_start, local_end = start.astimezone(tz), end.astimezone(tz)
            first = resource._get_week_of(local_start.date())
            last = resource._get_week_of(last_day_of(local_start, local_end))
            starts.append(datetime.combine(first, time.min, tz).astimezone(UTC))
            stops.append(
                datetime.combine(last + timedelta(days=7), time.min, tz).astimezone(UTC)
            )
        return min(starts, default=start), max(stops, default=end)

    def _get_flexible_resource_valid_work_intervals(
        self,
        start: datetime,
        end: datetime,
        compute_leaves: bool = True,
        leave_domain: list | None = None,
    ) -> tuple[dict[int, Intervals], dict, dict]:
        if not self:
            return {}, {}, {}

        if not all(record._is_flexible() for record in self):
            raise ValueError("all resources must be flexible")
        if not (start.tzinfo and end.tzinfo):
            raise ValueError("start and end datetimes must be timezone-aware")

        min_start_date, max_end_date = self._get_flexible_week_bounds(start, end)
        days_by_resource = {
            resource.id: (
                start.astimezone(timezone(resource.tz)).date(),
                last_day_of(
                    start.astimezone(timezone(resource.tz)),
                    end.astimezone(timezone(resource.tz)),
                ),
            )
            for resource in self
        }

        resource_work_intervals = defaultdict(Intervals)
        calendar_resources = defaultdict(lambda: self.env["resource.resource"])

        resource_calendar_validity_intervals = (
            self._get_flexible_resources_calendars_validity_within_period(
                min_start_date, max_end_date
            )
        )
        for resource in self:
            for calendar, work_intervals in resource_calendar_validity_intervals[
                resource.id
            ].items():
                calendar_resources[calendar] |= resource
                resource_work_intervals[resource.id] |= work_intervals

        resource_by_id = {resource.id: resource for resource in self}

        resource_hours_per_day = defaultdict(lambda: defaultdict(float))
        resource_hours_per_week = defaultdict(lambda: defaultdict(float))

        for resource in self:
            if resource._is_fully_flexible():
                continue
            start_day, end_day = days_by_resource[resource.id]
            start_week_key = resource._get_week_of(start_day)
            end_week_key = resource._get_week_of(end_day)
            duration_per_day = hours_by_day(
                resource_work_intervals.get(resource.id, Intervals())
            )
            for day, hours in duration_per_day.items():
                day_working_hours = min(hours, resource.calendar_id.hours_per_day)
                if day >= start_day and day <= end_day:
                    resource_hours_per_day[resource.id][day] = day_working_hours

                year_week = resource._get_week_of(day)
                if start_week_key <= year_week <= end_week_key:
                    cap = resource.calendar_id._get_flexible_hours_per_week()
                    resource_hours_per_week[resource.id][year_week] = min(
                        cap,
                        day_working_hours
                        + resource_hours_per_week[resource.id][year_week],
                    )

        if compute_leaves:
            no_attendance = self.env["resource.calendar.attendance"]
            for calendar, resources in calendar_resources.items():
                leave_calendar = (
                    calendar
                    or self.env["resource.calendar"]._get_fully_flexible_calendar()
                )
                leave_intervals = leave_calendar._leave_intervals_batch(
                    min_start_date, max_end_date, resources, leave_domain
                )
                for resource_id, leaves in leave_intervals.items():
                    if not resource_id:
                        continue
                    resource = resource_by_id[resource_id]
                    leave_hours, leave_windows = (
                        leave_calendar._get_flexible_leave_hours(
                            leaves, timezone(resource.tz)
                        )
                    )
                    if not resource._is_fully_flexible():
                        start_day, end_day = days_by_resource[resource_id]
                        for day, hours in leave_hours.items():
                            if start_day <= day <= end_day:
                                resource_hours_per_day[resource_id][day] -= hours
                            resource_hours_per_week[resource_id][
                                resource._get_week_of(day)
                            ] -= hours
                    resource_work_intervals[resource_id] -= Intervals(
                        [
                            (window_start, window_stop, no_attendance)
                            for windows in leave_windows.values()
                            for window_start, window_stop in windows
                        ]
                    )

        for resource_id, work_intervals in resource_work_intervals.items():
            tz = timezone(resource_by_id[resource_id].tz)
            resource_work_intervals[resource_id] = work_intervals & Intervals(
                [
                    (
                        start.astimezone(tz),
                        end.astimezone(tz),
                        self.env["resource.calendar.attendance"],
                    )
                ]
            )

        return resource_work_intervals, resource_hours_per_day, resource_hours_per_week

    def _get_flexible_booking_hours_per_day(self, bookings_by_resource, start, end):
        resources = self.filtered(
            lambda resource: (
                bookings_by_resource.get(resource.id)
                and not resource._is_fully_flexible()
            )
        )
        intervals, day_limits, week_limits = (
            resources._get_flexible_resource_valid_work_intervals(start, end)
        )
        result = defaultdict(lambda: defaultdict(float))
        for resource in resources:
            for booking_start, booking_end, percentage in bookings_by_resource.get(
                resource.id, []
            ):
                booking_intervals = (
                    Intervals(
                        [(localized(booking_start), localized(booking_end), set())]
                    )
                    & intervals[resource.id]
                )
                hours_per_day = defaultdict(float)
                resource._get_flexible_resource_work_hours(
                    booking_intervals,
                    day_limits[resource.id],
                    week_limits[resource.id],
                    hours_per_day,
                )
                for day, hours in hours_per_day.items():
                    result[resource.id][day] += hours * percentage / 100
        return result

    def _get_flexible_resource_work_hours(
        self,
        intervals: Intervals,
        flexible_resources_hours_per_day: dict,
        flexible_resources_hours_per_week: dict,
        work_hours_per_day: dict | None = None,
    ) -> float:
        if not self._is_flexible():
            raise ValueError("resource must be flexible")

        if self._is_fully_flexible():
            return round(get_intervals_hours(intervals), 2)

        duration_per_day = dict(flexible_resources_hours_per_day)
        duration_per_week = dict(flexible_resources_hours_per_week)

        tz = timezone(self.tz)
        interval_duration_per_day = hours_by_day(
            (start.astimezone(tz), end.astimezone(tz), None)
            for start, end, _dummy in intervals
        )

        work_hours = 0.0
        for day, hours in interval_duration_per_day.items():
            week = self._get_week_of(day)
            day_working_hours = max(
                0.0,
                min(
                    hours,
                    duration_per_day.get(day, 0.0),
                    duration_per_week.get(week, 0.0),
                ),
            )
            work_hours += day_working_hours
            duration_per_week[week] = (
                duration_per_week.get(week, 0.0) - day_working_hours
            )

            if work_hours_per_day is not None:
                work_hours_per_day[day] += day_working_hours

        return work_hours

    def _lock_for_integrity(self) -> None:
        if self:
            self.env.cr.execute(
                SQL(
                    """
                WITH locked AS MATERIALIZED (
                    SELECT id FROM resource_resource
                     WHERE id = ANY(%s) ORDER BY id FOR NO KEY UPDATE
                )
                UPDATE resource_resource AS resource
                   SET write_date = resource.write_date
                  FROM locked WHERE resource.id = locked.id
                """,
                    self.ids,
                )
            )

    def _get_local_date(self, moment: datetime | None = None) -> date:
        self.check_singleton()
        if moment is not None and moment.tzinfo is not None:
            moment = moment.astimezone(UTC).replace(tzinfo=None)
        return fields.Date.context_today(
            self.with_context(tz=self.tz), timestamp=moment
        )

    def _get_local_day_bounds(self, day: date) -> tuple[datetime, datetime]:
        self.check_singleton()
        zone = ZoneInfo(self.tz or "UTC")
        start = datetime.combine(day, time(), tzinfo=zone)
        end = datetime.combine(day + timedelta(days=1), time(), tzinfo=zone)
        return (
            start.astimezone(UTC).replace(tzinfo=None),
            end.astimezone(UTC).replace(tzinfo=None),
        )

    def _on_custody_changed(self, role, changes, planned=False):
        pass

    def _announce_custody_change(self, role, before, after, planned=False) -> None:
        pass

    def _get_vals_to_write(self, vals: ValuesType) -> ValuesType:
        if self.env.context.get("check_idempotence") and len(self) == 1:
            return changed_vals(self, vals)
        return vals

    def _sync_custody(self, field_name):
        role = CUSTODY_ROLE_BY_FIELD[field_name]
        now = fields.Datetime.now()
        Assignment = self.env["resource.assignment"]
        live = Assignment._get_custody_assignments(self, roles=(role,), archived=True)
        live_by_resource = defaultdict(live.browse)
        for assignment in live:
            live_by_resource[assignment.resource_id.id] |= assignment
        new_vals_list = []
        changes = {}
        for resource in self:
            current = live_by_resource[resource.id]
            holding = current.filtered("active")
            holder = resource[field_name]
            if holder and holding.assignee_id == holder:
                continue
            if not holder and not current:
                continue
            changes[resource.id] = (holding.assignee_id[:1], holder)
            current._end(now)
            if holder:
                new_vals_list.append(
                    {
                        "resource_id": resource.id,
                        "assignee_id": holder.id,
                        "custody_role": role,
                        "date_start": now,
                    }
                )
        if new_vals_list:
            Assignment.sudo().with_context(**{CUSTODY_SYNC: True}).create(new_vals_list)
        changed = self.browse(changes)
        changed._on_custody_changed(role, changes)
        return changed

    def _update_party_vals(self, vals_list: list[ValuesType]) -> None:
        default_type = self.default_get(["type"]).get("type")
        unbound = []
        persons = [
            values
            for values in vals_list
            if not values.get("partner_id")
            and values.get("type", default_type) == "human"
        ]
        partner_by_user = {
            user.id: user.partner_id.id
            for user in self.env["res.users"]
            .sudo()
            .browse({values["user_id"] for values in persons if values.get("user_id")})
        }
        for values in persons:
            if values.get("user_id") in partner_by_user:
                values["partner_id"] = partner_by_user[values["user_id"]]
            elif values.get("name"):
                unbound.append(values)
            else:
                raise ValidationError(
                    self.env._("A person needs a name, a party or a user.")
                )
        parties = (
            self.env["res.partner"]
            .sudo()
            .create(
                [
                    {
                        "name": values["name"],
                        "email": values.get("email") or False,
                        "tz": values.get("tz") or False,
                    }
                    for values in unbound
                ]
            )
        )
        for values, party in zip(unbound, parties, strict=True):
            values["partner_id"] = party.id

    def _is_fully_flexible(self) -> bool:
        self.check_singleton()
        return self.calendar_id.schedule_type == "fully_flexible"

    def _is_flexible(self) -> bool:
        self.check_singleton()
        return self.calendar_id.schedule_type in ("flexible", "fully_flexible")

    @api.model
    def _normalize_calendar_vals(self, vals: ValuesType) -> ValuesType:
        return self.env["resource.calendar"]._normalize_calendar_vals(
            vals, "calendar_id"
        )

    def _check_host_type(self, resource_type):
        if any(resource.type != resource_type for resource in self):
            raise ValidationError(
                self.env._("The resource type is incompatible with its representation.")
            )

    def _get_identifier(self, code: str) -> str | None:
        self.check_singleton()
        identifier = self.identifier_ids.filtered(lambda i: i.type_id.code == code)[:1]
        return identifier.value or None

    def _update_identifier(self, code: str, value) -> None:
        self.check_singleton()
        identifier_type = (
            self.env["resource.identifier.type"]
            .sudo()
            .search([("code", "=", code)], limit=1)
        )
        if not identifier_type:
            return
        current = self.sudo().identifier_ids.filtered(
            lambda i: i.type_id == identifier_type
        )[:1]
        if value and current and current.value != value:
            current.value = value
        elif value and not current:
            self.env["resource.identifier"].sudo().create(
                {"resource_id": self.id, "type_id": identifier_type.id, "value": value}
            )
        elif not value and current:
            current.unlink()

    def action_set_available(self) -> None:
        self._transition("available")

    def action_set_in_service(self) -> None:
        self._transition("in_service")

    def action_set_maintenance(self) -> None:
        self._transition("maintenance")

    def action_end_maintenance(self) -> None:
        self._end_maintenance()

    def action_set_out_of_service(self) -> None:
        self._transition("out_of_service")

    def action_dispose(self):
        return self._dispose()

    def _dispose(self, date: date | None = None) -> None:
        self._transition("disposed", date=date)

    def _transition(self, state: str, date: date | None = None) -> None:
        self.write(self._get_transition_vals(state, date))

    @api.model
    def _get_transition_vals(self, state: str, date: date | None = None) -> ValuesType:
        if state != "disposed":
            return {"state": state}
        return {
            "state": state,
            "date_disposal": date or fields.Date.context_today(self),
            "active": False,
        }

    def _end_maintenance(self) -> None:
        under_maintenance = self.filtered(
            lambda resource: resource.state == "maintenance"
        )
        for state, resources in under_maintenance.grouped(
            lambda resource: resource._get_state_after_maintenance()
        ).items():
            resources._transition(state)

    def _get_state_after_maintenance(self) -> str:
        self.check_singleton()
        return self.state_before_maintenance or "available"

    def _check_transition(self, state: str) -> None:
        pass

    def _check_reactivation(self) -> None:
        pass

    def get_formview_action(self, access_uid=None):
        if len(self) == 1:
            model_name = self._get_kind_models()[self.id]
            if model_name != self._name:
                return (
                    self.env[model_name]
                    .browse(self.id)
                    .get_formview_action(access_uid=access_uid)
                )
        return super().get_formview_action(access_uid=access_uid)

    def get_formview_id(self, access_uid=None):
        if len(self) == 1 and self.kind_id:
            return self.env.ref("base.resource_asset_view_form").id
        return super().get_formview_id(access_uid=access_uid)

    @api.constrains("type", "kind_id")
    def _check_a_thing_is_material(self) -> None:
        if self.filtered(
            lambda resource: resource.kind_id and resource.type != "material"
        ):
            raise ValidationError(
                self.env._("A resource of a kind is a thing, not a person.")
            )

    @api.depends("meter_ids.kind")
    def _compute_odometer_meter_id(self) -> None:
        for resource in self:
            resource.odometer_meter_id = resource.meter_ids.filtered(
                lambda m: m.kind == "odometer"
            )[:1]

    @api.depends("odometer_meter_id.last_reading_id.value")
    def _compute_odometer(self) -> None:
        for resource in self:
            resource.odometer = resource.odometer_meter_id.value

    def _inverse_odometer(self) -> None:
        for resource in self:
            meter = resource.odometer_meter_id
            if not resource.odometer and not meter:
                continue
            if not meter:
                meter = resource._create_odometer_meter()
            if meter.value > resource.odometer:
                _debug.logic(
                    "odometer.refused", reason="below_last_reading", resource=resource
                )
                raise ValidationError(
                    self.env._(
                        "%(asset)s: the odometer cannot go below its last reading of %(value)s.",
                        asset=resource.display_name,
                        value=meter.value,
                    )
                )
            if meter.value != resource.odometer:
                meter.record(resource.odometer)

    def _create_odometer_meter(self):
        self.check_singleton()
        meter = self.env["resource.meter"].create(
            {
                "resource_id": self.id,
                "name": self.env._("Odometer"),
                "kind": "odometer",
                "uom_id": self.odometer_uom_id.id,
            }
        )
        self.invalidate_recordset(["odometer_meter_id"])
        return meter

    def _check_odometer_uom_is_not_reinterpreted(self, new_uom_id) -> None:
        changing = self.filtered(
            lambda resource: resource.odometer_uom_id.id != new_uom_id
        )
        with_readings = changing.sudo().filtered(
            lambda resource: resource.odometer_meter_id.reading_ids
        )
        if with_readings:
            _debug.logic(
                "odometer_uom.refused", reason="readings_exist", resources=self
            )
            raise ValidationError(
                self.env._(
                    "%(assets)s already carry odometer readings in their current "
                    "unit. Changing it now would restate every one of them; "
                    "convert the readings deliberately instead.",
                    assets=", ".join(with_readings.mapped("display_name")),
                )
            )

    @api.model
    def _get_identifier_field_names(self) -> tuple[str, ...]:
        return tuple(
            name
            for name, field in self._fields.items()
            if isinstance(field, ResourceIdentifier)
        )

    def _check_required_identifiers(self) -> None:
        if self.env.context.get(SKIP_IDENTITY_CHECK):
            return
        enforced = self.filtered(lambda resource: resource.kind_id.enforce_identifiers)
        if not enforced:
            return
        enforced.invalidate_recordset(
            [
                "identifier_ids",
                "missing_identifier_type_ids",
                *self._get_identifier_field_names(),
            ]
        )
        for resource in enforced:
            missing = resource.missing_identifier_type_ids
            if missing:
                _debug.logic(
                    "asset.refused",
                    reason="missing_required_identifiers",
                    resource=resource,
                )
                raise ValidationError(
                    self.env._(
                        "%(asset)s is a %(kind)s, which requires %(types)s.",
                        asset=resource.name or self.env._("This asset"),
                        kind=resource.kind_id.display_name,
                        types=", ".join(missing.mapped("name")),
                    )
                )

    @api.depends("identifier_ids.type_id", "kind_id.identifier_type_ids")
    def _compute_missing_identifier_type_ids(self) -> None:
        for resource in self:
            resource.missing_identifier_type_ids = (
                resource.kind_id.identifier_type_ids - resource.identifier_ids.type_id
            )

    def _search_missing_identifier_type_ids(self, operator, value):
        if operator in ("any", "not any"):
            type_query = self.env["resource.identifier.type"]._search(value)
            domain = self._get_missing_identifier_domain(
                SQL("rel.type_id IN %s", type_query.subselect())
            )
        elif operator in ("in", "not in"):
            type_ids = [type_id for type_id in value if type_id]
            domain = Domain.FALSE
            if type_ids:
                domain |= self._get_missing_identifier_domain(
                    SQL("rel.type_id = ANY(%s)", type_ids)
                )
            if len(type_ids) < len(value):
                domain |= ~self._get_missing_identifier_domain()
        else:
            return NotImplemented
        return ~domain if operator.startswith("not") else domain

    @api.model
    def _get_missing_identifier_domain(self, type_condition=None):
        def to_sql(model, alias, query):
            return SQL(
                """
                EXISTS (
                    SELECT 1
                      FROM resource_asset_kind_identifier_type_rel rel
                     WHERE rel.kind_id = %(kind)s
                       AND %(types)s
                       AND NOT EXISTS (
                           SELECT 1
                             FROM resource_identifier identifier
                            WHERE identifier.resource_id = %(resource)s
                              AND identifier.type_id = rel.type_id
                       )
                )
                """,
                kind=SQL.identifier(alias, "kind_id"),
                resource=SQL.identifier(alias, "id"),
                types=type_condition or SQL("TRUE"),
            )

        return Domain.custom(to_sql=to_sql)

    @api.depends(
        "membership_ids.parent_id",
        "membership_ids.relation_type",
        "membership_ids.active",
        "membership_ids.date_start",
        "membership_ids.date_end",
    )
    @api.depends_context("uid", "allowed_company_ids")
    def _compute_parent_id(self):
        Relation = self.env["resource.relation"]
        relations = Relation.search(
            Relation._get_domain_live_relations() + [("member_id", "in", self.ids)]
        )
        things = (
            self.with_context(active_test=False)
            .search([("id", "in", relations.parent_id.ids), ("kind_id", "!=", False)])
            .ids
        )
        by_member = {
            relation.member_id.id: relation.parent_id.id
            for relation in relations
            if relation.parent_id.id in things
        }
        for resource in self:
            resource.parent_id = by_member.get(resource.id, False)

    def _parent_id_sql(self, field, alias, query=None):
        Relation = self.env["resource.relation"]
        relations = Relation._search(Relation._get_domain_live_relations())
        parents = self.with_context(active_test=False)._search(
            [("kind_id", "!=", False)]
        )
        return SQL(
            """(SELECT relation.parent_id FROM resource_relation relation
                 WHERE relation.member_id = %s AND relation.id IN %s
                   AND relation.parent_id IN %s)""",
            self._field_to_sql(alias, "id", query),
            relations.subselect(),
            parents.subselect(),
        )

    def _search_parent_id(self, operator, value):
        if operator in ("any", "not any"):
            value = self.with_context(active_test=False)._search(value)
            operator = "in" if operator == "any" else "not in"
        if operator not in ("in", "not in"):
            return NotImplemented
        values = list(value) if not isinstance(value, Query) else None
        parent_ids = value if values is None else [v for v in values if v]
        wants_none = values is not None and len(parent_ids) < len(values)

        def to_sql(model, alias, query):
            parent = model._parent_id_sql(model._fields["parent_id"], alias, query)
            if isinstance(parent_ids, Query):
                condition = SQL("%s IN %s", parent, parent_ids.subselect())
            else:
                condition = SQL("%s = ANY(%s)", parent, parent_ids)
            if wants_none:
                condition = SQL("(%s OR %s IS NULL)", condition, parent)
            return SQL("COALESCE(%s, FALSE)", condition)

        domain = Domain.custom(to_sql=to_sql)
        return ~domain if operator == "not in" else domain

    def _inverse_parent_id(self):
        for resource in self:
            resource._set_parent(resource.parent_id)

    def _set_parent(self, parent, operation="write"):
        self.check_singleton()
        self.check_access(operation)
        if parent:
            parent.check_access("write")
        if parent == self:
            raise ValidationError(self.env._("An asset cannot be a part of itself."))
        Relation = self.env["resource.relation"]
        old_parents = (
            Relation.sudo()
            .search(
                Relation._get_domain_live_relations() + [("member_id", "=", self.id)]
            )
            .parent_id
        )
        if not parent and old_parents and not old_parents.filtered("kind_id"):
            return
        self.browse(old_parents.ids).check_access("write")
        with self.env.cr.savepoint():
            Relation.sudo()._set_containment_parent(self.sudo(), parent.sudo())
        self.invalidate_recordset(["parent_id"])

    @api.ondelete(at_uninstall=False)
    def _unlink_except_membership_history(self):
        things = self.filtered("kind_id")
        if things and self.env["resource.relation"].sudo().with_context(
            active_test=False
        ).search_count(
            [
                "|",
                ("parent_id", "in", things.ids),
                ("member_id", "in", things.ids),
            ],
            limit=1,
        ):
            raise ValidationError(
                self.env._(
                    "Archive assets with resource membership history instead of deleting them."
                )
            )

    @api.model
    def _asset_projection_sql(self, resource_id):
        things = self.with_context(active_test=False)._search(
            [("kind_id", "!=", False)]
        )
        return SQL(
            "(SELECT thing.id FROM resource_resource thing WHERE thing.id = %s AND thing.id IN %s)",
            resource_id,
            things.subselect(),
        )

    @api.model
    @tools.ormcache(cache="stable")
    def _get_kind_model_names(self) -> dict[str, str]:
        return {
            model._resource_kind_code: name
            for name, model in self.env.registry.items()
            if getattr(model, "_resource_kind_code", None)
            and model._inherits_shared_id
            and model._inherits.get("resource.resource")
        }

    @api.model
    def _get_model_for_kind(self, kind) -> str:
        return self._get_kind_model_names().get(kind.code, self._name)

    def _get_kind_models(self) -> dict[int, str]:
        found = {}
        for model_name in set(self._get_kind_model_names().values()):
            extended = self.env[model_name].with_context(active_test=False)
            for record_id in extended.search([("id", "in", self.ids)]).ids:  # noqa: E8507 -- one query per kind model, two of them
                found[record_id] = model_name
        return {record_id: found.get(record_id, self._name) for record_id in self.ids}

    def _around_the_clock(self, vals):
        if "calendar_id" in vals:
            return False
        kind = self.env["resource.kind"].browse(vals.get("kind_id"))
        shared = "company_id" in vals and not vals["company_id"]
        return not kind.scheduled or shared

    def _create_in_kind_models(self, vals_list) -> Self | None:
        Kind = self.env["resource.kind"]
        creating = self.env.context.get(KIND_MODEL_CREATING)
        by_model = defaultdict(list)
        for index, vals in enumerate(vals_list):
            model_name = self._get_model_for_kind(Kind.browse(vals.get("kind_id")))
            if model_name == creating:
                model_name = self._name
            by_model[model_name].append((index, vals))
        if set(by_model) <= {self._name}:
            return None
        _debug.pipeline(
            "resource.create_dispatched",
            models={name: len(rows) for name, rows in by_model.items()},
        )
        created = {}
        for model_name, indexed in by_model.items():
            if model_name == self._name:
                records = self.create([vals for __, vals in indexed])
            else:
                records = self.env[model_name].create([vals for __, vals in indexed])
            for (index, __), record in zip(indexed, records, strict=True):
                created[index] = record.id
        return self.browse(created[index] for index in range(len(vals_list)))

    def _write_in_kind_models(self, vals) -> bool:
        by_model = defaultdict(list)
        for record_id, model_name in self._get_kind_models().items():
            by_model[model_name].append(record_id)
        unknown = sorted(vals.keys() - self._fields.keys())
        if self._name in by_model:
            _debug.logic(
                "write.refused",
                reason="field_of_no_kind",
                resources=self,
                fields=unknown,
            )
            raise ValueError(f"Invalid field {unknown[0]!r} in {self._name!r}")
        _debug.pipeline(
            "resource.write_dispatched",
            models={name: len(ids) for name, ids in by_model.items()},
        )
        for model_name, ids in by_model.items():
            self.env[model_name].browse(ids).write(vals)
        return True

    def _notify_kind_models(self, vals) -> None:
        by_model = defaultdict(list)
        for resource in self:
            model_name = self._get_model_for_kind(resource.kind_id)
            if model_name != self._name:
                by_model[model_name].append(resource.id)
        for model_name, ids in by_model.items():
            self.env[model_name].browse(ids)._on_resource_written(vals)

    def _on_kind_changed(self, vals) -> None:
        if not self.env.context.get(KIND_MODEL_CREATING):
            self._check_required_identifiers()

    def _check_kind_keeps_its_model(self, kind_id) -> None:
        kind = self.env["resource.kind"].browse(kind_id)
        target = self._get_model_for_kind(kind)
        for model_name in set(self._get_kind_models().values()):
            if model_name != target:
                _debug.logic(
                    "write.refused", reason="kind_changes_model", resources=self
                )
                raise ValidationError(
                    self.env._(
                        "An asset of kind %(kind)s is a %(model)s, and this "
                        "one is not. Retype it instead.",
                        kind=kind.display_name,
                        model=target,
                    )
                )

    def _retype(self, kind) -> Self:
        target = self._get_model_for_kind(kind)
        by_source = defaultdict(list)
        for record_id, model_name in self._get_kind_models().items():
            if model_name != target:
                by_source[model_name].append(record_id)
        _debug.lifecycle(
            "retype",
            resources=self,
            target=target,
            moving={source: len(ids) for source, ids in by_source.items()},
        )
        if by_source:
            self.env.flush_all()
            for source, ids in by_source.items():
                if source != self._name:
                    self.env.cr.execute(
                        SQL(
                            "DELETE FROM %s WHERE id = ANY(%s)",
                            SQL.identifier(self.env[source]._table),
                            ids,
                        )
                    )
            self.env.invalidate_all()
            moving = [record_id for ids in by_source.values() for record_id in ids]
            if target != self._name:
                self.env[target].with_context(**{KIND_MODEL_CREATING: target}).create(
                    [{"resource_id": record_id} for record_id in moving]
                )
        self.with_context(active_test=False).write({"kind_id": kind.id})
        return self.browse(self.ids)

    def _compute_operator_history_count(self) -> None:
        counts = dict(
            self.env["resource.assignment"]._read_group(
                [
                    ("resource_id", "in", self.ids),
                    ("custody_role", "=", OPERATOR_ROLE),
                ],
                ["resource_id"],
                ["__count"],
            )
        )
        for resource in self:
            resource.operator_history_count = counts.get(resource, 0)

    def _get_assets_released_by_operator_change(self):
        return self.search(
            [
                ("kind_id", "in", self.kind_id.ids),
                ("operator_id", "in", self.future_operator_id.ids),
                ("id", "not in", self.ids),
            ]
        )

    def action_accept_operator_change(self):
        resources = self.filtered("future_operator_id")
        resources._get_assets_released_by_operator_change().operator_id = False
        now = fields.Datetime.now()
        Assignment = self.env["resource.assignment"]
        for resource in resources:
            planned = Assignment._get_custody_assignments(
                resource, roles=(OPERATOR_ROLE,), when="planned"
            ).sorted("date_start")[:1]
            previous = resource.operator_id
            current = Assignment._get_custody_assignments(
                resource, roles=(OPERATOR_ROLE,)
            )
            current._end(now)
            planned.date_start = now
            resource.invalidate_recordset(
                ["operator_id", "future_operator_id", "date_future_operator"]
            )
            resource._announce_custody_change(
                OPERATOR_ROLE, previous, resource.operator_id
            )

    def action_view_operator_history(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Operators"),
            "view_mode": "list,form",
            "res_model": "resource.assignment",
            "domain": [
                ("resource_id", "=", self.id),
                ("custody_role", "=", OPERATOR_ROLE),
            ],
            "context": {
                "default_resource_id": self.id,
                "default_role": OPERATOR_ROLE,
                "active_test": False,
            },
        }

    def _get_holder(self, custody_role=None, at=None):
        self.check_singleton()
        return self.env["resource.assignment"]._get_holder(
            self, custody_role=custody_role, at=at
        )
