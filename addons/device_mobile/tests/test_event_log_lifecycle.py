from odoo.libs.json import dumps_bytes as json_dumps_bytes
from odoo.tests.common import tagged

from odoo.addons.device.tests.common import DeviceHttpCase


@tagged("post_install", "-at_install")
class TestMobileEventLogLifecycle(DeviceHttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.env["device.profile"].create(
            {
                "name": "Mobile Lifecycle Config",
                "auth_type": "bearer",
                "auth_token": "lifecycle_token",
            }
        )
        cls.device = cls.env["device.device"].create(
            {
                "name": "Lifecycle Phone",
                "identifier": "PHONE-LIFECYCLE-001",
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
            f"/remote/mobile/PHONE-LIFECYCLE-001/{route}",
            data=json_dumps_bytes(body),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.token}",
            },
        )

    def _events(self):
        return self.env["integration.exchange"].search(
            [("channel_id", "=", f"device.device,{self.device.id}")],
            order="id",
        )

    def _generic_logs(self):
        return self.env["device.data.log"].search([("device_id", "=", self.device.id)])

    def _run_retry_cron(self):
        self.env["integration.exchange"]._cron_retry_failed_events()
        self.env.invalidate_all()

    def test_a_stored_batch_closes_its_event_log(self):
        response = self._push(
            "location",
            {
                "points": [
                    {"latitude": 19.4, "longitude": -99.1, "timestamp": 1785339000000}
                ]
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._events().state, "success")

    def test_the_retry_cron_does_not_store_the_batch_a_second_time(self):
        self._push(
            "location",
            {
                "points": [
                    {"latitude": 19.4, "longitude": -99.1, "timestamp": 1785339000000}
                ]
            },
        )
        before = len(self._generic_logs())

        self._run_retry_cron()

        self.assertEqual(
            len(self._generic_logs()),
            before,
            "the cron replayed a request the route had already stored",
        )
        self.assertEqual(len(self._events()), 1)

    def test_a_batch_nothing_was_stored_from_is_recorded_as_failed(self):
        response = self._push("location", {"points": [{"latitude": None}]})

        self.assertEqual(response.status_code, 422)
        self.assertEqual(self._events().state, "failed")

    def test_a_refused_batch_is_not_scheduled_for_a_server_side_retry(self):
        self._push("location", {"points": [{"latitude": None}]})

        event = self._events()
        self.assertEqual(event.state, "failed")
        self.assertFalse(event.date_next_retry)

        self._run_retry_cron()

        self.assertEqual(len(self._generic_logs()), 0)

    def test_a_call_log_push_closes_its_event_log(self):
        response = self._push(
            "calllog",
            {"calls": [{"number": "5512345678", "direction": "incoming"}]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._events().state, "success")

    def test_an_empty_payload_is_recorded_rather_than_left_pending(self):
        response = self._push("calllog", {"calls": []})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self._events().state, "failed")
