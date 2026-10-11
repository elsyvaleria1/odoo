import calendar as cal
import random
from datetime import UTC, datetime, time, timedelta
from math import floor
from urllib.parse import urlencode as url_encode
from zoneinfo import ZoneInfoNotFoundError

from babel.dates import format_datetime, format_time
from dateutil import rrule
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Command, Domain
from odoo.libs.datetime import timezone as get_timezone
from odoo.libs.web import urljoin as url_join
from odoo.tools import float_compare, frozendict
from odoo.tools.misc import babel_locale_parse, get_lang

from odoo.addons.base.models.res_partner import _selection_timezones
from odoo.addons.base.models.resource_utils import peak_capacity


def _utc_to_tz(naive_utc, tz):
    return naive_utc.replace(tzinfo=UTC).astimezone(tz)


class AppointmentType(models.Model):
    _name = "appointment.type"
    _description = "Appointment Type"
    _inherit = ["mixin.image", "mixin.mail.thread", "mixin.mail.activity"]
    _order = "sequence, id"
    _mail_post_access = "read"
    _access_anchors = frozendict(
        {
            "owner": models.Anchor("staff_user_ids", shared=True),
        }
    )

    def write(self, vals):
        result = super().write(vals)
        if {
            "manage_capacity",
            "user_capacity",
            "max_bookings",
            "schedule_based_on",
        } & vals.keys():
            self.env["calendar.event"].sudo().search(
                [
                    ("appointment_type_id", "in", self.ids),
                ]
            )._sync_reservations()
        return result

    @api.model
    def default_get(self, fields):
        result = super().default_get(fields)
        if "category" not in fields or result.get("category") == "custom":
            if "name" in fields and not result.get("name"):
                result["name"] = self.env._("%s - Let's meet", self.env.user.name)
            if "staff_user_ids" in fields and not result.get("staff_user_ids"):
                result["staff_user_ids"] = [Command.set(self.env.user.ids)]
        if "event_videocall_source" in fields and not result.get(
            "event_videocall_source"
        ):
            if not result.get("location_id"):
                result["event_videocall_source"] = (
                    self._get_default_event_videocall_source()
                )
        return result

    def _default_booked_mail_template_id(self):
        return self.env["ir.model.data"]._xmlid_to_res_id(
            "calendar.attendee_invitation_mail_template"
        )

    def _default_canceled_mail_template_id(self):
        return self.env["ir.model.data"]._xmlid_to_res_id(
            "calendar.appointment_canceled_mail_template"
        )

    @api.model
    def _default_question_ids(self):
        return (
            self.env["survey.question"]
            .search([("is_default", "=", True), ("active", "=", True)])
            .ids
        )

    def _get_default_event_videocall_source(self):
        return "discuss"

    sequence = fields.Integer(default=10)
    name = fields.Char(
        string="Appointment Title",
        translate=True,
        required=True,
    )
    active = fields.Boolean(default=True)

    appointment_duration = fields.Float(
        string="Duration",
        default=1.0,
        required=True,
    )
    appointment_duration_formatted = fields.Char(
        string="Appointment Duration Formatted ",
        compute="_compute_appointment_duration_formatted",
        readonly=True,
        help="Appointment Duration formatted in words",
    )
    appointment_tz = fields.Selection(
        selection=_selection_timezones,
        string="Timezone",
        default=lambda self: self.env.user.tz or "UTC",
        required=True,
        help="Timezone where appointment take place",
    )
    auto_confirm = fields.Boolean(
        default=True,
        help="""Automatically confirm appointments at creation, up to the given percentage of the total capacity reserved.
            If unchecked, the appointments will be created as requests and will need manual confirmation.
            Requested appointments are still considered as reserved for the slots availability""",
    )
    is_always_confirm = fields.Boolean(compute="_compute_is_always_confirm")
    image_1920 = fields.Image(string="Background Image")
    location_id = fields.Many2one(comodel_name="res.partner")
    location = fields.Char(
        string="Location formatted",
        compute="_compute_location",
        compute_sudo=True,
        help="Location formatted for one line uses",
    )
    event_videocall_source = fields.Selection(
        selection=[("discuss", "Odoo Discuss")],
        string="Video Link",
        help="Defines the type of video call link that will be used for the generated events. Keep it empty to prevent generating meeting url.",
    )
    allow_guests = fields.Boolean(
        string="Allow invitations",
        help="Let attendees invite guests when registering a meeting.",
    )
    manual_confirmation_percentage = fields.Float(
        string="Capacity Percentage",
        default=1.0,
        help="""Bookings will not be automatically confirmed once the total
        reserved user/resource capacity exceeds this percentage of total capacity.""",
    )
    manage_capacity = fields.Boolean(
        string="Manage Capacities",
        help="""Manage the maximum amount of people a user/resource can handle (e.g. Table for 6 persons, ...)""",
    )
    max_bookings = fields.Integer(
        string="Total Bookings",
        default=1,
        help="""The maximum amount of bookings per slot the appointment can handle (e.g. Allow 6 bookings for the given user/resource).
            This field is only used if the appointment type is not set to manage capacity.""",
    )
    start_datetime = fields.Datetime()
    end_datetime = fields.Datetime()
    booked_mail_template_id = fields.Many2one(
        comodel_name="mail.template",
        string="Booking Email",
        default=lambda self: self._default_booked_mail_template_id(),
        domain=[("model", "=", "calendar.attendee")],
        ondelete="restrict",
        help="If set an email will be sent to the customer when the appointment is booked.",
    )
    canceled_mail_template_id = fields.Many2one(
        comodel_name="mail.template",
        string="Cancellation Email",
        default=lambda self: self._default_canceled_mail_template_id(),
        domain=[("model", "=", "calendar.event")],
        ondelete="restrict",
        help="If set an email will be sent to the customer when the appointment is cancelled.",
    )

    assignment_method = fields.Selection(
        selection=[("auto", "Automatically"), ("manual", "By visitor")],
        string="Assignment",
        compute="_compute_assignment_method",
        readonly=False,
        help="How users and resources will be assigned to the meetings that customers book on your website.",
    )
    is_auto_assign = fields.Boolean(string="Assign automatically")
    is_date_first = fields.Boolean(string="Select date and time first")
    select_first = fields.Selection(
        selection=[("date", "Date"), ("user_resource", "User / Resource")],
        string="Starts with",
        compute="_compute_select_first",
        readonly=False,
        help="What is selected first by the customer when booking an appointment.",
    )

    category = fields.Selection(
        selection=[
            ("recurring", "Weekly Schedule"),
            ("punctual", "Date-limited"),
            ("custom", "Flexible Schedule"),
            ("anytime", "Calendar Link"),
        ],
        compute="_compute_category_id",
        inverse="_inverse_category",
        store=True,
        help="""Used to define this appointment type's category.\n
        Can be one of:\n
            - Weekly Schedule: the default category, weekly recurring slots. Accessible from the website\n
            - Date-limited: regular slots limited between 2 datetimes. Accessible from the website\n
            - Flexible Schedule: the user will create and share to another user a custom appointment type with hand-picked time slots\n
            - Calendar Link: the user will create and share to another user an appointment type covering all their time slots""",
    )
    category_slot_scheduling = fields.Selection(
        selection=[("weekly", "Weekly"), ("flexible", "Flexible")],
        string="Schedule",
        compute="_compute_category_slot_scheduling",
        readonly=False,
    )
    category_time_display = fields.Selection(
        selection=[
            ("recurring_fields", "Within the next"),
            ("punctual_fields", "On specific dates"),
        ],
        string="Displayed category time fields",
        compute="_compute_category_time_display",
        readonly=False,
    )
    country_ids = fields.Many2many(
        comodel_name="res.country",
        relation="appointment_type_country_rel",
        string="Allowed Countries",
        help="Keep empty to allow visitors from any country, otherwise you only allow visitors from selected countries",
    )

    message_confirmation = fields.Html(
        string="Confirmation Message",
        translate=True,
        help="Extra information provided once the appointment is booked.",
    )
    message_intro = fields.Html(
        string="Introduction Message",
        translate=True,
        sanitize_attributes=False,
        help="Small description of the appointment type.",
    )

    hide_duration = fields.Boolean()
    hide_timezone = fields.Boolean(string="Hide Time Zone")
    show_avatars = fields.Boolean(
        string="Display pictures",
        compute="_compute_show_avatars",
        store=True,
        readonly=False,
        help="""Display user or resource images across the entire booking flow.""",
    )

    min_cancellation_hours = fields.Float(
        string="Cancel Before (hours)",
        default=1.0,
        required=True,
    )
    min_schedule_hours = fields.Float(
        string="Schedule before (hours)",
        default=1.0,
        required=True,
    )
    max_schedule_days = fields.Integer(
        string="Schedule not after (days)",
        default=15,
        required=True,
    )

    question_ids = fields.Many2many(
        comodel_name="survey.question",
        relation="appointment_type_survey_question_rel",
        column1="appointment_type_id",
        column2="survey_question_id",
        string="Questions",
        default=lambda self: self._default_question_ids(),
    )
    reminder_ids = fields.Many2many(
        comodel_name="calendar.alarm",
        string="Reminders",
        default=lambda self: self.env["calendar.alarm"].search(
            [("default_for_new_appointment_type", "=", True)]
        ),
    )
    schedule_based_on = fields.Selection(
        selection=[("users", "Users"), ("resources", "Resources")],
        string="Book",
        default="users",
        required=True,
    )
    slot_ids = fields.One2many(
        comodel_name="appointment.slot",
        inverse_name="appointment_type_id",
        string="Availabilities",
        copy=True,
    )
    slot_creation_interval = fields.Float(
        string="Create slot every",
        default=1.0,
        help="Starting from the beginning of the time slot, Odoo will create a new slot at regular intervals based on the time specified here.",
    )

    staff_user_ids = fields.Many2many(
        comodel_name="res.users",
        relation="appointment_type_res_users_rel",
        string="Users",
        compute="_compute_staff_user_ids",
        default=lambda self: self.env.user,
        store=True,
        readonly=False,
        domain="[('share', '=', False)]",
        tracking=True,
    )
    staff_user_count = fields.Count(
        count_of="staff_user_ids",
        string="# Staff Users",
    )
    user_capacity = fields.Integer(
        default=1,
        help="The maximum amount of capacity a user can handle when manage capacity is enabled.",
    )

    resource_ids = fields.Many2many(
        comodel_name="resource.resource",
        relation="appointment_type_resource_rel",
        column1="appointment_type_id",
        column2="resource_id",
        string="Resources",
        compute="_compute_resource_ids",
        store=True,
        readonly=False,
        tracking=True,
    )
    resource_count = fields.Integer(
        string="# Resources",
        compute="_compute_resource_info",
    )
    resource_total_capacity = fields.Integer(
        string="Total Capacity",
        compute="_compute_resource_info",
    )

    appointment_count = fields.Integer(
        string="# Appointments",
        compute="_compute_appointment_counts",
    )
    appointment_count_request = fields.Integer(
        string="# Appointments To Confirm",
        compute="_compute_appointment_counts",
    )
    appointment_count_upcoming = fields.Integer(
        string="# Upcoming Appointments",
        compute="_compute_appointment_counts",
    )
    appointment_invite_ids = fields.Many2many(
        comodel_name="appointment.invite",
        string="Invitation Links",
        copy=False,
    )
    appointment_invite_count = fields.Integer(
        string="# Invitation Links",
        compute="_compute_appointment_invite_count",
    )
    meeting_ids = fields.One2many(
        comodel_name="calendar.event",
        inverse_name="appointment_type_id",
        string="Appointment Meetings",
    )

    connectors_displayed = fields.Boolean(compute="_compute_connectors_displayed")
    is_published = fields.Boolean()

    _check_manual_confirmation_percentage = models.Constraint(
        "check(manual_confirmation_percentage >= 0 and manual_confirmation_percentage <= 1)",
        "The capacity percentage should be between 0 and 100%",
    )

    _check_capacity_positive = models.Constraint(
        "check(user_capacity >= 1 AND max_bookings >= 1)",
        "Capacity should be at least 1.",
    )

    @api.depends("meeting_ids")
    def _compute_appointment_counts(self) -> None:
        mapped_status_data = {}
        allowed_events = {}
        status_data = self.env["calendar.event"]._read_group(
            [("appointment_type_id", "in", self.ids)],
            ["appointment_type_id", "appointment_status"],
            ["__count", "id:array_agg"],
        )
        for appointment_type, status, count, event_ids in status_data:
            if appointment_type.id not in mapped_status_data:
                mapped_status_data[appointment_type.id] = {}
            mapped_status_data[appointment_type.id][status] = count
            allowed_events.setdefault(appointment_type.id, set()).update(event_ids)

        mapped_upcoming_data = {
            appointment_type.id: len(
                set(event_ids) & allowed_events[appointment_type.id]
            )
            for appointment_type, event_ids in self.env["calendar.event"]
            .sudo()
            ._read_group(
                domain=[
                    ("appointment_type_id", "in", mapped_status_data.keys()),
                    ("start", ">", datetime.now()),
                ],
                groupby=["appointment_type_id"],
                aggregates=["id:array_agg"],
            )
        }
        for appointment_type in self:
            appointment_status_data = mapped_status_data.get(
                appointment_type.id, {"booked": 0}
            )
            appointment_type.appointment_count = sum(appointment_status_data.values())
            appointment_type.appointment_count_request = appointment_status_data.get(
                "request", 0
            )
            appointment_type.appointment_count_upcoming = mapped_upcoming_data.get(
                appointment_type.id, 0
            )

    @api.depends("appointment_duration")
    def _compute_appointment_duration_formatted(self) -> None:
        for record in self:
            record.appointment_duration_formatted = self.env[
                "ir.qweb.field.duration"
            ].value_to_html(
                record.appointment_duration * 3600,
                {}
                if record.appointment_duration % 1 == 0
                and record.appointment_duration < 24
                else {"format": "short"},
            )

    @api.depends("appointment_invite_ids")
    def _compute_appointment_invite_count(self) -> None:
        appointment_data = self.env["appointment.invite"]._read_group(
            [("appointment_type_ids", "in", self.ids)],
            ["appointment_type_ids"],
            ["__count"],
        )
        mapped_data = {
            appointment_type.id: count for appointment_type, count in appointment_data
        }
        for appointment_type in self:
            appointment_type.appointment_invite_count = mapped_data.get(
                appointment_type.id, 0
            )

    @api.depends("is_auto_assign")
    def _compute_assignment_method(self) -> None:
        for appointment in self:
            appointment.assignment_method = (
                "auto" if appointment.is_auto_assign else "manual"
            )

    @api.onchange("assignment_method")
    def _onchange_assignment_method(self) -> None:
        for appointment in self:
            appointment.is_auto_assign = appointment.assignment_method == "auto"

    @api.depends("category")
    def _compute_show_avatars(self) -> None:
        for record in self:
            record.show_avatars = record.category not in ["punctual", "recurring"]

    @api.depends("start_datetime", "end_datetime")
    def _compute_category_id(self) -> None:
        for appointment_type in self.filtered(lambda apt: apt.category != "custom"):
            appointment_type.category = (
                "punctual"
                if appointment_type.start_datetime or appointment_type.end_datetime
                else "recurring"
            )
            if not appointment_type.slot_ids:
                appointment_type.slot_ids = appointment_type._get_default_slots(
                    appointment_type.category
                )

    def _inverse_category(self) -> None:
        for appointment_type in self:
            if appointment_type.category == "anytime":
                appointment_type.slot_ids = appointment_type._get_default_slots(
                    "anytime"
                )
            if appointment_type.category == "custom":
                appointment_type.slot_ids -= appointment_type.slot_ids.filtered(
                    lambda slot: not (slot.start_datetime and slot.end_datetime)
                )
                appointment_type.update(
                    {
                        "start_datetime": False,
                        "end_datetime": False,
                    }
                )

    @api.depends("category")
    def _compute_category_slot_scheduling(self) -> None:
        for apt in self:
            apt.category_slot_scheduling = (
                "flexible" if apt.category == "custom" else "weekly"
            )

    @api.onchange("category_slot_scheduling")
    def _onchange_category_slot_scheduling(self) -> None:
        for apt in self.filtered(lambda apt: apt.category != "anytime"):
            previous_category = apt.category
            apt.category = (
                "custom"
                if apt.category_slot_scheduling == "flexible"
                else "punctual"
                if apt.start_datetime or apt.end_datetime
                else "recurring"
            )
            if previous_category == "custom" and apt.category != "custom":
                apt.slot_ids = apt._get_default_slots(apt.category)
            elif apt.category == "custom":
                apt.slot_ids = False

    @api.depends("category")
    def _compute_category_time_display(self) -> None:
        for appointment_type in self:
            appointment_type.category_time_display = (
                "punctual_fields"
                if appointment_type.category == "punctual"
                else "recurring_fields"
            )

    @api.onchange("category_time_display")
    def _onchange_category_time_display(self) -> None:
        if self.category_time_display == "recurring_fields":
            self.update(
                {
                    "start_datetime": False,
                    "end_datetime": False,
                }
            )

    @api.depends("location_id")
    def _compute_location(self) -> None:
        for record in self:
            if (record.location_id.contact_address or "").strip():
                record.location = ", ".join(
                    frag.strip()
                    for frag in record.location_id.contact_address.split("\n")
                    if frag.strip()
                )
            else:
                record.location = record.location_id.name or ""

    @api.depends("auto_confirm", "manual_confirmation_percentage")
    def _compute_is_always_confirm(self) -> None:
        for appointment_type in self:
            appointment_type.is_always_confirm = (
                appointment_type.auto_confirm
                and float_compare(
                    appointment_type.manual_confirmation_percentage, 1.0, 3
                )
                == 0
            )

    @api.depends("schedule_based_on")
    def _compute_resource_ids(self) -> None:
        for appointment_type in self.filtered(
            lambda appt: appt.schedule_based_on == "users"
        ):
            appointment_type.resource_ids = False

    @api.depends("schedule_based_on", "staff_user_ids")
    @api.depends_context("uid")
    def _compute_connectors_displayed(self) -> None:
        connectors_enabled = (
            not self._get_calendars_already_setup()
            and self._get_calendars_possible_to_setup()
        )
        for appointment_type in self:
            appointment_type.connectors_displayed = (
                connectors_enabled
                and appointment_type.schedule_based_on == "users"
                and appointment_type.env.user in appointment_type.staff_user_ids
            )

    @api.depends("is_date_first")
    def _compute_select_first(self) -> None:
        for appointment in self:
            appointment.select_first = (
                "date" if appointment.is_date_first else "user_resource"
            )

    @api.onchange("select_first")
    def _onchange_select_first(self) -> None:
        for appointment in self:
            appointment.is_date_first = appointment.select_first == "date"

    @api.depends("schedule_based_on")
    def _compute_staff_user_ids(self) -> None:
        for appointment_type in self.filtered(
            lambda appt: appt.schedule_based_on == "resources"
        ):
            appointment_type.staff_user_ids = False

    @api.depends("resource_ids", "resource_ids.capacity")
    def _compute_resource_info(self) -> None:
        resource_data = self.env["resource.resource"]._read_group(
            [("appointment_type_ids", "in", self.ids)],
            ["appointment_type_ids"],
            ["__count", "capacity:sum"],
        )
        mapped_data = {
            appointment_type.id: {
                "count": count,
                "total_capacity": total_capacity,
            }
            for appointment_type, count, total_capacity in resource_data
        }

        for appointment_type in self:
            if not appointment_type.id:
                appointment_type.resource_count = len(appointment_type.resource_ids)
                appointment_type.resource_total_capacity = sum(
                    resource.capacity for resource in appointment_type.resource_ids
                )
            else:
                appointment_type_data = mapped_data.get(appointment_type.id, {})
                appointment_type.resource_count = appointment_type_data.get("count", 0)
                appointment_type.resource_total_capacity = appointment_type_data.get(
                    "total_capacity", 0
                )

    @api.constrains("question_ids")
    def _check_appointment_questions(self) -> None:
        self.question_ids._check_appointment_question()
        self.question_ids._check_question_type()

    @api.constrains("category", "start_datetime", "end_datetime")
    def _check_appointment_category_time_boundaries(self) -> None:
        for appointment_type in self:
            if appointment_type.category == "punctual" and not (
                appointment_type.start_datetime and appointment_type.end_datetime
            ):
                raise ValidationError(
                    self.env._(
                        "A punctual appointment type should be limited between a start and end datetime."
                    )
                )
            if appointment_type.category != "punctual" and (
                appointment_type.start_datetime or appointment_type.end_datetime
            ):
                raise ValidationError(
                    self.env._(
                        "A %s appointment type shouldn't be limited by datetimes.",
                        appointment_type.category,
                    )
                )
            if (
                appointment_type.start_datetime
                and appointment_type.end_datetime
                and appointment_type.start_datetime > appointment_type.end_datetime
            ):
                raise ValidationError(
                    self.env._("Start date should precede the end date.")
                )

    @api.constrains("appointment_duration")
    def _check_appointment_duration(self) -> None:
        for record in self:
            if not record.appointment_duration > 0.0:
                raise ValidationError(
                    self.env._("Appointment Duration should be higher than 0.00.")
                )

    @api.constrains("category", "staff_user_ids", "schedule_based_on")
    def _check_staff_user_configuration(self) -> None:
        anytime_appointments = self.search([("category", "=", "anytime")])
        for appointment_type in self.filtered(
            lambda appt: (
                appt.schedule_based_on == "users" and appt.category == "anytime"
            )
        ):
            duplicate = anytime_appointments.filtered_domain(
                [("staff_user_ids", "in", appointment_type.staff_user_ids.ids)]
            )
            if appointment_type.ids != duplicate.ids:
                raise ValidationError(
                    self.env._(
                        "Only one anytime appointment type is allowed for a specific user."
                    )
                )

    def _can_return_content(self, field_name=None, access_token=None) -> bool:
        if field_name in ["image_%s" % size for size in [1920, 1024, 512, 256, 128]]:
            return True
        return super()._can_return_content(field_name, access_token)

    @api.model_create_multi
    def create(self, vals_list):
        return super(
            AppointmentType, self.with_context(mail_create_nosubscribe=True)
        ).create(vals_list)

    def copy_data(self, default=None):
        vals_list = super().copy_data(default=default)
        return [
            dict(
                vals,
                name=self.env._("%s (copy)", appointment_type.name),
                category=appointment_type.category,
            )
            for appointment_type, vals in zip(self, vals_list, strict=False)
        ]

    def copy_translations(self, new, excluded=()) -> None:
        super().copy_translations(new, excluded=(*excluded, "name"))
        self._copy_translations_of_renamed_field(
            new, "name", lambda record, term: record.env._("%s (copy)", term)
        )

    def action_calendar_event_view_request(self):
        action = self.action_calendar_meetings(
            calendar_event_domain=[("appointment_status", "=", "request")]
        )
        action["context"].update(
            {
                "search_default_filter_appointment_status_request": True,
            }
        )
        return action

    def action_calendar_meetings(self, calendar_event_domain=False):
        self.check_singleton()
        action = self._get_calendar_booking_action(self.schedule_based_on)
        domain = Domain("start", ">=", datetime.today())
        if calendar_event_domain:
            domain &= Domain(calendar_event_domain)
        appointments = self.meeting_ids.filtered_domain(domain)
        nbr_appointments_week_later = appointments.filtered_domain(
            [("start", ">=", datetime.today() + timedelta(weeks=1))]
        )

        action["context"].update(
            {
                "default_appointment_type_id": self.id,
                "default_duration": self.appointment_duration,
                "default_partner_ids": [],
                "search_default_appointment_type_id": self.id,
                "default_mode": "month" if nbr_appointments_week_later else "week",
                "initial_date": appointments[0].start
                if appointments
                else datetime.today(),
            }
        )
        return action

    def _get_calendar_booking_action(self, schedule_based_on):
        xml_id = (
            "calendar.calendar_event_action_view_bookings_users"
            if schedule_based_on == "users"
            else "calendar.calendar_event_action_view_bookings_resources"
        )
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(xml_id)
        action = self._reorder_action_views(action, self._get_booking_view_types())
        action["context"] = self.env["ir.actions.actions"]._eval_action_context(
            action["context"]
        )
        return action

    @api.model
    def action_calendar_meetings_resources_all(self):
        action = self.browse()._get_calendar_booking_action("resources")
        action["path"] = "resource-bookings"
        return action

    @api.model
    def action_calendar_meetings_users_all(self):
        action = self.browse()._get_calendar_booking_action("users")
        action["path"] = "staff-bookings"
        return action

    def action_share_invite(self):
        return {
            "name": self.env._("Create a Share Link"),
            "type": "ir.actions.act_window",
            "res_model": "appointment.invite",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_appointment_type_ids": self.ids,
                "dialog_size": "medium",
            },
        }

    def action_customer_preview(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_url",
            "url": url_join(self.get_base_url(), "/appointment/%s" % self.id),
            "target": "self",
        }

    def acquire_share_url(self) -> str:
        self.check_singleton()
        existing_invitation = self.env["appointment.invite"]._find_identical_config(
            self.ids, "all_assigned_resources"
        )
        if existing_invitation:
            return existing_invitation.book_url

        return (
            self.env["appointment.invite"]
            .create(
                [
                    {
                        "appointment_type_ids": self.ids,
                        "resources_choice": "all_assigned_resources",
                    }
                ]
            )
            .book_url
        )

    @staticmethod
    def _reorder_action_views(action, first_view_names):
        existing_views = [
            view
            for view in action["view_mode"].split(",")
            if view not in first_view_names
        ]
        action["view_mode"] = ",".join(first_view_names + existing_views)
        for view_type in reversed(first_view_names):
            to_insert = (False, view_type)
            try:
                existing_view_id = next(
                    index
                    for index, view_tuple in enumerate(action["views"])
                    if view_tuple[1] == view_type
                )
                to_insert = action["views"].pop(existing_view_id)
            except StopIteration:
                pass
            action["views"].insert(0, to_insert)
        return action

    @api.model
    def _get_calendars_already_setup(self):
        return []

    @api.model
    def _get_calendars_possible_to_setup(self):
        return []

    def _get_main_phone_question(self):
        self.check_singleton()
        return next(
            (
                q
                for q in self.question_ids
                if q.question_type == "char_box" and q.char_box_type == "phone"
            ),
            self.env["survey.question"],
        )

    def _get_placeholder_filename(self, field):
        return "calendar/static/src/booking/img/appointment_cover_0.jpg"

    @api.model
    def _get_default_slots(self, category) -> list:
        range_values = self._get_default_range_slots(category)
        return [
            Command.create(
                {
                    "weekday": str(weekday),
                    "start_hour": start_hour,
                    "end_hour": end_hour,
                }
            )
            for weekday in range(*range_values["weekday_range"])
            for (start_hour, end_hour) in range_values["hours_range"]
        ]

    def _get_default_range_slots(self, category):
        if category not in ["punctual", "recurring", "anytime"]:
            raise ValueError(
                f"Default slots cannot be applied to the {category} appointment type category."
            )
        if category in ["punctual", "recurring"]:
            weekday_range = (1, 6)
            hours_range = ((9, 12), (14, 17))
        else:
            weekday_range = (1, 8)
            hours_range = ((7, 19),)
        return {
            "weekday_range": weekday_range,
            "hours_range": hours_range,
        }

    def _get_default_appointment_status(self, start_dt, stop_dt, capacity_reserved):
        self.check_singleton()
        default_state = "booked"
        if not self.is_always_confirm:
            if not self.auto_confirm:
                default_state = "request"
            else:
                bookings_data = (
                    self.env["appointment.booking.line"]
                    .sudo()
                    ._read_group(
                        [
                            ("appointment_type_id", "=", self.id),
                            ("event_start", "<", stop_dt),
                            ("event_stop", ">", start_dt),
                        ],
                        [],
                        ["capacity_used:sum"],
                    )
                )
                capacity_already_used = bookings_data[0][0]

                if self.manage_capacity:
                    total_capacity = (
                        self.resource_total_capacity
                        if self.schedule_based_on == "resources"
                        else len(self.staff_user_ids) * self.user_capacity
                    )
                else:
                    total_capacity = (
                        len(self.resource_ids) * self.max_bookings
                        if self.schedule_based_on == "resources"
                        else len(self.staff_user_ids) * self.max_bookings
                    )

                total_capacity_used = capacity_already_used + capacity_reserved
                if not total_capacity or (
                    float_compare(
                        total_capacity_used / total_capacity,
                        self.manual_confirmation_percentage,
                        2,
                    )
                    > 0
                ):
                    default_state = "request"
        return default_state

    def _slots_generate(self, first_day, last_day, timezone, reference_date=None):
        if not reference_date:
            reference_date = datetime.now(UTC)
        appt_tz = get_timezone(self.appointment_tz)
        requested_tz = get_timezone(timezone)
        end_tz_apt_type = (
            _utc_to_tz(self.end_datetime, appt_tz)
            if self.category == "punctual"
            else False
        )
        ref_tz_apt_type = (
            reference_date.replace(tzinfo=UTC)
            if reference_date.tzinfo is None
            else reference_date
        ).astimezone(appt_tz)
        now_tz_apt_type = datetime.now(UTC).astimezone(appt_tz)
        slots = []

        ref_start = ref_tz_apt_type
        if ref_start <= (
            now_tz_apt_type + relativedelta(hours=self.min_schedule_hours)
        ):
            ref_start += relativedelta(hours=self.min_schedule_hours)

        def add_slot(day, slot):
            local_start = datetime.combine(
                day,
                time(
                    hour=int(slot.start_hour), minute=round((slot.start_hour % 1) * 60)
                ),
            ).replace(tzinfo=appt_tz)
            while local_start < ref_start:
                local_start += relativedelta(hours=self.slot_creation_interval)
            local_end = local_start + relativedelta(hours=self.appointment_duration)
            local_slot_end = (
                day.replace(hour=0, minute=0, second=0)
                + timedelta(hours=slot._convert_end_hour_24_format())
            ).replace(tzinfo=appt_tz)
            if (
                end_tz_apt_type
                and local_start.date() == end_tz_apt_type.date()
                and local_slot_end > end_tz_apt_type
            ):
                local_slot_end = end_tz_apt_type

            while (
                local_start + relativedelta(hours=self.appointment_duration)
                <= local_slot_end
            ):
                slots.append(
                    {
                        self.appointment_tz: (
                            local_start,
                            local_end,
                        ),
                        timezone: (
                            local_start.astimezone(requested_tz),
                            local_end.astimezone(requested_tz),
                        ),
                        "UTC": (
                            local_start.astimezone(UTC).replace(tzinfo=None),
                            local_end.astimezone(UTC).replace(tzinfo=None),
                        ),
                        "slot": slot,
                    }
                )
                local_start += relativedelta(hours=self.slot_creation_interval)
                local_end = local_start + relativedelta(hours=self.appointment_duration)

        if self.category != "custom":
            if (
                last_day < ref_tz_apt_type.astimezone(UTC)
                or self.slot_creation_interval <= 0
            ):
                return slots

            slot_weekday = [
                int(weekday) - 1 for weekday in self.slot_ids.mapped("weekday")
            ]
            slots_by_isoweekday = self.slot_ids.grouped(lambda x: int(x.weekday))
            for day in rrule.rrule(
                rrule.DAILY,
                dtstart=first_day.astimezone(appt_tz).date(),
                until=last_day.astimezone(appt_tz).date(),
                byweekday=slot_weekday,
            ):
                for slot in slots_by_isoweekday.get(
                    day.isoweekday(), self.slot_ids.browse()
                ):
                    add_slot(day, slot)
        else:
            unique_slots = self.slot_ids.filtered(
                lambda slot: (
                    slot.slot_type == "unique"
                    and _utc_to_tz(slot.start_datetime, appt_tz) > ref_start
                )
            )

            for slot in unique_slots:
                start = slot.start_datetime.replace(tzinfo=UTC)
                end = slot.end_datetime.replace(tzinfo=UTC)
                startUTC = start.astimezone(UTC).replace(tzinfo=None)
                endUTC = end.astimezone(UTC).replace(tzinfo=None)
                slots.append(
                    {
                        self.appointment_tz: (
                            start.astimezone(appt_tz),
                            end.astimezone(appt_tz),
                        ),
                        timezone: (
                            start.astimezone(requested_tz),
                            end.astimezone(requested_tz),
                        ),
                        "UTC": (
                            startUTC,
                            endUTC,
                        ),
                        "slot": slot,
                    }
                )
        return slots

    def _get_appointment_slots(
        self,
        timezone,
        filter_users=None,
        filter_resources=None,
        asked_capacity=1,
        reference_date=None,
    ):
        self.check_singleton()

        if not self.active:
            return []
        now = fields.Datetime.now()
        if not reference_date:
            reference_date = now

        try:
            requested_tz = get_timezone(timezone)
        except ZoneInfoNotFoundError:
            requested_tz = get_timezone(self.appointment_tz)

        appointment_duration_days = self.max_schedule_days
        unique_slots = self.slot_ids.filtered(lambda slot: slot.slot_type == "unique")

        if self.category == "custom" and unique_slots:
            start_first_slot = unique_slots[0].start_datetime
            first_day = _utc_to_tz(max(reference_date, start_first_slot), requested_tz)
            last_day = _utc_to_tz(
                max(unique_slots.mapped("end_datetime")), requested_tz
            )
        elif self.category == "punctual":
            first_day = _utc_to_tz(max(now, self.start_datetime), requested_tz)
            last_day = _utc_to_tz(self.end_datetime, requested_tz)
        else:
            first_day = _utc_to_tz(
                reference_date + relativedelta(hours=self.min_schedule_hours),
                requested_tz,
            )
            last_day = _utc_to_tz(
                reference_date + relativedelta(days=appointment_duration_days),
                requested_tz,
            )

        slots = self._slots_generate(
            first_day.astimezone(UTC),
            last_day.astimezone(UTC),
            timezone,
            reference_date=reference_date,
        )

        if not slots:
            return slots
        valid_users = (
            filter_users.filtered(lambda user: user in self.staff_user_ids)
            if filter_users
            else None
        )
        valid_resources = (
            filter_resources.filtered(lambda resource: resource in self.resource_ids)
            if filter_resources
            else None
        )
        if filter_users and not valid_users:
            return []
        if filter_resources and not valid_resources:
            return []
        last_day_end_of_day = datetime.combine(
            last_day.astimezone(get_timezone(self.appointment_tz)) + timedelta(days=1),
            time.min,
        ).replace(tzinfo=get_timezone(self.appointment_tz))
        if self.schedule_based_on == "users":
            self._slots_add_users_availability(
                slots,
                first_day.astimezone(UTC),
                last_day_end_of_day.astimezone(UTC),
                valid_users,
                asked_capacity,
            )
            slot_field_label = (
                "available_staff_users"
                if not self.is_auto_assign and self.is_date_first
                else "staff_user_id"
            )
        else:
            self._slots_add_resources_availability(
                slots,
                first_day.astimezone(UTC),
                last_day_end_of_day.astimezone(UTC),
                valid_resources,
                asked_capacity,
            )
            slot_field_label = "available_resource_ids"

        total_nb_slots = sum(slot_field_label in slot for slot in slots)
        if not total_nb_slots and asked_capacity == 1:
            return []

        today = _utc_to_tz(reference_date, requested_tz)
        start = slots[0][timezone][0] if slots else today
        locale = babel_locale_parse(get_lang(self.env).code)
        month_dates_calendar = cal.Calendar(locale.first_week_day).monthdatescalendar
        months = []
        while (start.year, start.month) <= (last_day.year, last_day.month):
            has_availabilities = False
            dates = month_dates_calendar(start.year, start.month)
            for week_index, week in enumerate(dates):
                for day_index, day in enumerate(week):
                    mute_cls = weekend_cls = today_cls = None
                    today_slots = []
                    if day.weekday() in (locale.weekend_start, locale.weekend_end):
                        weekend_cls = "o_weekend bg-light"
                    if day == today.date() and day.month == today.month:
                        today_cls = "o_today"
                    if day.month != start.month:
                        mute_cls = "d-none"
                    else:
                        tz = (
                            self.appointment_tz
                            if slots and slots[0]["slot"].allday
                            else timezone
                        )
                        while slots and (slots[0][tz][0].date() <= day):
                            is_allday = slots[0]["slot"].allday
                            tz = self.appointment_tz if is_allday else timezone
                            if (slots[0][tz][0].date() == day) and (
                                slot_field_label in slots[0]
                            ):
                                slot_start_dt_tz, slot_end_dt_tz = slots[0][tz]
                                slot_start_dt_tz_formatted = slot_start_dt_tz.strftime(
                                    "%Y-%m-%d %H:%M:%S"
                                )
                                slot_duration = slots[0]["slot"].duration or str(
                                    (slot_end_dt_tz - slot_start_dt_tz).total_seconds()
                                    / 3600
                                )
                                is_multi_day = (
                                    (
                                        slot_start_dt_tz.date()
                                        != (
                                            slot_end_dt_tz - timedelta(seconds=1)
                                        ).date()
                                    )
                                    if not is_allday
                                    else slot_duration > 24
                                )
                                slot = {
                                    "available_resources": [
                                        {
                                            "id": resource.id,
                                            "name": resource.name,
                                            "capacity": resource.capacity,
                                        }
                                        for resource in slots[0][
                                            "available_resource_ids"
                                        ]
                                    ]
                                    if self.schedule_based_on == "resources"
                                    else False,
                                    "datetime": slot_start_dt_tz_formatted,
                                }
                                if (
                                    self.schedule_based_on == "users"
                                    and not self.is_auto_assign
                                    and self.is_date_first
                                ):
                                    slot.update(
                                        {
                                            "available_staff_users": [
                                                {
                                                    "id": staff.id,
                                                    "name": staff.name,
                                                }
                                                for staff in slots[0][
                                                    "available_staff_users"
                                                ]
                                            ]
                                        }
                                    )
                                elif self.schedule_based_on == "users":
                                    slot.update(
                                        {"staff_user_id": slots[0]["staff_user_id"].id}
                                    )

                                start_date = format_datetime(
                                    slot_start_dt_tz, format="EEE d", locale=locale
                                )
                                end_date = format_datetime(
                                    slot_end_dt_tz, format="EEE d", locale=locale
                                )
                                start_hour = format_time(
                                    slot_start_dt_tz.time(),
                                    format="short",
                                    locale=locale,
                                )
                                end_hour = format_time(
                                    slot_end_dt_tz.time(), format="short", locale=locale
                                )
                                if is_multi_day:
                                    slot_start_formatted = start_date
                                    slot_end_formatted = end_date
                                    if not is_allday:
                                        slot_start_formatted = (
                                            f"{slot_start_formatted} - {start_hour}"
                                        )
                                        slot_end_formatted = (
                                            f"{slot_end_formatted} - {end_hour}"
                                        )
                                elif is_allday:
                                    slot_start_formatted = self.env._("All day")
                                    slot_end_formatted = False
                                else:
                                    slot_start_formatted = start_hour
                                    slot_end_formatted = (
                                        end_hour if self.category == "custom" else False
                                    )
                                slot.update(
                                    {
                                        "end_hour": slot_end_formatted,
                                        "is_long_duration": is_multi_day or is_allday,
                                        "slot_duration": slot_duration,
                                        "start_hour": slot_start_formatted,
                                    }
                                )

                                url_parameters = {
                                    "allday": int(is_allday),
                                    "date_time": slot_start_dt_tz_formatted,
                                    "duration": slot_duration,
                                }
                                if self.schedule_based_on == "users" and not (
                                    self.is_date_first and not self.is_auto_assign
                                ):
                                    url_parameters.update(
                                        staff_user_id=str(slots[0]["staff_user_id"].id)
                                    )
                                elif self.schedule_based_on == "resources":
                                    url_parameters.update(
                                        available_resource_ids=str(
                                            slots[0]["available_resource_ids"].ids
                                        )
                                    )
                                slot["url_parameters"] = url_encode(url_parameters)
                                today_slots.append(slot)
                            slots.pop(0)
                    today_slots = sorted(
                        today_slots,
                        key=lambda d: (not d["is_long_duration"], d["datetime"]),
                    )
                    dates[week_index][day_index] = {
                        "day": day,
                        "slots": today_slots,
                        "mute_cls": mute_cls,
                        "weekend_cls": weekend_cls,
                        "today_cls": today_cls,
                    }

                    has_availabilities = has_availabilities or bool(today_slots)

            months.append(
                {
                    "id": len(months),
                    "month": format_datetime(
                        start, "LLLL Y", locale=get_lang(self.env).code
                    ),
                    "weeks": dates,
                    "has_availabilities": has_availabilities,
                }
            )
            start += relativedelta(months=1)
        return months

    def _check_appointment_is_valid_slot(
        self,
        staff_user,
        resources,
        asked_capacity,
        timezone,
        start_dt,
        duration,
        allday,
    ) -> bool:
        self_sudo = self.sudo()
        end_dt = start_dt + relativedelta(hours=duration)
        if allday:
            end_dt -= relativedelta(days=1)
        slots = self_sudo._slots_generate(start_dt, end_dt, timezone)
        slots = [
            slot
            for slot in slots
            if slot["UTC"]
            == (start_dt.replace(tzinfo=None), end_dt.replace(tzinfo=None))
        ]
        if (
            slots
            and self_sudo.schedule_based_on == "users"
            and (not staff_user or staff_user in self_sudo.staff_user_ids)
        ):
            self_sudo._slots_add_users_availability(
                slots, start_dt, end_dt, staff_user, asked_capacity=asked_capacity
            )
        elif (
            slots
            and self_sudo.schedule_based_on == "resources"
            and (not resources or all(r in self_sudo.resource_ids for r in resources))
        ):
            self_sudo._slots_add_resources_availability(
                slots,
                start_dt,
                end_dt,
                filter_resources=resources,
                asked_capacity=asked_capacity,
            )
        for slot in slots:
            if (
                staff_user
                and not (self_sudo.is_date_first and not self_sudo.is_auto_assign)
                and slot.get("staff_user_id", False) != staff_user
            ):
                continue
            if (
                staff_user
                and self_sudo.is_date_first
                and not self_sudo.is_auto_assign
                and staff_user
                not in slot.get("available_staff_users", self.env["res.users"])
            ):
                continue
            if resources and any(
                resource not in slot.get("available_resource_ids", [])
                for resource in resources
            ):
                continue
            if (
                slot["slot"].slot_type == "recurring"
                and float_compare(self_sudo.appointment_duration, duration, 2) != 0
            ):
                continue
            if slot["slot"].slot_type == "unique" and slot["slot"].duration != round(
                duration, 2
            ):
                continue
            return True
        return False

    @api.model
    def _prepare_clean_appointment_context(self) -> dict:
        whitelist_default_fields = [
            f"default_{field}"
            for field in self._get_calendar_view_appointment_type_default_context_fields_whitelist()
        ]
        return {
            key: value
            for key, value in self.env.context.items()
            if key in whitelist_default_fields or not key.startswith("default_")
        }

    @api.model
    def _get_calendar_view_appointment_type_default_context_fields_whitelist(self):
        return []

    def _prepare_calendar_event_values(
        self,
        asked_capacity,
        booking_line_values,
        description,
        duration,
        allday,
        appointment_invite,
        guests,
        name,
        customer,
        staff_user,
        start,
        stop,
    ):
        self.check_singleton()
        partners = (staff_user.partner_id | customer) if staff_user else customer
        guests = guests or self.env["res.partner"]
        appointment_status = self._get_default_appointment_status(
            start, stop, asked_capacity
        )
        attendee_values = [
            Command.create({"partner_id": pid, "state": "accepted"})
            for pid in partners.ids
        ] + [
            Command.create({"partner_id": guest.id})
            for guest in guests - partners
            if guest
        ]
        if allday:
            stop -= relativedelta(days=1)
            start = start.astimezone(get_timezone(self.appointment_tz)).replace(
                tzinfo=None
            )
            stop = stop.astimezone(get_timezone(self.appointment_tz)).replace(
                tzinfo=None
            )
        return {
            "alarm_ids": [Command.set(self.reminder_ids.ids)],
            "allday": allday,
            "appointment_booker_id": customer.id,
            "appointment_invite_id": appointment_invite.id,
            "appointment_status": appointment_status,
            "appointment_type_id": self.id,
            "attendee_ids": attendee_values,
            "booking_line_ids": [Command.create(vals) for vals in booking_line_values],
            "description": description,
            "duration": duration,
            "location": self.location,
            "name": self.env._(
                "%(attendee_name)s - %(appointment_name)s Booking",
                attendee_name=name,
                appointment_name=self.name,
            ),
            "partner_ids": [Command.link(pid) for pid in (partners | guests).ids],
            "start": fields.Datetime.to_string(start),
            "start_date": fields.Datetime.to_string(start),
            "stop": fields.Datetime.to_string(stop),
            "stop_date": fields.Datetime.to_string(stop),
            "user_id": staff_user.id
            if self.schedule_based_on == "users"
            else self.create_uid.id,
        }

    def _slots_add_users_availability(
        self, slots, start_dt, end_dt, filter_users=None, asked_capacity=1
    ) -> None:
        available_users = [
            user.with_context(tz=user.tz)
            for user in (filter_users or self.staff_user_ids)
        ]
        random.shuffle(available_users)
        available_users_tz = self.env["res.users"].concat(*available_users)

        availability_values = self._slot_availability_prepare_users_values(
            available_users_tz, start_dt, end_dt
        )

        self.slot_ids.mapped("restrict_to_user_ids")
        for slot in slots:
            if (self.is_date_first and not self.is_auto_assign) or self.env.context.get(
                "slots_check_all_users", False
            ):
                available_staff_users = self._get_available_staff_users(
                    slot, available_users_tz, availability_values, asked_capacity
                )
            else:
                available_staff_users = next(
                    (
                        staff_user
                        for staff_user in available_users_tz
                        if self._slot_availability_is_user_available(
                            slot,
                            staff_user,
                            availability_values,
                            asked_capacity,
                        )
                    ),
                    False,
                )
            if available_staff_users:
                if (
                    self.is_date_first and not self.is_auto_assign
                ) or self.env.context.get("slots_check_all_users", False):
                    slot["available_staff_users"] = available_staff_users
                else:
                    slot["staff_user_id"] = available_staff_users

    def _get_available_staff_users(
        self, slot, staff_users, availability_values, asked_capacity
    ):
        return staff_users.filtered(
            lambda staff_user: self._slot_availability_is_user_available(
                slot, staff_user, availability_values, asked_capacity
            )
        )

    def _slot_availability_is_user_available(
        self, slot, staff_user, availability_values, asked_capacity=1
    ):
        slot_start_dt_utc, slot_end_dt_utc = slot["UTC"][0], slot["UTC"][1]

        if (
            slot["slot"].restrict_to_user_ids
            and staff_user not in slot["slot"].restrict_to_user_ids
        ):
            return False

        if slot["slot"].allday:
            slot_end_dt_utc += relativedelta(days=1)

        users_remaining_capacity = self._get_users_remaining_capacity(
            staff_user,
            slot["UTC"][0],
            slot["UTC"][1],
            users_to_bookings=availability_values.get("users_to_bookings"),
            booking_loads=availability_values.get("booking_loads"),
            user_resources=availability_values.get("user_resources"),
        )
        if users_remaining_capacity["total_remaining_capacity"] < asked_capacity:
            return False
        intervals = availability_values.get("partner_to_intervals", {}).get(
            staff_user.partner_id.id, ()
        )
        for event_start, event_stop, event in intervals:
            if event_start < slot_end_dt_utc and event_stop > slot_start_dt_utc:
                if not event.allday and self == event.appointment_type_id:
                    continue
                return False
        return True

    def _get_booking_loads(self, resources, start, stop):
        ignored = self.env.context.get("ignore_event_ids", [])
        domain = (
            ~(
                Domain("res_model", "=", "calendar.event")
                & Domain("res_id", "in", ignored)
            )
            if ignored
            else Domain.TRUE
        )
        return self.env["resource.reservation"]._get_booking_load_batch(
            resources,
            start,
            stop,
            domain=domain,
        )

    def _get_users_remaining_capacity(
        self,
        users,
        slot_start_utc,
        slot_stop_utc,
        users_to_bookings=None,
        filter_users=None,
        booking_loads=None,
        user_resources=None,
    ):
        self.check_singleton()

        all_users = users & self.staff_user_ids
        if filter_users:
            all_users &= filter_users
        if not all_users:
            return dict.fromkeys(users, 0) | {"total_remaining_capacity": 0}

        if user_resources is None:
            user_resources = all_users._get_calendar_event_resources()
        unlinked_users = all_users.filtered(lambda user: not user_resources[user])
        booking_lines = self.env["appointment.booking.line"].sudo()
        if users_to_bookings is None and unlinked_users:
            booking_lines = (
                self.env["appointment.booking.line"]
                .sudo()
                .search(
                    [
                        ("appointment_user_id", "in", unlinked_users.ids),
                        ("appointment_type_id.schedule_based_on", "=", "users"),
                        ("event_start", "<", slot_stop_utc),
                        ("event_stop", ">", slot_start_utc),
                    ]
                )
            )
        elif users_to_bookings:
            for user, booking_line_ids in users_to_bookings.items():
                if user in all_users:
                    booking_lines |= booking_line_ids
            booking_lines = booking_lines.filtered(
                lambda bl: (
                    bl.event_start < slot_stop_utc and bl.event_stop > slot_start_utc
                )
            )

        users_booking_lines = booking_lines.grouped("appointment_user_id")

        users_remaining_capacity = {}
        max_capacity = self.user_capacity if self.manage_capacity else self.max_bookings
        for user in all_users:
            users_remaining_capacity[user] = max(
                0,
                max_capacity
                - peak_capacity(
                    (
                        (line.event_start, line.event_stop, line.capacity_used)
                        for line in users_booking_lines.get(user, [])
                    ),
                    slot_start_utc,
                    slot_stop_utc,
                ),
            )

        physical_resources = self.env["resource.resource"].concat(
            *user_resources.values()
        )
        loads = (
            booking_loads
            if booking_loads is not None
            else self._get_booking_loads(
                physical_resources,
                slot_start_utc,
                slot_stop_utc,
            )
        )
        for user in all_users:
            resource = user_resources[user]
            if resource:
                peak = peak_capacity(loads[resource.id], slot_start_utc, slot_stop_utc)
                users_remaining_capacity[user] = max(
                    0,
                    floor(
                        max_capacity * (resource.booking_limit_percentage - peak) / 100
                        + 1e-7
                    ),
                )

        users_remaining_capacity.update(
            total_remaining_capacity=sum(users_remaining_capacity.values())
        )
        return users_remaining_capacity

    def _slot_availability_prepare_users_values_bookings(
        self, users, start_dt_utc, end_dt_utc
    ) -> dict:

        users_to_bookings = {}
        if users:
            booking_lines = (
                self.env["appointment.booking.line"]
                .sudo()
                .search(
                    [
                        ("appointment_user_id", "in", users.ids),
                        ("appointment_type_id.schedule_based_on", "=", "users"),
                        ("event_stop", ">", datetime.combine(start_dt_utc, time.min)),
                        ("event_start", "<", datetime.combine(end_dt_utc, time.max)),
                    ]
                )
            )

            users_to_bookings = booking_lines.grouped("appointment_user_id")
        return {
            "users_to_bookings": users_to_bookings,
        }

    def _slot_availability_prepare_users_values(self, staff_users, start_dt, end_dt):

        user_resources = staff_users._get_calendar_event_resources()
        users_values = self._slot_availability_prepare_users_values_meetings(
            staff_users, start_dt, end_dt, user_resources=user_resources
        )
        users_values.update(
            self._slot_availability_prepare_users_values_bookings(
                staff_users.filtered(lambda user: not user_resources[user]),
                start_dt,
                end_dt,
            )
        )
        physical_resources = self.env["resource.resource"].concat(
            *user_resources.values()
        )
        users_values["user_resources"] = user_resources
        users_values["booking_loads"] = self._get_booking_loads(
            physical_resources,
            start_dt.astimezone(UTC).replace(tzinfo=None),
            end_dt.astimezone(UTC).replace(tzinfo=None),
        )
        return users_values

    def _slot_availability_prepare_users_values_meetings(
        self, staff_users, start_dt, end_dt, *, user_resources=None
    ) -> dict:
        return {
            "partner_to_intervals": staff_users.partner_id.with_env(
                self.env
            )._get_busy_calendar_intervals(
                start_dt,
                end_dt,
                user_resources=user_resources,
            ),
        }

    def _slots_add_resources_availability(
        self, slots, start_dt_utc, end_dt_utc, filter_resources=None, asked_capacity=1
    ) -> None:
        if self.resource_total_capacity < asked_capacity:
            return
        available_resources = [
            resource.with_context(tz=resource.tz)
            for resource in (filter_resources or self.resource_ids)
        ]
        available_resources = self.env["resource.resource"].concat(*available_resources)
        available_resources = available_resources.with_prefetch(
            available_resources.combinable_resource_ids.ids
        )

        availability_values = self._slot_availability_prepare_resources_values(
            available_resources, start_dt_utc, end_dt_utc
        )

        capacity_info_to_best_resources = {}
        for slot in slots:
            capacity_info = {}
            for resource in available_resources:
                if not self._slot_availability_is_resource_available(
                    slot, resource, availability_values
                ):
                    continue
                resources_remaining_capacity = self._get_resources_remaining_capacity(
                    resource,
                    slot["UTC"][0],
                    slot["UTC"][1],
                    resource_to_bookings=availability_values.get(
                        "resource_to_bookings"
                    ),
                    filter_resources=slot["slot"].restrict_to_resource_ids
                    & available_resources
                    or available_resources,
                    with_combinable_resources=self.manage_capacity,
                    booking_loads=availability_values.get("booking_loads"),
                )
                if (
                    resources_remaining_capacity["total_remaining_capacity"]
                    < asked_capacity
                ):
                    continue
                capacity_info[resource] = {
                    "total_remaining_capacity": resources_remaining_capacity[
                        "total_remaining_capacity"
                    ],
                    "remaining_capacity": resources_remaining_capacity[resource],
                }
                del resources_remaining_capacity["total_remaining_capacity"]
                del resources_remaining_capacity[resource]
                for (
                    combinable_resource,
                    remaining_capacity,
                ) in resources_remaining_capacity.items():
                    if not remaining_capacity or combinable_resource in capacity_info:
                        continue
                    capacity_info[combinable_resource] = {
                        "total_remaining_capacity": remaining_capacity,
                        "remaining_capacity": remaining_capacity,
                    }
            capacity_info = frozendict(capacity_info)
            if capacity_info:
                if not capacity_info_to_best_resources.get(capacity_info):
                    best_resources_selected = (
                        self._slot_availability_select_best_resources(
                            capacity_info,
                            asked_capacity,
                        )
                    )
                    capacity_info_to_best_resources[capacity_info] = (
                        best_resources_selected
                    )
                else:
                    best_resources_selected = capacity_info_to_best_resources[
                        capacity_info
                    ]
                if best_resources_selected:
                    slot["available_resource_ids"] = best_resources_selected
        return

    def _slot_availability_is_resource_available(
        self, slot, resource, availability_values
    ):
        if (
            slot["slot"].restrict_to_resource_ids
            and resource not in slot["slot"].restrict_to_resource_ids
        ):
            return False

        slot_start_dt_utc, slot_end_dt_utc = slot["UTC"][0], slot["UTC"][1]
        resource_to_bookings = availability_values.get("resource_to_bookings")
        bookings = resource_to_bookings.get(
            resource, self.env["appointment.booking.line"]
        ).filtered(
            lambda line: (
                line.capacity_used > 0
                and line.event_start < slot_end_dt_utc
                and line.event_stop > slot_start_dt_utc
            )
        )
        if bookings and (
            (self.manage_capacity and resource.booking_exclusive)
            or any(
                line.appointment_type_id.manage_capacity
                and line.resource_id.booking_exclusive
                for line in bookings
            )
        ):
            return False

        slot_start_dt_utc_l, slot_end_dt_utc_l = (
            slot_start_dt_utc.replace(tzinfo=UTC),
            slot_end_dt_utc.replace(tzinfo=UTC),
        )
        for i_start, i_stop in availability_values.get(
            "resource_unavailabilities", {}
        ).get(resource, []):
            if i_start < slot_end_dt_utc_l and i_stop > slot_start_dt_utc_l:
                return False

        return True

    def _get_resources_remaining_capacity(
        self,
        resources,
        slot_start_utc,
        slot_stop_utc,
        resource_to_bookings=None,
        with_combinable_resources=True,
        filter_resources=None,
        booking_loads=None,
    ):
        self.check_singleton()

        all_resources = (
            (resources | resources.combinable_resource_ids)
            if with_combinable_resources
            else resources
        ) & self.resource_ids
        if filter_resources:
            all_resources &= filter_resources
        if not all_resources:
            return dict.fromkeys(resources, 0) | {"total_remaining_capacity": 0}

        loads = (
            booking_loads
            if booking_loads is not None
            else self._get_booking_loads(
                all_resources,
                slot_start_utc,
                slot_stop_utc,
            )
        )
        resources_remaining_capacity = {}
        for resource in all_resources:
            peak = peak_capacity(loads[resource.id], slot_start_utc, slot_stop_utc)
            units = resource.capacity if self.manage_capacity else self.max_bookings
            remaining = max(
                0,
                floor(units * (resource.booking_limit_percentage - peak) / 100 + 1e-7),
            )
            resources_remaining_capacity[resource] = remaining
        resources_remaining_capacity["total_remaining_capacity"] = sum(
            resources_remaining_capacity.values()
        )
        return resources_remaining_capacity

    def _slot_availability_select_best_resources(self, capacity_info, asked_capacity):
        self.check_singleton()
        available_resources = (
            self.env["resource.resource"]
            .concat(*capacity_info.keys())
            .sorted("booking_sequence")
        )
        if not available_resources:
            return self.env["resource.resource"]
        if not self.manage_capacity:
            return (
                available_resources[0]
                if not (self.is_date_first and not self.is_auto_assign)
                else available_resources
            )

        perfect_matches = available_resources.filtered(
            lambda resource: (
                resource.capacity == asked_capacity
                and capacity_info[resource]["remaining_capacity"] == asked_capacity
            )
        )
        if perfect_matches:
            return (
                available_resources
                if self.is_date_first and not self.is_auto_assign
                else perfect_matches[0]
            )

        first_resource_selected = available_resources[0]
        first_resource_selected_capacity_info = capacity_info.get(
            first_resource_selected
        )
        first_resource_selected_capacity = first_resource_selected_capacity_info[
            "remaining_capacity"
        ]
        capacity_needed = asked_capacity - first_resource_selected_capacity
        if capacity_needed > 0:
            resource_possible_combinations = (
                available_resources._get_filtered_possible_capacity_combinations(
                    asked_capacity,
                    capacity_info,
                )
            )
            if not resource_possible_combinations:
                return self.env["resource.resource"]
            if (
                asked_capacity
                <= first_resource_selected_capacity_info["total_remaining_capacity"]
                - first_resource_selected_capacity
            ):
                r_ids = (
                    first_resource_selected.ids
                    + first_resource_selected.combinable_resource_ids.ids
                )
                resource_possible_combinations = list(
                    filter(
                        lambda cap: any(r_id in r_ids for r_id in cap[0]),
                        resource_possible_combinations,
                    )
                )
            resources_combinations_exact_capacity = list(
                filter(
                    lambda cap: cap[1] == asked_capacity, resource_possible_combinations
                )
            )
            resources_combination_selected = (
                resources_combinations_exact_capacity[0]
                if resources_combinations_exact_capacity
                else resource_possible_combinations[0]
            )
            return available_resources.filtered(
                lambda resource: resource.id in resources_combination_selected[0]
            )

        if self.is_date_first and not self.is_auto_assign:
            return available_resources

        return first_resource_selected

    def _slot_availability_prepare_resources_values(
        self, resources, start_dt_utc, end_dt_utc
    ):
        resources_values = self._slot_availability_prepare_resources_bookings_values(
            resources, start_dt_utc, end_dt_utc
        )
        resources_values.update(
            self._slot_availability_prepare_resources_leave_values(
                resources, start_dt_utc, end_dt_utc
            )
        )
        resources_values["booking_loads"] = self._get_booking_loads(
            resources | resources.combinable_resource_ids,
            start_dt_utc.astimezone(UTC).replace(tzinfo=None),
            end_dt_utc.astimezone(UTC).replace(tzinfo=None),
        )
        return resources_values

    def _slot_availability_prepare_resources_bookings_values(
        self, resources, start_dt_utc, end_dt_utc
    ) -> dict:

        resource_to_bookings = {}
        if resources:
            domain = Domain(
                [
                    ("resource_id", "in", resources.ids),
                    ("event_stop", ">", datetime.combine(start_dt_utc, time.min)),
                    ("event_start", "<", datetime.combine(end_dt_utc, time.max)),
                ]
            )
            ignore_event_ids = self.env.context.get("ignore_event_ids", False)
            if ignore_event_ids:
                domain &= Domain("calendar_event_id", "not in", ignore_event_ids)
            booking_lines = self.env["appointment.booking.line"].sudo().search(domain)
            by_resource = booking_lines.grouped("resource_id")
            resource_to_bookings = {
                resource: by_resource.get(resource, booking_lines.browse())
                for resource in resources
            }

        return {
            "resource_to_bookings": resource_to_bookings,
        }

    def _slot_availability_prepare_resources_leave_values(
        self, resources, start_dt_utc, end_dt_utc
    ) -> dict:
        unavailabilities = resources.sudo()._get_unavailable_intervals(
            start_dt_utc, end_dt_utc, exclude_bookings=False
        )
        return {
            "resource_unavailabilities": {
                resource: unavailabilities.get(resource.id, [])
                for resource in resources
            }
        }

    def _get_booking_view_types(self) -> list:
        return ["calendar"]
