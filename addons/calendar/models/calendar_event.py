import itertools
import logging
import math
import re
from collections import Counter
from datetime import UTC, datetime, time, timedelta
from itertools import repeat
from typing import NamedTuple, Self
from urllib.parse import urlsplit, urlunsplit

from markupsafe import Markup

from odoo import api, fields, models
from odoo.api import ValuesType
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command, Domain
from odoo.libs.datetime import timezone
from odoo.libs.intervals import intervals_overlap
from odoo.tools import (
    format_date,
    format_time,
    html2plaintext,
    html_sanitize,
    is_html_empty,
    single_email_re,
)

from odoo.addons.base.models.mixin_recurrence_rrule import (
    BYDAY_SELECTION,
    MONTH_BY_SELECTION,
    REPEAT_TYPE_SELECTION_RRULE,
    WEEKDAY_SELECTION,
    weekday_to_field,
)
from odoo.addons.base.models.mixin_recurrence_rule import (
    REPEAT_UNIT_SELECTION,
)
from odoo.addons.base.models.res_partner import _selection_timezones
from odoo.addons.calendar.models.calendar_attendee import (
    CalendarAttendee,
    invitation_link_end,
)
from odoo.addons.calendar.models.utils import (
    generate_calendar_token,
)

_logger = logging.getLogger(__name__)

try:
    import vobject
except ImportError:
    _logger.warning(
        "`vobject` Python module not found, iCal file generation disabled. Consider installing this module if you want to generate iCal files"
    )
    vobject = None

REPEAT_UNIT_SELECTION_UI = [
    ("day", "Daily"),
    ("week", "Weekly"),
    ("month", "Monthly"),
    ("year", "Yearly"),
    ("custom", "Custom"),
]


def get_weekday_occurence(date):
    occurence_in_month = math.ceil(date.day / 7)
    if occurence_in_month in {4, 5}:
        return -1
    return occurence_in_month


class RecurrencePolicy(NamedTuple):

    setting: str | None
    update: bool
    breaking: bool
    from_base_event: bool


def _add_ics_date(vevent, name, day) -> None:
    prop = vevent.add(name)
    prop.value = day.strftime("%Y%m%d")
    prop.value_param = "DATE"
    prop.isNative = False


class CalendarEvent(models.Model):
    _name = "calendar.event"
    _description = "Calendar Event"
    _order = "start desc"
    _search_visibility_fields = (
        "privacy",
        "user_id",
        "partner_ids",
    )
    _inherit = [
        "mixin.mail.thread",
        "mixin.recurrence.occurrence",
        "mixin.resource.scheduling",
        "mixin.bearer.token",
    ]
    _systray_view = "calendar"

    _reservation_sync_manual = True

    DISCUSS_ROUTE = "calendar/join_videocall"

    @api.model
    def get_state_selections(self):
        return CalendarAttendee.STATE_SELECTION

    @api.model
    def default_get(self, fields):
        context = dict(self.env.context)
        if context.get("default_res_model") and not context.get("default_res_model_id"):
            context.update(
                default_res_model_id=self.env["ir.model"]._get_id(
                    context["default_res_model"]
                )
            )
        if context.get("default_res_model_id") and not context.get("default_res_model"):
            context.update(
                default_res_model=self.env["ir.model"]
                .browse(self.env.context["default_res_model_id"])
                .sudo()
                .model
            )

        defaults = super(CalendarEvent, self.with_context(context)).default_get(fields)

        if (
            "res_model_id" not in defaults
            and "res_model_id" in fields
            and context.get("active_model")
            and context["active_model"] != "calendar.event"
        ):
            defaults["res_model_id"] = self.env["ir.model"]._get_id(
                context["active_model"]
            )
            defaults["res_model"] = context.get("active_model")
        if (
            "res_id" not in defaults
            and "res_id" in fields
            and defaults.get("res_model_id")
            and context.get("active_id")
        ):
            defaults["res_id"] = context["active_id"]

        return defaults

    @api.model
    def _default_partner_ids(self):
        partners = self.env.user.partner_id
        active_id = self.env.context.get("active_id")
        if (
            self.env.context.get("active_model") == "res.partner"
            and active_id
            and active_id not in partners.ids
        ):
            partners |= self.env["res.partner"].browse(active_id)
        return partners

    @api.model
    def _default_start(self):
        now = fields.Datetime.now()
        return now + (datetime.min - now) % timedelta(minutes=30)

    @api.model
    def _default_stop(self):
        now = fields.Datetime.now()
        duration_hours = self.get_default_duration()
        start = now + (datetime.min - now) % timedelta(minutes=30)
        return start + timedelta(hours=duration_hours)

    name = fields.Char(
        string="Meeting Subject",
        required=True,
    )
    description = fields.Html(
        help="""When synchronization with an external calendar is active, this description is synchronized \
        with the one of the associated meeting in that external calendar. Any update will be propagated there \
        and vice versa."""
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Organizer",
        default=lambda self: self.env.user,
        index="btree_not_null",
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        related="user_id.partner_id",
        string="Scheduled by",
        readonly=True,
    )
    location = fields.Char(tracking=True)
    notes = fields.Html()
    videocall_location = fields.Char(
        string="Meeting URL",
        compute="_compute_videocall_location",
        store=True,
        copy=True,
    )
    access_token = fields.Char(string="Invitation Token")
    videocall_source = fields.Selection(
        selection=[("discuss", "Discuss"), ("custom", "Custom")],
        compute="_compute_videocall_source",
    )
    videocall_channel_id = fields.Many2one(
        comodel_name="discuss.channel",
        string="Discuss Channel",
        index="btree_not_null",
    )
    privacy = fields.Selection(
        selection=[
            ("public", "Public"),
            ("private", "Private"),
            ("confidential", "Only internal users"),
        ],
        help="People to whom this event will be visible.",
    )
    effective_privacy = fields.Selection(
        selection=[
            ("public", "Public"),
            ("private", "Private"),
            ("confidential", "Only internal users"),
        ],
        compute="_compute_effective_privacy",
        help="Whether the event is private, considering the user privacy",
    )
    show_as = fields.Selection(
        selection=[("free", "Available"), ("busy", "Busy")],
        string="Show as",
        default="busy",
        required=True,
        help="If the time is shown as 'busy', this event will be visible to other people with either the full \
        information or simply 'busy' written depending on its privacy. Use this option to let other people know \
        that you are unavailable during that period of time. \n If the event is shown as 'free', other users know \
        that you are available during that period of time.",
    )
    is_highlighted = fields.Boolean(
        string="Is the Event Highlighted",
        compute="_compute_is_highlighted",
    )
    is_organizer_alone = fields.Boolean(
        string="Is the Organizer Alone",
        compute="_compute_is_organizer_alone",
        help="""Check if the organizer is alone in the event, i.e. if the organizer is the only one that hasn't declined
        the event (only if the organizer is not the only attendee)""",
    )
    active = fields.Boolean(
        default=True,
        tracking=True,
        help="If the active field is set to false, it will allow you to hide the event alarm information without removing it.",
    )
    categ_ids = fields.Many2many(
        comodel_name="calendar.event.type",
        relation="meeting_category_rel",
        column1="event_id",
        column2="type_id",
        string="Tags",
    )
    start = fields.Datetime(
        default=lambda self: self._default_start(),
        index=True,
        required=True,
        tracking=True,
        help="Start date of an event, without time for full days events",
    )
    stop = fields.Datetime(
        compute="_compute_stop",
        default=lambda self: self._default_stop(),
        store=True,
        readonly=False,
        required=True,
        tracking=True,
        help="Stop date of an event, without time for full days events",
    )
    display_time = fields.Char(
        string="Event Time",
        compute="_compute_display_time",
    )
    allday = fields.Boolean(
        string="All Day",
        default=False,
    )
    start_date = fields.Date(
        compute="_compute_dates",
        inverse="_inverse_dates",
        store=True,
        tracking=True,
    )
    stop_date = fields.Date(
        string="End Date",
        compute="_compute_dates",
        inverse="_inverse_dates",
        store=True,
        tracking=True,
    )
    duration = fields.Float(
        compute="_compute_duration",
        store=True,
        readonly=False,
    )
    res_id = fields.Many2oneReference(
        model_field="res_model",
        string="Document ID",
    )
    res_model_id = fields.Many2one(
        comodel_name="ir.model",
        string="Document Model",
        ondelete="cascade",
    )
    res_model = fields.Char(
        related="res_model_id.model",
        string="Document Model Name",
        readonly=True,
    )
    res_model_name = fields.Char(related="res_model_id.name")
    activity_ids = fields.One2many(
        comodel_name="mail.activity",
        inverse_name="calendar_event_id",
        string="Activities",
    )
    attendee_ids = fields.One2many(
        comodel_name="calendar.attendee",
        inverse_name="event_id",
        string="Participant",
    )
    current_attendee = fields.Many2one(
        comodel_name="calendar.attendee",
        compute="_compute_current_attendee",
        search="_search_current_attendee",
    )
    current_status = fields.Selection(
        related="current_attendee.state",
        string="Attending?",
        readonly=False,
    )
    should_show_status = fields.Boolean(compute="_compute_should_show_status")
    partner_ids = fields.Many2many(
        comodel_name="res.partner",
        relation="calendar_event_res_partner_rel",
        string="Attendees",
        default=lambda self: self._default_partner_ids(),
        context={"active_test": False},
    )
    invalid_email_partner_ids = fields.Many2many(
        comodel_name="res.partner",
        compute="_compute_invalid_email_partner_ids",
    )
    unavailable_partner_ids = fields.Many2many(
        comodel_name="res.partner",
        string="Unavailable Attendees",
        compute="_compute_unavailable_partner_ids",
    )
    alarm_ids = fields.Many2many(
        comodel_name="calendar.alarm",
        relation="calendar_alarm_calendar_event_rel",
        string="Reminders",
        ondelete="restrict",
        help="Notifications sent to all attendees to remind of the meeting.",
    )
    recurrency = fields.Boolean(string="Recurrent")
    recurrence_id = fields.Many2one(
        comodel_name="calendar.recurrence",
        string="Recurrence Rule",
        index="btree_not_null",
    )
    follow_recurrence = fields.Boolean(
        default=False
    )
    recurrence_update = fields.Selection(
        selection=[
            ("this", "This event"),
            ("subsequent", "This and following events"),
            ("all", "All events"),
        ],
        help="Choose what to do with other events in the recurrence. Updating All Events is not allowed when dates or time is modified",
    )
    rrule = fields.Char(
        string="Recurrent Rule",
        compute="_compute_recurrence",
        readonly=False,
    )
    repeat_unit_ui = fields.Selection(
        selection=REPEAT_UNIT_SELECTION_UI,
        string="Repeat",
        compute="_compute_repeat_unit_ui",
        readonly=False,
        help="Let the event automatically repeat at that interval",
    )
    repeat_unit = fields.Selection(
        selection=REPEAT_UNIT_SELECTION,
        string="Recurrence",
        compute="_compute_recurrence",
        readonly=False,
        help="Let the event automatically repeat at that interval",
    )
    event_tz = fields.Selection(
        selection=_selection_timezones,
        string="Timezone",
        compute="_compute_recurrence",
        readonly=False,
    )
    repeat_type = fields.Selection(
        selection=REPEAT_TYPE_SELECTION_RRULE,
        string="Recurrence Termination",
        compute="_compute_recurrence",
        readonly=False,
    )
    repeat_interval = fields.Integer(
        string="Repeat On",
        compute="_compute_recurrence",
        readonly=False,
        help="Repeat every (Days/Week/Month/Year)",
    )
    repeat_number = fields.Integer(
        string="Number of Repetitions",
        compute="_compute_recurrence",
        readonly=False,
        help="Repeat x times",
    )
    mon = fields.Boolean(
        compute="_compute_recurrence",
        readonly=False,
    )
    tue = fields.Boolean(
        compute="_compute_recurrence",
        readonly=False,
    )
    wed = fields.Boolean(
        compute="_compute_recurrence",
        readonly=False,
    )
    thu = fields.Boolean(
        compute="_compute_recurrence",
        readonly=False,
    )
    fri = fields.Boolean(
        compute="_compute_recurrence",
        readonly=False,
    )
    sat = fields.Boolean(
        compute="_compute_recurrence",
        readonly=False,
    )
    sun = fields.Boolean(
        compute="_compute_recurrence",
        readonly=False,
    )
    month_by = fields.Selection(
        selection=MONTH_BY_SELECTION,
        string="Option",
        compute="_compute_recurrence",
        readonly=False,
    )
    day = fields.Integer(
        string="Date of month",
        compute="_compute_recurrence",
        readonly=False,
    )
    weekday = fields.Selection(
        selection=WEEKDAY_SELECTION,
        compute="_compute_recurrence",
        readonly=False,
    )
    byday = fields.Selection(
        selection=BYDAY_SELECTION,
        string="By day",
        compute="_compute_recurrence",
        readonly=False,
    )
    repeat_until = fields.Date(
        compute="_compute_recurrence",
        readonly=False,
    )
    display_description = fields.Boolean(compute="_compute_display_description")
    attendees_count = fields.Integer(compute="_compute_attendees_count")
    accepted_count = fields.Integer(compute="_compute_attendees_count")
    declined_count = fields.Integer(compute="_compute_attendees_count")
    tentative_count = fields.Integer(compute="_compute_attendees_count")
    awaiting_count = fields.Integer(compute="_compute_attendees_count")
    user_can_edit = fields.Boolean(compute="_compute_user_can_edit")

    @api.depends("attendee_ids")
    @api.depends_context("uid")
    def _compute_should_show_status(self) -> None:
        for event in self:
            event.should_show_status = event.current_attendee and any(
                attendee.partner_id != self.env.user.partner_id
                for attendee in event.attendee_ids
            )

    @api.depends("attendee_ids", "attendee_ids.partner_id")
    @api.depends_context("uid")
    def _compute_current_attendee(self) -> None:
        for event in self:
            current_attendee = event.attendee_ids.filtered(
                lambda attendee: attendee.partner_id == self.env.user.partner_id
            )
            event.current_attendee = current_attendee and current_attendee[0]

    def _search_current_attendee(self, operator, value) -> list:
        return [
            (
                "attendee_ids",
                "any",
                [
                    ("partner_id", "=", self.env.user.partner_id.id),
                    ("id", operator, value),
                ],
            )
        ]

    @api.depends("attendee_ids", "attendee_ids.state", "partner_ids")
    def _compute_attendees_count(self) -> None:
        for event in self:
            count_event = Counter(event.attendee_ids.mapped("state"))
            event.update(
                {
                    "accepted_count": count_event["accepted"],
                    "declined_count": count_event["declined"],
                    "tentative_count": count_event["tentative"],
                    "attendees_count": len(event.attendee_ids),
                    "awaiting_count": count_event["needsAction"],
                }
            )

    @api.depends("partner_ids")
    @api.depends_context("uid")
    def _compute_user_can_edit(self) -> None:
        for event in self:
            editor_candidates = set(event.partner_ids.user_ids + event.user_id)
            if event._origin:
                editor_candidates |= set(event._origin.partner_ids.user_ids)
            if (
                self.env.user.has_group("base.group_system")
                and event.privacy != "private"
            ):
                editor_candidates.add(self.env.user)
            event.user_can_edit = self.env.user in editor_candidates

    @api.depends("partner_ids")
    def _compute_invalid_email_partner_ids(self) -> None:
        for event in self:
            event.invalid_email_partner_ids = event.partner_ids.filtered(
                lambda a: not (a.email and single_email_re.match(a.email))
            )

    @api.depends("privacy", "user_id")
    def _compute_effective_privacy(self) -> None:
        for event in self:
            event.effective_privacy = (
                event.privacy or event.sudo().user_id.calendar_default_privacy
            )

    @api.depends_context("active_model", "active_id")
    def _compute_is_highlighted(self) -> None:
        if self.env.context.get("active_model") == "res.partner":
            partner_id = self.env.context.get("active_id")
            for event in self:
                if event.partner_ids.filtered(lambda s: s.id == partner_id):
                    event.is_highlighted = True
                else:
                    event.is_highlighted = False
        else:
            for event in self:
                event.is_highlighted = False

    @api.depends("partner_id", "attendee_ids")
    def _compute_is_organizer_alone(self) -> None:
        for event in self:
            organizer = event.attendee_ids.filtered_domain(
                [("partner_id", "=", event.partner_id.id)]
            )
            all_declined = not any(
                (event.attendee_ids - organizer).filtered(
                    lambda a: a.state != "declined"
                )
            )
            event.is_organizer_alone = len(event.attendee_ids) > 1 and all_declined

    def _compute_display_time(self) -> None:
        for meeting in self:
            meeting.display_time = self._get_display_time(
                meeting.start, meeting.stop, meeting.duration, meeting.allday
            )

    @api.depends("allday", "start", "stop")
    def _compute_dates(self) -> None:
        for meeting in self:
            if meeting.allday and meeting.start and meeting.stop:
                meeting.start_date = meeting.start.date()
                meeting.stop_date = meeting.stop.date()
            else:
                meeting.start_date = False
                meeting.stop_date = False

    @api.depends("stop", "start")
    def _compute_duration(self):
        for event in self:
            event.duration = self._get_duration(event.start, event.stop)

    @api.depends("start", "duration")
    def _compute_stop(self) -> None:
        duration_field = self._fields["duration"]
        self.env.remove_to_compute(duration_field, self)
        for event in self:
            event.stop = event.start and event.start + timedelta(
                minutes=round((event.duration or 1.0) * 60)
            )
            if event.allday:
                event.stop -= timedelta(seconds=1)

    @api.onchange("start_date", "stop_date")
    def _onchange_date(self) -> None:
        for event in self:
            if event.stop_date and event.start_date:
                event.with_context(is_calendar_event_new=True).write(
                    {
                        "start": fields.Datetime.from_string(event.start_date).replace(
                            hour=8
                        ),
                        "stop": fields.Datetime.from_string(event.stop_date).replace(
                            hour=18
                        ),
                    }
                )

    def _inverse_dates(self) -> None:
        for meeting in self:
            if meeting.allday:
                enddate = fields.Datetime.from_string(meeting.stop_date or meeting.stop)
                enddate = enddate.replace(hour=18)

                startdate = fields.Datetime.from_string(
                    meeting.start_date or meeting.start
                )
                startdate = startdate.replace(hour=8)

                if meeting.start_date and meeting.stop_date:
                    meeting.write(
                        {
                            "start": startdate.replace(tzinfo=None),
                            "stop": enddate.replace(tzinfo=None),
                        }
                    )
                else:
                    meeting.write(
                        {
                            "start_date": startdate.replace(tzinfo=None),
                            "stop_date": enddate.replace(tzinfo=None),
                        }
                    )

    @api.constrains("start", "stop", "start_date", "stop_date")
    def _check_closing_date(self) -> None:
        for meeting in self:
            if (
                not meeting.allday
                and meeting.start
                and meeting.stop
                and meeting.stop < meeting.start
            ):
                raise ValidationError(
                    self.env._(
                        "The ending date and time cannot be earlier than the starting date and time.\n"
                        "Meeting “%(name)s” starts at %(start_time)s and ends at %(end_time)s",
                        name=meeting.name,
                        start_time=meeting.start,
                        end_time=meeting.stop,
                    ),
                )
            if (
                meeting.allday
                and meeting.start_date
                and meeting.stop_date
                and meeting.stop_date < meeting.start_date
            ):
                raise ValidationError(
                    self.env._(
                        "The ending date cannot be earlier than the starting date.\n"
                        "Meeting “%(name)s” starts on %(start_date)s and ends on %(end_date)s",
                        name=meeting.name,
                        start_date=meeting.start_date,
                        end_date=meeting.stop_date,
                    ),
                )

    def _get_organizer_validation_conditions(self, vals_list):
        return [True] * len(vals_list)

    @api.depends("recurrence_id", "recurrency")
    def _compute_repeat_unit_ui(self) -> None:
        defaults = self.env["calendar.recurrence"].default_get(
            ["repeat_interval", "repeat_unit"]
        )
        for event in self:
            if event.recurrency:
                if event.recurrence_id:
                    event.repeat_unit_ui = (
                        "custom"
                        if event.recurrence_id.repeat_interval != 1
                        else (event.recurrence_id.repeat_unit)
                    )
                else:
                    event.repeat_unit_ui = defaults["repeat_unit"]

    @api.depends("recurrence_id", "recurrency", "repeat_unit_ui")
    def _compute_recurrence(self) -> None:
        recurrence_fields = self._get_fields_recurrent()
        false_values = dict.fromkeys(
            recurrence_fields, False
        )
        defaults = self.env["calendar.recurrence"].default_get(recurrence_fields)
        default_rrule_values = self.recurrence_id.default_get(recurrence_fields)
        for event in self:
            if event.recurrency:
                current_rrule = (
                    event.repeat_unit
                    if event.repeat_unit_ui == "custom"
                    else event.repeat_unit_ui
                )
                event.update(
                    defaults
                )
                event_values = event._get_recurrence_params()
                rrule_values = {
                    field: event.recurrence_id[field]
                    for field in recurrence_fields
                    if event.recurrence_id[field]
                }
                rrule_values = rrule_values or default_rrule_values
                rrule_values["repeat_unit"] = (
                    current_rrule
                    or rrule_values.get("repeat_unit")
                    or defaults["repeat_unit"]
                )
                event.update(
                    {**false_values, **defaults, **event_values, **rrule_values}
                )
            else:
                event.update(false_values)

    @api.depends("description")
    def _compute_display_description(self) -> None:
        for event in self:
            event.display_description = not is_html_empty(event.description)

    @api.depends(
        "partner_ids",
        "start",
        "stop",
        "allday",
        "start_date",
        "stop_date",
        "attendee_ids.state",
    )
    def _compute_unavailable_partner_ids(self) -> None:
        self.unavailable_partner_ids = False
        windows = [
            (start, stop, event, partner)
            for event in self.filtered(lambda event: event.start and event.stop)
            for partner in event.partner_ids
            for start, stop in event._get_attendee_intervals(partner)
        ]
        if not windows:
            return
        busy_events = self.partner_ids._search_busy_calendar_events(
            min(start for start, _stop, _event, _partner in windows),
            max(stop for _start, stop, _event, _partner in windows),
        )
        for start, stop, event, partner in windows:
            events_by_partner = partner._group_busy_calendar_events(
                busy_events, start, stop
            )
            if event._is_partner_unavailable(
                partner,
                events_by_partner.get(partner._origin.id, self.env["calendar.event"]),
            ):
                event.unavailable_partner_ids |= partner

    @api.depends("videocall_source", "access_token")
    def _compute_videocall_location(self) -> None:
        for event in self:
            if event.videocall_source == "discuss":
                event._set_discuss_videocall_location()

    def _is_partner_unavailable(self, partner, partner_events) -> bool:
        self.check_singleton()
        return any(
            intervals_overlap(own_interval, other_interval)
            for own_interval in self._get_attendee_intervals(partner)
            for partner_event in partner_events
            if partner_event != self
            for other_interval in partner_event._get_attendee_intervals(partner)
        )

    @api.model
    def _set_videocall_location(self, vals_list) -> None:
        for vals in vals_list:
            if not vals.get("videocall_location"):
                continue
            url = urlsplit(vals["videocall_location"])
            if url.scheme in ("http", "https"):
                continue
            base = urlsplit(self.get_base_url())
            vals["videocall_location"] = urlunsplit(
                url._replace(scheme=base.scheme, netloc=base.netloc)
            )

    def _is_video_call_required(self) -> bool:
        self.check_singleton()
        return True

    @api.depends("videocall_location")
    def _compute_videocall_source(self) -> None:
        for event in self:
            if (
                event.videocall_location
                and self.DISCUSS_ROUTE in event.videocall_location
            ):
                event.videocall_source = "discuss"
            else:
                event.videocall_source = "custom"

    def _set_discuss_videocall_location(self) -> None:
        if not self.access_token:
            self.access_token = generate_calendar_token()
        self.videocall_location = (
            f"{self.get_base_url()}/{self.DISCUSS_ROUTE}/{self.access_token}"
        )

    @api.model
    def get_discuss_videocall_location(self) -> str:
        access_token = generate_calendar_token()
        return f"{self.get_base_url()}/{self.DISCUSS_ROUTE}/{access_token}"


    _CREATE_DEFAULT_FNAMES = (
        "activity_ids",
        "allday",
        "description",
        "name",
        "partner_ids",
        "res_model_id",
        "res_id",
        "start",
        "user_id",
    )

    def _create_apply_defaults(self, vals_list, defaults) -> list:
        return [
            {
                **vals,
                "activity_ids": vals.get("activity_ids", defaults.get("activity_ids")),
                "allday": vals.get("allday", defaults.get("allday")),
                "description": vals.get("description", defaults.get("description")),
                "name": vals.get("name", defaults.get("name")),
                "res_id": vals.get("res_id") or defaults.get("res_id"),
                "res_model_id": vals.get("res_model_id", defaults.get("res_model_id")),
                "start": vals.get("start", defaults.get("start")),
                "user_id": vals.get(
                    "user_id", defaults.get("user_id", self.env.user.id)
                ),
            }
            for vals in vals_list
        ]

    def _create_prepare_stop(self, vals_list) -> None:
        pending = [
            vals for vals in vals_list if "stop" not in vals and vals.get("start")
        ]
        if not pending or "default_stop" in self.env.context:
            return
        default_duration = (
            self.env.context.get("default_duration") or self.get_default_duration()
        )
        for vals in pending:
            duration = vals.get("duration") or default_duration
            stop = fields.Datetime.to_datetime(vals["start"]) + timedelta(
                minutes=round(duration * 60)
            )
            vals["stop"] = stop - timedelta(seconds=1) if vals.get("allday") else stop

    @api.model_create_multi
    def create(self, vals_list):
        self = self.with_context(is_calendar_event_new=True)
        defaults = self.browse().default_get(list(self._CREATE_DEFAULT_FNAMES))
        vals_list = self._create_apply_defaults(vals_list, defaults)
        self._create_prepare_stop(vals_list)
        self._create_prepare_activities(vals_list)
        self._set_videocall_location(vals_list)
        vals_list = self._create_prepare_attendees(vals_list, defaults)
        if not self.env.context.get("skip_contact_description"):
            self._create_prepare_contact_description(vals_list)

        events = self._create_split_by_recurrency(vals_list)
        events._create_missing_videocall_channels()

        events.filtered(
            lambda event: event.start > fields.Datetime.now()
        ).attendee_ids._send_invitation_emails()
        self._create_sync_activities(events, vals_list)
        if not self.env.context.get("dont_notify"):
            self._create_setup_alarms(events, vals_list)
        to_sync = events._active_for_sync()
        to_sync.flush_recordset()
        to_sync._sync_reservations()
        return events.with_context(is_calendar_event_new=False)

    def _create_prepare_activities(self, vals_list) -> None:
        meeting_activity_types = self.env["mail.activity.type"].search(
            [("category", "=", "meeting")]
        )
        if not meeting_activity_types:
            return
        model_ids = list(filter(None, {values["res_model_id"] for values in vals_list}))
        all_models = self.env["ir.model"].sudo().browse(model_ids)
        excluded_models = self._get_activity_excluded_models()

        existing_event, existing_type = self.browse(), self.env["mail.activity.type"]
        orig_activity_ids = self.env["mail.activity"].browse(
            self.env.context.get("orig_activity_ids", [])
        )

        if len(orig_activity_ids) == 1:
            existing_event = orig_activity_ids.calendar_event_id
            if (
                existing_event
                and orig_activity_ids.activity_type_id.category == "meeting"
            ):
                existing_type = orig_activity_ids.activity_type_id

        model_by_id = {model.id: model for model in all_models}
        for values in vals_list:
            if values["activity_ids"] and not existing_event:
                continue
            res_model = model_by_id.get(values["res_model_id"], all_models.browse())
            res_id = values["res_id"]
            if (
                not res_model
                or not res_id
                or res_model.model in excluded_models
                or not res_model.is_mail_activity
            ):
                continue

            meeting_activity_type = self.env["mail.activity.type"]
            if existing_type and existing_type.res_model in {False, res_model.model}:
                meeting_activity_type = existing_type
            if not meeting_activity_type:
                meeting_activity_type = meeting_activity_types.filtered_domain(
                    [("res_model", "in", [False, res_model.model])]
                )
            if not meeting_activity_type:
                continue

            values["activity_ids"] = [
                Command.create(
                    self._prepare_meeting_activity_vals(
                        values, meeting_activity_type[0]
                    )
                )
            ]

    def _prepare_meeting_activity_vals(self, values, activity_type):
        activity_vals = {
            "res_model_id": values["res_model_id"],
            "res_id": values["res_id"],
            "activity_type_id": activity_type.id,
        }
        if values["description"]:
            activity_vals["note"] = values["description"]
        if values["name"]:
            activity_vals["summary"] = values["name"]
        if values["start"]:
            activity_vals["date_deadline"] = self._get_activity_deadline_from_start(
                fields.Datetime.from_string(values["start"]), values["allday"]
            )
        if values["user_id"]:
            activity_vals["user_id"] = values["user_id"]
        return activity_vals

    def _create_prepare_attendees(self, vals_list, defaults) -> list:
        default_partners_ids = defaults.get("partner_ids") or (
            [Command.link(self.env.user.partner_id.id)]
        )
        return [
            dict(
                vals,
                attendee_ids=self._attendees_values(
                    vals.get("partner_ids", default_partners_ids)
                ),
            )
            if not vals.get("attendee_ids")
            else vals
            for vals in vals_list
        ]

    def _create_prepare_contact_description(self, vals_list) -> None:
        organizer_ids, partner_ids = set(), set()
        vals_partner_list = []
        for vals in vals_list:
            if vals.get("user_id"):
                organizer_ids.add(vals["user_id"])
            partner_ids_from_attendees = {
                attendee_vals[2]["partner_id"]
                for attendee_vals in vals["attendee_ids"]
                if len(attendee_vals) > 2
                and isinstance(attendee_vals[2], dict)
                and "partner_id" in attendee_vals[2]
            }
            partner_ids.update(partner_ids_from_attendees)
            vals_partner_list.append(partner_ids_from_attendees)
        organizers = (
            self.env["res.users"].browse(organizer_ids).with_prefetch(organizer_ids)
        )
        partners = (
            self.env["res.partner"].browse(partner_ids).with_prefetch(partner_ids)
        )

        for vals, vals_partner_ids in zip(vals_list, vals_partner_list, strict=True):
            contact_description = self._get_contact_details_description(
                organizers.browse(vals.get("user_id", False)),
                partners.browse(vals_partner_ids),
            )
            if not is_html_empty(contact_description):
                base_description = (
                    f"{vals['description']}<br/>"
                    if not is_html_empty(vals.get("description"))
                    else ""
                )
                vals["description"] = (
                    f"<div>{base_description}{contact_description}</div>"
                )

    def _create_split_by_recurrency(self, vals_list):
        recurrence_fields = self._get_fields_recurrent()
        other_idx = [
            i for i, vals in enumerate(vals_list) if not vals.get("recurrency")
        ]
        recurring_idx = [
            i for i, vals in enumerate(vals_list) if vals.get("recurrency")
        ]
        other_vals = [vals_list[i] for i in other_idx]
        recurring_vals = [vals_list[i] for i in recurring_idx]

        other_events = super().create(other_vals)

        for vals in recurring_vals:
            vals["follow_recurrence"] = True
        recurring_events = super().create(recurring_vals)

        events_by_index = dict(zip(other_idx, other_events, strict=True))
        events_by_index.update(zip(recurring_idx, recurring_events, strict=True))
        events = self.browse(events_by_index[i].id for i in range(len(vals_list)))

        for event, vals in zip(recurring_events, recurring_vals, strict=True):
            recurrence_values = {
                field: vals.pop(field) for field in recurrence_fields if field in vals
            }
            if vals.get("recurrency"):
                detached_events = event.with_context(
                    skip_contact_description=True
                )._apply_recurrence_values(recurrence_values)
                detached_events.active = False

        return events

    @api.model
    def _create_sync_activities(self, events, vals_list) -> None:
        to_sync_activities = self.browse()
        for event, event_values in zip(events, vals_list, strict=True):
            if any(
                command[0] != 0 for command in event_values.get("activity_ids") or []
            ):
                to_sync_activities += event
        to_sync_activities._sync_activities(
            fields={f for vals in vals_list for f in vals}
        )

    @api.model
    def _create_setup_alarms(self, events, vals_list) -> None:
        alarm_events = self.browse()
        for event, values in zip(events, vals_list, strict=True):
            if values.get("allday"):
                continue
            alarm_events |= event
        recurring_events = alarm_events.filtered("recurrence_id")
        recurring_events.recurrence_id._schedule_next_occurrence_alarm()
        (alarm_events - recurring_events)._setup_alarms()

    def _compute_field_value(self, field, validate=True):
        if field.compute_sudo:
            return super(
                CalendarEvent, self.with_context(prefetch_fields=False)
            )._compute_field_value(field, validate=validate)
        return super()._compute_field_value(field, validate=validate)

    def _fetch_query(self, query, fields):
        if self.env.su:
            return super()._fetch_query(query, fields)

        public_fnames = self._get_fields_public()
        private_fields = [field for field in fields if field.name not in public_fnames]
        if not private_fields:
            return super()._fetch_query(query, fields)

        fields_to_fetch = list(fields) + [
            self._fields[name] for name in ("privacy", "user_id", "partner_ids")
        ]
        events = super()._fetch_query(query, fields_to_fetch)

        others_private_events = events.filtered(
            lambda ev: ev._check_private_event_conditions()
        )
        if not others_private_events:
            return events

        private_fields.append(self._fields["partner_ids"])
        for field in private_fields:
            replacement = field.convert_to_cache(
                self.env._("Busy") if field.name == "name" else False,
                others_private_events,
            )
            field._update_cache_items(
                self.env, zip(others_private_events._ids, repeat(replacement))
            )

        return events


    def _get_fields_reservation_date(self) -> tuple:
        return ("start", "stop")

    def _prepare_reservation_vals_by_record(self) -> dict:
        partner_resources = self.partner_ids._get_calendar_event_resources()
        return {
            event.id: event._prepare_reservation_vals_list(
                partner_resources=partner_resources
            )
            for event in self
        }

    def _prepare_reservation_vals_list(self, *, partner_resources=None):
        self.check_singleton()
        if not self.start or not self.stop or self.show_as != "busy":
            return []

        vals_list = []
        booked = set()
        partners = self._get_scheduled_partners()
        if partner_resources is None:
            partner_resources = partners._get_calendar_event_resources()
        for partner in partners:
            resource = partner_resources[partner]
            if not resource or resource.id in booked:
                continue
            booked.add(resource.id)
            start, stop = self._get_reservation_interval(partner.tz or resource.tz)
            vals_list.append(
                {
                    "name": self.display_name,
                    "date_start": start,
                    "date_end": stop,
                    "resource_id": resource.id,
                    "allocated_percentage": 100.0,
                    "enforcement_mode": "soft",
                }
            )
        return vals_list

    def _get_scheduled_partners(self):
        self.check_singleton()
        return (
            self.partner_ids
            - self.attendee_ids.filtered(
                lambda attendee: attendee.state == "declined"
            ).partner_id
        )

    def _get_attendee_intervals(self, partner, *, resources=None) -> list:
        self.check_singleton()
        if partner not in self._get_scheduled_partners():
            return []
        if not self.allday:
            return [self._get_reservation_interval("UTC")]
        if resources is None:
            resources = partner._get_calendar_event_resources()[partner]
        timezones = {partner.tz or resource.tz or "UTC" for resource in resources}
        return [
            self._get_reservation_interval(timezone)
            for timezone in sorted(timezones or {partner.tz or "UTC"})
        ]

    def _get_reservation_interval(self, tz) -> tuple:
        self.check_singleton()
        if not self.allday:
            return self.start, self.stop
        zone = timezone(tz or "UTC")
        start = datetime.combine(self.start_date or self.start.date(), time.min, zone)
        stop = datetime.combine(
            (self.stop_date or self.stop.date()) + timedelta(days=1), time.min, zone
        )
        return (
            start.astimezone(UTC).replace(tzinfo=None),
            stop.astimezone(UTC).replace(tzinfo=None),
        )

    def _get_fields_sync_trigger(self):
        return super()._get_fields_sync_trigger() | {
            "partner_ids",
            "name",
            "show_as",
            "allday",
            "start_date",
            "stop_date",
        }

    def _write_recurrence_policy(self, values):
        setting = values.pop("recurrence_update", None)
        if setting and not self.recurrence_id:
            setting = None
        update = bool(
            setting in ("all", "subsequent") and len(self) == 1 and self.recurrence_id
        )
        if any(fname in self._get_fields_recurrent() for fname in values) and not (
            update or values.get("recurrency")
        ):
            raise UserError(
                self.env._('Unable to save the recurrence with "This Event"')
            )
        return RecurrencePolicy(
            setting=setting,
            update=update,
            breaking=values.get("recurrency") is False,
            from_base_event=(
                setting == "subsequent" and self == self.recurrence_id.base_event_id
            ),
        )

    def _write_update_recurrence(self, values, recurrence_values, policy) -> tuple:
        if policy.breaking:
            return self, self._break_recurrence(future=policy.setting == "subsequent")
        time_values = {
            field: values.pop(field)
            for field in self._get_fields_time()
            if field in values
        }
        values.pop("access_token", None)
        if policy.setting == "all" or policy.from_base_event:
            return self._rewrite_recurrence(
                values, time_values, recurrence_values
            ), self.browse()
        return self._update_future_events(
            values, time_values, recurrence_values
        ), self.browse()

    def _write_sync_reservations(self, written_fnames) -> None:
        if not (written_fnames & (self._get_fields_sync_trigger() | {"active"})):
            return
        to_sync = self.exists()._active_for_sync()
        to_sync.flush_recordset()
        to_sync._sync_reservations()

    def write(self, vals):
        if set(vals) == {"videocall_channel_id"}:
            return super().write(vals)
        if "partner_ids" in vals and len(self) > 1:
            invited = {tuple(sorted(event.partner_ids.ids)) for event in self}
            if len(invited) > 1:
                for event in self:
                    event.write(dict(vals))
                return True

        self = self.with_context(skip_attendee_reservation_sync=True)
        written_fnames = set(vals)
        requested_start = vals.get("start")
        previous_attendees = self.attendee_ids
        previous_partners = self.partner_ids
        detached_events = self.env["calendar.event"]
        policy = self._write_recurrence_policy(vals)

        self.filtered(
            lambda ev: ev.user_id and self.env.user != ev.user_id
        )._check_calendar_privacy_write_permissions()

        self._write_prepare_values(vals)

        touches_time = self._touches_time(vals)
        update_alarms = touches_time or "alarm_ids" in vals or "partner_ids" in vals

        if (
            not policy.setting or policy.setting == "this"
        ) and "follow_recurrence" not in vals:
            if touches_time:
                vals["follow_recurrence"] = False

        recurrence_values = {
            field: vals.pop(field)
            for field in self._get_fields_recurrent()
            if field in vals
        }
        notify_from = self
        if policy.update:
            notify_from, detached = self._write_update_recurrence(
                vals, recurrence_values, policy
            )
            detached_events |= detached
        else:
            super().write(vals)
            self._sync_activities(fields=vals.keys())

        if (
            policy.setting not in ["this", "all"]
            and not policy.from_base_event
            and not policy.breaking
        ):
            detached_events |= self._apply_recurrence_values(
                recurrence_values, future=policy.setting == "subsequent"
            )

        (detached_events & self).active = False
        (detached_events - self).with_context(archive_on_error=True).unlink()

        if not self.env.context.get("dont_notify") and update_alarms:
            self._write_reschedule_alarms()
        if touches_time:
            self._write_reset_organizer_answer()
            self._write_move_invitation_links()
        notify_from._write_notify_attendees(
            written_fnames,
            requested_start,
            previous_attendees,
            previous_partners,
            policy.update,
        )

        if vals.get("active") is False:
            self.env["calendar.recurrence"].search(
                [("base_event_id", "in", self.ids)]
            )._select_new_base_event()

        self._write_sync_reservations(written_fnames)

        ensure_channels = "videocall_location" in written_fnames or touches_time
        sync_channels = "name" in written_fnames or touches_time
        if ensure_channels or sync_channels:
            written = self.exists()
            if ensure_channels:
                written._create_missing_videocall_channels()
            if sync_channels:
                written._sync_videocall_channels()

        return True

    def _write_move_invitation_links(self) -> None:
        Link = self.env["access.link"]
        notification = Domain("cause", "=", "notification")
        links = (
            Link._record_links(self.attendee_ids, notification)
            | Link._record_links(self, notification)
        ).with_privilege("base.privilege_manage_links", reason="the meeting moved")
        ends = {
            ("calendar.attendee", attendee.id): attendee._invitation_link_end()
            for attendee in self.attendee_ids
        } | {(self._name, event.id): invitation_link_end(event) for event in self}
        for link in links:
            if end := ends.get((link.res_model, link.res_id)):
                link.date_to = end

    def _write_prepare_values(self, values) -> None:
        self._set_videocall_location([values])
        if "partner_ids" in values:
            values["attendee_ids"] = self._attendees_values(values["partner_ids"])
            self._write_sync_videocall_members(values["partner_ids"])

    def _write_sync_videocall_members(self, partner_commands) -> None:
        if not self.videocall_channel_id:
            return
        new_partner_ids = []
        for command in partner_commands:
            if command[0] == Command.LINK:
                new_partner_ids.append(command[1])
            elif command[0] == Command.SET:
                new_partner_ids.extend(command[2])
        self.videocall_channel_id._add_members(
            partners=self.env["res.partner"].browse(new_partner_ids).exists()
        )

    def _write_reschedule_alarms(self) -> None:
        self.recurrence_id._schedule_next_occurrence_alarm(recurrence_update=True)
        if not self.recurrence_id:
            self._setup_alarms()

    def _write_reset_organizer_answer(self) -> None:
        moved_by_others = self.filtered(
            lambda ev: ev.user_id and ev.user_id != self.env.user
        )
        moved_by_others.attendee_ids.filtered(
            lambda att: att.partner_id == att.event_id.user_id.partner_id
        ).write({"state": "needsAction"})

    def _write_notify_attendees(
        self,
        written_fnames,
        requested_start,
        previous_attendees,
        previous_partners,
        update_recurrence,
    ) -> None:
        if self.env.context.get("skip_attendee_notification"):
            return
        current_attendees = self.filtered("active").attendee_ids
        previous_partner_ids = set(previous_partners.ids)
        previous_attendee_ids = set(previous_attendees.ids)

        def is_new(attendee) -> bool:
            return (
                attendee.id not in previous_attendee_ids
                and attendee.partner_id.id not in previous_partner_ids
            )

        if "partner_ids" in written_fnames:
            current_attendees.filtered(is_new)._notify_attendees(
                self.env.ref(
                    "calendar.calendar_template_meeting_invitation",
                    raise_if_not_found=False,
                ),
                force_send=True,
            )
        if self.env.context.get("is_calendar_event_new") or not (
            written_fnames & {"start", "stop"}
        ):
            return
        start_date = fields.Datetime.to_datetime(requested_start) or (
            self[:1].start if self else None
        )
        if start_date and start_date >= fields.Datetime.now():
            current_attendees.filtered(lambda att: not is_new(att)).with_context(
                calendar_template_ignore_recurrence=not update_recurrence
            )._notify_attendees(
                self.env.ref(
                    "calendar.calendar_template_meeting_changedate",
                    raise_if_not_found=False,
                ),
                force_send=True,
            )

    def _check_calendar_privacy_write_permissions(self) -> None:
        if not self.env.su:
            for event in self:
                if event._check_private_event_conditions():
                    raise self.env["ir.access"]._prepare_record_access_error(
                        event, "write"
                    )

    def _check_private_event_conditions(self):
        self.check_singleton()
        event_is_private = self.privacy == "private"
        calendar_is_private = (
            not self.privacy
            and self.sudo().user_id.calendar_default_privacy == "private"
        )
        user_is_not_partner = (
            self.user_id.id != self.env.uid
            and self.env.user.partner_id not in self.partner_ids
        )
        return (event_is_private or calendar_is_private) and user_is_not_partner

    @api.depends("privacy", "user_id")
    def _compute_display_name(self):
        hidden = self.filtered(lambda event: event._check_private_event_conditions())
        hidden.display_name = self.env._("Busy")
        super(CalendarEvent, self - hidden)._compute_display_name()

    def _privacy_restricted_fnames(self, fnames) -> set:
        public = self._get_fields_public()
        return {
            fname
            for fname in fnames
            if (field := self._fields.get(fname))
            and field.store
            and fname not in public
        }

    def _search(
        self,
        domain,
        offset=0,
        limit=None,
        order=None,
        *,
        active_test=True,
        bypass_access=False,
    ):
        if not (self.env.su or bypass_access):
            fnames = self._search_referenced_fnames(domain, order)
            if self._privacy_restricted_fnames(fnames):
                domain = Domain.AND([domain, self._get_domain_default_privacy()])
        return super()._search(
            domain,
            offset=offset,
            limit=limit,
            order=order,
            active_test=active_test,
            bypass_access=bypass_access,
        )

    @api.model
    def _search_referenced_fnames(self, domain, order):
        fnames = {
            condition.field_expr.split(".")[0].split(":")[0]
            for condition in Domain(domain).iter_conditions()
        }
        for spec in (order or "").split(","):
            fname = spec.strip().split(" ")[0].split(".")[0]
            if fname:
                fnames.add(fname)
        return fnames

    @api.model
    def _read_group(
        self,
        domain,
        groupby=(),
        aggregates=(),
        having=None,
        offset=0,
        limit=None,
        order=None,
    ) -> list[tuple]:
        fnames = {
            spec.split(":")[0]
            for spec in itertools.chain(
                groupby,
                aggregates,
                [cond[0] for cond in having or () if isinstance(cond, (list, tuple))],
            )
        }
        for spec in (order or "").split(","):
            fname = spec.strip().split(" ")[0].split(".")[0].split(":")[0]
            if fname:
                fnames.add(fname)
        if not self.env.su and self._privacy_restricted_fnames(fnames):
            domain = Domain.AND([domain, self._get_domain_default_privacy()])
        return super()._read_group(
            domain,
            groupby,
            aggregates,
            having=having,
            offset=offset,
            limit=limit,
            order=order,
        )

    @api.model
    def _read_grouping_sets(
        self, domain, grouping_sets, aggregates=(), order=None
    ) -> list[tuple]:
        fnames = {
            spec.split(":")[0]
            for spec in itertools.chain(
                *grouping_sets,
                aggregates,
            )
        }
        for spec in (order or "").split(","):
            fname = spec.strip().split(" ")[0].split(".")[0].split(":")[0]
            if fname:
                fnames.add(fname)
        if not self.env.su and self._privacy_restricted_fnames(fnames):
            domain = Domain.AND([domain, self._get_domain_default_privacy()])
        return super()._read_grouping_sets(
            domain, grouping_sets, aggregates, order=order
        )

    def unlink(self):
        if not self:
            return super().unlink()

        self.filtered(
            lambda ev: ev.user_id and self.env.user != ev.user_id
        )._check_calendar_privacy_write_permissions()

        events = self.filtered_domain([("alarm_ids", "!=", False)])
        partner_ids = events.mapped("partner_ids").ids

        recurrences = self.env["calendar.recurrence"].search(
            [("base_event_id", "in", [e.id for e in self])]
        )
        videocall_channels = self.videocall_channel_id

        result = super().unlink()

        if recurrences:
            recurrences._select_new_base_event()
        videocall_channels._retire_orphan_meeting_channels()

        self.env["calendar.alarm_manager"]._notify_next_alarm(partner_ids)
        return result

    def copy(self, default=None):
        default = dict(default or {})
        default.update(partner_ids=[Command.set([])], attendee_ids=[Command.set([])])
        new_events = super(
            CalendarEvent, self.with_context(skip_contact_description=True)
        ).copy(default)
        for old_event, new_event in zip(self, new_events, strict=True):
            new_event.write({"partner_ids": [(Command.set(old_event.partner_ids.ids))]})
        return new_events

    def action_unlink_event(self, recurrence=False) -> dict | None:
        if self.user_id._has_any_active_synchronization() or len(self.ids) > 1:
            self._unlink_by_recurrence_policy(recurrence)
            return {
                "type": "ir.actions.act_url",
                "target": "self",
                "url": "/odoo/calendar",
            }

        template = self.env.ref(
            "calendar.calendar_template_delete_event", raise_if_not_found=False
        )
        if not template:
            self.unlink()
            _logger.warning(
                'Template "calendar.calendar_template_delete_event" was not found. Cannot send delete notifications.'
            )
            return {}

        if self.ids and (lang := template._render_lang(self.ids)[self.id]):
            context = {
                "default_use_template": bool(template),
                "default_template_id": template.id,
                "default_calendar_event_id": self.id,
                "default_recurrence": recurrence,
                "model_description": self.with_context(lang=lang),
            }
            return {
                "name": self.env._("Delete Event"),
                "res_model": "wizard.calendar.event.delete",
                "view_id": self.env.ref("calendar.view_event_delete_wizard_form").id,
                "type": "ir.actions.act_window",
                "context": context,
                "target": "new",
                "views": [(False, "form")],
            }
        return None

    @api.model
    def _mail_operation_domains(self, message_operation):
        if message_operation != "read":
            return super()._mail_operation_domains(message_operation)
        private = Domain("privacy", "=", "private") & Domain(
            "attendee_ids",
            "not any",
            Domain("partner_id", "in", self.env.user.partner_id.ids),
        )
        return {"write": private, "read": ~private}

    def _attendees_values(self, partner_commands):
        attendee_commands = []

        current = set(self.partner_ids.ids)
        desired = set(current)
        if partner_commands and isinstance(partner_commands[0], int):
            partner_commands = [Command.set(partner_commands)]
        for command in partner_commands:
            op = command[0]
            if op in (Command.DELETE, Command.UNLINK):
                desired.discard(command[1])
            elif op == Command.SET:
                desired = set(command[2])
            elif op == Command.LINK:
                desired.add(command[1])
            elif op == Command.CLEAR:
                desired.clear()
        removed_partner_ids = sorted(current - desired)
        added_partner_ids = sorted(desired - current)

        if not self:
            attendees_to_unlink = self.env["calendar.attendee"]
        else:
            attendees_to_unlink = self.env["calendar.attendee"].search(
                [
                    ("event_id", "in", self.ids),
                    ("partner_id", "in", removed_partner_ids),
                ]
            )
        attendee_commands += [
            [2, attendee.id] for attendee in attendees_to_unlink
        ]

        attendee_commands += [
            [0, 0, {"partner_id": partner_id}] for partner_id in added_partner_ids
        ]
        return attendee_commands

    def _create_missing_videocall_channels(self) -> None:
        events = self.filtered(lambda event: event.id and event.active)
        events.flush_recordset(["videocall_location"])
        now = fields.Datetime.now()
        for event in events:
            if (
                event.videocall_channel_id
                or event.videocall_source != "discuss"
                or (event.stop and event.stop < now)
                or (event.recurrency and not event.recurrence_id)
            ):
                continue
            event._create_videocall_channel()

    def _sync_videocall_channels(self) -> None:
        for channel in self.videocall_channel_id._with_meeting_channel_privilege():
            meeting = channel.calendar_event_ids[:1]
            if not meeting:
                continue
            channel.name = meeting.name
            channel.channel_change_description(
                meeting._get_videocall_channel_description()
            )

    def _get_videocall_channel_description(self):
        self.check_singleton()
        return self.recurrence_id.name or self.display_time

    @api.model
    def _get_today_domain(self):
        start_of_day, end_of_day = self.env["discuss.channel"]._get_today_bounds()
        return Domain("start", "<=", end_of_day) & Domain("stop", ">=", start_of_day)

    def _create_videocall_channel(self) -> None:
        if self.recurrency:
            event_with_channel = self.env["calendar.event"].search(
                [
                    ("recurrence_id", "=", self.recurrence_id.id),
                    ("videocall_channel_id", "!=", False),
                ],
                limit=1,
            )
            if event_with_channel:
                self.videocall_channel_id = event_with_channel.videocall_channel_id
                return
        self.videocall_channel_id = self._create_videocall_channel_id(
            self.name, self.partner_ids.ids
        )
        self.videocall_channel_id.channel_change_description(
            self._get_videocall_channel_description()
        )

    def _create_videocall_channel_id(self, name, partner_ids):
        videocall_channel = self.env["discuss.channel"]._create_group(
            partner_ids, default_display_mode="video_full_screen", name=name
        )
        if self.recurrency:
            recurrent_events_without_channel = self.env["calendar.event"].search(
                [
                    ("recurrence_id", "=", self.recurrence_id.id),
                    ("videocall_channel_id", "=", False),
                ]
            )
            recurrent_events_without_channel.videocall_channel_id = videocall_channel
        return videocall_channel

    def _get_domain_default_privacy(self):
        settings = self.env["res.users.settings"].sudo()
        owner_default_is_public = Domain(
            "user_id",
            "in",
            settings._search([("calendar_default_privacy", "!=", "private")]).select(
                "user_id"
            ),
        )
        if self.env["res.users"]._get_user_calendar_default_privacy() != "private":
            owner_default_is_public |= Domain(
                "user_id", "not in", settings._search([]).select("user_id")
            )
        return Domain.OR(
            [
                Domain("privacy", "in", ["public", "confidential"]),
                Domain("user_id", "=", self.env.user.id),
                Domain("partner_ids", "in", self.env.user.partner_id.id),
                Domain("privacy", "=", False)
                & (Domain("user_id", "=", False) | owner_default_is_public),
            ]
        )

    def _is_event_over(self) -> bool:
        self.check_singleton()
        now = fields.Datetime.now()
        today = fields.Date.today()

        if self.allday:
            return bool(self.stop_date and self.stop_date < today)

        return bool(self.stop and self.stop < now)


    def set_discuss_videocall_location(self) -> bool:
        return True

    def clear_videocall_location(self) -> bool:
        return True

    def action_view_calendar_event(self):
        if self.res_model and self.res_id:
            return self.env[self.res_model].browse(self.res_id).get_formview_action()
        return None

    def action_sendmail(self) -> None:
        if self.env.user.email:
            self.attendee_ids._notify_attendees(
                self.env.ref(
                    "calendar.calendar_template_meeting_invitation",
                    raise_if_not_found=False,
                ),
            )

    def action_view_composer(self) -> dict:
        if not self.partner_ids:
            raise UserError(self.env._("There are no attendees on these events"))
        template_id = self.env["ir.model.data"]._xmlid_to_res_id(
            "calendar.calendar_template_meeting_update", raise_if_not_found=False
        )
        default_composition_mode = self.env.context.get(
            "default_composition_mode",
            self.env.context.get("composition_mode", "comment"),
        )
        compose_ctx = {
            "default_composition_mode": default_composition_mode,
            "default_model": "calendar.event",
            "default_res_ids": self.ids,
            "default_template_id": template_id,
            "default_partner_ids": self.partner_ids.ids,
            "mail_tz": self.env.user.tz,
        }
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Contact Attendees"),
            "view_mode": "form",
            "res_model": "wizard.mail.message.send",
            "views": [(False, "form")],
            "view_id": False,
            "target": "new",
            "context": compose_ctx,
        }

    def action_join_video_call(self) -> dict:
        return {
            "type": "ir.actions.act_url",
            "url": self.videocall_location,
            "target": "new",
        }

    def action_join_meeting(self, partner_id) -> None:
        self.check_singleton()
        partner = self.env["res.partner"].browse(partner_id)
        if partner not in self.partner_ids:
            self.write({"partner_ids": [Command.link(partner.id)]})

    RECURRENCE_DELETE_POLICIES = {
        "all": "all",
        "subsequent": "subsequent",
        "next": "subsequent",
        "this": "this",
        "one": "this",
    }

    @api.model
    def _normalize_recurrence_policy(self, policy):
        return self.RECURRENCE_DELETE_POLICIES.get(policy, "this")

    def _unlink_by_recurrence_policy(self, policy) -> None:
        policy = self._normalize_recurrence_policy(policy)
        if policy == "this" or not self.recurrency or len(self) > 1:
            self.unlink()
            return
        self.action_mass_deletion(policy)

    def action_mass_deletion(self, recurrence_update_setting) -> None:
        self.check_singleton()
        if recurrence_update_setting == "all":
            events = self.recurrence_id.calendar_event_ids
            self.recurrence_id.unlink()
            events.unlink()
        elif recurrence_update_setting == "subsequent":
            self.recurrence_id._stop_at(self).unlink()
        else:
            raise UserError(
                self.env._(
                    "Unknown recurrence update setting: %s",
                    recurrence_update_setting,
                )
            )

    def action_mass_archive(self, recurrence_update_setting) -> None:
        self.check_singleton()
        if recurrence_update_setting == "all":
            self.recurrence_id.calendar_event_ids.write({"active": False})
        elif recurrence_update_setting == "subsequent":
            detached_events = self.recurrence_id._stop_at(self)
            detached_events.write({"active": False})
        elif recurrence_update_setting == "this":
            self.write({"active": False, "recurrence_update": "this"})
            if len(self.recurrence_id.calendar_event_ids) == 0:
                self.recurrence_id.unlink()
            elif self == self.recurrence_id.base_event_id:
                self.recurrence_id._select_new_base_event()


    def _skip_send_mail_status_update(self):
        return False

    def _get_mail_tz(self):
        self.check_singleton()
        return self.event_tz or self.env.user.tz

    def _sync_activities(self, fields) -> None:
        for event in self:
            if event.activity_ids:
                activity_values = {}
                if "name" in fields:
                    activity_values["summary"] = event.name
                if "description" in fields:
                    activity_values["note"] = event.description
                if "start" in fields and not self.env.context.get(
                    "mail_activity_meeting_update"
                ):
                    activity_values["date_deadline"] = (
                        self._get_activity_deadline_from_start(
                            event.start, event.allday
                        )
                    )
                if "user_id" in fields:
                    activity_values["user_id"] = event.user_id.id
                if activity_values.keys():
                    event.activity_ids.with_context(
                        calendar_event_meeting_update=True
                    ).write(activity_values)

    @api.model
    def _get_activity_deadline_from_start(self, start, allday):
        deadline = start
        user_tz = self.env.context.get("tz")
        if user_tz and not allday:
            deadline = deadline.replace(tzinfo=UTC)
            deadline = deadline.astimezone(timezone(user_tz))
        return deadline.date()


    def _get_trigger_alarm_types(self):
        return ["email"]

    def _setup_event_recurrent_alarms(self, events_by_alarm) -> None:
        for event in self:
            if event.recurrence_id:
                next_date = event.get_next_alarm_date(events_by_alarm)
                if next_date:
                    event.recurrence_id.with_context(
                        date=next_date
                    )._schedule_next_occurrence_alarm()

    def _setup_alarms(self):
        cron = self.env.ref("calendar.ir_cron_scheduler_alarm").sudo()
        alarm_types = self._get_trigger_alarm_types()
        now = fields.Datetime.now()
        events_to_notify = self.env["calendar.event"]
        triggers_by_events = {}
        for event in self:
            existing_trigger = event.recurrence_id.sudo().trigger_id
            for alarm in (
                alarm for alarm in event.alarm_ids if alarm.alarm_type in alarm_types
            ):
                at = event.start - timedelta(minutes=alarm.duration_minutes)
                create_trigger = not existing_trigger or existing_trigger.call_at != at
                if create_trigger and (not cron.lastcall or at > cron.lastcall):
                    trigger = cron._trigger(at=at)
                    triggers_by_events[event.id] = trigger.id
            if (
                any(alarm.alarm_type == "notification" for alarm in event.alarm_ids)
                and event.stop >= now
            ):
                events_to_notify |= event
        if events_to_notify:
            self.env["calendar.alarm_manager"]._notify_next_alarm(
                events_to_notify.partner_ids.ids
            )
        return triggers_by_events

    def get_next_alarm_date(self, events_by_alarm):
        self.check_singleton()
        now = fields.Datetime.now()
        sorted_alarms = self.alarm_ids.sorted("duration_minutes")
        triggered_alarms = sorted_alarms.filtered(
            lambda alarm: (
                alarm.id in events_by_alarm and self.id in events_by_alarm[alarm.id]
            )
        )[0]
        event_has_future_alarms = sorted_alarms[0] != triggered_alarms
        next_date = None
        if (
            self.recurrence_id.trigger_id
            and self.recurrence_id.trigger_id.call_at <= now
        ):
            next_date = (
                self.start - timedelta(minutes=sorted_alarms[0].duration_minutes)
                if event_has_future_alarms
                else self.start
            )
        recurrence_has_no_trigger = (
            self.recurrence_id and not self.recurrence_id.trigger_id
        )
        if recurrence_has_no_trigger and not next_date and len(sorted_alarms) > 0:
            future_recurrent_events = self.recurrence_id.calendar_event_ids.filtered(
                lambda ev: ev.start > self.start
            )
            if future_recurrent_events:
                next_recurrent_event = future_recurrent_events.sorted("start")[0]
                next_date = next_recurrent_event.start - timedelta(
                    minutes=sorted_alarms[0].duration_minutes
                )
        return next_date


    def _apply_recurrence_values(self, values, future=True):
        if not values:
            return self.browse()
        recurrence_vals = []
        to_update = self.env["calendar.recurrence"]
        for event in self:
            if not event.recurrence_id:
                recurrence_vals += [
                    dict(
                        values,
                        base_event_id=event.id,
                        calendar_event_ids=[Command.link(event.id)],
                    )
                ]
            elif future:
                to_update |= event.recurrence_id._split_from(event, values)
        self.write({"recurrency": True, "follow_recurrence": True})
        to_update |= self.env["calendar.recurrence"].create(recurrence_vals)
        return to_update._apply_recurrence()

    def _get_recurrence_params(self):
        if not self:
            return {}
        return self._get_recurrence_params_by_date(self._get_start_date())

    @api.model
    def _get_recurrence_params_by_date(self, event_date) -> dict:
        weekday_field_name = weekday_to_field(event_date.weekday())
        return {
            weekday_field_name: True,
            "weekday": weekday_field_name.upper(),
            "byday": str(get_weekday_occurence(event_date)),
            "day": event_date.day,
        }

    def _break_recurrence(self, future=True):
        recurrences_to_unlink = self.env["calendar.recurrence"]
        detached_events = self.env["calendar.event"]
        for event in self:
            recurrence = event.recurrence_id
            if future:
                detached_events |= recurrence._stop_at(event)
            else:
                detached_events |= recurrence.calendar_event_ids
                recurrence.calendar_event_ids.recurrence_id = False
                recurrences_to_unlink |= recurrence
        recurrences_to_unlink.with_context(archive_on_error=True).unlink()
        return detached_events - self

    def _get_time_update_dict(self, base_event, time_values):
        if not base_event:
            raise UserError(
                self.env._("You can't update a recurrence without base event.")
            )
        [base_time_values] = base_event.read(["start", "stop", "allday"])
        update_dict = {}
        start_update = fields.Datetime.to_datetime(time_values.get("start"))
        stop_update = fields.Datetime.to_datetime(time_values.get("stop"))
        allday = base_time_values["allday"]
        if start_update or stop_update:
            if start_update:
                if allday:
                    start = base_time_values["start"] + (
                        start_update.date() - self.start.date()
                    )
                    stop = base_time_values["stop"] + (
                        start_update.date() - self.start.date()
                    )
                else:
                    start = base_time_values["start"] + (start_update - self.start)
                    stop = base_time_values["stop"] + (start_update - self.start)
                start_date = base_time_values["start"].date() + (
                    start_update.date() - self.start.date()
                )
                stop_date = base_time_values["stop"].date() + (
                    start_update.date() - self.start.date()
                )
                update_dict.update(
                    {
                        "start": start,
                        "start_date": start_date,
                        "stop": stop,
                        "stop_date": stop_date,
                    }
                )
            if stop_update:
                if not start_update:
                    if allday:
                        start = base_time_values["start"] + (
                            stop_update.date() - self.stop.date()
                        )
                    else:
                        start = base_time_values["start"] + (stop_update - self.stop)
                    start_date = base_time_values["start"].date() + (
                        stop_update.date() - self.stop.date()
                    )
                    update_dict.update({"start": start, "start_date": start_date})
                if allday:
                    stop = base_time_values["stop"] + (
                        stop_update.date() - self.stop.date()
                    )
                else:
                    stop = base_time_values["stop"] + (stop_update - self.stop)
                stop_date = base_time_values["stop"].date() + (
                    stop_update.date() - self.stop.date()
                )
                update_dict.update({"stop": stop, "stop_date": stop_date})
        return update_dict

    @api.model
    def _has_values_to_sync(self, values) -> bool:
        return False

    def _forget_sync_ids(self) -> None:
        pass

    def _prepare_updated_recurrence_vals(self, new_start_date) -> ValuesType:
        [previous_recurrence_values] = self.recurrence_id.copy_data()
        if self.start.weekday() != new_start_date.weekday():
            previous_recurrence_values.pop(weekday_to_field(self.start.weekday()), None)
        return previous_recurrence_values

    def _update_future_events(self, values, time_values, recurrence_values) -> Self:
        self.check_singleton()
        base_event = self
        update_dict = self._get_time_update_dict(base_event, time_values)
        time_values.update(update_dict)
        start_date = (
            time_values["start"].date() if "start" in time_values else self.start.date()
        )
        previous_recurrence_values = self._prepare_updated_recurrence_vals(start_date)

        detached_events_split = self.recurrence_id._stop_at(self)
        (detached_events_split - self)._forget_sync_ids()
        (detached_events_split - self).write({"active": False})

        if values or time_values:
            self._forget_sync_ids()
            self.with_context(skip_attendee_notification=True).write(
                {
                    **time_values,
                    **values,
                }
            )
            if time_values:
                self._reset_attendees_status()

        new_values = {
            **previous_recurrence_values,
            **self._get_recurrence_params_by_date(start_date),
            **recurrence_values,
            "repeat_number": recurrence_values.get("repeat_number", 0)
            or len(detached_events_split),
        }
        new_values.pop("rrule", None)

        self._apply_recurrence_values(new_values)
        return self

    def _rewrite_recurrence(self, values, time_values, recurrence_values):
        self.check_singleton()
        base_event = (
            self.recurrence_id.base_event_id
            or self.recurrence_id._get_first_event(include_outliers=False)
        )
        update_dict = self._get_time_update_dict(base_event, time_values)
        time_values.update(update_dict)

        if self._has_values_to_sync(values) or time_values or recurrence_values:
            start_date = (
                time_values["start"].date()
                if "start" in time_values
                else self.start.date()
            )
            old_recurrence_values = self._prepare_updated_recurrence_vals(start_date)

            base_event.action_mass_archive("all")
            base_event.recurrence_id.unlink()
            base_event.with_context(skip_attendee_notification=True).write(
                {"active": True, "recurrence_id": False, **values, **time_values}
            )

            if time_values:
                base_event._reset_attendees_status()

            new_values = {
                **old_recurrence_values,
                **base_event._get_recurrence_params(),
                **recurrence_values,
            }
            new_values.pop("rrule", None)

            detached_events = base_event._apply_recurrence_values(new_values)
            detached_events.write({"active": False})
        else:
            self.recurrence_id._write_events(values)
        return base_event


    def change_attendee_status(self, status, recurrence_update_setting):
        self.check_singleton()
        if recurrence_update_setting == "all":
            events = self.recurrence_id.calendar_event_ids
        elif recurrence_update_setting == "subsequent":
            events = self.recurrence_id.calendar_event_ids.filtered(
                lambda ev: ev.start >= self.start
            )
        else:
            events = self
        attendee = events.attendee_ids.filtered(
            lambda x: x.partner_id == self.env.user.partner_id
        )
        if status == "accepted":
            return attendee.do_accept()
        if status == "declined":
            return attendee.do_decline()
        return attendee.do_tentative()

    def find_partner_customer(self):
        self.check_singleton()
        return next(
            (
                attendee.partner_id
                for attendee in self.attendee_ids
                if attendee.partner_id != self.user_id.partner_id
            ),
            self.env["res.partner"],
        )


    @api.model
    def _get_activity_excluded_models(self):
        return []

    def _reset_attendees_status(self) -> None:
        for attendee in self.attendee_ids:
            if attendee.partner_id == self.env.user.partner_id:
                attendee.state = "accepted"
            else:
                attendee.state = "needsAction"

    def _get_start_date(self):
        if not self.start:
            return fields.Date.today()
        if self.recurrency and self.event_tz:
            tz = timezone(self.event_tz)
            start = self.start if not self.allday else self.start.replace(hour=12)
            return start.replace(tzinfo=UTC).astimezone(tz).date()
        return self.start.date()

    def _range(self) -> tuple:
        self.check_singleton()
        return (self.start, self.stop)

    def get_display_time_tz(self, tz=False):
        self.check_singleton()
        if tz:
            self = self.with_context(tz=tz)
        return self._get_display_time(self.start, self.stop, self.duration, self.allday)

    def _get_ics_file(self):
        result = {}

        def ics_datetime(idate):
            return idate.replace(tzinfo=timezone("UTC")) if idate else False

        if not vobject:
            return result

        for meeting in self:
            cal = vobject.iCalendar()
            event = cal.add("vevent")

            if not meeting.start or not meeting.stop:
                raise UserError(
                    self.env._("First you have to specify the date of the invitation.")
                )
            event.add("created").value = ics_datetime(fields.Datetime.now())
            if meeting.allday:
                _add_ics_date(event, "dtstart", meeting.start.date())
                _add_ics_date(event, "dtend", meeting.stop.date() + timedelta(days=1))
            else:
                event.add("dtstart").value = ics_datetime(meeting.start)
                event.add("dtend").value = ics_datetime(meeting.stop)
            event.add("summary").value = meeting._get_customer_summary()
            description = html2plaintext(meeting._get_customer_description())
            if description:
                event.add("description").value = description
            if meeting.location:
                event.add("location").value = meeting.location
            if meeting._can_ics_declare_recurrence() and (
                rrule_value := self._get_ics_rrule(meeting.rrule)
            ):
                event.add("rrule").value = rrule_value

            meeting._ics_add_alarms(event)
            meeting._ics_add_people(event)

            result[meeting.id] = cal.serialize().encode("utf-8")

        return result

    def _ics_add_alarms(self, vevent) -> None:
        self.check_singleton()
        for alarm in self.alarm_ids:
            valarm = vevent.add("valarm")
            trigger = valarm.add("TRIGGER")
            trigger.params["related"] = ["START"]
            trigger.value = -timedelta(minutes=alarm.duration_minutes)
            valarm.add("DESCRIPTION").value = alarm.name or "Odoo"

    def _ics_add_people(self, vevent) -> None:
        self.check_singleton()
        for attendee in self.attendee_ids:
            vevent.add("attendee").value = "MAILTO:" + (attendee.email or "")
        if self.partner_id.email:
            organizer = vevent.add("organizer")
            organizer.value = "MAILTO:" + self.partner_id.email
            if self.partner_id.name:
                organizer.params["CN"] = [
                    self.partner_id.display_name.replace('"', "'")
                ]

    def _can_ics_declare_recurrence(self) -> bool:
        self.check_singleton()
        if not self.rrule or self.env.context.get(
            "calendar_template_ignore_recurrence"
        ):
            return False
        return not self.recurrence_id or self == self.recurrence_id.base_event_id

    @api.model
    def _get_ics_rrule(self, rrule):
        value = self.env["calendar.recurrence"]._rrule_value(rrule)
        return re.sub(r"(UNTIL=\d{8}T\d{6})($|;)", r"\1Z\2", value)

    @api.model
    def _get_contact_details_description(self, organizer, partners):
        odoobot = self.env.ref("base.user_root")
        contact_description = []
        if organizer and organizer != odoobot:
            contact_description.extend(
                self._prepare_partner_contact_details_html(
                    self.env._("Organized by"), organizer.partner_id
                )
            )
        first_partner = partners.filtered(
            lambda partner: partner not in (odoobot.partner_id + organizer.partner_id)
        )[:1]
        if first_partner:
            if contact_description:
                contact_description.append(
                    ""
                )
            contact_description.extend(
                self._prepare_partner_contact_details_html(
                    self.env._("Contact Details"), first_partner
                )
            )
        return Markup("<br/>").join(contact_description)

    @api.model
    def _prepare_partner_contact_details_html(self, section_title, partner):
        details = list(
            filter(
                None,
                [
                    partner.name,
                    partner.email
                    and Markup("<a href='mailto:%(email)s'>%(email)s</a>")
                    % {"email": partner.email},
                    partner._phone_get_number().number
                    and Markup("<a href='tel:%(phone)s'>%(phone)s</a>")
                    % {"phone": partner._phone_get_number().number},
                ],
            )
        )
        if details:
            details.insert(0, Markup("<strong>%s</strong>") % section_title)
        return details

    def _get_customer_description(self):
        return (
            html_sanitize(self.description)
            if not is_html_empty(self.description)
            else ""
        )

    def _get_customer_summary(self):
        return self.name or ""

    @api.model
    def _get_display_time(self, start, stop, zduration, zallday):
        tz_name = self.env.context.get("tz") or self.env.user.partner_id.tz or "UTC"

        self_tz = self.with_context(tz=tz_name)
        date = fields.Datetime.context_timestamp(
            self_tz, fields.Datetime.from_string(start)
        )
        date_deadline = fields.Datetime.context_timestamp(
            self_tz, fields.Datetime.from_string(stop)
        )

        date_str = format_date(self.env, date.date())
        time_str = format_time(self.env, date.time())

        if zallday:
            display_time = self.env._("All Day, %(day)s", day=date_str)
        elif zduration < 24:
            duration = date + timedelta(minutes=round(zduration * 60))
            duration_time = format_time(self.env, duration.time())
            display_time = self.env._(
                "%(day)s at (%(start)s To %(end)s) (%(timezone)s)",
                day=date_str,
                start=time_str,
                end=duration_time,
                timezone=tz_name,
            )
        else:
            dd_date = format_date(self.env, date_deadline.date())
            dd_time = format_time(self.env, date_deadline.time())
            display_time = self.env._(
                "%(date_start)s at %(time_start)s To\n %(date_end)s at %(time_end)s (%(timezone)s)",
                date_start=date_str,
                time_start=time_str,
                date_end=dd_date,
                time_end=dd_time,
                timezone=tz_name,
            )
        return display_time

    def _get_duration(self, start, stop):
        if not start or not stop:
            return 0
        duration = (stop - start).total_seconds() / 3600
        return round(duration, 2)

    @api.model
    @api.model
    def _get_fields_recurrent(self) -> set:
        return {
            "byday",
            "repeat_until",
            "repeat_unit",
            "month_by",
            "event_tz",
            "rrule",
            "repeat_interval",
            "repeat_number",
            "repeat_type",
            "mon",
            "tue",
            "wed",
            "thu",
            "fri",
            "sat",
            "sun",
            "day",
            "weekday",
        }

    @api.model
    def _get_fields_time(self) -> set:
        return {"start", "stop", "start_date", "stop_date"}

    @api.model
    def _touches_time(self, values) -> bool:
        return any(values.get(fname) for fname in self._get_fields_time())

    @api.model
    def _get_fields_custom(self) -> set:
        all_fields = self.fields_get(attributes=["manual"])
        return {fname for fname in all_fields if all_fields[fname]["manual"]}

    @api.model
    def _get_fields_public(self):
        return (
            self._get_fields_recurrent()
            | self._get_fields_time()
            | self._get_fields_custom()
            | {
                "id",
                "active",
                "allday",
                "duration",
                "user_id",
                "repeat_interval",
                "partner_id",
                "repeat_number",
                "rrule",
                "recurrence_id",
                "show_as",
                "privacy",
            }
        )

    @api.model
    def get_default_duration(self):
        defaults = self.env["ir.default"].sudo()._get_model_defaults("calendar.event")
        return defaults.get("duration") or 1

    def _update_access_token(self) -> None:
        for event in self:
            event.access_token = generate_calendar_token()
