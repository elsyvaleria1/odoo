from datetime import UTC, date, datetime
from urllib.parse import quote, unquote_plus
from urllib.parse import urlencode as url_encode
from zoneinfo import ZoneInfoNotFoundError

from babel.dates import format_date, format_datetime, format_time
from dateutil.relativedelta import relativedelta
from markupsafe import Markup
from werkzeug.exceptions import BadRequest, Forbidden, NotFound

from odoo import fields, http
from odoo.fields import Command, Domain
from odoo.http import request, route
from odoo.libs.datetime import localize_standard, wall_to_utc
from odoo.libs.datetime import timezone as get_timezone
from odoo.libs.json import loads as json_loads
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT as dtf
from odoo.tools import email_normalize
from odoo.tools.mail import is_html_empty
from odoo.tools.misc import babel_locale_parse, get_lang
from odoo.tools.translate import LazyTranslate
from odoo.tools.urls import keep_query

from odoo.addons.base.models.res_partner import _selection_timezones
from odoo.addons.phone_validation.tools import phone_validation
from odoo.addons.web.controllers.utils import Fragment, render_fragments

_lt = LazyTranslate(__name__)

GUEST_LIMIT = 10


def _formated_weekdays(locale):
    formated_days = [
        format_date(date(2021, 3, day), "EEE", locale=locale) for day in range(1, 8)
    ]
    first_weekday_index = babel_locale_parse(locale).first_week_day
    return list(formated_days[first_weekday_index:] + formated_days)[:7]


class AppointmentController(http.Controller):

    @route(["/book/<string:short_code>"], type="http", auth="public", website=True)
    def appointment_invite(self, short_code, **kwargs):
        invitation = (
            request.env["appointment.invite"]
            .sudo()
            .search([("short_code", "=", short_code)])
        )
        if not invitation:
            raise NotFound
        return request.redirect(f"{invitation.redirect_url}&{url_encode(kwargs)}")


    @route(
        ["/calendar", "/calendar/page/<int:page>"],
        type="http",
        auth="public",
        website=True,
        sitemap=True,
    )
    def appointment_type_index_old(self, page=1, **kwargs):
        return request.redirect(
            "/appointment%s?%s"
            % ("/page/%s" % page if page != 1 else "", url_encode(kwargs)),
            code=301,
        )

    @route(
        ["/appointment", "/appointment/page/<int:page>"],
        type="http",
        auth="public",
        website=True,
        sitemap=True,
        list_as_website_content=_lt("Appointments"),
    )
    def appointment_type_index(self, page=1, **kwargs):
        kwargs["domain"] = self._appointment_website_domain()
        return request.render(
            "calendar.appointments_list_layout",
            self._prepare_appointments_list_data(**kwargs),
        )


    def _prepare_appointments_list_data(self, appointment_types=None, **kwargs):

        appointment_types = (
            appointment_types
            or self._get_checked_private_appointment_types(
                kwargs.get("filter_appointment_type_ids"),
                kwargs.get("filter_staff_user_ids"),
                kwargs.get("filter_resource_ids"),
                kwargs.get("invite_token"),
                domain=self._appointments_base_domain(
                    filter_appointment_type_ids=kwargs.get(
                        "filter_appointment_type_ids"
                    ),
                    search=kwargs.get("search"),
                    invite_token=kwargs.get("invite_token"),
                    additional_domain=kwargs.get("domain"),
                    filter_countries=True,
                ),
            )
        )
        appointment_types = appointment_types.sorted("is_published", reverse=True)
        return {
            "appointment_types": appointment_types,
            "invite_token": kwargs.get("invite_token"),
            "filter_appointment_type_ids": kwargs.get("filter_appointment_type_ids"),
            "filter_staff_user_ids": kwargs.get("filter_staff_user_ids"),
            "filter_resource_ids": kwargs.get("filter_resource_ids"),
        }

    @classmethod
    def _appointments_base_domain(
        cls,
        filter_appointment_type_ids,
        search=False,
        invite_token=False,
        additional_domain=None,
        filter_countries=False,
    ):

        domain = Domain(additional_domain or Domain.TRUE)
        if filter_appointment_type_ids:
            filter_appointment_type_ids = unquote_plus(filter_appointment_type_ids)
            domain &= Domain(
                "id",
                "in",
                cls._parse_json_param(
                    filter_appointment_type_ids, name="filter_appointment_type_ids"
                ),
            )

        if not invite_token and filter_countries:
            country = cls._get_customer_country()
            if country:
                country_domain = Domain("country_ids", "in", [False, country.id])
                domain &= country_domain

        if search:
            domain &= Domain("name", "ilike", search)

        if request.env.user.share and not invite_token:
            domain &= Domain("is_published", "=", True)

        return domain

    def _appointment_website_domain(self):
        return [
            "|",
            ("end_datetime", "=", False),
            ("end_datetime", ">=", datetime.now(UTC)),
        ]


    @route(
        ["/calendar/<string:appointment_type>"],
        type="http",
        auth="public",
        website=True,
        sitemap=True,
    )
    def appointment_type_page_old(self, appointment_type, **kwargs):
        return request.redirect(
            "/appointment/%s?%s"
            % (request.env["ir.http"]._unslug(appointment_type)[1], keep_query("*")),
            code=301,
        )

    @route(
        ["/appointment/<int:appointment_type_id>"],
        type="http",
        auth="public",
        website=True,
        sitemap=True,
    )
    def appointment_type_page(
        self,
        appointment_type_id,
        state=False,
        staff_user_id=False,
        resource_selected_id=False,
        **kwargs,
    ):
        kwargs["domain"] = self._appointments_base_domain(
            filter_appointment_type_ids=kwargs.get("filter_appointment_type_ids"),
            search=kwargs.get("search"),
            invite_token=kwargs.get("invite_token"),
            additional_domain=kwargs.get("domain"),
        )
        available_appointments = self._get_checked_private_appointment_types(
            kwargs.get("filter_appointment_type_ids"),
            kwargs.get("filter_staff_user_ids"),
            kwargs.get("filter_resource_ids"),
            kwargs.get("invite_token"),
            domain=kwargs["domain"],
        )
        appointment_type = available_appointments.filtered(
            lambda appt: appt.id == int(appointment_type_id)
        )

        kwargs["available_appointments"] = available_appointments
        if not appointment_type:
            raise NotFound

        page_values = self._prepare_appointment_type_page_values(
            appointment_type, staff_user_id, resource_selected_id, **kwargs
        )
        return self._get_appointment_type_page_view(
            appointment_type, page_values, state, **kwargs
        )

    def _get_slots_from_filter(
        self, appointment_type, filter_records, asked_capacity=1
    ):
        slots = appointment_type._get_appointment_slots(
            request.session["timezone"],
            filter_users=filter_records
            if appointment_type.schedule_based_on == "users"
            else None,
            filter_resources=filter_records
            if appointment_type.schedule_based_on == "resources"
            else None,
            asked_capacity=asked_capacity,
        )
        return {
            "slots": slots,
            "month_first_available": next(
                (month["id"] for month in slots if month["has_availabilities"]), False
            ),
        }

    def _prepare_slots_values(
        self,
        appointment_type,
        selected_filter_record,
        default_filter_record,
        possible_filter_records,
        asked_capacity=1,
    ):
        if selected_filter_record:
            return self._get_slots_from_filter(
                appointment_type, selected_filter_record, asked_capacity
            )

        if not default_filter_record:
            return self._get_slots_from_filter(
                appointment_type, possible_filter_records, asked_capacity
            )

        ordered_filters = default_filter_record | possible_filter_records
        for current_filter in ordered_filters:
            values = self._get_slots_from_filter(
                appointment_type, current_filter, asked_capacity
            )
            if values["month_first_available"] is not False:
                if appointment_type.schedule_based_on == "users":
                    values["user_selected"] = current_filter
                else:
                    values["resource_selected"] = current_filter
                return values
        return values

    def _get_appointment_type_page_view(
        self, appointment_type, page_values, state=False, **kwargs
    ):
        request.session["timezone"] = self._get_default_timezone(appointment_type)
        asked_capacity = self._parse_int_param(
            kwargs.get("asked_capacity"), default=1, name="asked_capacity"
        )
        filter_prefix = (
            "user" if appointment_type.schedule_based_on == "users" else "resource"
        )
        slots_values = self._prepare_slots_values(
            appointment_type,
            selected_filter_record=page_values[f"{filter_prefix}_selected"],
            default_filter_record=page_values[f"{filter_prefix}_default"],
            possible_filter_records=page_values[f"{filter_prefix}s_possible"],
            asked_capacity=asked_capacity,
        )
        formated_days = _formated_weekdays(get_lang(request.env).code)

        render_params = {
            "appointment_type": appointment_type,
            "is_html_empty": is_html_empty,
            "formated_days": formated_days,
            "main_object": appointment_type,
            "month_kept_from_update": False,
            "state": state,
            "timezone": request.session["timezone"],
            **page_values,
            **slots_values,
        }
        return request.render(
            "calendar.appointment_info",
            render_params,
            headers={"Cache-Control": "no-store"},
        )

    def _prepare_appointment_type_page_values(
        self,
        appointment_type,
        staff_user_id=False,
        resource_selected_id=False,
        **kwargs,
    ):
        filter_staff_user_ids = self._parse_json_param(
            unquote_plus(kwargs.get("filter_staff_user_ids") or "[]"),
            name="filter_staff_user_ids",
        )
        filter_resource_ids = self._parse_json_param(
            unquote_plus(kwargs.get("filter_resource_ids") or "[]"),
            name="filter_resource_ids",
        )
        users_possible = self._get_possible_staff_users(
            appointment_type, filter_staff_user_ids
        )
        user_forced = self._get_forced_staff_user(appointment_type, users_possible)
        resources_possible = self._get_possible_resources(
            appointment_type, filter_resource_ids
        )
        user_default = user_selected = request.env["res.users"]
        resource_default = resource_selected = request.env["resource.resource"]
        staff_user_id = int(staff_user_id) if staff_user_id else False
        resource_selected_id = (
            int(resource_selected_id) if resource_selected_id else False
        )

        if appointment_type.schedule_based_on == "users":
            if (
                not appointment_type.is_auto_assign
                and not appointment_type.is_date_first
                and users_possible
            ):
                if staff_user_id and staff_user_id in users_possible.ids:
                    user_selected = (
                        request.env["res.users"].sudo().browse(staff_user_id)
                    )
                user_default = users_possible[0]
            elif appointment_type.is_auto_assign and len(users_possible) == 1:
                user_default = users_possible[0]
        elif resources_possible:
            if (
                resource_selected_id
                and resource_selected_id in resources_possible.ids
                and not (
                    appointment_type.is_date_first
                    and not appointment_type.is_auto_assign
                )
            ):
                resource_selected = (
                    request.env["resource.resource"].sudo().browse(resource_selected_id)
                )
            elif (
                not appointment_type.is_auto_assign
                and not appointment_type.is_date_first
            ):
                resource_default = resources_possible[0]
        if appointment_type.manage_capacity:
            if appointment_type.schedule_based_on == "users":
                max_capacity_possible = appointment_type.user_capacity
            else:
                max_capacity_possible = self._get_max_capacity_possible(
                    resources_possible,
                    resource_selected_id=(resource_selected or resource_default).id,
                )
        else:
            max_capacity_possible = 1
        allowed_max_capacity = int(
            request.env.registry.settings.get(
                request.env, "appointment.resource_max_capacity_allowed", 12
            )
        )

        return {
            "asked_capacity": self._parse_int_param(
                kwargs["asked_capacity"], name="asked_capacity"
            )
            if kwargs.get("asked_capacity")
            else False,
            "available_appointments": kwargs["available_appointments"],
            "filter_appointment_type_ids": kwargs.get("filter_appointment_type_ids"),
            "filter_staff_user_ids": kwargs.get("filter_staff_user_ids"),
            "filter_resource_ids": kwargs.get("filter_resource_ids"),
            "hide_select_dropdown": len(
                users_possible
                if appointment_type.schedule_based_on == "users"
                else resources_possible
            )
            <= 1,
            "invite_token": kwargs.get("invite_token"),
            "max_capacity": min(allowed_max_capacity, max_capacity_possible),
            "resource_default": resource_default,
            "resource_selected": resource_selected,
            "resources_possible": resources_possible,
            "user_default": user_default,
            "user_forced": user_forced,
            "user_selected": user_selected,
            "users_possible": users_possible,
        }


    @http.route(
        "/appointment/<int:appointment_type_id>/avatar",
        type="http",
        auth="public",
        cors="*",
    )
    def appointment_staff_user_avatar(
        self, appointment_type_id, user_id=False, avatar_size=512
    ):
        user = request.env["res.users"].sudo().browse(int(user_id))
        appointment_type = (
            request.env["appointment.type"].sudo().browse(appointment_type_id)
        )

        user = (
            user
            if appointment_type.show_avatars and user in appointment_type.staff_user_ids
            else request.env["res.users"]
        )
        return (
            request.env["ir.binary"]
            ._get_stream_image_from_record(
                user,
                field_name=self._get_avatar_field_name(avatar_size),
                placeholder="mail/static/src/img/smiley/avatar.jpg",
            )
            .prepare_response()
        )

    def _get_possible_resources(self, appointment_type, filter_resource_ids):
        if not filter_resource_ids:
            return appointment_type.resource_ids
        return appointment_type.resource_ids.filtered(
            lambda resource: resource.id in filter_resource_ids
        )

    def _get_forced_staff_user(self, appointment_type, possible_staff_users):
        return self.env["res.users"]

    def _get_possible_staff_users(self, appointment_type, filter_staff_user_ids):
        if not filter_staff_user_ids:
            possible_staff_users = appointment_type.staff_user_ids
        else:
            possible_staff_users = appointment_type.staff_user_ids.filtered(
                lambda staff_user: staff_user.id in filter_staff_user_ids
            )
        return (
            self._get_forced_staff_user(appointment_type, possible_staff_users)
            or possible_staff_users
        )


    @http.route(
        "/appointment/<int:appointment_type_id>/resource_avatar",
        type="http",
        auth="public",
    )
    def appointment_resource_avatar(
        self, appointment_type_id, resource_id=False, avatar_size=512
    ):
        resource = request.env["resource.resource"].sudo().browse(int(resource_id))
        appointment_type = (
            request.env["appointment.type"].sudo().browse(appointment_type_id)
        )

        pictured = (
            resource._get_booking_picture()
            if appointment_type.show_avatars
            and resource in appointment_type.resource_ids
            else request.env["resource.resource"]
        )
        return (
            request.env["ir.binary"]
            ._get_stream_image_from_record(
                pictured,
                field_name=self._get_avatar_field_name(avatar_size),
            )
            .prepare_response()
        )


    @staticmethod
    def _get_checked_private_appointment_types(
        appointment_type_ids, staff_user_ids, resource_ids, invite_token, domain=False
    ):
        appointment_type_ids = AppointmentController._parse_json_param(
            unquote_plus(appointment_type_ids or "[]"), name="appointment_type_ids"
        )
        if not appointment_type_ids and domain is not False:
            appointment_type_ids = (
                request.env["appointment.type"].sudo().search(domain).ids
            )
        elif not appointment_type_ids:
            raise NotFound

        appointment_types = (
            request.env["appointment.type"].browse(appointment_type_ids).exists()
        )
        staff_users = (
            request.env["res.users"]
            .sudo()
            .browse(
                AppointmentController._parse_json_param(
                    unquote_plus(staff_user_ids or "[]"), name="staff_user_ids"
                )
            )
        )
        resources = (
            request.env["resource.resource"]
            .sudo()
            .browse(
                AppointmentController._parse_json_param(
                    unquote_plus(resource_ids or "[]"), name="resource_ids"
                )
            )
        )

        if invite_token:
            appt_invite = (
                request.env["appointment.invite"]
                .sudo()
                .search([("access_token", "=", invite_token)])
            )
            if not appt_invite or not appt_invite._check_appointments_params(
                appointment_types, staff_users, resources
            ):
                raise Forbidden
            appointment_types = appointment_types.sudo()
        elif request.env.user.share:
            appointment_types = (
                appointment_types.sudo().filtered("is_published") or appointment_types
            )

        if not appointment_types.browse().has_access("read"):
            raise Forbidden
        appointment_types = appointment_types._filtered_access("read")

        if domain:
            appointment_types = appointment_types.filtered_domain(domain)
        return appointment_types


    @http.route(
        ["/appointment/<int:appointment_type_id>/info"],
        type="http",
        auth="public",
        website=True,
        sitemap=False,
    )
    def appointment_type_id_form(
        self,
        appointment_type_id,
        date_time,
        duration,
        staff_user_id=None,
        resource_selected_id=None,
        available_resource_ids=None,
        asked_capacity=1,
        **kwargs,
    ):
        domain = self._appointments_base_domain(
            filter_appointment_type_ids=kwargs.get("filter_appointment_type_ids"),
            search=kwargs.get("search"),
            invite_token=kwargs.get("invite_token"),
        )
        available_appointments = self._get_checked_private_appointment_types(
            kwargs.get("filter_appointment_type_ids"),
            kwargs.get("filter_staff_user_ids"),
            kwargs.get("filter_resource_ids"),
            kwargs.get("invite_token"),
            domain=domain,
        )
        appointment_type = available_appointments.filtered(
            lambda appt: appt.id == int(appointment_type_id)
        )

        if not appointment_type:
            raise NotFound

        if not self._check_appointment_is_valid_slot(
            appointment_type,
            staff_user_id,
            resource_selected_id,
            available_resource_ids,
            date_time,
            duration,
            asked_capacity,
            **kwargs,
        ):
            raise NotFound

        partner = self._get_customer_partner()
        partner_data = (
            {
                "name": partner.name,
                "email": partner.email,
                "phone": partner._phone_get_number().number,
            }
            if partner
            else {}
        )
        allday = bool(int(kwargs.get("allday", 0)))
        date_time = unquote_plus(date_time)
        date_time_object = datetime.strptime(date_time, dtf)
        day_name = format_datetime(
            date_time_object, "EEE", locale=get_lang(request.env).code
        )
        date_formated = format_date(
            date_time_object.date(), locale=get_lang(request.env).code
        )
        time_locale = format_time(
            date_time_object.time(), locale=get_lang(request.env).code, format="short"
        )
        resource = (
            request.env["resource.resource"].sudo().browse(int(resource_selected_id))
            if resource_selected_id
            else request.env["resource.resource"]
        )
        staff_user = (
            appointment_type.staff_user_ids.filtered(
                lambda user: user.id == int(staff_user_id)
            )
            if staff_user_id
            else request.env["res.users"]
        )
        users_possible = self._get_possible_staff_users(
            appointment_type,
            self._parse_json_param(
                unquote_plus(kwargs.get("filter_staff_user_ids") or "[]"),
                name="filter_staff_user_ids",
            ),
        )
        resources_possible = self._get_possible_resources(
            appointment_type,
            self._parse_json_param(
                unquote_plus(kwargs.get("filter_resource_ids") or "[]"),
                name="filter_resource_ids",
            ),
        )
        return request.render(
            "calendar.appointment_form",
            {
                "partner_data": partner_data,
                "allday": allday,
                "appointment_type": appointment_type,
                "available_appointments": available_appointments,
                "is_html_empty": is_html_empty,
                "main_object": appointment_type,
                "datetime": date_time,
                "date_locale": f"{day_name} {date_formated}",
                "time_locale": time_locale,
                "datetime_str": date_time,
                "duration_str": duration,
                "duration": float(duration),
                "staff_user": staff_user,
                "resource": resource,
                "asked_capacity": int(asked_capacity),
                "timezone": request.session.get("timezone")
                or appointment_type.appointment_tz,
                "users_possible": users_possible,
                "resources_possible": resources_possible,
                "available_resource_ids": available_resource_ids,
                "login_with_redirect_url": f"/web/login?redirect={quote(request.httprequest.full_path)}",
                "main_phone_question": appointment_type._get_main_phone_question(),
            },
        )

    def _check_appointment_is_valid_slot(
        self,
        appointment_type,
        staff_user_id,
        resource_selected_id,
        available_resource_ids,
        start_dt,
        duration,
        asked_capacity,
        **kwargs,
    ):
        if not appointment_type or not start_dt or not duration:
            return False
        if appointment_type.schedule_based_on == "users" and not staff_user_id:
            return False
        if (
            appointment_type.schedule_based_on == "resources"
            and not resource_selected_id
            and not available_resource_ids
        ):
            return False

        staff_user = None
        resources = None
        try:
            allday = bool(int(kwargs.get("allday", 0)))
            duration = float(duration)
            asked_capacity = int(asked_capacity)
            staff_user_id = int(staff_user_id) if staff_user_id else False
            resource_selected_id = (
                int(resource_selected_id) if resource_selected_id else False
            )
            available_resource_ids = (
                json_loads(unquote_plus(available_resource_ids))
                if available_resource_ids
                else False
            )
            start_dt = unquote_plus(start_dt)
        except ValueError:
            return False

        try:
            session_tz = (
                request.session.get("timezone") or appointment_type.appointment_tz
            )
            if not allday:
                tz_info = get_timezone(session_tz)
            else:
                tz_info = get_timezone(appointment_type.appointment_tz)
            start_dt_utc = localize_standard(
                fields.Datetime.from_string(start_dt), tz_info
            ).astimezone(UTC)
        except ValueError, ZoneInfoNotFoundError:
            return False

        if start_dt_utc < datetime.today().astimezone(UTC):
            return False

        if appointment_type.schedule_based_on == "users":
            staff_user = (
                request.env["res.users"].sudo().search([("id", "=", staff_user_id)])
            )
        else:
            resources = (
                request.env["resource.resource"]
                .sudo()
                .search([("id", "in", available_resource_ids)])
            )
            if resource_selected_id:
                resource = (
                    request.env["resource.resource"]
                    .sudo()
                    .search([("id", "=", resource_selected_id)])
                )
                if not resource or resource not in resources:
                    return False

        return appointment_type._check_appointment_is_valid_slot(
            staff_user,
            resources,
            asked_capacity,
            session_tz,
            start_dt_utc,
            duration,
            allday,
        )

    @http.route(
        ["/appointment/<int:appointment_type_id>/submit"],
        type="http",
        auth="public",
        website=True,
        methods=["POST"],
        csrf=False,
    )
    def appointment_form_submit(
        self,
        appointment_type_id,
        datetime_str,
        duration_str,
        name,
        email,
        staff_user_id=None,
        available_resource_ids=None,
        asked_capacity=1,
        guest_emails_str=None,
        **kwargs,
    ):
        csrf_token = request.params.pop("csrf_token", None)
        if request.session.uid and not request.is_valid_csrf(csrf_token):
            raise BadRequest("Session expired (invalid CSRF token)")

        domain = self._appointments_base_domain(
            filter_appointment_type_ids=kwargs.get("filter_appointment_type_ids"),
            search=kwargs.get("search"),
            invite_token=kwargs.get("invite_token"),
        )

        available_appointments = self._get_checked_private_appointment_types(
            kwargs.get("filter_appointment_type_ids"),
            kwargs.get("filter_staff_user_ids"),
            kwargs.get("filter_resource_ids"),
            kwargs.get("invite_token"),
            domain=domain,
        )
        appointment_type = available_appointments.filtered(
            lambda appt: appt.id == int(appointment_type_id)
        )

        if not appointment_type:
            raise NotFound
        timezone = request.session.get("timezone") or appointment_type.appointment_tz
        tz_session = get_timezone(timezone)
        allday = bool(int(kwargs.get("allday", 0)))
        datetime_str = unquote_plus(datetime_str)
        start_dt = fields.Datetime.from_string(datetime_str)
        if allday:
            date_start = wall_to_utc(
                start_dt, get_timezone(appointment_type.appointment_tz)
            )
        else:
            date_start = wall_to_utc(start_dt, tz_session)
        duration = float(duration_str)
        date_end = date_start + relativedelta(hours=duration)
        invite_token = kwargs.get("invite_token")

        staff_user = request.env["res.users"]
        resources = request.env["resource.resource"]
        resource_ids = None
        asked_capacity = int(asked_capacity)
        resources_remaining_capacity = None
        users_remaining_capacity = None
        if appointment_type.schedule_based_on == "resources":
            resource_ids = self._parse_json_param(
                unquote_plus(available_resource_ids), name="available_resource_ids"
            )
            resources = (
                request.env["resource.resource"].sudo().browse(resource_ids).exists()
            )
            if any(
                resource not in appointment_type.resource_ids for resource in resources
            ):
                raise NotFound
            resources._lock_for_integrity()
            resources_remaining_capacity = (
                appointment_type._get_resources_remaining_capacity(
                    resources, date_start, date_end, with_combinable_resources=False
                )
            )
            if (
                resources_remaining_capacity["total_remaining_capacity"]
                < asked_capacity
            ):
                return request.redirect(
                    "/appointment/%s?%s"
                    % (appointment_type.id, keep_query("*", state="failed-resource"))
                )
        else:
            staff_user = (
                request.env["res.users"]
                .sudo()
                .search([("id", "=", int(staff_user_id))])
            )
            if staff_user not in appointment_type.staff_user_ids:
                raise NotFound
            staff_user._get_or_create_calendar_event_resource()
            users_remaining_capacity = appointment_type._get_users_remaining_capacity(
                staff_user, date_start, date_end
            )
            if (
                staff_user
                and not staff_user.partner_id._is_calendar_available(
                    date_start, date_end, appointment_type
                )
            ) or users_remaining_capacity["total_remaining_capacity"] < asked_capacity:
                return request.redirect(
                    "/appointment/%s?%s"
                    % (appointment_type.id, keep_query("*", state="failed-staff-user"))
                )

        if not appointment_type._check_appointment_is_valid_slot(
            staff_user,
            resources,
            asked_capacity,
            timezone,
            date_start.replace(tzinfo=UTC),
            duration,
            allday,
        ):
            raise NotFound

        guests = None
        if appointment_type.allow_guests:
            if guest_emails_str:
                guests = (
                    request.env["calendar.event"]
                    .sudo()
                    ._get_or_create_partners(guest_emails_str, limit=GUEST_LIMIT)
                )

        partner_inputs = appointment_type.question_ids._get_form_answers(kwargs)
        main_phone_question = appointment_type._get_main_phone_question()
        phone = (
            partner_inputs.get(main_phone_question.id) if main_phone_question else None
        )
        question_description = appointment_type.question_ids._get_answers_description(
            partner_inputs
        )

        customer = (
            self._get_customer_partner() if csrf_token else self.env["res.partner"]
        )

        new_customer = not customer.email
        if (
            not new_customer
            and customer.email != email
            and customer.email_normalized != email_normalize(email)
        ):
            new_customer = True
        if not new_customer:
            if not customer.phone_ids:
                if phone:
                    customer.phone_ids = [
                        Command.create(
                            {
                                "number": customer._phone_format(number=phone) or phone,
                                "type": "mobile",
                            }
                        )
                    ]
            elif main_phone_question:
                if phone:
                    customer_phone_fmt = customer._phone_format(fname="phone_ids")
                    input_country = self._get_customer_country()
                    input_phone_fmt = phone_validation.phone_format(
                        phone,
                        input_country.code,
                        input_country.phone_code,
                        force_format="E164",
                        raise_exception=False,
                    )
                    new_customer = (
                        customer._phone_get_number().number != phone
                        and customer_phone_fmt != input_phone_fmt
                    )
                else:
                    new_customer = True

        if new_customer:
            customer = customer.sudo().create(
                {
                    "name": name,
                    "phone_ids": [
                        Command.create(
                            {
                                "number": customer._phone_format(
                                    number=phone, country=self._get_customer_country()
                                )
                                or phone,
                                "type": "mobile",
                            }
                        )
                    ]
                    if phone
                    else False,
                    "email": email,
                    "lang": request.lang.code,
                }
            )

        description = Markup("<br/>").join(
            request.env["calendar.event"]._prepare_partner_contact_details_html(
                request.env._("Contact Details"), customer
            )
        )
        if question_description:
            description += Markup("<br/>") + question_description

        booking_line_values = []
        if appointment_type.schedule_based_on == "resources":
            capacity_to_assign = asked_capacity
            for resource in resources:
                resource_remaining_capacity = resources_remaining_capacity.get(resource)
                new_capacity_reserved = min(
                    resource_remaining_capacity, capacity_to_assign, resource.capacity
                )
                capacity_to_assign -= new_capacity_reserved
                booking_line_values.append(
                    {
                        "resource_id": resource.id,
                        "capacity_reserved": new_capacity_reserved,
                        "capacity_used": new_capacity_reserved
                        if not resource.booking_exclusive
                        and appointment_type.manage_capacity
                        else resource.capacity
                        if appointment_type.manage_capacity
                        else 1,
                    }
                )
        else:
            user_remaining_capacity = users_remaining_capacity[
                "total_remaining_capacity"
            ]
            new_capacity_reserved = min(
                user_remaining_capacity, asked_capacity, appointment_type.user_capacity
            )
            booking_line_values.append(
                {
                    "capacity_reserved": new_capacity_reserved,
                    "capacity_used": new_capacity_reserved,
                }
            )

        if invite_token:
            appointment_invite = (
                request.env["appointment.invite"]
                .sudo()
                .search([("access_token", "=", invite_token)])
            )
        else:
            appointment_invite = request.env["appointment.invite"]

        return self._handle_appointment_form_submission(
            appointment_type,
            date_start,
            date_end,
            description,
            duration,
            allday,
            partner_inputs,
            name,
            customer,
            appointment_invite,
            guests,
            staff_user,
            asked_capacity,
            booking_line_values,
            self._prepare_extra_calendar_event_vals(**kwargs),
        )

    def _prepare_extra_calendar_event_vals(self, **kwargs):
        return {}

    def _handle_appointment_form_submission(
        self,
        appointment_type,
        date_start,
        date_end,
        description,
        duration,
        allday,
        answers,
        name,
        customer,
        appointment_invite,
        guests=None,
        staff_user=None,
        asked_capacity=1,
        booking_line_values=None,
        extra_calendar_event_params=None,
    ):
        event = (
            request.env["calendar.event"]
            .with_context(
                mail_notify_author=True,
                mail_create_nolog=True,
                mail_create_nosubscribe=True,
                allowed_company_ids=self._get_allowed_companies(
                    staff_user or appointment_type.create_uid
                ).ids,
            )
            .sudo()
            .with_context(skip_contact_description=True)
            .create(
                {
                    **appointment_type._prepare_calendar_event_values(
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
                        date_start,
                        date_end,
                    ),
                    **(extra_calendar_event_params or {}),
                    "booking_capacity_enforced": True,
                }
            )
        )
        response = (
            request.env["survey.user_input"]
            .sudo()
            .create(
                {
                    "appointment_type_id": appointment_type.id,
                    "calendar_event_id": event.id,
                    "partner_id": customer.id,
                    "predefined_question_ids": [
                        Command.set(appointment_type.question_ids.ids)
                    ],
                }
            )
        )
        response._submit_answers(answers)
        return request.redirect(
            f"/calendar/view/{event.booking_access_token}?partner_id={customer.id}&{keep_query('*', state='new')}"
        )


    def _get_allowed_companies(self, organizer):
        return organizer.company_ids

    def _get_customer_partner(self):
        partner = request.env["res.partner"]
        if not request.env.user._is_public():
            partner = request.env.user.partner_id
        return partner

    @staticmethod
    def _get_customer_country():
        country = request.env["res.country"]
        if request.geoip.country_code:
            country = country.search([("code", "=", request.geoip.country_code)])
        if not country:
            country = (
                request.env.user.country_id
                if not request.env.user._is_public()
                else country
            )
        return country

    def _parse_int_param(self, value, default=None, name="parameter"):
        if value is None or value == "":
            if default is None:
                raise BadRequest(f"Missing {name}")
            return default
        try:
            return int(value)
        except (TypeError, ValueError) as err:
            raise BadRequest(f"Invalid {name}") from err

    @staticmethod
    def _parse_json_param(value, name="parameter"):
        try:
            return json_loads(value)
        except (TypeError, ValueError) as err:
            raise BadRequest(f"Invalid {name}") from err

    def _get_avatar_field_name(self, avatar_size):
        size = self._parse_int_param(avatar_size, default=512, name="avatar_size")
        if size not in (128, 256, 512, 1024, 1920):
            size = 512
        return "avatar_%d" % size

    def _is_valid_timezone(self, timezone) -> bool:
        return bool(timezone) and timezone in dict(_selection_timezones(self))

    def _get_default_timezone(self, appointment_type):
        if "timezone" in request.session:
            return request.session["timezone"]
        if appointment_type.location_id:
            return appointment_type.appointment_tz
        cookie = request.cookies.get("tz")
        if self._is_valid_timezone(cookie):
            return cookie
        return appointment_type.appointment_tz

    def _get_max_capacity_possible(self, resources, resource_selected_id=False):
        if not resources:
            return 1
        possible_combinations = resources._get_filtered_possible_capacity_combinations(
            1, {}
        )
        capacity_to_resources = {
            resource_ids: capacity
            for resource_ids, capacity in possible_combinations
            if not resource_selected_id or int(resource_selected_id) in resource_ids
        }
        return max(capacity_to_resources.values()) if capacity_to_resources else 1


    @http.route(
        ["/appointment/get_upcoming_appointments"], type="jsonrpc", auth="public"
    )
    def get_upcoming_appointments(self, calendar_event_access_tokens=False):
        common_domain = Domain("appointment_type_id", "!=", False) & Domain(
            "start", ">", datetime.now()
        )
        if not request.env.user._is_public():
            domain = Domain(
                "appointment_booker_id", "=", request.env.user.partner_id.id
            )
        else:
            Event = request.env["calendar.event"]
            domain = Domain(
                "id",
                "in",
                [
                    Event._from_booking_token(token).id
                    for token in (calendar_event_access_tokens or [])[:50]
                    if isinstance(token, str)
                ],
            )
        upcoming_appointments = (
            request.env["calendar.event"]
            .sudo()
            .search_read(
                common_domain & domain,
                fields=[
                    "booking_access_token",
                    "appointment_booker_id",
                    "appointment_type_id",
                    "start",
                ],
                order="start",
                limit=20,
            )
        )
        for appointment in upcoming_appointments:
            appointment["access_token"] = appointment.pop("booking_access_token")
        if not upcoming_appointments:
            return False
        return {
            "next_upcoming_appointment": upcoming_appointments[0],
            "valid_access_tokens": [
                appt["access_token"] for appt in upcoming_appointments
            ]
            if request.env.user._is_public()
            else [],
        }

    @http.route(
        ["/appointment/<int:appointment_type_id>/get_message_intro"],
        type="jsonrpc",
        auth="public",
        methods=["POST"],
        website=True,
    )
    def get_appointment_message_intro(self, appointment_type_id, **kwargs):
        domain = self._appointments_base_domain(
            filter_appointment_type_ids=kwargs.get("filter_appointment_type_ids"),
            search=kwargs.get("search"),
            invite_token=kwargs.get("invite_token"),
        )

        available_appointments = self._get_checked_private_appointment_types(
            kwargs.get("filter_appointment_type_ids"),
            kwargs.get("filter_staff_user_ids"),
            kwargs.get("filter_resource_ids"),
            kwargs.get("invite_token"),
            domain=domain,
        )
        appointment_type = available_appointments.filtered(
            lambda appt: appt.id == int(appointment_type_id)
        )

        if not appointment_type:
            raise NotFound

        return appointment_type.message_intro or ""

    @http.route(
        ["/appointment/<int:appointment_type_id>/update_available_slots"],
        type="jsonrpc",
        auth="public",
        website=True,
    )
    def appointment_update_available_slots(
        self,
        appointment_type_id,
        staff_user_id=None,
        resource_selected_id=None,
        asked_capacity=1,
        timezone=None,
        **kwargs,
    ):
        domain = self._appointments_base_domain(
            filter_appointment_type_ids=kwargs.get("filter_appointment_type_ids"),
            search=kwargs.get("search"),
            invite_token=kwargs.get("invite_token"),
        )

        available_appointments = self._get_checked_private_appointment_types(
            kwargs.get("filter_appointment_type_ids"),
            kwargs.get("filter_staff_user_ids"),
            kwargs.get("filter_resource_ids"),
            kwargs.get("invite_token"),
            domain=domain,
        )
        appointment_type = available_appointments.filtered(
            lambda appt: appt.id == int(appointment_type_id)
        )

        if not appointment_type:
            raise NotFound

        if not self._is_valid_timezone(timezone):
            timezone = appointment_type.appointment_tz
        request.session["timezone"] = timezone
        filter_staff_user_ids = self._parse_json_param(
            kwargs.get("filter_staff_user_ids") or "[]", name="filter_staff_user_ids"
        )
        filter_resource_ids = self._parse_json_param(
            kwargs.get("filter_resource_ids") or "[]", name="filter_resource_ids"
        )
        filter_users = filter_resources = False
        if staff_user_id:
            filter_users = request.env["res.users"].sudo().browse(int(staff_user_id))
        elif resource_selected_id:
            filter_resources = (
                request.env["resource.resource"]
                .sudo()
                .browse(int(resource_selected_id))
            )
        else:
            filter_users = self._get_possible_staff_users(
                appointment_type, filter_staff_user_ids
            )
            filter_resources = self._get_possible_resources(
                appointment_type, filter_resource_ids
            )
        asked_capacity = int(asked_capacity)
        slots = appointment_type._get_appointment_slots(
            request.session["timezone"],
            filter_users,
            filter_resources,
            asked_capacity=asked_capacity,
        )
        month_first_available = next(
            (month["id"] for month in slots if month["has_availabilities"]), False
        )
        month_before_update = kwargs.get("month_before_update")
        month_kept_from_update = (
            next(
                (
                    month["id"]
                    for month in slots
                    if month["month"] == month_before_update
                ),
                False,
            )
            if month_before_update
            else False
        )
        formated_days = _formated_weekdays(get_lang(request.env).code)
        if not appointment_type.manage_capacity:
            max_possible_capacity = 1
        elif appointment_type.schedule_based_on == "users":
            max_possible_capacity = appointment_type.user_capacity
        else:
            max_possible_capacity = self._get_max_capacity_possible(
                filter_resources, resource_selected_id
            )

        return render_fragments(
            request.env,
            Fragment(
                "calendar.appointment_calendar",
                {
                    "appointment_type": appointment_type,
                    "available_appointments": available_appointments,
                    "asked_capacity": asked_capacity,
                    "timezone": request.session["timezone"],
                    "formated_days": formated_days,
                    "slots": slots,
                    "month_kept_from_update": month_kept_from_update,
                    "month_first_available": month_first_available,
                    "max_resource_capacity": max_possible_capacity,
                },
            ),
        )
