import logging
from datetime import UTC

from odoo import http, tools
from odoo.exceptions import AccessError, UserError
from odoo.fields import Domain
from odoo.http import request
from odoo.libs.datetime import timezone
from odoo.libs.debug_log import DebugLog
from odoo.tools import format_duration
from odoo.tools.misc import get_lang

from odoo.addons.base.models.access_link import LinkLoginRequired, LinkRefused

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)

try:
    import vobject
except ImportError:
    _logger.warning(
        "`vobject` Python module not found, vcard file generation disabled. Consider installing this module if you want to generate vcard files"
    )
    vobject = None


class ShiftController(http.Controller):
    @http.route(
        ["/planning/<string:planning_token>/<string:employee_token>"],
        type="http",
        auth="public",
        website=True,
    )
    def planning(self, planning_token, employee_token, message=False, **kwargs):
        planning_data = self._planning_get(planning_token, employee_token, message)
        if not planning_data:
            raise request.prepare_not_found_error()
        return request.render("planning.period_report_template", planning_data)

    def _get_slot_title(self, slot):
        return "%s%s" % (
            slot.role_id.name or request.env._("Shift"),
            " \U0001f4ac" if slot.name else "",
        )

    def _prepare_slot_display_data(self, slot, is_open_shift):
        return {
            "title": self._get_slot_title(slot),
            "color": slot.role_id._get_color_from_code(is_open_shift),
            "alloc_hours": format_duration(slot.allocated_hours),
            "alloc_perc": f"{slot.allocated_percentage:.2f}",
            "slot_id": slot.id,
            "note": slot.name,
            "allow_self_unassign": slot.allow_self_unassign,
            "is_unassign_deadline_passed": slot.is_unassign_deadline_passed,
            "role": slot.role_id.name,
            "request_to_switch": slot.request_to_switch,
            "is_past": slot.is_past,
            "is_open_shift": is_open_shift,
        }

    def _prepare_slot_display_rows(
        self, slot, resource_sudo, attendance_intervals, is_open_shift
    ):
        person_tz = timezone(resource_sudo.tz or "UTC")
        datetime_start = slot.start_datetime.replace(tzinfo=UTC)
        datetime_end = slot.end_datetime.replace(tzinfo=UTC)

        if resource_sudo._is_flexible():
            vals = self._prepare_slot_display_data(slot, is_open_shift)
            vals["start"] = str(
                datetime_start.astimezone(person_tz).replace(tzinfo=None)
            )
            vals["end"] = str(datetime_end.astimezone(person_tz).replace(tzinfo=None))
            return [vals]

        res = []
        for start, stop, _dummy in attendance_intervals:
            if datetime_start < stop and datetime_end > start:
                vals = self._prepare_slot_display_data(slot, is_open_shift)
                vals["start"] = str(
                    max(datetime_start, start)
                    .astimezone(person_tz)
                    .replace(tzinfo=None)
                )
                vals["end"] = str(
                    min(datetime_end, stop).astimezone(person_tz).replace(tzinfo=None)
                )
                res.append(vals)

        return [
            {**vals, "alloc_hours": format_duration(slot.allocated_hours / len(res))}
            for vals in res
        ]

    @staticmethod
    def _planning_of(token, resource_sudo):
        Planning = request.env["planning.planning"]
        if not resource_sudo:
            return Planning
        try:
            resolution = request.env["access.link"]._resolve(
                token, model=Planning._name, role="comment", action=None
            )
        except LinkRefused, LinkLoginRequired:
            return Planning
        link = resolution.link
        if link.cause_model and (link.cause_model, link.cause_res_id) != (
            resource_sudo._name,
            resource_sudo.id,
        ):
            return Planning
        return resolution.record

    def _planning_get(self, planning_token, employee_token, message=False):
        resource_sudo = (
            request.env["resource.resource"]
            .sudo()
            .search([("planning_token", "=", employee_token)], limit=1)
        )
        if not resource_sudo:
            _debug.logic("portal_denied", reason="unknown_employee_token")
            return None

        planning_sudo = self._planning_of(planning_token, resource_sudo)
        if not planning_sudo:
            _debug.logic(
                "portal_denied",
                reason="unknown_planning_token",
                employee=resource_sudo,
            )
            return None

        _debug.pipeline(
            "portal_planning", employee=resource_sudo, planning=planning_sudo
        )
        person_tz = timezone(resource_sudo.tz or "UTC")
        person_fullcalendar_data = []
        open_slots = []
        unwanted_slots = []
        person_slots = []

        domain = Domain(
            [
                ("start_datetime", ">=", planning_sudo.start_datetime),
                ("end_datetime", "<=", planning_sudo.end_datetime),
                (
                    "state",
                    "in",
                    planning_sudo.env["planning.slot"]._get_scheduled_states(),
                ),
            ]
        )
        if planning_sudo.include_unassigned:
            domain &= Domain(
                [
                    "|",
                    ("resource_id", "=", resource_sudo.id),
                    "|",
                    ("resource_id", "=", False),
                    ("request_to_switch", "=", True),
                ]
            )
        else:
            domain &= Domain(
                [
                    "|",
                    ("resource_id", "=", resource_sudo.id),
                    ("request_to_switch", "=", True),
                ]
            )
        planning_slots = (
            request.env["planning.slot"]
            .sudo()
            .search(domain, order="start_datetime asc")
        )
        datetime_start = planning_sudo.start_datetime.replace(tzinfo=UTC)
        datetime_end = planning_sudo.end_datetime.replace(tzinfo=UTC)
        resource_work_intervals, dummy = (
            resource_sudo._get_valid_work_intervals(
                datetime_start,
                datetime_end,
            )
        )
        attendance_intervals = resource_work_intervals[resource_sudo.id]

        slots_start_datetime = []
        slots_end_datetime = []
        checkin_min = 8
        checkout_max = 18
        planning_values = {
            "person_slots_fullcalendar_data": person_fullcalendar_data,
            "open_slots_ids": open_slots,
            "unwanted_slots_ids": unwanted_slots,
            "planning_planning_id": planning_sudo,
            "person": resource_sudo,
            "person_token": employee_token,
            "planning_token": planning_token,
            "no_data": True,
        }
        for slot in planning_slots:
            if slot.resource_id:
                slot_start_datetime = (
                    slot.start_datetime.replace(tzinfo=UTC)
                    .astimezone(person_tz)
                    .replace(tzinfo=None)
                )
                slot_end_datetime = (
                    slot.end_datetime.replace(tzinfo=UTC)
                    .astimezone(person_tz)
                    .replace(tzinfo=None)
                )
                if slot.request_to_switch and (
                    not slot.role_id
                    or slot.resource_id == resource_sudo
                    or not resource_sudo.role_ids
                    or slot.role_id in resource_sudo.role_ids
                ):
                    unwanted_slots.append(slot)
                if slot.resource_id == resource_sudo:
                    person_slots.append(slot)
                    vals = self._prepare_slot_display_rows(
                        slot, resource_sudo, attendance_intervals, False
                    )
                    person_fullcalendar_data.extend(vals)
                slots_start_datetime.append(slot_start_datetime)
                slots_end_datetime.append(slot_end_datetime)
            elif (
                not slot.is_past
                and (
                    not resource_sudo.role_ids
                    or not slot.role_id
                    or slot.role_id in resource_sudo.role_ids
                )
                and (
                    resource_sudo._is_flexible()
                    or any(
                        slot.start_datetime.replace(tzinfo=UTC) < end
                        and slot.end_datetime.replace(tzinfo=UTC) > start
                        for start, end, dummy in attendance_intervals._items
                    )
                )
            ):
                concurrent_slot = False
                for open_slot in open_slots:
                    if (
                        slot.start_datetime == open_slot.start_datetime
                        and slot.end_datetime == open_slot.end_datetime
                    ):
                        concurrent_slot = open_slot
                        break
                if (
                    not concurrent_slot
                    or slot.role_id == resource_sudo.default_role_id
                    or (
                        slot.role_id.sequence < concurrent_slot.role_id.sequence
                        and concurrent_slot.role_id != resource_sudo.default_role_id
                    )
                ):
                    open_slots.append(slot)
                    if concurrent_slot:
                        open_slots.remove(concurrent_slot)

        slots_to_remove = []
        for slot in open_slots:
            if any(
                slot.start_datetime == person_slot.start_datetime
                and slot.end_datetime == person_slot.end_datetime
                for person_slot in person_slots
            ):
                slots_to_remove.append(slot)
            else:
                vals = self._prepare_slot_display_rows(
                    slot, resource_sudo, attendance_intervals, True
                )
                person_fullcalendar_data.extend(vals)

        for slot in slots_to_remove:
            open_slots.remove(slot)

        min_start_datetime = (
            slots_start_datetime and min(slots_start_datetime)
        ) or planning_sudo.start_datetime.replace(tzinfo=UTC).astimezone(
            person_tz
        ).replace(tzinfo=None)
        max_end_datetime = (
            slots_end_datetime and max(slots_end_datetime)
        ) or planning_sudo.end_datetime.replace(tzinfo=UTC).astimezone(
            person_tz
        ).replace(tzinfo=None)
        if min_start_datetime.isocalendar()[1] == max_end_datetime.isocalendar()[1]:
            default_view = "timeGridWeek"
        else:
            default_view = "dayGridMonth"
        if resource_sudo.calendar_id and attendance_intervals:
            checkin_min = 24
            checkout_max = 0
            for start, end, _dummy in attendance_intervals:
                checkin_min = min(checkin_min, start.hour)
                checkout_max = max(checkout_max, end.hour)
        if slots_start_datetime and slots_end_datetime:
            event_hour_min = min(s.hour for s in slots_start_datetime)
            event_hour_max = max(s.hour for s in slots_end_datetime)
            mintime_weekview, maxtime_weekview = self._get_hours_intervals(
                checkin_min, checkout_max, event_hour_min, event_hour_max
            )
        else:
            mintime_weekview, maxtime_weekview = checkin_min, checkout_max
        if person_fullcalendar_data or open_slots or unwanted_slots:
            planning_values.update(
                {
                    "person_slots_fullcalendar_data": person_fullcalendar_data,
                    "open_slots_ids": open_slots,
                    "unwanted_slots_ids": unwanted_slots,
                    "locale": get_lang(request.env).iso_code.split("_")[0],
                    "format_datetime": lambda dt, dt_format: tools.format_datetime(
                        request.env, dt, tz=person_tz.key, dt_format=dt_format
                    ),
                    "notification_text": message
                    in [
                        "assign",
                        "unassign",
                        "already_assign",
                        "deny_unassign",
                        "switch",
                        "cancel_switch",
                    ],
                    "message_slug": message,
                    "open_slot_has_role": any(s.role_id.id for s in open_slots),
                    "open_slot_has_note": any(s.name for s in open_slots),
                    "unwanted_slot_has_role": any(s.role_id.id for s in unwanted_slots),
                    "unwanted_slot_has_note": any(s.name for s in unwanted_slots),
                    "start_datetime": planning_sudo.start_datetime,
                    "end_datetime": planning_sudo.end_datetime,
                    "mintime": "%02d:00:00" % mintime_weekview,
                    "maxtime": "%02d:00:00" % maxtime_weekview,
                    "default_view": default_view,
                    "default_start": min_start_datetime.date(),
                    "no_data": False,
                }
            )
        return planning_values

    @http.route(
        "/planning/<string:token_planning>/<string:token_employee>/assign/<int:slot_id>",
        type="http",
        auth="public",
        website=True,
    )
    def planning_self_assign(
        self, token_planning, token_employee, slot_id, message=False, **kwargs
    ):
        slot_sudo = request.env["planning.slot"].sudo().browse(slot_id)
        if not slot_sudo.exists():
            _debug.logic("self_assign_denied", reason="no_slot", slot=slot_id)
            raise request.prepare_not_found_error()

        resource_sudo = (
            request.env["resource.resource"]
            .sudo()
            .search([("planning_token", "=", token_employee)], limit=1)
        )
        if not resource_sudo:
            _debug.logic("self_assign_denied", reason="unknown_employee_token")
            raise request.prepare_not_found_error()

        planning_sudo = self._planning_of(token_planning, resource_sudo)
        if not planning_sudo._is_slot_in_planning(slot_sudo):
            _debug.logic(
                "self_assign_denied",
                reason="slot_outside_planning",
                slot=slot_sudo,
                planning=planning_sudo,
            )
            raise request.prepare_not_found_error()

        if slot_sudo.resource_id and not slot_sudo.request_to_switch:
            _debug.logic(
                "self_assign_denied", reason="already_assigned", slot=slot_sudo
            )
            return request.redirect(
                "/planning/%s/%s?message=%s"
                % (token_planning, token_employee, "already_assign")
            )

        _debug.lifecycle("portal_self_assigned", slot=slot_sudo, employee=resource_sudo)
        slot_sudo.write({"resource_id": resource_sudo.id})
        slot_sudo.slot_properties
        if message:
            return request.redirect(
                "/planning/%s/%s?message=%s"
                % (token_planning, token_employee, "assign")
            )
        else:
            return request.redirect(
                "/planning/%s/%s" % (token_planning, token_employee)
            )

    @http.route(
        "/planning/<string:token_planning>/<string:token_employee>/unassign/<int:shift_id>",
        type="http",
        auth="public",
        website=True,
    )
    def planning_self_unassign(
        self, token_planning, token_employee, shift_id, message=False, **kwargs
    ):
        slot_sudo = (
            request.env["planning.slot"].sudo().search([("id", "=", shift_id)], limit=1)
        )
        if not slot_sudo or not slot_sudo.allow_self_unassign:
            raise request.prepare_not_found_error()

        if slot_sudo.is_unassign_deadline_passed:
            return request.redirect(
                "/planning/%s/%s?message=%s"
                % (token_planning, token_employee, "deny_unassign")
            )

        resource_sudo = (
            request.env["resource.resource"]
            .sudo()
            .search([("planning_token", "=", token_employee)], limit=1)
        )
        if not resource_sudo or resource_sudo.id != slot_sudo.resource_id.id:
            raise request.prepare_not_found_error()

        planning_sudo = self._planning_of(token_planning, resource_sudo)
        if not planning_sudo._is_slot_in_planning(slot_sudo):
            raise request.prepare_not_found_error()

        slot_sudo.write({"resource_id": False})
        slot_sudo.slot_properties
        if message:
            return request.redirect(
                "/planning/%s/%s?message=%s"
                % (token_planning, token_employee, "unassign")
            )
        else:
            return request.redirect(
                "/planning/%s/%s" % (token_planning, token_employee)
            )

    @http.route(
        "/planning/<string:token_planning>/<string:token_employee>/switch/<int:shift_id>",
        type="http",
        auth="public",
        website=True,
    )
    def planning_switch_shift(self, token_planning, token_employee, shift_id, **kwargs):
        slot_sudo = request.env["planning.slot"].sudo().browse(shift_id)
        if not slot_sudo.exists():
            raise request.prepare_not_found_error()

        resource_sudo = (
            request.env["resource.resource"]
            .sudo()
            .search([("planning_token", "=", token_employee)], limit=1)
        )
        if not resource_sudo or resource_sudo != slot_sudo.resource_id:
            raise request.prepare_not_found_error()

        planning_sudo = self._planning_of(token_planning, resource_sudo)
        if not planning_sudo._is_slot_in_planning(slot_sudo):
            raise request.prepare_not_found_error()

        slot_sudo.write({"request_to_switch": True})
        return request.redirect(
            f"/planning/{token_planning}/{token_employee}?message=switch"
        )

    @http.route(
        "/planning/<string:token_planning>/<string:token_employee>/cancel_switch/<int:shift_id>",
        type="http",
        auth="public",
        website=True,
    )
    def planning_cancel_shift_switch(
        self, token_planning, token_employee, shift_id, **kwargs
    ):
        slot_sudo = request.env["planning.slot"].sudo().browse(shift_id)
        if not slot_sudo.exists():
            raise request.prepare_not_found_error()

        resource_sudo = (
            request.env["resource.resource"]
            .sudo()
            .search([("planning_token", "=", token_employee)], limit=1)
        )
        if not resource_sudo or resource_sudo != slot_sudo.resource_id:
            raise request.prepare_not_found_error()

        planning_sudo = self._planning_of(token_planning, resource_sudo)
        if not planning_sudo._is_slot_in_planning(slot_sudo):
            raise request.prepare_not_found_error()

        slot_sudo.write({"request_to_switch": False})
        return request.redirect(
            f"/planning/{token_planning}/{token_employee}?message=cancel_switch"
        )

    @http.route(
        "/planning/<string:token_planning>/<string:token_employee>/take_open_shift/<int:shift_id>",
        type="http",
        auth="public",
        website=True,
    )
    def planning_self_assign_with_user_from_calendar(
        self, token_planning, token_employee, shift_id, **kwargs
    ):
        slot_sudo = request.env["planning.slot"].sudo().browse(shift_id)
        if not slot_sudo.exists():
            raise request.prepare_not_found_error()

        resource_sudo = (
            request.env["resource.resource"]
            .sudo()
            .search([("planning_token", "=", token_employee)], limit=1)
        )
        if not resource_sudo:
            raise request.prepare_not_found_error()

        planning_sudo = self._planning_of(token_planning, resource_sudo)
        if not planning_sudo._is_slot_in_planning(slot_sudo):
            raise request.prepare_not_found_error()

        if not slot_sudo.resource_id:
            slot_sudo.write({"resource_id": resource_sudo.id})
            slot_sudo.slot_properties

        return request.redirect(
            f"/planning/{token_planning}/{token_employee}?message=assign"
        )

    @http.route(
        "/planning/assign/<string:token_employee>/<int:shift_id>",
        type="http",
        auth="user",
        website=True,
    )
    def planning_self_assign_with_user(self, token_employee, shift_id, **kwargs):
        slot = request.env["planning.slot"].search([("id", "=", shift_id)], limit=1)
        if not slot:
            raise request.prepare_not_found_error()

        if not request.env.user.employee_id:
            raise request.prepare_not_found_error()

        if not slot.employee_id:
            try:
                slot.action_self_assign()
            except AccessError, UserError:
                raise request.prepare_not_found_error() from None
            slot.slot_properties

        return request.redirect("/odoo/action-planning.planning_action_view_shift")

    @http.route(
        "/planning/unassign/<string:token_employee>/<int:shift_id>",
        type="http",
        auth="user",
        website=True,
    )
    def planning_self_unassign_with_user(self, token_employee, shift_id, **kwargs):
        slot_sudo = (
            request.env["planning.slot"].sudo().search([("id", "=", shift_id)], limit=1)
        )
        if not slot_sudo or not slot_sudo.allow_self_unassign:
            raise request.prepare_not_found_error()

        if slot_sudo.is_unassign_deadline_passed:
            return request.redirect("/odoo/action-planning.planning_action_view_shift")

        if slot_sudo.resource_id.user_id != request.env.user:
            raise request.prepare_not_found_error()

        slot_sudo.write({"resource_id": False})
        slot_sudo.slot_properties

        return request.redirect("/odoo/action-planning.planning_action_view_shift")

    @http.route(
        ["/slot/<string:access_token>.ics"], type="http", auth="public", website=True
    )
    def slot_get_ics_file(self, access_token, **kwargs):
        try:
            slot = (
                request.env["access.link"]
                ._resolve(
                    access_token, model="planning.slot", role="view", action="download"
                )
                .record
            )
        except LinkRefused, LinkLoginRequired:
            raise request.prepare_not_found_error() from None
        if not vobject:
            raise request.prepare_not_found_error()

        calendar = vobject.iCalendar()
        slot._append_ics_events(
            calendar, slot.employee_id.tz or request.env.user.tz or "UTC"
        )
        if not calendar:
            raise request.prepare_not_found_error()
        content = calendar.serialize().encode("utf-8")

        shift_name = (
            slot.role_id.name.replace(" ", "_")
            if slot.role_id
            else request.env._("New_Shift")
        )
        shift_start_time = slot.start_datetime.astimezone(
            timezone(slot._get_tz())
        ).strftime("%m_%d_%H_%M")

        return request.prepare_response(
            content,
            [
                ("Content-Type", "application/octet-stream"),
                ("Content-Length", len(content)),
                (
                    "Content-Disposition",
                    f"attachment; filename=shift_{shift_name}_{shift_start_time}.ics",
                ),
            ],
        )

    @http.route(
        ["/planning/<string:planning_token>/<string:employee_token>.ics"],
        type="http",
        auth="public",
        website=True,
    )
    def planning_get_ics_file(self, planning_token, employee_token, **kwargs):
        resource_sudo = (
            request.env["resource.resource"]
            .sudo()
            .search([("planning_token", "=", employee_token)], limit=1)
        )
        if not resource_sudo:
            raise request.prepare_not_found_error()

        planning_sudo = (
            request.env["planning.planning"]
            .sudo()
            .search([("access_token", "=", planning_token)], limit=1)
        )
        if not (planning_sudo and vobject):
            raise request.prepare_not_found_error()

        calendar = vobject.iCalendar()
        planning_sudo._append_ics_events(calendar, resource_sudo)
        start_name = planning_sudo.date_start.strftime("%m_%d")
        end_name = planning_sudo.date_end.strftime("%m_%d")
        response = request.prepare_response(calendar.serialize())
        response.headers.add("Content-Type", "text/calendar")
        response.headers.add(
            "Content-Disposition",
            "attachment",
            filename=f"planning_{start_name}_to_{end_name}.ics",
        )
        return response

    @staticmethod
    def _get_hours_intervals(checkin_min, checkout_max, event_hour_min, event_hour_max):
        if event_hour_min is not None and checkin_min > event_hour_min:
            mintime = max(event_hour_min - 2, 0)
        else:
            mintime = checkin_min
        if event_hour_max and checkout_max < event_hour_max:
            maxtime = min(event_hour_max + 2, 24)
        else:
            maxtime = checkout_max

        return mintime, maxtime
