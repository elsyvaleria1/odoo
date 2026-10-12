from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode as url_encode

from babel.dates import format_date, format_datetime
from werkzeug.exceptions import BadRequest, Forbidden

from odoo import Command, fields, http
from odoo.http import prepare_content_disposition_header, request, route
from odoo.libs.datetime import timezone as get_timezone
from odoo.tools.misc import get_lang
from odoo.tools.urls import keep_query

GUEST_LIMIT = 10


class CalendarController(http.Controller):
    @staticmethod
    def _attendee_from_token(token, extra_domain=None):
        attendee = request.env["calendar.attendee"]._from_invitation_token(token)
        if attendee and extra_domain:
            return attendee.filtered_domain(extra_domain)
        return attendee

    @staticmethod
    def _event_from_token(token):
        if not token:
            return request.env["calendar.event"]
        return (
            request.env["calendar.event"]  # noqa: E8537 -- public: an identifier that is not meant to be secret
            .sudo()
            .search([("access_token", "=", token)], limit=1)
        )

    @staticmethod
    def _confirm_answer(token, event_id, answer, *, recurrence=False):
        if request.httprequest.method == "POST":
            return None
        attendee = CalendarController._attendee_from_token(
            token, [("event_id", "=", event_id)]
        )
        if not attendee:
            raise request.prepare_not_found_error()
        return request.render(
            "calendar.invitation_answer_confirm",
            {
                "attendee": attendee,
                "event": attendee.event_id,
                "answer": answer,
                "recurrence": recurrence,
                "token": token,
            },
        )

    @http.route(
        "/calendar/meeting/accept",
        type="http",
        auth="receiver",
        receiver="calendar.attendee:_receiver_for_invitation",
        receiver_event="calendar_invitation",
        methods=["GET", "POST"],
        typed=True,
    )
    def accept_meeting(self, token: str, id: int, **kwargs):
        if confirmation := self._confirm_answer(token, id, "accept"):
            return confirmation
        attendee = self._attendee_from_token(token, [("state", "!=", "accepted")])
        attendee.do_accept()
        return self.view_meeting(token, id)

    @http.route(
        "/calendar/recurrence/accept",
        type="http",
        auth="receiver",
        receiver="calendar.attendee:_receiver_for_invitation",
        receiver_event="calendar_invitation",
        methods=["GET", "POST"],
        typed=True,
    )
    def accept_recurrence(self, token: str, id: int, **kwargs):
        if confirmation := self._confirm_answer(token, id, "accept", recurrence=True):
            return confirmation
        attendee = self._attendee_from_token(token, [("state", "!=", "accepted")])
        if attendee:
            attendees = (
                request.env["calendar.attendee"]
                .sudo()
                .search(
                    [
                        (
                            "event_id",
                            "in",
                            attendee.event_id.recurrence_id.calendar_event_ids.ids,
                        ),
                        ("partner_id", "=", attendee.partner_id.id),
                        ("state", "!=", "accepted"),
                    ]
                )
            )
            attendees.do_accept()
        return self.view_meeting(token, id)

    @http.route(
        "/calendar/meeting/decline",
        type="http",
        auth="receiver",
        receiver="calendar.attendee:_receiver_for_invitation",
        receiver_event="calendar_invitation",
        methods=["GET", "POST"],
        typed=True,
    )
    def decline_meeting(self, token: str, id: int, **kwargs):
        if confirmation := self._confirm_answer(token, id, "decline"):
            return confirmation
        attendee = self._attendee_from_token(token, [("state", "!=", "declined")])
        attendee.do_decline()
        return self.view_meeting(token, id)

    @http.route(
        "/calendar/recurrence/decline",
        type="http",
        auth="receiver",
        receiver="calendar.attendee:_receiver_for_invitation",
        receiver_event="calendar_invitation",
        methods=["GET", "POST"],
        typed=True,
    )
    def decline_recurrence(self, token: str, id: int, **kwargs):
        if confirmation := self._confirm_answer(token, id, "decline", recurrence=True):
            return confirmation
        attendee = self._attendee_from_token(token, [("state", "!=", "declined")])
        if attendee:
            attendees = (
                request.env["calendar.attendee"]
                .sudo()
                .search(
                    [
                        (
                            "event_id",
                            "in",
                            attendee.event_id.recurrence_id.calendar_event_ids.ids,
                        ),
                        ("partner_id", "=", attendee.partner_id.id),
                        ("state", "!=", "declined"),
                    ]
                )
            )
            attendees.do_decline()
        return self.view_meeting(token, id)

    @http.route("/calendar/meeting/join", type="http", auth="user", website=True)
    def calendar_join_meeting(self, token, **kwargs):
        event = self._event_from_token(token)
        if not event:
            raise request.prepare_not_found_error()
        event.action_join_meeting(request.env.user.partner_id.id)
        attendee = (
            request.env["calendar.attendee"]
            .sudo()
            .search(
                [
                    ("partner_id", "=", request.env.user.partner_id.id),
                    ("event_id", "=", event.id),
                ],
                limit=1,
            )
        )
        return request.redirect(
            "/calendar/meeting/view?token=%s&id=%s" % (attendee.access_token, event.id)
        )

    @http.route("/calendar/notify", type="jsonrpc", auth="user")
    def notify(self):
        return request.env["calendar.alarm_manager"].get_next_notif()

    @http.route("/calendar/notify_ack", type="jsonrpc", auth="user")
    def notify_ack(self):
        return request.env["res.partner"].sudo()._set_calendar_last_notif_ack()

    @http.route(
        "/calendar/join_videocall/<string:access_token>", type="http", auth="public"
    )
    def calendar_join_videocall(self, access_token):  # noqa: E8539 -- public: a meeting room every attendee shares
        event = self._event_from_token(access_token)
        if not event:
            raise request.prepare_not_found_error()

        if not event.videocall_channel_id:
            event._create_videocall_channel()

        return request.redirect(event.videocall_channel_id.invitation_url)

    @http.route("/calendar/check_credentials", type="jsonrpc", auth="user")
    def check_calendar_credentials(self):
        return request.env["res.users"].check_calendar_credentials()

    @route(
        ["/calendar/view/<string:access_token>"],
        type="http",
        auth="public",
        website=True,
    )
    def appointment_view(self, access_token, partner_id=False, state=False, **kwargs):
        event, partner_id, can_manage = self._meeting_access(
            access_token, archived=True
        )
        if not event:
            raise request.prepare_not_found_error()
        partner = event.env["res.partner"].browse(partner_id)
        if partner.lang:
            request.update_context(lang=partner.lang)
            event = event.with_context(lang=partner.lang)
        timezone = request.session.get("timezone")
        if not timezone:
            timezone = (
                request.env.context.get("tz")
                or event.appointment_type_id.appointment_tz
                or (event.partner_ids and event.partner_ids[0].tz)
                or event.user_id.tz
                or "UTC"
            )
            request.session["timezone"] = timezone
        tz_session = get_timezone(timezone)

        format_func = format_datetime
        if not event.allday:
            url_date_start = fields.Datetime.from_string(event.start).strftime(
                "%Y%m%dT%H%M%SZ"
            )
            url_date_stop = fields.Datetime.from_string(event.stop).strftime(
                "%Y%m%dT%H%M%SZ"
            )
            date_start = (
                fields.Datetime.from_string(event.start)
                .replace(tzinfo=UTC)
                .astimezone(tz_session)
            )
        else:
            url_date_start = fields.Date.from_string(event.start_date).strftime(
                "%Y%m%d"
            )
            url_date_stop = (
                fields.Date.from_string(event.stop_date) + timedelta(days=1)
            ).strftime("%Y%m%d")
            date_start = fields.Date.from_string(event.start_date)
            format_func = format_date

        locale = get_lang(request.env).code
        day_name = format_func(date_start, "EEE", locale=locale)
        date_start = f"{day_name} {format_func(date_start, locale=locale)}"
        params = {
            "action": "TEMPLATE",
            "text": event._get_customer_summary(),
            "dates": f"{url_date_start}/{url_date_stop}",
            "details": event._get_customer_description(),
        }
        if event.location:
            params.update(location=event.location.replace("\n", " "))
        encoded_params = url_encode(params)
        google_url = "https://www.google.com/calendar/render?" + encoded_params

        return request.render(
            "calendar.appointment_validated",
            {
                "access_token": access_token,
                "can_manage": can_manage,
                "cancel_responsible": event.user_id
                if event.user_id.active and event.user_id._is_internal()
                else False,
                "event": event,
                "datetime_start": date_start,
                "google_url": google_url,
                "state": state,
                "partner_id": partner_id,
                "attendee_status": event.attendee_ids.filtered(
                    lambda a: a.partner_id.id == partner_id
                ).state
                if partner_id
                else False,
                "is_cancelled": not event.active,
            },
            headers={"Cache-Control": "no-store"},
        )

    @route(
        ["/calendar/<string:access_token>/add_attendees_from_emails"],
        type="jsonrpc",
        auth="public",
        website=True,
    )
    def appointment_add_attendee(self, access_token, emails_str):
        event_sudo, _, _ = self._meeting_access(access_token, management=True)
        if not event_sudo:
            raise request.prepare_not_found_error()
        if not event_sudo.appointment_type_id.allow_guests:
            raise BadRequest
        if not emails_str:
            return []
        guests = event_sudo.sudo()._get_or_create_partners(
            emails_str, limit=GUEST_LIMIT
        )
        if guests:
            event_sudo.write({"partner_ids": [Command.link(pid.id) for pid in guests]})
        return None

    @route(
        [
            "/calendar/cancel/<string:access_token>",
            "/calendar/<string:access_token>/cancel",
        ],
        type="http",
        auth="public",
        methods=["POST"],
        website=True,
    )
    def appointment_cancel(self, access_token, partner_id=False, **kwargs):
        event, partner_id, _ = self._meeting_access(access_token, management=True)
        appointment_type = event.appointment_type_id
        appointment_invite = event.appointment_invite_id
        if not event:
            raise request.prepare_not_found_error()
        if cancel_status := self._get_prevent_cancel_status(event):
            return request.redirect(
                f"/calendar/view/{access_token}?state={cancel_status}&partner_id={partner_id}"
            )
        event.sudo().action_cancel_meeting([int(partner_id)] if partner_id else [])
        if not appointment_type:
            return request.redirect(f"/calendar/view/{access_token}?state=cancel")
        if appointment_invite:
            redirect_url = appointment_invite.redirect_url + "&state=cancel"
        else:
            reset_params = {"state": "cancel"}
            if appointment_type.schedule_based_on == "resources":
                reset_params.update(
                    {
                        "resource_selected_id": "",
                        "available_resource_ids": "",
                    }
                )
            redirect_url = (
                f"/appointment/{appointment_type.id}?{keep_query('*', **reset_params)}"
            )
        return request.redirect(redirect_url)

    def _get_prevent_cancel_status(self, event):
        if fields.Datetime.from_string(
            (event.allday and event.start_date) or event.start
        ) < datetime.now() + timedelta(
            hours=event.appointment_type_id.min_cancellation_hours
        ):
            return "no_time_left"
        return False

    @route(
        ["/calendar/ics/<string:access_token>.ics"],
        type="http",
        auth="public",
        website=True,
    )
    def appointment_get_ics_file(self, access_token, **kwargs):
        event, _, _ = self._meeting_access(access_token)
        if not event or not event.attendee_ids:
            raise request.prepare_not_found_error()
        files = event._get_ics_file()
        content = files[event.id]
        return request.prepare_response(
            content,
            [
                ("Content-Type", "application/octet-stream"),
                ("Content-Length", len(content)),
                (
                    "Content-Disposition",
                    prepare_content_disposition_header(
                        event._get_customer_summary() + ".ics"
                    ),
                ),
            ],
        )

    @route("/calendar/videocall/<string:access_token>", type="http", auth="public")
    def calendar_videocall(self, access_token):  # noqa: E8539 -- public: a meeting room every attendee shares
        if not access_token:
            raise Forbidden
        event = (
            request.env["calendar.event"]  # noqa: E8537 -- public: an identifier that is not meant to be secret
            .sudo()
            .search([("access_token", "=", access_token)], limit=1)
        )
        if not event or not event.videocall_location:
            raise request.prepare_not_found_error()

        if event.videocall_source == "discuss":
            return self.calendar_join_videocall(access_token)
        return request.redirect(event.videocall_location, local=False)

    @classmethod
    def _meeting_access(cls, token, *, management=False, archived=False):
        empty = request.env["calendar.event"]
        if not token:
            return empty, False, False
        event = empty._from_booking_token(token, archived=archived)
        if event:
            return event, event.appointment_booker_id.id, True
        attendee = cls._attendee_from_token(token)
        if not attendee or (not archived and not attendee.event_id.active):
            return empty, False, False
        event = attendee.event_id
        can_manage = attendee.partner_id in (
            event.appointment_booker_id | event.user_id.partner_id
        )
        if management and not can_manage:
            return empty, False, False
        return event, attendee.partner_id.id, can_manage

    @http.route(
        "/calendar/meeting/view",
        type="http",
        auth="receiver",
        receiver="calendar.attendee:_receiver_for_invitation",
        receiver_event="calendar_invitation",
        typed=True,
    )
    def view_meeting(self, token: str, id: int, **kwargs):
        try:
            event_id = int(id)
        except TypeError, ValueError:
            raise request.prepare_not_found_error() from None
        attendee = self._attendee_from_token(token, [("event_id", "=", event_id)])
        if not attendee:
            raise request.prepare_not_found_error()
        if request.env.user._is_internal():
            return request.redirect(
                f"/odoo/calendar.event/{event_id}?db={request.env.cr.dbname}"
            )
        request.session["timezone"] = (
            attendee.partner_id.tz or attendee.event_id._get_mail_tz() or "UTC"
        )
        return request.redirect(f"/calendar/view/{token}")
