from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import dumps_bytes as json_dumps_bytes
from odoo.tests.common import tagged

from odoo.addons.device.tests.common import (
    DeviceHttpCase,
    DeviceTransactionCase,
    NarrowedReceiver,
)
from odoo.addons.device_gps.models.device_device import (
    TRACKER_AUTH_MODE_PARAM,
    TRACKER_MAX_ANONYMOUS_BODY,
    TRACKER_NACK,
)

RECEIVER_KEY = "0012345678"


class TestTrackerAuthMode(DeviceTransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.env["device.profile"].create(
            {"name": "Webhook Auth Config", "gps_protocol": "teltonika"}
        )
        cls.device = cls.env["device.device"].create(
            {
                "name": "Webhook Tracker",
                "identifier": "WEBHOOK-AUTH-1",
                "gps_receiver_key": RECEIVER_KEY,
                "config_id": cls.config.id,
                "comm_protocol": "http",
                "endpoint": "10.0.0.5",
                "device_category_id": cls.env.ref("device.device_category_gps").id,
            }
        )

    def _set_mode(self, mode):
        self.env["ir.config_parameter"].sudo().set_param(TRACKER_AUTH_MODE_PARAM, mode)

    def test_default_mode_is_enforce(self):
        self.env["ir.config_parameter"].sudo().search(
            [("key", "=", TRACKER_AUTH_MODE_PARAM)]
        ).unlink()
        self.assertEqual(self.device._inbound_auth_mode(), "enforce")

    def test_a_tracker_reads_the_mode_parameter_by_itself(self):
        self._set_mode("audit")
        self.assertEqual(
            self.device._inbound_auth_mode(),
            self.device._inbound_auth_mode(TRACKER_AUTH_MODE_PARAM),
        )
        self.assertEqual(self.device._inbound_auth_mode(), "audit")

    def test_an_unrecognised_mode_falls_back_to_enforce(self):
        self._set_mode("enfrce")
        self.assertEqual(self.device._inbound_auth_mode(), "enforce")

    def test_a_device_of_another_kind_keeps_the_gate_default(self):
        self._set_mode("off")
        other = self._create_device_device(
            config=self.config, identifier="NOT-A-TRACKER", device_category_id=False
        )
        self.assertEqual(other._inbound_auth_mode(), "enforce")


@tagged("post_install", "-at_install")
class TestTrackerWebhook(DeviceHttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.env["device.profile"].create(
            {"name": "Webhook Auth Config", "gps_protocol": "teltonika"}
        )
        cls.device = cls.env["device.device"].create(
            {
                "name": "Webhook Tracker",
                "identifier": "WEBHOOK-AUTH-1",
                "gps_receiver_key": RECEIVER_KEY,
                "config_id": cls.config.id,
                "comm_protocol": "http",
                "endpoint": "10.0.0.5",
                "device_category_id": cls.env.ref("device.device_category_gps").id,
            }
        )
        cls.token = cls.device.credential_id.sudo().credential_value

    def setUp(self):
        super().setUp()
        self._set_mode("enforce")

    def _set_mode(self, mode):
        self.env["ir.config_parameter"].sudo().set_param(TRACKER_AUTH_MODE_PARAM, mode)

    def _push(self, token=None, receiver_key=RECEIVER_KEY, body=None):
        body = (
            body
            or json_dumps_bytes({"state": {"reported": {"14": receiver_key, "latlng": "19.4,-99.1"}}})
        )
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return self.url_open("/remote/gps/webhook", data=body, headers=headers)

    def _exchanges(self):
        return self.env["integration.exchange"].search(
            [("channel_id", "=", f"device.device,{self.device.id}")]
        )

    def _admitted(self, **kwargs):
        before = len(self._exchanges())
        response = self._push(**kwargs)
        self.assertEqual(response.status_code, 200)
        return len(self._exchanges()) > before, response

    def _signature(self, response):
        return (response.status_code, response.content)

    def test_enforce_rejects_an_anonymous_push(self):
        admitted, response = self._admitted()
        self.assertFalse(admitted)
        self.assertEqual(response.content, TRACKER_NACK)

    def test_enforce_rejects_a_wrong_token(self):
        admitted, response = self._admitted(token="not-the-token")
        self.assertFalse(admitted)
        self.assertEqual(response.content, TRACKER_NACK)

    def test_enforce_accepts_the_device_token(self):
        admitted, _response = self._admitted(token=self.token)
        self.assertTrue(admitted)
        self.assertEqual(self._exchanges().sorted("id")[-1].event_type, "gps_fix")

    def test_audit_accepts_an_anonymous_push(self):
        self._set_mode("audit")
        admitted, _response = self._admitted()
        self.assertTrue(admitted)

    def test_off_skips_the_check(self):
        self._set_mode("off")
        admitted, _response = self._admitted()
        self.assertTrue(admitted)

    def test_every_refusal_looks_the_same(self):
        baseline = (200, TRACKER_NACK)

        self.assertEqual(self._signature(self._push()), baseline)
        self.assertEqual(self._signature(self._push(token="not-the-token")), baseline)
        self.assertEqual(
            self._signature(self._push(receiver_key="000000000000000")),
            baseline,
            "a registered receiver key must be refused exactly like anything else",
        )

        self.device.write({"ip_whitelist": "10.0.0.0/8"})
        self.assertEqual(self._signature(self._push(token=self.token)), baseline)
        self.device.write({"ip_whitelist": False})

    def test_duplicate_key_in_another_company_is_refused_in_every_mode(self):
        company = self.env["res.company"].create({"name": "Other tracker tenant"})
        self._create_device_device(
            identifier="AMBIGUOUS-TRACKER",
            gps_receiver_key=RECEIVER_KEY,
            company_id=company.id,
        )
        for mode in ("enforce", "audit", "off"):
            with self.subTest(mode=mode):
                self._set_mode(mode)
                admitted, response = self._admitted(token=self.token)
                self.assertFalse(admitted)
                self.assertEqual(response.content, TRACKER_NACK)

    def test_non_scalar_keys_are_refused_without_server_errors(self):
        for key in (True, 1.5, [], {}, None):
            with self.subTest(key=key):
                admitted, response = self._admitted(token=self.token, receiver_key=key)
                self.assertFalse(admitted)
                self.assertEqual(response.content, TRACKER_NACK)

    def test_authentication_does_not_spend_the_decryption_budget(self):
        self.device.write({"rate_limit_enabled": False})
        for attempt in range(130):
            admitted, _response = self._admitted(token=self.token)
            self.assertTrue(
                admitted,
                f"push {attempt + 1} was refused with the endpoint limiter off, "
                f"so authentication is still spending the decryption budget",
            )

    def test_the_endpoint_rate_limit_still_applies(self):
        self.device.write(
            {
                "rate_limit_enabled": True,
                "rate_limit_requests": 5,
                "rate_limit_window_seconds": 60,
            }
        )
        outcomes = [self._admitted(token=self.token)[0] for _ in range(8)]
        self.assertTrue(outcomes[0], "the first push must be accepted")
        self.assertIn(
            False, outcomes, "the configured rate limit must still refuse pushes"
        )


@tagged("post_install", "-at_install")
class TestWebhookRefusesWhatItCannotName(DeviceHttpCase):
    def _post(self, body, headers=None):
        return self.url_open(
            "/remote/gps/webhook",
            data=body,
            headers={"Content-Type": "application/json", **(headers or {})},
        )

    def _unknown_rows(self):
        return self.env["integration.exchange"].search(
            [
                ("state", "=", "refused"),
                ("refusal_reason", "=", "endpoint_not_found"),
                ("channel_name", "like", "device.device:%"),
            ]
        )

    def test_an_unknown_receiver_key_is_refused_and_recorded_once_per_caller(self):
        body = json_dumps(
            {"state": {"reported": {"14": "000000000000999", "latlng": "19.4,-99.1"}}}
        )

        first = self._post(body.encode())
        second = self._post(body.encode())

        self.assertEqual(first.content, TRACKER_NACK)
        self.assertEqual(second.content, TRACKER_NACK)
        rows = self._unknown_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows.attempt_count, 2)
        self.assertEqual(
            rows.channel_name, "device.device: unresolved GPS receiver key"
        )

    def test_a_body_past_the_cap_is_refused_without_a_declared_length(self):
        oversize = b"[" + b"0," * (TRACKER_MAX_ANONYMOUS_BODY // 2) + b"0]"

        def chunks():
            yield oversize

        response = self._post(chunks())

        self.assertEqual(response.content, TRACKER_NACK)


@tagged("post_install", "-at_install")
class TestTrackerWebhookWithoutSu(NarrowedReceiver, TestTrackerWebhook):
    pass
