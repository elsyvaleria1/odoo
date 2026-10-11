import calendar as cal
from datetime import datetime, timedelta
from unittest.mock import patch

from freezegun import freeze_time

from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads
from odoo.tests import common, tagged

from odoo.addons.appointment_google_reserve.tests.common import GoogleReserveCommon
from odoo.addons.calendar.models.utils import generate_calendar_token


@tagged("appointment_google_reserve")
class AppointmentGoogleReserveControllerTest(GoogleReserveCommon, common.HttpCase):

    @freeze_time("2022-02-14 07-00-00")
    def test_google_reserve_availability_lookup(self):

        start_slot = datetime(2022, 2, 14, 15, 0, 0)
        response = self.opener.get(
            f"{self.base_url()}/appointment/{self.apt_type_resource_google.id}/{self.apt_type_resource_google.google_reserve_access_token}/google_reserve/availabilities",
            data=json_dumps(
                [
                    {
                        "duration_sec": "3600",
                        "resource_ids": {
                            "party_size": party_size,
                        },
                        "start_sec": self._to_utc(start_slot + timedelta(hours=i)),
                    }
                    for i in range(4)
                    for party_size in range(1, 6)
                ]
            ),
            headers={
                "Content-Type": "application/json",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(bool(response.json()))

        expected_availabilities = [
            {"party_size": 1, "start_time": 15, "available": True},
            {"party_size": 2, "start_time": 15, "available": True},
            {"party_size": 3, "start_time": 15, "available": True},
            {"party_size": 4, "start_time": 15, "available": True},
            {
                "party_size": 5,
                "start_time": 15,
                "available": False,
            },
            {"party_size": 1, "start_time": 16, "available": True},
            {"party_size": 2, "start_time": 16, "available": True},
            {"party_size": 3, "start_time": 16, "available": True},
            {"party_size": 4, "start_time": 16, "available": True},
            {
                "party_size": 5,
                "start_time": 16,
                "available": False,
            },
            {"party_size": 1, "start_time": 17, "available": True},
            {"party_size": 2, "start_time": 17, "available": True},
            {"party_size": 3, "start_time": 17, "available": True},
            {"party_size": 4, "start_time": 17, "available": True},
            {
                "party_size": 5,
                "start_time": 17,
                "available": False,
            },
            {"party_size": 1, "start_time": 18, "available": False},
            {"party_size": 2, "start_time": 18, "available": False},
            {"party_size": 3, "start_time": 18, "available": False},
            {"party_size": 4, "start_time": 18, "available": False},
            {
                "party_size": 5,
                "start_time": 18,
                "available": False,
            },
        ]

        for availability, expected_availability in zip(
            response.json(), expected_availabilities, strict=False
        ):
            slot_time = availability.get("slot_time")
            self.assertEqual(
                slot_time.get("resource_ids").get("party_size"),
                expected_availability["party_size"],
            )
            expected_start_sec = self._to_utc(
                start_slot.replace(hour=expected_availability["start_time"])
            )
            self.assertEqual(slot_time.get("start_sec"), expected_start_sec)
            self.assertEqual(
                availability.get("available"), expected_availability["available"]
            )

        response = self.opener.get(
            f"{self.base_url()}/appointment/{self.apt_type_resource_google.id}/{self.apt_type_resource_google.google_reserve_access_token}/google_reserve/availabilities",
            data=json_dumps(
                [
                    {
                        "duration_sec": "3600",
                        "resource_ids": {
                            "party_size": 4,
                        },
                        "start_sec": self._to_utc(start_slot),
                    }
                ]
            ),
            headers={
                "Content-Type": "application/json",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(bool(response.json()))
        availability = response.json()[0]
        slot_time = availability.get("slot_time")
        self.assertEqual(slot_time.get("resource_ids").get("party_size"), 4)
        self.assertEqual(slot_time.get("start_sec"), self._to_utc(start_slot))
        self.assertEqual(availability.get("available"), True)

    @freeze_time("2022-02-14 07-00-00")
    @patch(
        "odoo.addons.appointment_google_reserve.tools.google_reserve_iap.GoogleReserveIAP.update_availabilities",
        autospec=True,
    )
    def test_google_reserve_availability_lookup_combinable(self, update_availabilities):
        self.apt_type_resources_table_1.write(
            {
                "combinable_resource_ids": [(4, self.apt_type_resources_table_2.id)],
            }
        )

        self.apt_type_resources_table_2.write(
            {
                "combinable_resource_ids": [(4, self.apt_type_resources_table_1.id)],
            }
        )

        self.env["calendar.event"].create(
            [
                {
                    "appointment_type_id": self.apt_type_resource_google.id,
                    "name": "Booking 1",
                    "start": datetime(2022, 2, 14, 15, 0, 0),
                    "stop": datetime(2022, 2, 14, 16, 0, 0),
                    "booking_line_ids": [
                        (
                            0,
                            0,
                            {
                                "resource_id": self.apt_type_resources_table_1.id,
                                "capacity_reserved": 3,
                                "capacity_used": 4,
                            },
                        )
                    ],
                },
                {
                    "appointment_type_id": self.apt_type_resource_google.id,
                    "name": "Booking 2",
                    "start": datetime(2022, 2, 14, 16, 0, 0),
                    "stop": datetime(2022, 2, 14, 17, 0, 0),
                    "booking_line_ids": [
                        (
                            0,
                            0,
                            {
                                "resource_id": self.apt_type_resources_table_1.id,
                                "capacity_reserved": 4,
                                "capacity_used": 4,
                            },
                        ),
                        (
                            0,
                            0,
                            {
                                "resource_id": self.apt_type_resources_table_2.id,
                                "capacity_reserved": 1,
                                "capacity_used": 2,
                            },
                        ),
                    ],
                },
            ]
        )

        start_slot = datetime(2022, 2, 14, 15, 0, 0)
        response = self.opener.get(
            f"{self.base_url()}/appointment/{self.apt_type_resource_google.id}/{self.apt_type_resource_google.google_reserve_access_token}/google_reserve/availabilities",
            data=json_dumps(
                [
                    {
                        "duration_sec": "3600",
                        "resource_ids": {
                            "party_size": party_size,
                        },
                        "start_sec": self._to_utc(start_slot + timedelta(hours=i)),
                    }
                    for i in range(3)
                    for party_size in range(1, 9)
                ]
            ),
            headers={
                "Content-Type": "application/json",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(bool(response.json()))

        expected_availabilities = [
            {"party_size": 1, "start_time": 15, "available": True},
            {"party_size": 2, "start_time": 15, "available": True},
            {
                "party_size": 3,
                "start_time": 15,
                "available": False,
            },
            {
                "party_size": 4,
                "start_time": 15,
                "available": False,
            },
            {
                "party_size": 5,
                "start_time": 15,
                "available": False,
            },
            {
                "party_size": 6,
                "start_time": 15,
                "available": False,
            },
            {
                "party_size": 7,
                "start_time": 15,
                "available": False,
            },
            {
                "party_size": 8,
                "start_time": 15,
                "available": False,
            },
            {
                "party_size": 1,
                "start_time": 16,
                "available": False,
            },
            {
                "party_size": 2,
                "start_time": 16,
                "available": False,
            },
            {
                "party_size": 3,
                "start_time": 16,
                "available": False,
            },
            {
                "party_size": 4,
                "start_time": 16,
                "available": False,
            },
            {
                "party_size": 5,
                "start_time": 16,
                "available": False,
            },
            {
                "party_size": 6,
                "start_time": 16,
                "available": False,
            },
            {
                "party_size": 7,
                "start_time": 16,
                "available": False,
            },
            {
                "party_size": 8,
                "start_time": 16,
                "available": False,
            },
            {"party_size": 1, "start_time": 17, "available": True},
            {"party_size": 2, "start_time": 17, "available": True},
            {"party_size": 3, "start_time": 17, "available": True},
            {"party_size": 4, "start_time": 17, "available": True},
            {"party_size": 5, "start_time": 17, "available": True},
            {"party_size": 6, "start_time": 17, "available": True},
            {
                "party_size": 7,
                "start_time": 17,
                "available": False,
            },
            {
                "party_size": 8,
                "start_time": 17,
                "available": False,
            },
        ]

        for availability, expected_availability in zip(
            response.json(), expected_availabilities, strict=False
        ):
            slot_time = availability.get("slot_time")
            self.assertEqual(
                slot_time.get("resource_ids").get("party_size"),
                expected_availability["party_size"],
            )
            expected_start_sec = self._to_utc(
                start_slot.replace(hour=expected_availability["start_time"])
            )
            self.assertEqual(slot_time.get("start_sec"), expected_start_sec)
            self.assertEqual(
                availability.get("available"), expected_availability["available"]
            )


    @freeze_time("2022-02-14 07-00-00")
    @patch(
        "odoo.addons.appointment_google_reserve.tools.google_reserve_iap.GoogleReserveIAP.update_availabilities",
        autospec=True,
    )
    def test_google_reserve_create_cancel_booking(self, update_availabilities):

        start_slot = datetime(2022, 2, 14, 15, 0, 0)

        slot_creation_data = {
            "confirmation_mode": "CONFIRMATION_MODE_SYNCHRONOUS",
            "duration_sec": "3600",
            "merchant_id": str(self.apt_type_resource_google.id),
            "resources": {
                "party_size": "4",
            },
            "service_id": str(self.apt_type_resource_google.id),
            "start_sec": self._to_utc(start_slot),
        }

        create_response = self.url_open(
            f"/appointment/{self.apt_type_resource_google.id}/{self.apt_type_resource_google.google_reserve_access_token}/google_reserve/booking/create",
            data=json_dumps(
                {
                    "idempotency_token": "token1",
                    "slot": slot_creation_data,
                    "user_information": {
                        "email": "john.doe@test.com",
                        "family_name": "Doe",
                        "given_name": "John",
                        "telephone": "+32476112233",
                        "user_id": "1234567890",
                    },
                }
            ),
            headers={
                "Content-Type": "application/json",
            },
        )

        self.assertEqual(create_response.status_code, 200)
        create_data = create_response.json()
        self.env["calendar.event"].flush_model()

        self.assertFalse(bool(create_data.get("booking_failure")))
        self.assertTrue(bool(create_data.get("booking").get("booking_id")))
        booking_id = create_data["booking"]["booking_id"]
        calendar_event = self.env["calendar.event"].browse(int(booking_id))
        self.assertTrue(bool(calendar_event.exists()))
        self.assertEqual(
            calendar_event.appointment_type_id, self.apt_type_resource_google
        )
        self.assertEqual(calendar_event.total_capacity_reserved, 4)
        self.assertEqual(calendar_event.start, start_slot)

        self.assertEqual(update_availabilities.call_count, 1)
        args, _kwargs = update_availabilities.call_args_list[0]
        self.assertEqual(args[1], calendar_event.appointment_type_id)
        self.assertEqual(args[2], calendar_event.start)
        self.assertEqual(args[3], calendar_event.stop)

        old_conference_token = calendar_event.access_token
        calendar_event.access_token = generate_calendar_token()
        self.assertNotEqual(calendar_event.access_token, old_conference_token)
        retry_response = self.url_open(
            create_response.request.url,
            data=create_response.request.body,
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(retry_response.status_code, 200)
        self.assertEqual(retry_response.json()["booking"]["booking_id"], booking_id)
        self.assertEqual(update_availabilities.call_count, 1)

        second_booking_data = {
            "idempotency_token": "token2",
            "slot": slot_creation_data,
            "user_information": {
                "email": "raoulette.poilvache@test.com",
                "family_name": "poilvache",
                "given_name": "raoulette",
                "telephone": "+32476112244",
                "user_id": "1234567891",
            },
        }

        create_response = self.url_open(
            f"/appointment/{self.apt_type_resource_google.id}/{self.apt_type_resource_google.google_reserve_access_token}/google_reserve/booking/create",
            data=json_dumps({**second_booking_data}),
            headers={
                "Content-Type": "application/json",
            },
        )

        self.assertEqual(create_response.status_code, 200)
        create_data = create_response.json()

        self.assertEqual(
            create_data.get("booking_failure").get("cause"), "SLOT_UNAVAILABLE"
        )
        self.assertFalse(bool(create_data.get("booking").get("booking_id")))

        cancel_response = self.url_open(
            f"/appointment/{self.apt_type_resource_google.id}/{self.apt_type_resource_google.google_reserve_access_token}/google_reserve/booking/{booking_id}/update",
            data=json_dumps(
                {
                    "booking": {
                        "booking_id": str(booking_id),
                        "status": "CANCELED",
                    }
                }
            ),
            headers={
                "Content-Type": "application/json",
            },
        )
        self.assertEqual(cancel_response.status_code, 200)
        cancel_data = cancel_response.json()

        self.assertFalse(bool(cancel_data.get("booking_failure")))

        self.assertEqual(update_availabilities.call_count, 2)
        args, _kwargs = update_availabilities.call_args_list[0]
        self.assertEqual(args[1], calendar_event.appointment_type_id)
        self.assertEqual(args[2], calendar_event.start)
        self.assertEqual(args[3], calendar_event.stop)

        self.env["calendar.event"].flush_model()
        self.assertFalse(calendar_event.active)

        cancel_response = self.url_open(
            f"/appointment/{self.apt_type_resource_google.id}/{self.apt_type_resource_google.google_reserve_access_token}/google_reserve/booking/{booking_id}/update",
            data=json_dumps(
                {
                    "booking": {
                        "booking_id": str(booking_id),
                        "status": "CANCELED",
                    }
                }
            ),
            headers={
                "Content-Type": "application/json",
            },
        )
        self.assertEqual(cancel_response.status_code, 200)
        cancel_data = cancel_response.json()
        self.assertEqual(
            cancel_data.get("booking_failure").get("cause"), "BOOKING_ALREADY_CANCELLED"
        )

        self.assertEqual(update_availabilities.call_count, 2)

        create_response = self.url_open(
            f"/appointment/{self.apt_type_resource_google.id}/{self.apt_type_resource_google.google_reserve_access_token}/google_reserve/booking/create",
            data=json_dumps({"idempotency_token": "token3", **second_booking_data}),
            headers={
                "Content-Type": "application/json",
            },
        )

        self.assertEqual(create_response.status_code, 200)
        create_data = create_response.json()
        self.env["calendar.event"].flush_model()

        self.assertFalse(bool(create_data.get("booking_failure")))
        self.assertTrue(bool(create_data.get("booking").get("booking_id")))
        booking_id = create_data["booking"]["booking_id"]
        calendar_event_2 = self.env["calendar.event"].browse(int(booking_id))
        self.assertNotEqual(calendar_event, calendar_event_2)
        self.assertTrue(bool(calendar_event_2.exists()))
        self.assertEqual(
            calendar_event_2.appointment_type_id, self.apt_type_resource_google
        )

        self.assertEqual(update_availabilities.call_count, 3)
        args, _kwargs = update_availabilities.call_args_list[1]
        self.assertEqual(args[1], calendar_event_2.appointment_type_id)
        self.assertEqual(args[2], calendar_event_2.start)
        self.assertEqual(args[3], calendar_event_2.stop)

    @freeze_time("2022-02-14 07-00-00")
    @patch(
        "odoo.addons.appointment_google_reserve.tools.google_reserve_iap.GoogleReserveIAP.update_availabilities",
        autospec=True,
    )
    def test_google_reserve_create_update_booking(self, update_availabilities):

        start_slot = datetime(2022, 2, 14, 15, 0, 0)

        create_response = self.url_open(
            f"/appointment/{self.apt_type_resource_google.id}/{self.apt_type_resource_google.google_reserve_access_token}/google_reserve/booking/create",
            data=json_dumps(
                {
                    "idempotency_token": "token1",
                    "slot": {
                        "confirmation_mode": "CONFIRMATION_MODE_SYNCHRONOUS",
                        "duration_sec": "3600",
                        "merchant_id": str(self.apt_type_resource_google.id),
                        "resources": {
                            "party_size": "2",
                        },
                        "service_id": str(self.apt_type_resource_google.id),
                        "start_sec": self._to_utc(start_slot),
                    },
                    "user_information": {
                        "email": "john.doe@test.com",
                        "family_name": "Doe",
                        "given_name": "John",
                        "telephone": "+32476112233",
                        "user_id": "1234567890",
                    },
                }
            ),
            headers={
                "Content-Type": "application/json",
            },
        )

        self.assertEqual(create_response.status_code, 200)
        create_data = create_response.json()
        self.env["calendar.event"].flush_model()

        self.assertFalse(bool(create_data.get("booking_failure")))
        self.assertTrue(bool(create_data.get("booking").get("booking_id")))
        booking_id = create_data["booking"]["booking_id"]
        calendar_event = self.env["calendar.event"].browse(int(booking_id))
        self.assertTrue(bool(calendar_event.exists()))
        self.assertEqual(
            calendar_event.appointment_type_id, self.apt_type_resource_google
        )
        self.assertEqual(calendar_event.total_capacity_reserved, 2)
        self.assertEqual(calendar_event.start, start_slot)

        self.assertEqual(update_availabilities.call_count, 1)
        args, _kwargs = update_availabilities.call_args_list[0]
        self.assertEqual(args[1], calendar_event.appointment_type_id)
        self.assertEqual(args[2], calendar_event.start)
        self.assertEqual(args[3], calendar_event.stop)

        update_response = self.url_open(
            f"/appointment/{self.apt_type_resource_google.id}/{self.apt_type_resource_google.google_reserve_access_token}/google_reserve/booking/{booking_id}/update",
            data=json_dumps(
                {
                    "booking": {
                        "booking_id": str(booking_id),
                        "slot": {
                            "duration_sec": "3600",
                            "resources": {
                                "party_size": 4,
                            },
                            "start_sec": self._to_utc(start_slot + timedelta(hours=2)),
                        },
                    }
                }
            ),
            headers={
                "Content-Type": "application/json",
            },
        )

        self.assertEqual(update_response.status_code, 200)
        update_data = json_loads(update_response.content)
        self.assertFalse(bool(update_data.get("booking_failure")))
        calendar_event.flush_recordset()
        self.assertEqual(calendar_event.total_capacity_reserved, 4)
        self.assertEqual(calendar_event.start, start_slot + timedelta(hours=2))

        self.assertEqual(update_availabilities.call_count, 2)
        args, _kwargs = update_availabilities.call_args_list[1]
        self.assertEqual(args[1], calendar_event.appointment_type_id)
        self.assertEqual(
            args[2],
            start_slot,
            "Should update availabilities on Google side based from old event start and not new one",
        )
        self.assertEqual(args[3], calendar_event.stop)

        update_response = self.url_open(
            f"/appointment/{self.apt_type_resource_google.id}/{self.apt_type_resource_google.google_reserve_access_token}/google_reserve/booking/{booking_id}/update",
            data=json_dumps(
                {
                    "booking": {
                        "booking_id": str(booking_id),
                        "slot": {
                            "resources": {
                                "party_size": 5,
                            },
                        },
                    }
                }
            ),
            headers={
                "Content-Type": "application/json",
            },
        )

        self.assertEqual(update_response.status_code, 200)
        update_data = json_loads(update_response.content)
        self.assertEqual(
            update_data.get("booking_failure").get("cause"), "USER_OVER_BOOKING_LIMIT"
        )
        calendar_event.flush_recordset()
        self.assertEqual(calendar_event.total_capacity_reserved, 4)
        self.assertEqual(calendar_event.start, start_slot + timedelta(hours=2))

        self.assertEqual(update_availabilities.call_count, 2)

        update_response = self.url_open(
            f"/appointment/{self.apt_type_resource_google.id}/{self.apt_type_resource_google.google_reserve_access_token}/google_reserve/booking/{booking_id}/update",
            data=json_dumps(
                {
                    "booking": {
                        "booking_id": str(booking_id),
                        "slot": {
                            "duration_sec": "3600",
                            "start_sec": self._to_utc(start_slot + timedelta(hours=3)),
                        },
                    }
                }
            ),
            headers={
                "Content-Type": "application/json",
            },
        )

        self.assertEqual(update_response.status_code, 200)
        update_data = json_loads(update_response.content)
        self.assertEqual(
            update_data.get("booking_failure").get("cause"), "SLOT_UNAVAILABLE"
        )
        calendar_event.flush_recordset()
        self.assertEqual(calendar_event.total_capacity_reserved, 4)
        self.assertEqual(calendar_event.start, start_slot + timedelta(hours=2))

        self.assertEqual(update_availabilities.call_count, 2)

    @freeze_time("2022-02-14 07-00-00")
    @patch(
        "odoo.addons.appointment_google_reserve.tools.google_reserve_iap.GoogleReserveIAP.update_availabilities",
        autospec=True,
    )
    def test_google_reserve_create_update_booking_combinable(
        self, update_availabilities
    ):

        self.apt_type_resources_table_3 = self.env["resource.resource"].create(
            {
                "appointment_type_ids": self.apt_type_resource_google.ids,
                "capacity": 6,
                "name": "Table 3",
                "booking_sequence": 3,
                "combinable_resource_ids": [
                    (4, self.apt_type_resources_table_1.id),
                    (4, self.apt_type_resources_table_2.id),
                ],
            }
        )
        self.apt_resources_google += self.apt_type_resources_table_3

        self.apt_type_resources_table_1.write(
            {
                "combinable_resource_ids": [
                    (4, self.apt_type_resources_table_2.id),
                    (4, self.apt_type_resources_table_3.id),
                ],
            }
        )

        self.apt_type_resources_table_2.write(
            {
                "combinable_resource_ids": [
                    (4, self.apt_type_resources_table_1.id),
                    (4, self.apt_type_resources_table_3.id),
                ],
            }
        )

        create_response = self.url_open(
            f"/appointment/{self.apt_type_resource_google.id}/{self.apt_type_resource_google.google_reserve_access_token}/google_reserve/booking/create",
            data=json_dumps(
                {
                    "idempotency_token": "token1",
                    "slot": {
                        "confirmation_mode": "CONFIRMATION_MODE_SYNCHRONOUS",
                        "duration_sec": "3600",
                        "merchant_id": str(self.apt_type_resource_google.id),
                        "resources": {
                            "party_size": "6",
                        },
                        "service_id": str(self.apt_type_resource_google.id),
                        "start_sec": self._to_utc(datetime(2022, 2, 14, 15, 0, 0)),
                    },
                    "user_information": {
                        "email": "john.doe@test.com",
                        "family_name": "Doe",
                        "given_name": "John",
                        "telephone": "+32476112233",
                        "user_id": "1234567890",
                    },
                }
            ),
            headers={
                "Content-Type": "application/json",
            },
        )

        self.assertEqual(create_response.status_code, 200)
        create_data = create_response.json()
        self.env["calendar.event"].flush_model()

        self.assertFalse(bool(create_data.get("booking_failure")))
        self.assertTrue(bool(create_data.get("booking").get("booking_id")))
        booking_id = create_data["booking"]["booking_id"]
        calendar_event = self.env["calendar.event"].browse(int(booking_id))
        self.assertTrue(bool(calendar_event.exists()))
        self.assertEqual(
            calendar_event.appointment_type_id, self.apt_type_resource_google
        )
        self.assertEqual(calendar_event.total_capacity_reserved, 6)
        self.assertEqual(
            len(calendar_event.booking_line_ids),
            1,
            "Table 3 can accommodate 6 people -> should only use one booking",
        )
        self.assertEqual(
            calendar_event.booking_line_ids[0].resource_id,
            self.apt_type_resources_table_3,
        )

        update_response = self.url_open(
            f"/appointment/{self.apt_type_resource_google.id}/{self.apt_type_resource_google.google_reserve_access_token}/google_reserve/booking/{booking_id}/update",
            data=json_dumps(
                {
                    "booking": {
                        "booking_id": str(booking_id),
                        "slot": {
                            "resources": {
                                "party_size": 11,
                            },
                        },
                    }
                }
            ),
            headers={
                "Content-Type": "application/json",
            },
        )

        self.assertEqual(update_response.status_code, 200)
        update_data = json_loads(update_response.content)
        self.assertFalse(bool(update_data.get("booking_failure")))
        calendar_event.flush_recordset()
        self.assertEqual(calendar_event.total_capacity_reserved, 11)
        self.assertEqual(
            len(calendar_event.booking_line_ids),
            3,
            "By combining all 3 tables we can accommodate 11 people",
        )

        bookings_by_resource = calendar_event.booking_line_ids.grouped("resource_id")
        for resource in self.apt_resources_google:
            self.assertEqual(
                len(
                    bookings_by_resource.get(
                        resource, calendar_event.booking_line_ids.browse()
                    )
                ),
                1,
            )

        update_response = self.url_open(
            f"/appointment/{self.apt_type_resource_google.id}/{self.apt_type_resource_google.google_reserve_access_token}/google_reserve/booking/{booking_id}/update",
            data=json_dumps(
                {
                    "booking": {
                        "booking_id": str(booking_id),
                        "slot": {
                            "resources": {
                                "party_size": 15,
                            },
                        },
                    }
                }
            ),
            headers={
                "Content-Type": "application/json",
            },
        )

        self.assertEqual(update_response.status_code, 200)
        update_data = json_loads(update_response.content)
        self.assertEqual(
            update_data.get("booking_failure").get("cause"), "USER_OVER_BOOKING_LIMIT"
        )
        calendar_event.flush_recordset()
        self.assertEqual(calendar_event.total_capacity_reserved, 11)

        update_response = self.url_open(
            f"/appointment/{self.apt_type_resource_google.id}/{self.apt_type_resource_google.google_reserve_access_token}/google_reserve/booking/{booking_id}/update",
            data=json_dumps(
                {
                    "booking": {
                        "booking_id": str(booking_id),
                        "slot": {
                            "resources": {
                                "party_size": 4,
                            },
                        },
                    }
                }
            ),
            headers={
                "Content-Type": "application/json",
            },
        )

        self.assertEqual(update_response.status_code, 200)
        update_data = update_response.json()
        self.env["calendar.event"].flush_model()

        self.assertFalse(bool(update_data.get("booking_failure")))
        calendar_event.flush_recordset()
        self.assertEqual(calendar_event.total_capacity_reserved, 4)
        self.assertEqual(
            len(calendar_event.booking_line_ids),
            1,
            "Table 1 can accommodate 4 people -> should only use one booking",
        )
        self.assertEqual(
            calendar_event.booking_line_ids[0].resource_id,
            self.apt_type_resources_table_1,
        )

    @freeze_time("2022-02-14 07-00-00")
    @patch(
        "odoo.addons.appointment_google_reserve.tools.google_reserve_iap.GoogleReserveIAP.update_availabilities",
        autospec=True,
    )
    def test_google_reserve_move_booking(self, update_availabilities):

        bookings = self.env["calendar.event"].create(
            [
                {
                    "appointment_type_id": self.apt_type_resource_google.id,
                    "name": "Booking 1",
                    "start": datetime(2022, 2, 14, 15, 0, 0),
                    "stop": datetime(2022, 2, 14, 16, 0, 0),
                    "total_capacity_reserved": 2,
                    "booking_line_ids": [
                        (
                            0,
                            0,
                            {
                                "resource_id": self.apt_type_resources_table_2.id,
                                "capacity_reserved": 2,
                                "capacity_used": 2,
                            },
                        )
                    ],
                },
                {
                    "appointment_type_id": self.apt_type_resource_google.id,
                    "name": "Booking 2",
                    "start": datetime(2022, 2, 14, 16, 0, 0),
                    "stop": datetime(2022, 2, 14, 17, 0, 0),
                    "total_capacity_reserved": 2,
                    "booking_line_ids": [
                        (
                            0,
                            0,
                            {
                                "resource_id": self.apt_type_resources_table_2.id,
                                "capacity_reserved": 2,
                                "capacity_used": 2,
                            },
                        )
                    ],
                },
                {
                    "appointment_type_id": self.apt_type_resource_google.id,
                    "name": "Booking 3",
                    "start": datetime(2022, 2, 14, 17, 0, 0),
                    "stop": datetime(2022, 2, 14, 18, 0, 0),
                    "total_capacity_reserved": 6,
                    "booking_line_ids": [
                        (
                            0,
                            0,
                            {
                                "resource_id": self.apt_type_resources_table_1.id,
                                "capacity_reserved": 4,
                                "capacity_used": 4,
                            },
                        ),
                        (
                            0,
                            0,
                            {
                                "resource_id": self.apt_type_resources_table_2.id,
                                "capacity_reserved": 1,
                                "capacity_used": 2,
                            },
                        ),
                    ],
                },
            ]
        )

        edited_booking = bookings[0]

        update_response = self.url_open(
            f"/appointment/{self.apt_type_resource_google.id}/{self.apt_type_resource_google.google_reserve_access_token}/google_reserve/booking/{edited_booking.id}/update",
            data=json_dumps(
                {
                    "booking": {
                        "booking_id": str(edited_booking.id),
                        "slot": {
                            "duration_sec": "3600",
                            "start_sec": self._to_utc(datetime(2022, 2, 14, 16, 0, 0)),
                        },
                    }
                }
            ),
            headers={
                "Content-Type": "application/json",
            },
        )

        self.assertEqual(update_response.status_code, 200)
        update_data = update_response.json()
        edited_booking.flush_recordset()
        self.assertFalse(bool(update_data.get("booking_failure")))
        self.assertEqual(edited_booking.total_capacity_reserved, 2)
        self.assertEqual(
            len(edited_booking.booking_line_ids),
            1,
            "Table 1 is available can accommodate 4 people -> should only use one booking",
        )
        self.assertEqual(
            edited_booking.booking_line_ids[0].resource_id,
            self.apt_type_resources_table_1,
        )

        update_response = self.url_open(
            f"/appointment/{self.apt_type_resource_google.id}/{self.apt_type_resource_google.google_reserve_access_token}/google_reserve/booking/{edited_booking.id}/update",
            data=json_dumps(
                {
                    "booking": {
                        "booking_id": str(edited_booking.id),
                        "slot": {
                            "duration_sec": "3600",
                            "start_sec": self._to_utc(datetime(2022, 2, 14, 17, 0, 0)),
                        },
                    }
                }
            ),
            headers={
                "Content-Type": "application/json",
            },
        )

        self.assertEqual(update_response.status_code, 200)
        update_data = update_response.json()
        self.assertEqual(
            update_data.get("booking_failure").get("cause"), "SLOT_UNAVAILABLE"
        )
        edited_booking.flush_recordset()
        self.assertEqual(edited_booking.total_capacity_reserved, 2)
        self.assertEqual(
            len(edited_booking.booking_line_ids),
            1,
        )
        self.assertEqual(
            edited_booking.booking_line_ids[0].resource_id,
            self.apt_type_resources_table_1,
        )


    @freeze_time("2022-02-14 07-00-00")
    @patch(
        "odoo.addons.appointment_google_reserve.tools.google_reserve_iap.GoogleReserveIAP.update_availabilities",
        autospec=True,
    )
    def test_google_reserve_availability_lookup_staff(self, update_availabilities):

        start_slot = datetime(2022, 2, 14, 15, 0, 0)
        response = self.opener.get(
            f"{self.base_url()}/appointment/{self.apt_type_staff_google.id}/{self.apt_type_staff_google.google_reserve_access_token}/google_reserve/availabilities",
            data=json_dumps(
                [
                    {
                        "duration_sec": "3600",
                        "start_sec": self._to_utc(start_slot + timedelta(hours=i)),
                    }
                    for i in range(4)
                ]
            ),
            headers={
                "Content-Type": "application/json",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(bool(response.json()))

        expected_availabilities = [
            {"start_time": 15, "available": True},
            {"start_time": 16, "available": True},
            {"start_time": 17, "available": True},
            {"start_time": 18, "available": False},
        ]

        for availability, expected_availability in zip(
            response.json(), expected_availabilities, strict=False
        ):
            slot_time = availability.get("slot_time")
            expected_start_sec = self._to_utc(
                start_slot.replace(hour=expected_availability["start_time"])
            )
            self.assertEqual(slot_time.get("start_sec"), expected_start_sec)
            self.assertEqual(
                availability.get("available"), expected_availability["available"]
            )

        self.env["calendar.event"].create(
            [
                {
                    "name": "Manager Meeting",
                    "start": datetime(2022, 2, 14, 15, 0, 0),
                    "stop": datetime(2022, 2, 14, 16, 0, 0),
                    "partner_ids": [(4, self.apt_manager.partner_id.id)],
                },
                {
                    "name": "Whole Company Meeting",
                    "start": datetime(2022, 2, 14, 16, 0, 0),
                    "stop": datetime(2022, 2, 14, 17, 0, 0),
                    "partner_ids": [
                        (4, self.apt_manager.partner_id.id),
                        (4, self.staff_user_bxls.partner_id.id),
                    ],
                },
            ]
        )
        response = self.opener.get(
            f"{self.base_url()}/appointment/{self.apt_type_staff_google.id}/{self.apt_type_staff_google.google_reserve_access_token}/google_reserve/availabilities",
            data=json_dumps(
                [
                    {
                        "duration_sec": "3600",
                        "start_sec": self._to_utc(start_slot + timedelta(hours=i)),
                    }
                    for i in range(3)
                ]
            ),
            headers={
                "Content-Type": "application/json",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(bool(response.json()))

        expected_availabilities = [
            {"start_time": 15, "available": True},
            {"start_time": 16, "available": False},
            {"start_time": 17, "available": True},
        ]

        for availability, expected_availability in zip(
            response.json(), expected_availabilities, strict=False
        ):
            with self.subTest(
                start_time=expected_availability["start_time"],
                available=expected_availability["available"],
            ):
                slot_time = availability.get("slot_time")
                expected_start_sec = self._to_utc(
                    start_slot.replace(hour=expected_availability["start_time"])
                )
                self.assertEqual(slot_time.get("start_sec"), expected_start_sec)
                self.assertEqual(
                    availability.get("available"), expected_availability["available"]
                )


    @freeze_time("2022-02-14 07-00-00")
    @patch(
        "odoo.addons.appointment_google_reserve.tools.google_reserve_iap.GoogleReserveIAP.update_availabilities",
        autospec=True,
    )
    def test_google_reserve_create_update_booking_staff(self, update_availabilities):

        start_slot = datetime(2022, 2, 14, 15, 0, 0)

        self.apt_type_staff_google.staff_user_ids = [(6, 0, [self.staff_user_bxls.id])]
        self.env["calendar.event"].create(
            {
                "name": "Whole Company Meeting",
                "start": datetime(2022, 2, 14, 17, 0, 0),
                "stop": datetime(2022, 2, 14, 18, 0, 0),
                "partner_ids": [(4, self.staff_user_bxls.partner_id.id)],
            }
        )

        create_response = self.url_open(
            f"/appointment/{self.apt_type_staff_google.id}/{self.apt_type_staff_google.google_reserve_access_token}/google_reserve/booking/create",
            data=json_dumps(
                {
                    "idempotency_token": "token1",
                    "slot": {
                        "confirmation_mode": "CONFIRMATION_MODE_SYNCHRONOUS",
                        "duration_sec": "3600",
                        "merchant_id": str(self.apt_type_staff_google.id),
                        "service_id": str(self.apt_type_staff_google.id),
                        "start_sec": self._to_utc(start_slot),
                    },
                    "user_information": {
                        "email": "john.doe@test.com",
                        "family_name": "Doe",
                        "given_name": "John",
                        "telephone": "+32476112233",
                        "user_id": "1234567890",
                    },
                }
            ),
            headers={
                "Content-Type": "application/json",
            },
        )

        self.assertEqual(create_response.status_code, 200)
        create_data = create_response.json()
        self.env["calendar.event"].flush_model()

        self.assertFalse(bool(create_data.get("booking_failure")))
        self.assertTrue(bool(create_data.get("booking").get("booking_id")))
        booking_id = create_data["booking"]["booking_id"]
        calendar_event = self.env["calendar.event"].browse(int(booking_id))
        self.assertTrue(bool(calendar_event.exists()))
        self.assertEqual(calendar_event.appointment_type_id, self.apt_type_staff_google)
        self.assertEqual(calendar_event.start, start_slot)
        self.assertIn(self.staff_user_bxls.partner_id, calendar_event.partner_ids)

        self.assertEqual(update_availabilities.call_count, 1)
        args, _kwargs = update_availabilities.call_args_list[0]
        self.assertEqual(args[1], calendar_event.appointment_type_id)
        self.assertEqual(args[2], calendar_event.start)
        self.assertEqual(args[3], calendar_event.stop)

        update_response = self.url_open(
            f"/appointment/{self.apt_type_staff_google.id}/{self.apt_type_staff_google.google_reserve_access_token}/google_reserve/booking/{booking_id}/update",
            data=json_dumps(
                {
                    "booking": {
                        "booking_id": str(booking_id),
                        "slot": {
                            "duration_sec": "3600",
                            "start_sec": self._to_utc(start_slot + timedelta(hours=1)),
                        },
                    }
                }
            ),
            headers={
                "Content-Type": "application/json",
            },
        )

        self.assertEqual(update_response.status_code, 200)
        update_data = json_loads(update_response.content)
        self.assertFalse(bool(update_data.get("booking_failure")))
        calendar_event.flush_recordset()
        self.assertEqual(calendar_event.start, start_slot + timedelta(hours=1))

        self.assertEqual(update_availabilities.call_count, 2)

        update_response = self.url_open(
            f"/appointment/{self.apt_type_staff_google.id}/{self.apt_type_staff_google.google_reserve_access_token}/google_reserve/booking/{booking_id}/update",
            data=json_dumps(
                {
                    "booking": {
                        "booking_id": str(booking_id),
                        "slot": {
                            "duration_sec": "3600",
                            "start_sec": self._to_utc(start_slot + timedelta(hours=2)),
                        },
                    }
                }
            ),
            headers={
                "Content-Type": "application/json",
            },
        )

        self.assertEqual(update_response.status_code, 200)
        update_data = json_loads(update_response.content)
        self.assertEqual(
            update_data.get("booking_failure").get("cause"), "SLOT_UNAVAILABLE"
        )
        calendar_event.flush_recordset()
        self.assertEqual(calendar_event.start, start_slot + timedelta(hours=1))

        self.assertEqual(update_availabilities.call_count, 2)

        update_response = self.url_open(
            f"/appointment/{self.apt_type_staff_google.id}/{self.apt_type_staff_google.google_reserve_access_token}/google_reserve/booking/{booking_id}/update",
            data=json_dumps(
                {
                    "booking": {
                        "booking_id": str(booking_id),
                        "slot": {
                            "duration_sec": "3600",
                            "start_sec": self._to_utc(start_slot + timedelta(hours=3)),
                        },
                    }
                }
            ),
            headers={
                "Content-Type": "application/json",
            },
        )

        self.assertEqual(update_response.status_code, 200)
        update_data = json_loads(update_response.content)
        self.assertEqual(
            update_data.get("booking_failure").get("cause"), "SLOT_UNAVAILABLE"
        )
        calendar_event.flush_recordset()
        self.assertEqual(calendar_event.start, start_slot + timedelta(hours=1))

        self.assertEqual(update_availabilities.call_count, 2)


    def _to_utc(self, slot_datetime):
        return str(cal.timegm((slot_datetime).timetuple()))
