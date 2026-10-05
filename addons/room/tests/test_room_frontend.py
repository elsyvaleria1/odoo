import pathlib
from datetime import datetime

from freezegun import freeze_time

from odoo.tests.common import HttpCase, JsonRpcException, tagged
from odoo.tools.misc import file_path

from odoo.addons.room.tests.common import RoomCommon
from odoo.addons.web.tests.test_split_frontend_page import _MODULE_SCRIPT_RE


@tagged("post_install", "-at_install")
class TestRoomFrontend(RoomCommon, HttpCase):
    @freeze_time("2023-05-16 07:00:00")
    def test_unscheduled_private_claims_do_not_break_the_kiosk(self):
        self.env["resource.reservation"].create(
            [
                {
                    "name": "Private unscheduled work",
                    "resource_id": self.resources[0].id,
                    "date_end": datetime(2023, 5, 16, 18),
                },
                {
                    "name": "Private maintenance",
                    "resource_id": self.resources[0].id,
                    "date_start": datetime(2023, 5, 16, 8),
                    "date_end": datetime(2023, 5, 16, 9),
                },
            ]
        )
        self.authenticate(None, None)
        blocks = self.call_jsonrpc(
            f"/room/{self.resources[0].access_token}/get_existing_bookings", {}
        )
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]["name"], "Unavailable")
        self.assertEqual(blocks[0]["start_datetime"], "2023-05-16 08:00:00")
        self.assertTrue(blocks[0]["readonly"])

    @freeze_time("2023-05-15 11:15:00")
    def test_room_frontend(self):
        self.authenticate(None, None)
        res = self.url_open(f"/room/{self.resources[0].short_code}/book")
        self.assertEqual(res.status_code, 200)

        access_token = self.resources[0].access_token
        booking_id = self.call_jsonrpc(
            f"/room/{access_token}/booking/create",
            {
                "name": "public booking",
                "start_datetime": "2023-05-15 14:00:00",
                "stop_datetime": "2023-05-15 15:00:00",
            },
        )
        booking = self.env["calendar.event"].browse(booking_id)
        self.assertEqual(booking.name, "public booking")
        self.assertEqual(booking.resource_ids, self.resources[0])
        self.assertFalse(booking.user_id)
        self.assertEqual(booking.reservation_ids.enforcement_mode, "soft")
        self.assertTrue(booking.reservation_ids.resource_id.enforce_booking_limit)

        with self.assertRaises(JsonRpcException, msg="werkzeug.exceptions.NotFound"):
            self.call_jsonrpc(
                f"/room/{access_token[1:]}/booking/create",
                {
                    "name": "public booking",
                    "start_datetime": "2023-05-15 15:00:00",
                    "stop_datetime": "2023-05-15 16:00:00",
                },
            )

        self.env["resource.reservation"].create(
            {
                "name": "Repainting",
                "resource_id": self.rooms[0].resource_id.id,
                "date_start": datetime(2023, 5, 15, 16, 0),
                "date_end": datetime(2023, 5, 15, 17, 0),
                "enforcement_mode": "hard",
            }
        )
        bookings = self.call_jsonrpc(f"/room/{access_token}/get_existing_bookings", {})
        self.assertEqual(
            [(b["start_datetime"], b.get("readonly", False)) for b in bookings],
            [
                ("2023-05-15 11:00:00", False),
                ("2023-05-15 14:00:00", False),
                ("2023-05-15 16:00:00", True),
            ],
        )

        self.call_jsonrpc(
            f"/room/{access_token}/booking/{self.bookings[1].id}/update",
            {
                "name": "rescheduled booking",
                "start_datetime": "2023-05-15 12:00:00",
                "stop_datetime": "2023-05-15 13:00:00",
            },
        )
        self.assertEqual(self.bookings[1].name, "rescheduled booking")
        self.assertEqual(self.bookings[1].start, datetime(2023, 5, 15, 12, 0))
        self.assertEqual(self.bookings[1].stop, datetime(2023, 5, 15, 13, 0))

        with self.assertRaises(JsonRpcException, msg="werkzeug.exceptions.NotFound"):
            self.call_jsonrpc(
                f"/room/{self.resources[1].access_token}/booking/{self.bookings[1].id}/update",
                {
                    "name": "failed reschedule",
                    "start_datetime": "2023-05-15 13:00:00",
                    "stop_datetime": "2023-05-15 14:00:00",
                },
            )
        self.assertEqual(self.bookings[1].name, "rescheduled booking")

        self.call_jsonrpc(
            f"/room/{access_token}/booking/{self.bookings[1].id}/delete", {}
        )
        self.assertFalse(self.bookings[1].exists())

        with self.assertRaises(JsonRpcException, msg="werkzeug.exceptions.NotFound"):
            self.call_jsonrpc(
                f"/room/{self.resources[1].access_token}/booking/{self.bookings[0].id}/delete",
                {},
            )
        self.assertTrue(self.bookings[0].exists())

    def test_room_backend_tour(self):
        self.start_tour("/odoo/meeting-rooms", "room_backend_tour", login="admin")
        booking = self.env["calendar.event"].search([("name", "=", "Tour meeting")])
        self.assertEqual(booking.resource_ids, self.resources[1])
        self.assertEqual(booking.reservation_ids.resource_id, self.rooms[1].resource_id)
        self.assertEqual(booking.appointment_type_id, self.room_type)

    def test_the_booking_bundle_does_not_inline_web_core_again(self):
        # room.assets_room_booking is a secondary of the frontend family: the
        # session module the minimal and lazy halves carry is stubbed to their
        # loader, not compiled into the booking bundle a second time
        self.authenticate(None, None)
        html = self.url_open(f"/room/{self.resources[0].short_code}/book").text
        scripts = [
            src
            for src, bundle in _MODULE_SCRIPT_RE.findall(html)
            if bundle == "room.assets_room_booking"
        ]
        self.assertTrue(scripts, "fixture: the page serves the compiled booking bundle")
        session = pathlib.Path(file_path("web/static/src/session.js"))
        for src in scripts:
            meta = self.url_open(src.removesuffix(".esm.js") + ".meta.json").json()
            inlined = [
                path
                for path, info in meta["inputs"].items()
                if path.endswith("web/static/src/session.js")
                and info["bytes"] == session.stat().st_size
            ]
            self.assertEqual(inlined, [], src)
