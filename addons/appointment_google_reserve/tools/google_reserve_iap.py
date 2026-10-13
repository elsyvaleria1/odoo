import logging
from datetime import UTC
from urllib.parse import urljoin as url_join

import requests

from odoo import fields
from odoo.exceptions import AccessError
from odoo.libs.json import dumps as json_dumps
from odoo.tools import iap
from odoo.tools.iap import IAPServerError

_logger = logging.getLogger(__name__)


class GoogleReserveIAP:
    def register_appointment(self, appointment_type) -> None:

        if not appointment_type.google_reserve_merchant_id:
            raise ValueError(
                "You have to specify an appointment type that has a configured merchant."
            )

        merchant = appointment_type.google_reserve_merchant_id

        iap.jsonrpc(
            url_join(
                merchant._get_google_reserve_iap_endpoint(),
                "/api/google_reserve/1/appointment/register",
            ),
            params={
                "db_uuid": appointment_type.env.registry.settings.get(
                    appointment_type.env, "database.uuid", False
                ),
                "merchant_details": self._format_merchant_details(merchant),
                "appointment_details": {
                    "appointment_type_id": appointment_type.id,
                    "google_reserve_access_token": appointment_type.google_reserve_access_token,
                    "service_name": appointment_type.name,
                    "min_cancellation_hours": appointment_type.min_cancellation_hours,
                    "min_schedule_hours": appointment_type.min_schedule_hours,
                },
            },
            env=appointment_type.env,
        )

    def unregister_appointment(self, appointment_type) -> None:

        merchant = appointment_type.google_reserve_merchant_id
        iap.jsonrpc(
            url_join(
                merchant._get_google_reserve_iap_endpoint(),
                f"/api/google_reserve/1/appointment/{appointment_type.google_reserve_access_token}/unregister",
            ),
            params={
                "db_uuid": appointment_type.env.registry.settings.get(
                    appointment_type.env, "database.uuid", False
                ),
            },
            env=appointment_type.env,
        )

    def update_merchant(self, merchant) -> None:

        iap.jsonrpc(
            url_join(
                merchant._get_google_reserve_iap_endpoint(),
                "/api/google_reserve/1/merchant/update",
            ),
            params={
                "db_uuid": merchant.env.registry.settings.get(
                    merchant.env, "database.uuid", False
                ),
                "merchant_details": self._format_merchant_details(merchant),
            },
            env=merchant.env,
        )

    def update_availabilities(self, appointment_types, start_time, end_time) -> None:
        for appointment_type in appointment_types:
            start_time = start_time.astimezone(UTC)
            end_time = end_time.astimezone(UTC)

            availabilities = appointment_type._google_reserve_get_availabilities(
                start_time=start_time, end_time=end_time
            )

            data = {
                "db_uuid": appointment_types.env.registry.settings.get(
                    appointment_types.env, "database.uuid", False
                ),
                "availabilities": availabilities,
                "start_time": start_time.isoformat().replace("+00:00", "Z"),
                "end_time": end_time.isoformat().replace("+00:00", "Z"),
            }

            try:
                iap.jsonrpc(
                    url_join(
                        appointment_types.env[
                            "google.reserve.merchant"
                        ]._get_google_reserve_iap_endpoint(),
                        f"/api/google_reserve/1/appointment/{appointment_type.sudo().google_reserve_access_token}/update_availabilities",
                    ),
                    params=data,
                    timeout=5,
                    env=appointment_types.env,
                )
            except (IAPServerError, AccessError) as e:
                _logger.warning("Could not update availabilities: %s", e)

    def update_booking(
        self, appointment_type, calendar_event_ids, event_update_values
    ) -> None:

        if not appointment_type.google_reserve_enable:
            return

        booking_values = {}
        if event_update_values.get("active") is False:
            booking_values["status"] = "CANCELED"

        if "start" in event_update_values:
            start = event_update_values["start"]
            if isinstance(start, str):
                start = fields.Datetime.from_string(start)
            booking_values["startTime"] = start.isoformat() + "Z"

            if "stop" in event_update_values and "duration" not in event_update_values:
                stop = event_update_values["stop"]
                if isinstance(stop, str):
                    stop = fields.Datetime.from_string(stop)
                booking_values["duration"] = (
                    str(int((stop - start).total_seconds())) + "s"
                )

        if "duration" in event_update_values:
            booking_values["duration"] = (
                str(event_update_values["duration"] * 3600) + "s"
            )

        if "total_capacity_reserved" in event_update_values:
            booking_values["partySize"] = str(
                event_update_values["total_capacity_reserved"]
            )

        if not booking_values:
            return

        try:
            iap.jsonrpc(
                url_join(
                    appointment_type.env[
                        "google.reserve.merchant"
                    ]._get_google_reserve_iap_endpoint(),
                    f"/api/google_reserve/1/appointment/{appointment_type.sudo().google_reserve_access_token}/update_booking",
                ),
                params={
                    "booking_ids": calendar_event_ids,
                    "booking_values": booking_values,
                    "db_uuid": appointment_type.env.registry.settings.get(
                        appointment_type.env, "database.uuid", False
                    ),
                },
                timeout=5,
                env=appointment_type.env,
            )
        except (IAPServerError, AccessError) as e:
            _logger.warning("Could not update booking: %s", e)

    def upload_availabilities_feed(self, merchants) -> None:

        for merchant in merchants:
            try:
                now = merchant.env.cr.now()
                availabilities_by_token = {}

                google_reserve_appointment_types = (
                    merchant.appointment_type_ids.filtered("google_reserve_enable")
                )
                if not google_reserve_appointment_types:
                    continue

                for appointment_type in google_reserve_appointment_types:
                    availabilities = (
                        appointment_type._google_reserve_get_availabilities()
                    )
                    availabilities_by_token[
                        appointment_type.google_reserve_access_token
                    ] = availabilities

                json_content = json_dumps(availabilities_by_token)
                filename = f"availabilities_feed_{int(now.timestamp())}.json"
                res = merchant.env["ir.egress"].request(
                    "POST",
                    url_join(
                        merchant._get_google_reserve_iap_endpoint(),
                        "/api/google_reserve/1/merchant/upload_availabilities_feed",
                    ),
                    purpose="google_reserve",
                    policy="private",
                    data={
                        "db_uuid": merchant.env.registry.settings.get(
                            merchant.env, "database.uuid", False
                        ),
                        "merchant_id": merchant.id,
                    },
                    files={"upload_file": (filename, json_content.encode())},
                    timeout=120,
                )

                if not res.ok:
                    _logger.warning("Could not upload availability feed: %s", res.text)
            except requests.exceptions.RequestException as e:
                _logger.warning("Could not upload availability feed: %s", e)

    def _format_merchant_details(self, merchant) -> dict:
        return {
            "name": merchant.name,
            "id": merchant.id,
            "callback_url": merchant.get_base_url(),
            "business_category": merchant.business_category,
            "phone": merchant.phone_sanitized,
            "website_url": merchant.website_url,
            "location": {
                "country_code": merchant.location_id.country_id.code,
                "city": merchant.location_id.city,
                "region": merchant.location_id.state_id.code or False,
                "zip": merchant.location_id.zip,
                "street": merchant.location_id.street,
            },
        }
