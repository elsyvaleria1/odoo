import uuid

from markupsafe import Markup, escape

from odoo import Command, api, fields, models
from odoo.tools import format_date, format_time


class CalendarBooking(models.Model):
    _name = "calendar.booking"
    _description = "Meeting Booking"
    _order = "start desc, id desc"

    def _default_booking_token(self):
        return uuid.uuid4().hex

    appointment_response_ids = fields.One2many(
        comodel_name="survey.user_input",
        inverse_name="calendar_booking_id",
        copy=False,
    )
    appointment_answer_input_ids = fields.One2many(
        comodel_name="survey.user_input.line",
        inverse_name="calendar_booking_id",
        string="Appointment Answers",
    )
    appointment_invite_id = fields.Many2one(comodel_name="appointment.invite")
    appointment_type_id = fields.Many2one(
        comodel_name="appointment.type",
        required=True,
        ondelete="cascade",
    )
    description = fields.Html()
    duration = fields.Float(compute="_compute_duration")
    guest_ids = fields.Many2many(
        comodel_name="res.partner",
        string="Guests",
    )
    name = fields.Char(string="Customer Name")
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Contact",
    )
    allday = fields.Boolean()
    start = fields.Datetime(required=True)
    stop = fields.Datetime(required=True)
    asked_capacity = fields.Integer(default=0)
    booking_line_ids = fields.One2many(
        comodel_name="calendar.booking.line",
        inverse_name="calendar_booking_id",
        string="Booking Lines",
    )
    staff_user_id = fields.Many2one(
        comodel_name="res.users",
        string="Operator",
    )
    account_move_id = fields.Many2one(
        comodel_name="account.move",
        string="Appointment Invoice",
        index="btree_not_null",
        readonly=True,
    )
    product_id = fields.Many2one(
        comodel_name="product.product",
        required=True,
    )
    booking_token = fields.Char(
        string="Access Token",
        default=lambda self: self._default_booking_token(),
        copy=False,
        readonly=True,
    )
    not_available = fields.Boolean(string="Is Not Available")
    calendar_event_id = fields.Many2one(
        comodel_name="calendar.event",
        string="Meeting",
    )

    @api.depends("start", "stop")
    def _compute_duration(self):
        for booking in self:
            booking.duration = (booking.stop - booking.start).total_seconds() / 3600

    def unlink(self):
        answers = self.appointment_response_ids.filtered(
            lambda answer: not answer.calendar_event_id
        )
        answers.unlink()
        return super().unlink()

    def _filter_unavailable_bookings(self):
        user_bookings = self.filtered("staff_user_id")
        resource_bookings = self.filtered(lambda b: b.booking_line_ids.resource_id)
        if not user_bookings and not resource_bookings:
            return self

        def filter_available_user_bookings(user_bookings):
            boundaries = sorted(
                set(user_bookings.mapped("start") + user_bookings.mapped("stop"))
            )
            for index, start in enumerate(boundaries[:-1]):
                stop = boundaries[index + 1]
                interval_bookings = user_bookings.filtered_domain(
                    [("start", "<", stop), ("stop", ">", start)]
                )
                for user, booking_lines in interval_bookings.booking_line_ids.grouped(
                    "appointment_user_id"
                ).items():
                    booking_lines &= user_bookings.booking_line_ids
                    appointment_types = (
                        booking_lines.calendar_booking_id.appointment_type_id
                    )
                    if len(
                        appointment_types
                    ) > 1 or not user.partner_id._is_calendar_available(
                        start, stop, appointment_types
                    ):
                        user_bookings -= booking_lines.calendar_booking_id
                        continue
                    total_availability = (
                        appointment_types._get_users_remaining_capacity(
                            user, start, stop
                        )["total_remaining_capacity"]
                        if booking_lines
                        else 0
                    )
                    for booking_line in booking_lines:
                        if total_availability >= booking_line.capacity_used:
                            total_availability -= booking_line.capacity_used
                        else:
                            user_bookings -= booking_line.calendar_booking_id
            return user_bookings

        def filter_available_resource_bookings(resource_bookings):
            boundaries = sorted(
                set(
                    resource_bookings.mapped("start") + resource_bookings.mapped("stop")
                )
            )

            for index, start in enumerate(boundaries[:-1]):
                stop = boundaries[index + 1]
                interval_bookings = resource_bookings.filtered_domain(
                    [("start", "<", stop), ("stop", ">", start)]
                )
                for (
                    resource,
                    booking_lines,
                ) in interval_bookings.booking_line_ids.grouped("resource_id").items():
                    booking_lines &= resource_bookings.booking_line_ids
                    appointment_types = (
                        booking_lines.calendar_booking_id.appointment_type_id
                    )
                    if len(appointment_types) > 1 and not all(
                        appointment_types.mapped("manage_capacity")
                    ):
                        resource_bookings -= booking_lines.calendar_booking_id
                        continue
                    total_availability = (
                        appointment_types[0]._get_resources_remaining_capacity(
                            resource,
                            start,
                            stop,
                            with_combinable_resources=appointment_types[
                                0
                            ].manage_capacity,
                        )["total_remaining_capacity"]
                        if booking_lines
                        else 0
                    )
                    for booking_line in booking_lines:
                        if total_availability >= booking_line.capacity_used:
                            total_availability -= booking_line.capacity_used
                        else:
                            resource_bookings -= booking_line.calendar_booking_id
            return resource_bookings

        return self - (
            filter_available_user_bookings(user_bookings)
            | filter_available_resource_bookings(resource_bookings)
        )

    def _get_description(self):
        self.check_singleton()
        tz = (
            self.env.context.get("tz")
            or self.partner_id.tz
            or self.appointment_type_id.appointment_tz
        )
        env_tz = self.with_context(tz=tz).env
        if self.staff_user_id:
            return self.env._(
                "%(name)s with %(staff_user)s\n%(date_start)s at %(time_start)s to %(date_end)s at %(time_end)s (%(timezone)s)",
                name=self.appointment_type_id.name,
                staff_user=self.staff_user_id.display_name,
                date_start=format_date(env_tz, self.start),
                time_start=format_time(env_tz, self.start, tz=tz),
                date_end=format_date(env_tz, self.stop),
                time_end=format_time(env_tz, self.stop, tz=tz),
                timezone=tz,
            )
        else:
            return self.env._(
                "%(name)s\n%(date_start)s at %(time_start)s to %(date_end)s at %(time_end)s (%(timezone)s)",
                name=self.appointment_type_id.name,
                staff_user=self.staff_user_id.display_name,
                date_start=format_date(env_tz, self.start),
                time_start=format_time(env_tz, self.start, tz=tz),
                date_end=format_date(env_tz, self.stop),
                time_end=format_time(env_tz, self.stop, tz=tz),
                timezone=tz,
            )

    def _log_booking_collisions(self) -> None:
        odoobot = self.env.ref("base.partner_root")
        for booking in self.filtered("account_move_id"):
            booking.account_move_id._message_log(
                body=Markup("<p>%s</p>")
                % escape(
                    self.env._(
                        "The following booking was not confirmed due to insufficient availability or configuration changes: %s"
                    )
                )
                % booking._get_html_link(),
                author_id=odoobot.id,
            )

    def _create_event_from_paid_booking(self) -> None:
        if not self:
            return
        todo = self.filtered(lambda booking: not booking.calendar_event_id)
        unavailable_bookings = todo._filter_unavailable_bookings()

        for booking in todo - unavailable_bookings:
            booking_line_values = [
                {
                    "resource_id": line.resource_id.id,
                    "appointment_user_id": line.appointment_user_id.id,
                    "capacity_reserved": line.capacity_reserved,
                    "capacity_used": line.capacity_used,
                }
                for line in booking.booking_line_ids
            ]

            calendar_event_values = (
                booking.appointment_type_id._prepare_calendar_event_values(
                    booking.asked_capacity,
                    booking_line_values,
                    booking.description,
                    booking.duration,
                    booking.allday,
                    booking.appointment_invite_id,
                    booking.guest_ids,
                    booking.name,
                    booking.partner_id,
                    booking.staff_user_id,
                    booking.start,
                    booking.stop,
                )
            )
            calendar_event_values["appointment_response_ids"] = [
                Command.set(booking.appointment_response_ids.ids)
            ]

            meeting = (
                self.env["calendar.event"]
                .with_context(
                    mail_create_nolog=True,
                    mail_create_nosubscribe=True,
                    mail_notify_author=True,
                    skip_contact_description=True,
                    allowed_company_ids=booking.staff_user_id.company_ids.ids,
                )
                .sudo()
                .create(calendar_event_values)
            )
            booking.write({"calendar_event_id": meeting.id, "not_available": False})

        unavailable_bookings.not_available = True
        unavailable_bookings._log_booking_collisions()

    def _cancel_pending_booking(self):
        self.check_singleton()
        invoice = self.account_move_id
        invoice._lock_for_payment()
        if self.calendar_event_id or (
            invoice
            and (
                invoice.state != "draft"
                or invoice.transaction_ids
                or invoice.calendar_booking_ids != self
            )
        ):
            return False
        if invoice:
            invoice.action_cancel()
        self.unlink()
        return True

    def _create_booking_invoices(self):
        return self.env["account.move"].create(
            [
                {
                    "calendar_booking_ids": [Command.link(booking.id)],
                    "invoice_line_ids": [
                        Command.create(
                            {
                                "display_type": "product",
                                "name": booking._get_description(),
                                "product_id": booking.product_id.id,
                                "quantity": booking.asked_capacity or 1.0,
                            }
                        )
                    ],
                    "move_type": "out_invoice",
                    "partner_id": booking.partner_id.id,
                }
                for booking in self
            ]
        )

    @api.autovacuum
    def _gc_calendar_booking(self):
        max_creation_dt = fields.Datetime.subtract(fields.Datetime.now(), months=6)
        max_ending_dt = fields.Datetime.subtract(fields.Datetime.now(), months=2)
        domain = [
            "|",
            ("create_date", "<", max_creation_dt),
            ("stop", "<", max_ending_dt),
        ]
        return self.sudo().search(domain).unlink()
