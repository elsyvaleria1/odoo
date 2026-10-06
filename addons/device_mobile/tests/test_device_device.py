from unittest.mock import patch

from odoo.exceptions import ValidationError
from odoo.tests.common import tagged

from odoo.addons.device.tests.common import DeviceTransactionCase


@tagged("post_install", "-at_install")
class TestMobileDevice(DeviceTransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.env["device.profile"].create(
            {
                "name": "Dev Config",
                "auth_type": "bearer",
                "auth_token": "dev_token_123",
            }
        )

    def _device(self, identifier, **extra):
        return self.env["device.device"].create(
            {
                "name": identifier,
                "identifier": identifier,
                "config_id": self.config.id,
                "comm_protocol": "https",
                "endpoint": "x",
                **extra,
            }
        )

    def test_mobile_device_gets_recording_sized_payload(self):
        device = self._device(
            "MOB-1",
            device_category_id=self.env.ref(
                "device_mobile.device_category_mobile_phone"
            ).id,
        )
        self.assertGreater(device.max_payload_size, 1048576)

    def test_explicit_payload_is_respected(self):
        device = self._device(
            "MOB-2",
            device_category_id=self.env.ref(
                "device_mobile.device_category_mobile_phone"
            ).id,
            max_payload_size=2048,
        )
        self.assertEqual(device.max_payload_size, 2048)

    def test_non_mobile_device_keeps_default(self):
        device = self._device("IOT-1")
        self.assertEqual(device.max_payload_size, 1048576)

    def test_mobile_device_caps_what_it_logs_of_a_body(self):
        device = self._device(
            "MOBILE-LOGCAP",
            device_category_id=self.env.ref(
                "device_mobile.device_category_mobile_phone"
            ).id,
        )

        self.assertEqual(device.log_request_payload_max_bytes, 65536)
        self.assertEqual(device._payload_log_limit(), 65536)

    def test_a_non_mobile_device_is_unchanged(self):
        device = self._device("PLAIN-LOGCAP")

        self.assertEqual(device.log_request_payload_max_bytes, 0)
        self.assertEqual(device._payload_log_limit(), 0)

    def test_an_explicit_limit_is_not_overridden(self):
        device = self._device(
            "MOBILE-EXPLICIT",
            device_category_id=self.env.ref(
                "device_mobile.device_category_mobile_phone"
            ).id,
            log_request_payload_max_bytes=1024,
        )

        self.assertEqual(device.log_request_payload_max_bytes, 1024)

    def test_a_negative_log_limit_is_refused(self):
        with self.assertRaises(ValidationError):
            self._device("MOBILE-NEGATIVE", log_request_payload_max_bytes=-1)


@tagged("post_install", "-at_install")
class TestAPhoneIsAGpsDevice(DeviceTransactionCase):
    def test_the_mobile_category_is_declared_a_gps_category(self):
        self.assertIn(
            "mobile_phone",
            self.env["device.device"]._device_kind_categories("gps"),
            "a company phone reports its position, so it belongs on the GPS "
            "screens -- it used to qualify by carrying an IMEI",
        )

    def test_a_company_phone_is_flagged_as_a_gps_device(self):
        config = self.env["device.profile"].create({"name": "Phone Kind Config"})
        phone = self.env["device.device"].create(
            {
                "name": "Company Phone",
                "identifier": "PHONE-KIND-001",
                "config_id": config.id,
                "comm_protocol": "http",
                "endpoint": "10.0.0.11",
                "device_category_id": self.env.ref(
                    "device_mobile.device_category_mobile_phone"
                ).id,
            }
        )
        self.assertTrue(phone.is_gps_device)


@tagged("post_install", "-at_install")
class TestAPhoneIsNeverDialled(DeviceTransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.phone = cls._create_device_device(
            name="Phone",
            identifier="PHONE-NO-DIAL",
            comm_protocol="http",
            endpoint="companion-app",
            device_category_id=cls.env.ref(
                "device_mobile.device_category_mobile_phone"
            ).id,
        )

    def test_connecting_a_phone_marks_it_connected_without_a_request(self):
        with patch("requests.get", side_effect=AssertionError("dialled")) as get:
            self.phone.action_connect()
        get.assert_not_called()
        self.assertEqual(self.phone.connection_state, "connected")

    def test_polling_a_phone_reads_nothing(self):
        with patch("requests.get", side_effect=AssertionError("dialled")) as get:
            self.phone.action_read_data()
        get.assert_not_called()

    def test_the_crons_leave_a_phone_alone(self):
        self.phone.write({"connection_state": "disconnected"})
        with patch("requests.get", side_effect=AssertionError("dialled")) as get:
            self.env["device.device"]._cron_auto_reconnect()
            self.env["device.device"]._cron_poll_devices()
        get.assert_not_called()


@tagged("post_install", "-at_install")
class TestPhoneNumber(DeviceTransactionCase):
    """A company phone records its SIM's number, keyed as calls and Telegram
    accounts are matched to it, and no two active phones share one."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.env["device.profile"].create(
            {"name": "Phone Config", "auth_type": "bearer", "auth_token": "phone_tok"}
        )

    def _phone(self, identifier, number):
        return self.env["device.device"].create(
            {
                "name": identifier,
                "identifier": identifier,
                "config_id": self.config.id,
                "comm_protocol": "https",
                "endpoint": "x",
                "device_category_id": self.env.ref(
                    "device_mobile.device_category_mobile_phone"
                ).id,
                "line_number": number,
            }
        )

    def test_a_phone_number_is_keyed_by_its_last_digits(self):
        phone = self._phone("MOB-NUM-1", "+52 1 55 1234 5678")

        self.assertEqual(phone.line_number_digits, "5512345678")

    def test_a_phone_number_reads_in_its_company_s_country(self):
        self.env.company.country_id = self.env.ref("base.mx")

        self.assertEqual(
            self._phone("MOB-NUM-6", "55 1234 5678").line_number_e164, "+525512345678"
        )
        self.assertEqual(
            self._phone("MOB-NUM-7", "+52 1 55 8765 4321").line_number_e164,
            "+525587654321",
        )
        self.assertFalse(self._phone("MOB-NUM-8", "12").line_number_e164)

    def test_two_phones_cannot_share_a_number(self):
        self._phone("MOB-NUM-2", "55 1234 5678")

        with self.assertRaises(ValidationError):
            self._phone("MOB-NUM-3", "+52 55 1234 5678")

    def test_an_archived_phone_releases_its_number(self):
        old = self._phone("MOB-NUM-4", "55 8765 4321")
        old.active = False

        self._phone("MOB-NUM-5", "55 8765 4321")
