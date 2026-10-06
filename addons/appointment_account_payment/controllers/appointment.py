from datetime import UTC

from babel.dates import format_datetime
from werkzeug.exceptions import Conflict, NotFound

from odoo import Command, fields, http
from odoo.http import request
from odoo.libs.datetime import timezone as get_timezone
from odoo.tools.misc import get_lang
from odoo.tools.urls import keep_query

from odoo.addons.calendar.controllers.booking import AppointmentController
from odoo.addons.payment import utils as payment_utils


class AppointmentAccountPayment(AppointmentController):
    @http.route(
        ["/calendar_booking/<string:booking_token>/cancel"],
        type="http",
        auth="public",
        methods=["POST"],
        website=True,
        sitemap=False,
    )
    def calendar_booking_cancel(self, booking_token):
        """Cancel (unlink) the booking linked to booking_token and redirect to the page of
        the corresponding appointment type to take another appointment."""
        booking_sudo = (
            request.env["calendar.booking"]  # noqa: E8537  session: a checkout's handle to the record it is filling
            .sudo()
            .search([("booking_token", "=", booking_token)], limit=1)
        )
        if not booking_sudo or booking_sudo.calendar_event_id:
            raise NotFound

        appointment_type = booking_sudo.appointment_type_id
        invitation_params = (
            booking_sudo.appointment_invite_id._get_invitation_url_parameters()
        )
        if not booking_sudo._cancel_pending_booking():
            raise Conflict(
                request.env._(
                    "This booking can no longer be changed here. Please contact us."
                )
            )
        return request.redirect(
            f"/appointment/{appointment_type.id}?{keep_query(*invitation_params)}"
        )

    @http.route(
        ["/calendar_booking/<string:booking_token>/view"],
        type="http",
        auth="public",
        website=True,
        sitemap=False,
    )
    def calendar_booking_view(self, booking_token):
        """View the booking summary, reached at the end of the appointment flow when the
        payment is pending, failed or was cancelled. Redirect to the calendar event page
        instead when the event exists, which means the booking was paid."""
        booking_sudo = (
            request.env["calendar.booking"]  # noqa: E8537  session: a checkout's handle to the record it is filling
            .sudo()
            .search([("booking_token", "=", booking_token)], limit=1)
        )
        if not booking_sudo:
            raise NotFound
        if booking_sudo.calendar_event_id:
            return request.redirect(
                "/calendar/view/{event_token}?partner_id={pid}&{args}".format(
                    event_token=booking_sudo.calendar_event_id.booking_access_token,
                    pid=booking_sudo.partner_id.id,
                    args=keep_query(
                        *booking_sudo.appointment_invite_id._get_invitation_url_parameters(),
                        state="new",
                    ),
                )
            )

        timezone = (
            request.session.get("timezone")
            or request.env.context.get("tz")
            or booking_sudo.appointment_type_id.appointment_tz
        )
        start_tz = (
            fields.Datetime.from_string(booking_sudo.start)
            .replace(tzinfo=UTC)
            .astimezone(get_timezone(timezone))
        )
        locale = get_lang(request.env).code
        start_dt = f"{format_datetime(start_tz, 'EEE', locale=locale)} {format_datetime(start_tz, locale=locale)}"

        return request.render(
            "appointment_account_payment.calendar_booking_view",
            {
                "attendees": (
                    booking_sudo.partner_id | booking_sudo.staff_user_id.partner_id
                )
                if booking_sudo.staff_user_id
                else booking_sudo.partner_id,
                "booking": booking_sudo,
                "start_dt": start_dt,
                "timezone": timezone,
            },
        )

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
        """Override: when a payment step is necessary, store the information in a calendar.booking
        record instead of a calendar.event, and redirect to payment. The booking is turned into
        a calendar.event on payment, see _create_event_from_paid_booking on calendar.booking."""
        # Using a booking prevents synchronizing calendars with non-confirmed events.
        if appointment_type.has_payment_step and (
            appointment_type.product_id.service_tracking
            in ["task_in_project", "project_only", "task_global_project"]
            or appointment_type.product_id.lst_price
        ):
            calendar_booking = (
                request.env["calendar.booking"]
                .sudo()
                .create(
                    [
                        {
                            "allday": bool(allday),
                            "appointment_invite_id": appointment_invite.id,
                            "appointment_type_id": appointment_type.id,
                            "asked_capacity": asked_capacity,
                            "booking_line_ids": [
                                Command.create(vals) for vals in booking_line_values
                            ],
                            "description": description,
                            "guest_ids": [Command.link(pid) for pid in guests.ids]
                            if guests
                            else [],
                            "name": name,
                            "partner_id": customer.id,
                            "product_id": appointment_type.product_id.id,
                            "staff_user_id": staff_user.id,
                            "start": date_start,
                            "stop": date_end,
                        }
                    ]
                )
            )
            response = (
                request.env["survey.user_input"]
                .sudo()
                .create(
                    {
                        "appointment_type_id": appointment_type.id,
                        "calendar_booking_id": calendar_booking.id,
                        "partner_id": customer.id,
                        "predefined_question_ids": [
                            Command.set(appointment_type.question_ids.ids)
                        ],
                    }
                )
            )
            response._submit_answers(answers)
            return self._redirect_to_payment(calendar_booking)

        return super()._handle_appointment_form_submission(
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
            guests,
            staff_user,
            asked_capacity,
            booking_line_values,
            extra_calendar_event_params,
        )

    def _redirect_to_payment(self, calendar_booking):
        """Create a draft invoice linked to the booking and redirect to the payment page,
        called from the appointment form submission when the flow has a payment step."""
        # A new invoice is created each time a booking is created after filling the form.
        # Overridden when eCommerce is installed to use sale orders instead.
        invoice = calendar_booking.sudo()._create_booking_invoices()
        if not invoice:
            raise NotFound

        return request.redirect(
            "/payment/pay?appointment_type_id={aid}&invoice_id={iid}&partner_id={pid}&amount={amount}&access_token={token}&{args}".format(
                aid=calendar_booking.appointment_type_id.id,
                iid=invoice.id,
                pid=calendar_booking.partner_id.id,
                amount=invoice.amount_total,
                token=payment_utils.generate_access_token(
                    invoice.partner_id.id, invoice.amount_total, invoice.currency_id.id
                ),
                args=keep_query("*"),
            )
        )
