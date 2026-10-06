from unittest.mock import patch

from odoo.libs.json import dumps_bytes as json_dumps_bytes
from odoo.tests.common import tagged

from odoo.addons.device.tests.common import DeviceHttpCase
from odoo.addons.device_phone_call.models.device_device import COMPANION_SERVICE
from odoo.addons.phone_call.models.phone_call import number_key


@tagged("post_install", "-at_install")
class TestMobileIngestFailure(DeviceHttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.env["device.profile"].create(
            {
                "name": "Mobile Failure Config",
                "auth_type": "bearer",
                "auth_token": "failure_token",
            }
        )
        cls.device = cls.env["device.device"].create(
            {
                "name": "Failure Phone",
                "identifier": "PHONE-FAILURE-001",
                "config_id": cls.config.id,
                "comm_protocol": "https",
                "endpoint": "companion-app",
                "device_category_id": cls.env.ref(
                    "device_mobile.device_category_mobile_phone"
                ).id,
            }
        )
        cls.token = cls.device.credential_id.credential_value

    def _push(self, route, body):
        return self.url_open(
            f"/remote/mobile/PHONE-FAILURE-001/{route}",
            data=json_dumps_bytes(body),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.token}",
            },
        )

    def _calls(self, count=3, offset=0):
        return {
            "calls": [
                {
                    "number": f"+52551000{index + offset:04d}",
                    "direction": "incoming",
                    "timestamp": 1_767_225_600_000 + (index + offset) * 1_000,
                    "duration": 10,
                }
                for index in range(count)
            ]
        }

    def _events(self):
        return self.env["integration.exchange"].search(
            [("channel_id", "=", f"device.device,{self.device.id}")],
            order="id",
        )

    def test_control_a_healthy_batch_is_stored_and_logged_success(self):
        response = self._push("calllog", self._calls())

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["accepted"], 3)
        self.assertEqual(
            self.env["phone.call"].search_count([("device_id", "=", self.device.id)]),
            3,
        )
        self.assertEqual(self._events()[-1].state, "success")

    def test_a_database_error_during_ingest_still_says_why_on_the_event_log(self):
        # A partner matched by _match_partners and deleted before the create
        # lands is an ordinary concurrent-write outcome; the foreign key is
        # what makes it a DATABASE error rather than a Python one, and a
        # database error aborts the cursor for the rest of the transaction.
        with patch.object(
            type(self.env["phone.call"]),
            "_match_partners",
            lambda self, numbers, company: {
                number_key(number): 2_000_000_000 for number in numbers
            },
        ):
            response = self._push("calllog", self._calls(offset=100))

        self.assertEqual(
            self.env["phone.call"].search_count([("device_id", "=", self.device.id)]),
            0,
            "nothing should have been stored",
        )
        self.assertEqual(response.status_code, 500, response.text)
        self.assertEqual(
            response.json().get("error"),
            "processing_error",
            "the controller's own handler must run; without a savepoint the "
            "aborted cursor kills it and Odoo's generic 500 answers instead",
        )
        event = self._events()[-1]
        self.assertEqual(
            event.state,
            "failed",
            "an operator reading integration.exchange must not see this request as "
            "still in flight, nor find no row at all",
        )
        self.assertTrue(
            event.error_message,
            "the reason is the only server-side trace of a batch the handset "
            "will keep re-sending",
        )

    def test_a_database_error_on_the_location_endpoint_behaves_the_same(self):
        def poisoned(self, device, point):
            vals = self._mobile_point_to_vals.__wrapped__(self, device, point)
            if vals:
                vals["device_id"] = 2_000_000_000
            return vals

        with patch.object(
            type(self.env["device.data.log.gps"]), "_mobile_point_to_vals", poisoned
        ):
            response = self._push(
                "location",
                {
                    "points": [
                        {
                            "latitude": 19.4,
                            "longitude": -99.1,
                            "timestamp": 1_767_225_600_000,
                        }
                    ]
                },
            )

        self.assertEqual(response.status_code, 500, response.text)
        self.assertEqual(response.json().get("error"), "processing_error")
        self.assertEqual(self._events()[-1].state, "failed")


@tagged("post_install", "-at_install")
class TestMobileReplyContract(TestMobileIngestFailure):
    def test_every_reply_names_the_service_the_phone_is_talking_to(self):
        stored = self._push("calllog", self._calls(1))
        self.assertEqual(stored.status_code, 200)
        self.assertEqual(stored.json()["service"], COMPANION_SERVICE)
        self.assertEqual(
            stored.json()["max_payload_bytes"],
            self.device.max_payload_size,
            "a phone learns the cap from a success, not only from a 413",
        )

        refused = self._push("calllog", {"calls": []})
        self.assertEqual(refused.status_code, 400)
        self.assertEqual(refused.json()["service"], COMPANION_SERVICE)

    def test_a_413_states_its_cap_in_bytes_beside_the_rounded_message(self):
        self.device.sudo().write({"max_payload_size": 1500})

        response = self._push("calllog", self._calls(40))

        self.assertEqual(response.status_code, 413)
        body = response.json()
        self.assertEqual(body["error"], "payload_too_large")
        self.assertEqual(body["limit_bytes"], 1500)
        self.assertIn("1KB", body["message"])
