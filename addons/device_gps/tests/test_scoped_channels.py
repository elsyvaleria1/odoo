import time

from odoo.exceptions import UserError
from odoo.libs.json import dumps as json_dumps
from odoo.tests import tagged

from odoo.addons.device.tests.common import DeviceHttpCase
from odoo.addons.device_gps.models.device_device import TRACKER_ACK, TRACKER_NACK


@tagged("post_install", "-at_install")
class TestScopedGpsChannels(DeviceHttpCase):
    def _source(self, suffix, company=None):
        device = self._create_device_device(
            config=self._create_device_profile(gps_protocol="teltonika"),
            identifier=f"CHANNEL-GPS-{suffix}",
            gps_receiver_key=f"legacy-{suffix}",
            device_category_id=self.env.ref("device.device_category_gps").id,
            company_id=(company or self.env.company).id,
        )
        enrollment = self.env["device.enrollment"].create(
            {
                "name": f"GPS enrollment {suffix}",
                "device_id": device.id,
                "company_id": device.company_id.id,
            }
        )
        enrollment.action_provision_credential()
        enrollment.action_activate()
        channel = self.env["device.channel"].create(
            {
                "name": f"GPS channel {suffix}",
                "enrollment_id": enrollment.id,
                "external_identifier": "0012345678",
            }
        )
        return device, enrollment, channel

    def _push(self, enrollment, key="0012345678", token=None):
        token = token or enrollment.credential_id.sudo().credential_value
        return self.url_open(
            f"/device/v1/enrollments/{enrollment.key}/channels/0012345678/gps",
            data=json_dumps(
                {
                    "state": {
                        "reported": {
                            "14": key,
                            "latlng": "19.4,-99.1",
                            "ts": int(time.time() * 1000),
                            "sat": 10,
                            "sp": 0,
                            "182": 10,
                        }
                    }
                }
            ),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )

    def test_same_wire_key_is_scoped_by_enrollment_and_company(self):
        first_device, first, first_channel = self._source("first")
        company = self.env["res.company"].create({"name": "Other GPS tenant"})
        second_device, second, second_channel = self._source("second", company)
        first_token = first.credential_id.sudo().credential_value
        self.assertEqual(self._push(first).content, TRACKER_ACK)
        self.assertEqual(self._push(second, token=first_token).content, TRACKER_NACK)
        self.assertEqual(self._push(second).content, TRACKER_ACK)
        logs = self.env["device.data.log.gps"].search(
            [
                ("channel_id", "in", [first_channel.id, second_channel.id]),
            ]
        )
        self.assertEqual(len(logs), 2)
        for channel, device in (
            (first_channel, first_device),
            (second_channel, second_device),
        ):
            log = logs.filtered(lambda row, channel=channel: row.channel_id == channel)
            self.assertEqual(log.device_id, device)
            self.assertEqual(log.company_id, device.company_id)
            self.assertEqual(log.iccid2, "0012345678")
            self.assertEqual(log.source, "webhook")
            with self.assertRaises(UserError):
                log.channel_id = False

    def test_mismatched_payload_and_revoked_enrollment_do_not_store_samples(self):
        device, enrollment, channel = self._source("refused")
        self.assertEqual(self._push(enrollment, key="different").content, TRACKER_NACK)
        enrollment.action_revoke()
        self.assertEqual(self._push(enrollment).content, TRACKER_NACK)
        self.assertFalse(
            self.env["device.data.log.gps"].search([("channel_id", "=", channel.id)])
        )
        self.assertEqual(device.gps_receiver_key, "legacy-refused")

    def test_command_channel_does_not_accept_telemetry(self):
        _device, enrollment, channel = self._source("commands")
        # An unused channel of a draft enrollment may be replaced; active
        # identities stay immutable. A separate commands channel has its own key.
        command = self.env["device.channel"].create(
            {
                "name": "Commands",
                "enrollment_id": enrollment.id,
                "external_identifier": "control",
                "purpose": "commands",
            }
        )
        response = self.url_open(
            f"/device/v1/enrollments/{enrollment.key}/channels/{command.external_identifier}/gps",
            data="{}",
            headers={
                "Authorization": f"Bearer {enrollment.credential_id.sudo().credential_value}"
            },
        )
        self.assertEqual(response.content, TRACKER_NACK)
        self.assertFalse(
            self.env["device.data.log.gps"].search(
                [("channel_id", "in", [channel.id, command.id])]
            )
        )
