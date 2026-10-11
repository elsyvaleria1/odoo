from datetime import UTC, datetime, timedelta

from werkzeug.exceptions import BadRequest

from odoo.http import Controller, request, route
from odoo.tools import email_normalize, hmac, register_signed_scope

BOOKING_SCOPE = register_signed_scope(
    "appointment-google-reserve-create-booking",
    purpose="derive a Google Reserve booking's event token from its "
    "idempotency token, so a retried booking finds the event it made",
    lifetime="undated: stored on the booked event",
)


class GoogleReserveController(Controller):
    @route(
        "/appointment/<int:appointment_id>/<string:appointment_token>/google_reserve/availabilities",
        auth="receiver",
        receiver="appointment.type:_receiver_for_google_reserve",
        receiver_event="google_reserve",
        methods=["GET"],
        typed=True,
    )
    def google_reserve_batch_availability_lookup(
        self, appointment_id: int, appointment_token: str
    ):

        slot_time = (
            request.get_json_data()
        )
        if not slot_time:
            raise BadRequest("Invalid JSON payload")

        appointment_type_su = self._get_appointment(appointment_id, appointment_token)

        min_date = datetime.fromtimestamp(int(slot_time[0]["start_sec"]), tz=UTC)
        max_date = min_date + timedelta(seconds=int(slot_time[0]["duration_sec"]))
        for slot in slot_time:
            slot_start = datetime.fromtimestamp(int(slot["start_sec"]), tz=UTC)
            slot_stop = slot_start + timedelta(seconds=int(slot["duration_sec"]))

            min_date = min(min_date, slot_start)
            max_date = max(max_date, slot_stop)

        availabilities = appointment_type_su._google_reserve_get_availabilities(
            start_time=min_date, end_time=max_date
        )
        slot_time_availability = [
            {
                "available": any(
                    (
                        (
                            not slot.get("resource_ids")
                            or (
                                slot.get("resource_ids")
                                and slot["resource_ids"].get("party_size")
                                and a["resources"]["party_size"]
                                >= slot["resource_ids"]["party_size"]
                            )
                        )
                        and a["start_sec"] == int(slot["start_sec"])
                        and a["duration_sec"] == int(slot["duration_sec"])
                        and a["spots_open"] >= 1
                    )
                    for a in availabilities
                ),
                "slot_time": slot,
            }
            for slot in slot_time
        ]

        return request.prepare_json_response(slot_time_availability)

    @route(
        "/appointment/<int:appointment_id>/<string:appointment_token>/google_reserve/booking/create",
        auth="receiver",
        receiver="appointment.type:_receiver_for_google_reserve",
        receiver_event="google_reserve",
        methods=["POST"],
        csrf=False,
        typed=True,
    )
    def google_reserve_booking_create(
        self, appointment_id: int, appointment_token: str
    ):

        route_params = (
            request.get_json_data()
        )

        if not all(
            bool(route_params.get(key))
            for key in ["idempotency_token", "user_information", "slot"]
        ):
            raise BadRequest("Invalid JSON payload")

        appointment_type_su = self._get_appointment(appointment_id, appointment_token)
        slot_info = route_params["slot"]
        user_info = route_params["user_information"]

        token = hmac(
            request.env(su=True),
            BOOKING_SCOPE,
            (appointment_type_su.id, route_params["idempotency_token"]),
        )[:36]
        calendar_event = (
            request.env["calendar.event"]
            .sudo()
            .search([("google_reserve_idempotency_token", "=", token)])
        )
        if calendar_event:
            return request.prepare_json_response(
                {
                    "booking": {
                        "booking_id": str(calendar_event.id),
                        "status": "CONFIRMED",
                        "slot": slot_info,
                        "user_information": user_info,
                    }
                }
            )

        duration_sec = int(slot_info["duration_sec"])
        start_sec = int(slot_info["start_sec"])
        stop_sec = start_sec + duration_sec
        start_slot = datetime.fromtimestamp(start_sec)
        stop_slot = datetime.fromtimestamp(stop_sec)

        party_size = 0
        if "resources" in slot_info and "party_size" in slot_info["resources"]:
            party_size = int(slot_info["resources"]["party_size"])

        generated_slots = appointment_type_su._slots_generate(
            start_slot.astimezone(UTC),
            stop_slot.astimezone(UTC),
            "UTC",
        )
        selected_slot = next(
            (
                slot
                for slot in generated_slots
                if slot["UTC"][0] == start_slot and slot["UTC"][1] == stop_slot
            ),
            None,
        )
        slots_to_fill = [selected_slot] if selected_slot else []

        if appointment_type_su.schedule_based_on == "users":
            appointment_type_su._slots_add_users_availability(
                slots_to_fill,
                start_slot.astimezone(UTC),
                stop_slot.astimezone(UTC),
            )
        else:
            appointment_type_su._slots_add_resources_availability(
                slots_to_fill,
                start_slot.astimezone(UTC),
                stop_slot.astimezone(UTC),
                asked_capacity=party_size,
            )

        slot = slots_to_fill[0] if slots_to_fill else False

        staff_user = request.env["res.users"]
        booking_lines = []
        booking_response = False
        if (
            appointment_type_su.schedule_based_on == "resources"
            and slot
            and "available_resource_ids" in slot
        ):
            resources = slot["available_resource_ids"]
            booking_lines = [
                {
                    "resource_id": resource.id,
                    "capacity_reserved": party_size,
                    "capacity_used": party_size
                    if not resource.booking_exclusive
                    and appointment_type_su.manage_capacity
                    else resource.capacity,
                }
                for resource in resources
            ]
        elif (
            appointment_type_su.schedule_based_on == "users"
            and slot
            and ("available_staff_users" in slot or "staff_user_id" in slot)
        ):
            staff_user = (
                slot.get("available_staff_users", [False])[0] or slot["staff_user_id"]
            )

        if booking_lines or staff_user:
            customer_email = email_normalize(user_info["email"])
            customer = (
                request.env["mixin.mail.thread"]
                .sudo()
                ._partner_get_or_create_from_emails_single(
                    [customer_email], avoid_alias=True
                )
            )
            if not customer:
                raise BadRequest("Invalid Email")

            if "telephone" in user_info:
                customer_phone = (
                    customer._phone_format(number=user_info["telephone"])
                    or user_info["telephone"]
                )
                if customer.phone_sanitized != customer_phone:
                    customer._phone_replace_number("phone_ids", user_info["telephone"])

            appointment_values = appointment_type_su._prepare_calendar_event_values(
                asked_capacity=party_size,
                booking_line_values=booking_lines,
                description="",
                duration=duration_sec / 3600,
                allday=False,
                appointment_invite=request.env["appointment.invite"],
                guests=None,
                name=customer.name,
                customer=customer,
                staff_user=staff_user,
                start=start_slot,
                stop=stop_slot,
            )

            calendar_event = (
                request.env["calendar.event"]
                .sudo()
                .create(
                    {
                        **appointment_values,
                        "google_reserve_idempotency_token": token,
                        "is_google_reserve": True,
                    }
                )
            )

            booking_response = {
                "booking": {
                    "booking_id": str(calendar_event.id),
                    "status": "CONFIRMED",
                    "slot": slot_info,
                    "user_information": user_info,
                }
            }
        else:
            booking_response = {
                "booking": {
                    "booking_id": False,
                    "status": "FAILED",
                    "slot": slot_info,
                    "user_information": user_info,
                },
                "booking_failure": {
                    "cause": "SLOT_UNAVAILABLE",
                },
            }

        return request.prepare_json_response(booking_response)

    @route(
        "/appointment/<int:appointment_id>/<string:appointment_token>/google_reserve/booking/<int:calendar_event_id>/update",
        auth="receiver",
        receiver="appointment.type:_receiver_for_google_reserve",
        receiver_event="google_reserve",
        methods=["POST"],
        csrf=False,
        typed=True,
    )
    def google_reserve_booking_update(
        self, appointment_id: int, appointment_token: str, calendar_event_id: int
    ):

        route_params = (
            request.get_json_data()
        )

        if not route_params.get("booking"):
            raise BadRequest("Invalid JSON payload")

        appointment_type_su = self._get_appointment(appointment_id, appointment_token)
        calendar_event = (
            request.env["calendar.event"]
            .sudo()
            .with_context(
                active_test=False,
            )
            .search(
                [
                    ("id", "=", calendar_event_id),
                    ("appointment_type_id", "=", appointment_type_su.id),
                ]
            )
        )

        if not calendar_event:
            raise BadRequest("Unknown Booking")

        booking_info = route_params["booking"]

        booking_response = {}
        failure_status = False
        if booking_info.get("status") == "CANCELED":
            if not calendar_event.active:
                failure_status = "BOOKING_ALREADY_CANCELLED"
            else:
                calendar_event.with_context(
                    google_reserve_service_rpc=True
                ).action_archive()
                booking_response = {
                    "booking": booking_info,
                }
        elif "slot" in booking_info:
            calendar_event_vals = {
                "start": calendar_event.start,
                "duration": calendar_event.duration,
            }

            resources_booking = appointment_type_su.schedule_based_on == "resources"
            modifying_dates = (
                "start_sec" in booking_info["slot"]
                and "duration_sec" in booking_info["slot"]
            )
            modifying_party_size = (
                "resources" in booking_info["slot"]
                and "party_size" in booking_info["slot"]["resources"]
            )

            if modifying_dates:
                calendar_event_vals.update(
                    {
                        "start": datetime.fromtimestamp(
                            int(booking_info["slot"]["start_sec"])
                        ),
                        "duration": int(booking_info["slot"]["duration_sec"]) / 3600,
                    }
                )

                if not calendar_event.with_context(
                    ignore_event_ids=calendar_event.ids
                ).appointment_type_id._check_appointment_is_valid_slot(
                    staff_user=calendar_event.partner_id.user_ids[0]
                    if not resources_booking and calendar_event.partner_id.user_ids
                    else False,
                    resources=calendar_event.resource_ids,
                    asked_capacity=calendar_event.total_capacity_reserved,
                    timezone="UTC",
                    start_dt=calendar_event_vals["start"].astimezone(UTC),
                    duration=calendar_event_vals["duration"],
                    allday=calendar_event.allday,
                ):
                    if resources_booking and not modifying_party_size:
                        booking_info["slot"].update(
                            {
                                "resources": {
                                    "party_size": calendar_event.total_capacity_reserved
                                }
                            }
                        )
                        modifying_party_size = True
                    elif not resources_booking:
                        failure_status = "SLOT_UNAVAILABLE"

            if resources_booking and modifying_party_size:
                old_party_size = calendar_event.total_capacity_reserved
                new_party_size = int(booking_info["slot"]["resources"]["party_size"])
                booking_lines = calendar_event.booking_line_ids
                if (
                    not modifying_dates
                    and len(booking_lines) == 1
                    and (
                        new_party_size
                        <= max(
                            old_party_size,
                            booking_lines.resource_id.capacity,
                        )
                    )
                ):
                    calendar_event_vals["total_capacity_reserved"] = new_party_size
                else:
                    start_dt_utc = calendar_event_vals["start"].astimezone(UTC)
                    stop_dt_utc = start_dt_utc + timedelta(
                        hours=calendar_event_vals["duration"]
                    )
                    slots = calendar_event.appointment_type_id._slots_generate(
                        start_dt_utc, stop_dt_utc, "UTC"
                    )
                    slots = [
                        slot
                        for slot in slots
                        if slot["UTC"][0] == start_dt_utc.replace(tzinfo=None)
                        and slot["UTC"][1] == stop_dt_utc.replace(tzinfo=None)
                    ]
                    calendar_event.with_context(
                        ignore_event_ids=calendar_event.ids
                    ).appointment_type_id._slots_add_resources_availability(
                        slots,
                        start_dt_utc,
                        stop_dt_utc,
                        asked_capacity=new_party_size,
                    )
                    if slots and slots[0].get("available_resource_ids"):
                        calendar_event_vals.update(
                            {
                                "resource_ids": slots[0]["available_resource_ids"],
                                "total_capacity_reserved": new_party_size,
                            }
                        )
                    elif modifying_dates:
                        failure_status = "SLOT_UNAVAILABLE"
                    else:
                        failure_status = "USER_OVER_BOOKING_LIMIT"

            if not failure_status:
                calendar_event.with_context(google_reserve_service_rpc=True).write(
                    calendar_event_vals
                )

                booking_response = {
                    "booking": dict(
                        booking_info,
                        status="CONFIRMED",
                        payment_information={
                            "prepayment_status": "PREPAYMENT_NOT_PROVIDED"
                        },
                    ),
                }

                booking_response["booking"]["slot"]["resources"] = {
                    "party_size": str(calendar_event.total_capacity_reserved)
                }

        if failure_status:
            booking_response = {
                "booking": {
                    "booking_id": str(calendar_event.id),
                    "status": "FAILED",
                },
                "booking_failure": {
                    "cause": failure_status,
                },
            }

        return request.prepare_json_response(booking_response)

    @route(
        "/appointment/google_reserve/upload_availabilities_feed",
        auth="receiver",
        receiver="appointment.type:_receiver_for_google_reserve_feed",
        receiver_event="google_reserve_feed",
        methods=["POST"],
        csrf=False,
        typed=True,
    )
    def google_reserve_upload_availabilities_feed(self, **kwargs):
        request.env.ref(
            "appointment_google_reserve.ir_cron_iap_google_reserve_availabilities"
        )._trigger()


    def _get_appointment(self, appointment_id, appointment_token):
        return request.admission.subject
