from datetime import datetime, timedelta

from psycopg import IntegrityError

from odoo.libs.json import dumps_bytes as json_dumps_bytes
from odoo.tests import tagged
from odoo.tools import mute_logger

from odoo.addons.device.tests.common import DeviceHttpCase


@tagged("post_install", "-at_install")
class TestDeviceVoip(DeviceHttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.agent = cls.env["res.users"].create(
            {"name": "Agente", "login": "device_voip_agent"}
        )
        settings = cls.env["res.users.settings"]._get_or_create_for_user(cls.agent)
        settings.write({"voip_username": "7201", "voip_secret": "s3cret-7201"})
        cls.provider = settings.voip_provider_id
        cls.provider.write({"pbx_ip": "pbx.agromarin.mx"})
        cls.pbx = cls._create_device_device(
            name="Phone system",
            identifier="PBX-VOIP",
            device_category_id=cls.env.ref("device_phone_call.device_category_pbx").id,
        )
        cls.calls = cls.env["phone.call"]
        cls.bearer = cls.env["device.profile"].create(
            {"name": "Softphone config", "auth_type": "bearer", "auth_token": "sp"}
        )
        cls.when = datetime(2026, 10, 5, 10, 0, 0)

    def _report(self, **call):
        return self.calls.ingest_from_device(
            self.pbx,
            [
                {
                    "number": "5512345678",
                    "direction": "incoming",
                    "timestamp": self.when.isoformat(),
                    "duration": 90,
                    **call,
                }
            ],
        ).created

    def _softphone_call(self, start):
        call = self.calls.create(
            {
                "phone_number": "+52 55 1234 5678",
                "direction": "incoming",
                "state": "terminated",
                "channel": "softphone",
                "user_id": self.agent.id,
                "start_date": start,
            }
        )
        self.env.cr.execute(
            "UPDATE phone_call SET create_date = %s WHERE id = %s", [start, call.id]
        )
        call.invalidate_recordset(["create_date"])
        return call

    def test_the_extension_that_answered_answers_for_the_call(self):
        self.assertEqual(self._report(extension="7201").user_id, self.agent)

    def test_an_unknown_extension_leaves_the_device_user(self):
        self.assertFalse(self._report(extension="999").user_id)

    def test_the_phone_system_completes_the_softphone_call(self):
        softphone = self._softphone_call(self.when + timedelta(seconds=20))
        reported = self._report(extension="7201")
        self.assertEqual(reported, softphone, "no second call for one conversation")
        self.assertEqual(softphone.device_id, self.pbx)
        self.assertEqual(softphone.channel, "softphone")
        self.assertEqual(softphone.start_date, self.when)

    def test_a_softphone_call_long_before_is_another_call(self):
        softphone = self._softphone_call(self.when - timedelta(hours=1))
        reported = self._report(extension="7201")
        self.assertNotEqual(reported, softphone)
        self.assertFalse(softphone.device_id)

    def test_the_softphone_call_the_phone_system_names_is_completed(self):
        named = self._softphone_call(self.when + timedelta(seconds=90))
        named.sip_call_id = "dialog-1@browser"
        nearer = self._softphone_call(self.when + timedelta(seconds=5))
        reported = self._report(extension="7201", sip_call_id="dialog-1@browser")
        self.assertEqual(reported, named, "the dialog decides, not the clock")
        self.assertFalse(nearer.device_id)

    def _ringing_copy(self, user, start, state="missed"):
        call = self._softphone_call(start)
        call.write({"user_id": user.id, "state": state})
        return call

    def test_the_browsers_a_missed_call_rang_leave_one_call(self):
        other = self.env["res.users"].create(
            {"name": "Otra", "login": "device_voip_otra"}
        )
        copies = self._ringing_copy(self.agent, self.when + timedelta(seconds=1)) | (
            self._ringing_copy(other, self.when + timedelta(seconds=1), "calling")
        )
        missed = self._report(direction="missed", duration=0)
        self.assertFalse(copies.exists(), "the phone system's report is that call")
        self.assertFalse(missed.user_id)
        self.assertIn(
            missed,
            self.calls.with_user(self.agent).search(
                self.calls.with_user(self.agent)._softphone_history_domain()
            ),
            "everyone it rang sees the missed call in their history",
        )

    def test_an_answered_call_keeps_its_answerer_and_drops_the_other_copies(self):
        other = self.env["res.users"].create(
            {"name": "Otra", "login": "device_voip_otra2"}
        )
        answered = self._softphone_call(self.when + timedelta(seconds=2))
        copy = self._ringing_copy(other, self.when + timedelta(seconds=2))
        reported = self._report(extension="7201")
        self.assertEqual(reported, answered)
        self.assertFalse(copy.exists())

    def test_an_extension_belongs_to_one_user_per_provider(self):
        other = self.env["res.users"].create(
            {"name": "Otra", "login": "device_voip_otra3"}
        )
        settings = self.env["res.users.settings"]._get_or_create_for_user(other)
        settings.voip_provider_id = self.provider
        with (
            self.assertRaises(IntegrityError),
            mute_logger("odoo.db"),
            self.env.cr.savepoint(),
        ):
            settings.voip_username = "7201"
            self.env.flush_all()

    def _settings(self, device, token=None):
        return self.url_open(
            f"/remote/device/{device.identifier}/softphone",
            headers={"Authorization": f"Bearer {token or self._device_token(device)}"},
        )

    def test_a_handset_fetches_its_user_softphone_settings(self):
        phone = self._create_device_device(
            config=self.bearer,
            name="Agent phone",
            identifier="PHONE-VOIP",
            user_id=self.agent.id,
        )
        response = self._settings(phone)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            response.json()["sip"],
            {
                "username": "7201",
                "secret": "s3cret-7201",
                "domain": "pbx.agromarin.mx",
                "transport": "tls",
                "websocket": self.provider.ws_server or "",
            },
        )

    def test_an_archived_users_handset_gets_no_secret(self):
        leaver = self.env["res.users"].create(
            {"name": "Leaver", "login": "device_voip_leaver"}
        )
        self.env["res.users.settings"]._get_or_create_for_user(leaver).write(
            {"voip_username": "7299", "voip_secret": "s3cret-7299"}
        )
        phone = self._create_device_device(
            config=self.bearer,
            name="Leaver phone",
            identifier="PHONE-LEAVER",
            user_id=leaver.id,
        )
        leaver.active = False
        self.assertEqual(self._settings(phone).status_code, 404)

    def test_a_phone_system_gets_no_softphone_settings(self):
        self.pbx.write({"config_id": self.bearer.id, "user_id": self.agent.id})
        self.assertIsNone(self.pbx._softphone_settings())

    def test_a_handset_cannot_answer_for_another_extension(self):
        phone = self._create_device_device(
            name="Someone's phone", identifier="PHONE-OTHER"
        )
        created = self.calls.ingest_from_device(
            phone,
            [
                {
                    "number": "5512345678",
                    "direction": "incoming",
                    "timestamp": self.when.isoformat(),
                    "extension": "7201",
                }
            ],
        ).created
        self.assertNotEqual(created.user_id, self.agent)

    def test_an_extension_held_by_an_archived_user_is_nobodys(self):
        self.agent.active = False
        self.assertFalse(self._report(extension="7201").user_id)

    def test_a_handset_whose_user_has_no_extension_gets_none(self):
        phone = self._create_device_device(
            config=self.bearer, name="Bare phone", identifier="PHONE-BARE"
        )
        self.assertEqual(self._settings(phone).status_code, 404)

    def test_a_wrong_token_gets_nothing(self):
        phone = self._create_device_device(
            config=self.bearer,
            name="Agent phone",
            identifier="PHONE-VOIP2",
            user_id=self.agent.id,
        )
        self.assertEqual(self._settings(phone, token="nope").status_code, 401)

    def test_a_handset_asks_again_inside_its_duplicate_window(self):
        phone = self._create_device_device(
            config=self.bearer,
            name="Agent phone",
            identifier="PHONE-VOIP3",
            user_id=self.agent.id,
            duplicate_detection_enabled=True,
            duplicate_window_seconds=900,
        )
        self.assertEqual(self._settings(phone).status_code, 200)
        self.assertEqual(self._settings(phone).status_code, 200)


@tagged("post_install", "-at_install")
class TestDeviceVoipThroughTheRoute(TestDeviceVoip):
    allow_inherited_tests_method = True

    def _report(self, **call):
        response = self.url_open(
            f"/remote/device/{self.pbx.identifier}/calllog",
            data=json_dumps_bytes(
                {
                    "number": "5512345678",
                    "direction": "incoming",
                    "timestamp": self.when.isoformat(),
                    "duration": 90,
                    **call,
                }
            ),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._device_token(self.pbx)}",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["accepted"], 1)
        reported = self.calls.search(
            [("device_id", "=", self.pbx.id), ("start_date", "=", self.when)]
        )
        self.assertEqual(
            reported.write_uid, self.env.ref("device.user_device_receiver")
        )
        return reported
