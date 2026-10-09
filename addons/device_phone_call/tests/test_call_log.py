from odoo import Command
from odoo.libs.json import dumps_bytes as json_dumps_bytes
from odoo.tests.common import tagged

from odoo.addons.device.tests.common import DeviceHttpCase


@tagged("post_install", "-at_install")
class TestDeviceCallLog(DeviceHttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")
        cls.config = cls.env["device.profile"].create(
            {
                "name": "Mobile Call Config",
                "auth_type": "bearer",
                "auth_token": "call_token_123",
            }
        )
        cls.device = cls.env["device.device"].create(
            {
                "name": "Test Phone",
                "identifier": "PHONE-CALL-001",
                "config_id": cls.config.id,
                "comm_protocol": "https",
                "endpoint": "companion-app",
                "company_id": cls.company.id,
            }
        )
        cls.token = cls.device.credential_id.credential_value
        cls.partner = cls.env["res.partner"].create(
            {
                "name": "Rancho El Águila",
                "phone_ids": [
                    Command.create({"number": "+52 55 1234 5678", "type": "landline"})
                ],
            }
        )

    def _push(self, body, token=None):
        return self.url_open(
            "/remote/mobile/PHONE-CALL-001/calllog",
            data=json_dumps_bytes(body),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token or self.token}",
            },
        )

    def _calls(self):
        return self.env["phone.call"].search([("device_id", "=", self.device.id)])

    def test_push_call_matches_partner(self):
        resp = self._push(
            {
                "number": "5512345678",
                "type": 1,
                "duration": 65,
                "timestamp": "2026-07-28T15:30:00Z",
            }
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["accepted"], 1)
        self.assertEqual(body["matched"], 1)
        call = self._calls()
        self.assertEqual(len(call), 1)
        self.assertEqual((call.direction, call.state), ("incoming", "terminated"))
        self.assertEqual((call.end_date - call.start_date).total_seconds(), 65)
        self.assertEqual(call.partner_id, self.partner)
        self.assertEqual(call.start_date.hour, 15)
        self.assertEqual(call.channel, "mobile")
        self.assertEqual(call.company_id, self.company)
        self.assertEqual(self.partner.phone_call_count, 1)
        action = self.partner.action_view_phone_calls()
        self.assertIn(("partner_id", "=", self.partner.id), action["domain"])

    def test_batch_directions_and_skips(self):
        resp = self._push(
            {
                "calls": [
                    {"number": "5599999999", "direction": "outgoing", "duration": 12},
                    {"number": "5588888888", "type": 3},
                    {"number": "", "type": 2},
                    {"type": 1},
                ]
            }
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["accepted"], 2)
        self.assertEqual(body["skipped"], 2)
        self.assertEqual(body["skipped_indexes"], [2, 3])
        outcomes = {(call.direction, call.state) for call in self._calls()}
        self.assertEqual(outcomes, {("outgoing", "terminated"), ("incoming", "missed")})

    def test_epoch_millis_timestamp(self):
        resp = self._push({"number": "5512345678", "type": 2, "date": 1785339000000})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self._calls().start_date.year, 2026)

    def test_call_answered_externally_is_stored(self):
        resp = self._push({"calls": [{"number": "5512345678", "direction": "7"}]})

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["accepted"], 1)
        self.assertEqual(self._calls().direction, "incoming")
        self.assertEqual(self._calls().state, "terminated")

    def test_every_android_call_type_is_mapped(self):
        resp = self._push(
            {
                "calls": [
                    {"number": f"55000000{index}", "direction": str(index)}
                    for index in range(1, 8)
                ]
            }
        )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["accepted"], 7)
        self.assertEqual(resp.json()["skipped"], 0)

    def test_a_batch_already_stored_is_a_delivery_not_a_refusal(self):
        call = {
            "number": "5512345678",
            "direction": "outgoing",
            "duration": 12,
            "timestamp": 1730000000000,
        }
        self.assertEqual(self._push({"calls": [call]}).status_code, 200)

        resp = self._push({"calls": [call], "resent": True})

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["accepted"], 0)
        self.assertEqual(body["duplicates"], 1)
        self.assertEqual(body["skipped"], 0)
        self.assertEqual(len(self._calls()), 1)

    def test_a_partial_retry_counts_duplicates_apart_from_skipped(self):
        stored = {"number": "5512345678", "direction": "outgoing", "timestamp": 1000}
        fresh = {"number": "5599999999", "direction": "incoming", "timestamp": 2000}
        unusable = {"direction": "incoming"}
        self._push({"calls": [stored]})

        body = self._push({"calls": [stored, fresh, unusable]}).json()

        self.assertEqual(body["accepted"], 1)
        self.assertEqual(body["duplicates"], 1)
        self.assertEqual(body["skipped"], 1)

    def test_a_batch_with_nothing_storable_is_still_refused(self):
        resp = self._push({"calls": [{"direction": "incoming"}]})

        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["duplicates"], 0)
        self.assertEqual(resp.json()["skipped"], 1)

    def test_a_call_type_newer_than_this_module_is_stored_not_dropped(self):
        resp = self._push({"calls": [{"number": "5512345678", "direction": "9"}]})

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["accepted"], 1)
        self.assertEqual(self._calls().state, "unknown")
        self.assertFalse(self._calls().direction)

    def test_a_direction_that_is_not_a_number_is_still_skipped(self):
        resp = self._push(
            {"calls": [{"number": "5512345678", "direction": "sideways"}]}
        )

        self.assertEqual(resp.status_code, 422)
        self.assertFalse(self._calls())

    def test_bad_token_rejected(self):
        resp = self._push({"number": "5512345678", "type": 1}, token="nope")
        self.assertEqual(resp.status_code, 401)
        self.assertFalse(self._calls())

    def test_the_phone_user_answers_for_the_calls(self):
        user = self.env["res.users"].create(
            {"name": "Field rep", "login": "device_call_rep"}
        )
        self.device.user_id = user
        self._push({"number": "5512345678", "type": 2})
        self.assertEqual(self._calls().user_id, user)


@tagged("post_install", "-at_install")
class TestDeviceCallLogWithoutSu(TestDeviceCallLog):
    def test_the_receiver_files_the_calls_it_is_told_of(self):
        receiver = self.env.ref("device.user_device_receiver")
        resp = self._push(
            {
                "number": "5512345678",
                "type": 1,
                "duration": 65,
                "timestamp": "2026-07-28T15:30:00Z",
            }
        )
        self.assertEqual(resp.status_code, 200)
        call = self._calls()
        self.assertEqual(call.create_uid, receiver)
        self.assertEqual(call.partner_id, self.partner)
        messages = call.message_ids
        self.assertEqual(messages.author_id, receiver.partner_id)
