import calendar as cal
import uuid
from datetime import UTC, datetime, time, timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError
from odoo.http import request
from odoo.tools import consteq

from ..tools.google_reserve_iap import GoogleReserveIAP
from odoo.addons.integration.tools.admission import Resolution


class AppointmentType(models.Model):
    _inherit = "appointment.type"

    is_auto_assign = fields.Boolean(
        compute="_compute_is_auto_assign",
        store=True,
        readonly=False,
    )

    google_reserve_enable = fields.Boolean(string="Enable Google Booking")
    google_reserve_pending_sync = fields.Boolean(
        string="Google Booking Pending Synchronization",
        copy=False,
    )
    google_reserve_merchant_id = fields.Many2one(
        comodel_name="google.reserve.merchant",
        index="btree_not_null",
        groups="calendar.group_appointment_manager",
        help="Configure your company data for Google Reserve",
    )
    google_reserve_access_token = fields.Char(
        default=lambda self: uuid.uuid4().hex,
        copy=False,
        groups="calendar.group_appointment_manager",
    )

    @api.constrains("google_reserve_enable", "category", "is_auto_assign")
    def _check_appointment_category_for_google_reserve(self) -> None:
        for appointment_type in self.filtered("google_reserve_enable"):
            if appointment_type.category in ("custom", "punctual"):
                raise ValidationError(
                    self.env._(
                        "%(appointment_type_name)s: A %(appointment_category)s appointment type cannot be used with the Google Bookings integration.",
                        appointment_category=appointment_type.category,
                        appointment_type_name=appointment_type.name,
                    )
                )
            if not appointment_type.is_auto_assign:
                raise ValidationError(
                    self.env._(
                        "%(appointment_type_name)s: The Google Bookings integration only works in the auto-assign mode.",
                        appointment_type_name=appointment_type.name,
                    )
                )

    @api.constrains("google_reserve_enable", "google_reserve_merchant_id")
    def _check_google_reserve_fields(self) -> None:
        for appointment_type in self.filtered("google_reserve_enable"):
            if not appointment_type.google_reserve_merchant_id:
                raise ValidationError(
                    self.env._(
                        "%(appointment_type_name)s: Please configure your Google Reserve Merchant for Google Reserve.",
                        appointment_type_name=appointment_type.name,
                    )
                )

    @api.depends("google_reserve_enable")
    def _compute_is_auto_assign(self) -> None:
        for appointment_type in self:
            if appointment_type.google_reserve_enable:
                appointment_type.is_auto_assign = True

    @api.model_create_multi
    def create(self, vals_list):

        appointment_types = super().create(vals_list)

        google_reserve_appointments = appointment_types.filtered(
            "google_reserve_enable"
        )
        if google_reserve_appointments and not self.env.user.has_group(
            "calendar.group_appointment_manager"
        ):
            raise AccessError(
                self.env._(
                    "Only Appointment Managers can enable the Google Reserve Integration"
                )
            )

        for appointment_type in google_reserve_appointments:
            GoogleReserveIAP().register_appointment(appointment_type)
        return appointment_types

    def write(self, vals):

        if (
            not self.env.user.has_group("calendar.group_appointment_manager")
            and "google_reserve_enable" in vals
        ):
            raise AccessError(
                self.env._(
                    "Only Appointment Managers can enable or disable the Google Reserve Integration"
                )
            )

        old_google_booking_appointments = self.filtered("google_reserve_enable")
        result = super().write(vals)

        google_reserve_pending_sync = self.env["appointment.type"]
        google_reserve_iap = GoogleReserveIAP()
        if "google_reserve_enable" in vals:
            if vals["google_reserve_enable"]:
                for appointment_type in self - old_google_booking_appointments:
                    google_reserve_iap.register_appointment(appointment_type)
                    google_reserve_pending_sync += appointment_type
            else:
                for appointment_type in old_google_booking_appointments:
                    google_reserve_iap.unregister_appointment(appointment_type)
        elif "active" in vals:
            for appointment_type in old_google_booking_appointments:
                google_reserve_pending_sync += appointment_type
                if vals["active"]:
                    google_reserve_iap.register_appointment(appointment_type)
                else:
                    google_reserve_iap.unregister_appointment(appointment_type)
        else:
            appointment_altering_values = {
                "name",
                "min_cancellation_hours",
                "min_schedule_hours",
            }

            slots_altering_values = {
                "min_cancellation_hours",
                "min_schedule_hours",
                "slot_ids",
                "staff_user_ids",
                "resource_ids",
                "appointment_duration",
            }

            google_booking_appointments = self.filtered("google_reserve_enable")
            for appointment_type in google_booking_appointments:
                if vals.keys() & appointment_altering_values:
                    google_reserve_iap.register_appointment(appointment_type)
                    google_reserve_pending_sync += appointment_type

            if vals.keys() & slots_altering_values:
                google_reserve_pending_sync += google_booking_appointments

        google_reserve_pending_sync.google_reserve_pending_sync = True

        return result

    @api.ondelete(at_uninstall=True)
    def _unlink_unregister_google_reserve(self) -> None:
        google_reserve_iap = GoogleReserveIAP()
        for appointment_type in self.filtered("google_reserve_enable"):
            google_reserve_iap.unregister_appointment(appointment_type)

    def action_google_reserve_enable(self) -> None:
        self.google_reserve_enable = True

    def action_google_reserve_disable(self) -> None:
        self.google_reserve_enable = False

    @api.model
    def _receiver_for_google_reserve(
        self, appointment_id=None, appointment_token=None, **path_args
    ):
        appointment_type = self.sudo().search(
            [("id", "=", appointment_id), ("google_reserve_enable", "=", True)]
        )
        if not appointment_type:
            return Resolution(self.browse(), claimed=f"appointment {appointment_id}")
        return Resolution(
            appointment_type,
            verify=lambda headers, body: (
                bool(appointment_token)
                and consteq(  # noqa: E8537 -- inbound: a signature an outside service sends us
                    appointment_type.google_reserve_access_token, appointment_token
                )
            ),
        )

    @api.model
    def _receiver_for_google_reserve_feed(self, **path_args):
        try:
            pairs = request.get_json_data().get("google_reserve_access_token_pairs")
        except ValueError, AttributeError:
            pairs = None
        if not pairs or not isinstance(pairs, list):
            return Resolution(self.browse(), claimed="feed upload without token pairs")
        types = self.sudo()
        for pair in pairs:
            try:
                appointment_type = types.search(
                    [
                        ("id", "=", int(pair["appointment_type_id"])),
                        ("google_reserve_enable", "=", True),
                    ]
                )
            except KeyError, TypeError, ValueError:
                appointment_type = self.browse()
            if not appointment_type:
                return Resolution(
                    self.browse(), claimed="feed upload naming no appointment"
                )
            types |= appointment_type

        def is_request_authorized(headers, body) -> bool:
            by_id = {t.id: t for t in types}
            return all(
                consteq(  # noqa: E8537 -- inbound: a signature an outside service sends us
                    by_id[int(pair["appointment_type_id"])].google_reserve_access_token,
                    str(pair.get("appointment_token") or ""),
                )
                for pair in pairs
            )

        return Resolution(types[:1], verify=is_request_authorized)

    def _google_reserve_get_availabilities(self, start_time=False, end_time=False):

        self.check_singleton()
        availabilities = []
        if self.category in ("custom", "punctual"):
            return availabilities

        if not start_time:
            start_time = datetime.now().astimezone(UTC)

        if not end_time:
            max_schedule_days = max(30, self.max_schedule_days)
            max_schedule_days = min(730, self.max_schedule_days)
            end_time = datetime.combine(
                start_time + timedelta(days=max_schedule_days), time.max
            ).astimezone(UTC)

        slots = self._slots_generate(
            start_time + timedelta(hours=self.min_schedule_hours),
            end_time,
            "UTC",
            reference_date=start_time.replace(tzinfo=None),
        )

        if self.schedule_based_on == "users":
            self.with_context(slots_check_all_users=True)._slots_add_users_availability(
                slots,
                start_time,
                end_time,
            )

            availabilities = [
                self._google_reserve_format_slot_availabilities_users(slot)
                for slot in slots
            ]
        else:
            availability_values = self._slot_availability_prepare_resources_values(
                self.resource_ids,
                start_time + timedelta(hours=self.min_schedule_hours),
                end_time,
            )

            for slot in slots:
                availabilities += (
                    self._google_reserve_format_slot_availabilities_resources(
                        slot, availability_values
                    )
                )

        return availabilities

    def _google_reserve_format_slot_availabilities_users(self, slot) -> dict:
        [start_utc, end_utc] = slot["UTC"]

        return {
            "spots_total": len(
                slot["slot"].restrict_to_user_ids or self.staff_user_ids
            ),
            "spots_open": len(slot["available_staff_users"])
            if "available_staff_users" in slot
            else 0,
            "duration_sec": int((end_utc - start_utc).total_seconds()),
            "start_sec": cal.timegm(start_utc.timetuple()),
        }

    def _google_reserve_format_slot_availabilities_resources(
        self, slot, availability_values
    ):

        self.check_singleton()
        [start_utc, end_utc] = slot["UTC"]

        remaining_capacity_by_resource = {
            resource: {
                booked_resource: remaining_capacity
                for booked_resource, remaining_capacity in self._get_resources_remaining_capacity(
                    resource,
                    start_utc,
                    end_utc,
                    resource_to_bookings=availability_values.get(
                        "resource_to_bookings"
                    ),
                ).items()
                if isinstance(
                    booked_resource, models.BaseModel
                )
            }
            for resource in self.resource_ids
        }

        availabilities = []
        allowed_max_capacity = int(
            self.env.registry.settings.get(
                self.env, "appointment.resource_max_capacity_allowed", 12
            )
        )
        max_capacity = min(
            20, allowed_max_capacity, self.resource_total_capacity
        )
        for capacity in range(1, max_capacity + 1):
            used_resources = self.env["resource.resource"]
            total_spots = 0
            for capacity_by_booked_resource in remaining_capacity_by_resource.values():
                accommodated_capacity = 0
                for booked_resource in capacity_by_booked_resource:
                    if booked_resource in used_resources:
                        continue

                    accommodated_capacity += booked_resource.capacity
                    used_resources += booked_resource
                    if accommodated_capacity >= capacity:
                        total_spots += 1
                        break

            if total_spots == 0:
                break

            used_resources = self.env["resource.resource"]
            open_spots = 0
            for capacity_by_booked_resource in remaining_capacity_by_resource.values():
                accommodated_capacity = 0

                for (
                    booked_resource,
                    booked_capacity,
                ) in capacity_by_booked_resource.items():
                    if booked_resource in used_resources:
                        continue

                    accommodated_capacity += booked_capacity
                    used_resources += booked_resource
                    if accommodated_capacity >= capacity:
                        open_spots += 1
                        break

            availabilities.append(
                {
                    "spots_open": open_spots,
                    "spots_total": total_spots,
                    "duration_sec": int((end_utc - start_utc).total_seconds()),
                    "start_sec": cal.timegm(start_utc.timetuple()),
                    "resources": {
                        "party_size": capacity,
                    },
                }
            )

        return availabilities
