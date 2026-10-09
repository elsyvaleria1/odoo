import time
from unittest.mock import patch

from odoo.http import request
from odoo.libs.json import dumps_bytes as json_dumps_bytes
from odoo.tests import tagged

from odoo.addons.device.tests.common import DeviceHttpCase
from odoo.addons.device_gps.models.device_device import TRACKER_ACK
from odoo.addons.integration.tools.admission import Admission

RECEIVER_KEY = "0012345678"


def _fix(receiver_key=RECEIVER_KEY):
    return json_dumps_bytes(
        {
            "state": {
                "reported": {
                    "14": receiver_key,
                    "latlng": "19.4,-99.1",
                    "ts": int(time.time() * 1000),
                    "sat": 10,
                    "sp": 0,
                    "182": 10,
                }
            }
        }
    )


@tagged("post_install", "-at_install")
class TestGpsReceiverAuthority(DeviceHttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.device = cls._create_device_device(
            config=cls._create_device_profile(gps_protocol="teltonika"),
            identifier="AUTHORITY-GPS",
            gps_receiver_key=RECEIVER_KEY,
            device_category_id=cls.env.ref("device.device_category_gps").id,
        )

    def _authority_of(self, push):
        seen = []
        settle = Admission.settle

        def spy(admission, *args, **kwargs):
            seen.append((request.env.uid, request.env.su, request.env.privileges))
            return settle(admission, *args, **kwargs)

        with patch.object(Admission, "settle", spy):
            response = push()
        return response, seen

    def _logs(self):
        return self.env["device.data.log.gps"].search(
            [("device_id", "=", self.device.id)]
        )

    def _privileges(self, *xmlids):
        return frozenset(self.env.ref(xmlid).id for xmlid in xmlids)

    def test_a_channel_fix_is_filed_by_the_channel_s_principal_without_su(self):
        enrollment = self.env["device.enrollment"].create(
            {"name": "GPS authority", "device_id": self.device.id}
        )
        enrollment.action_provision_credential()
        enrollment.action_activate()
        self.env["device.channel"].create(
            {
                "name": "GPS authority channel",
                "enrollment_id": enrollment.id,
                "external_identifier": RECEIVER_KEY,
            }
        )
        token = enrollment.credential_id.sudo().credential_value
        self.env.flush_all()

        response, seen = self._authority_of(
            lambda: self.url_open(
                f"/device/v1/enrollments/{enrollment.key}/channels/{RECEIVER_KEY}/gps",
                data=_fix(),
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
            )
        )

        self.assertEqual(response.content, TRACKER_ACK)
        principal = enrollment.service_user_id
        self.assertEqual(
            seen,
            [
                (
                    principal.id,
                    False,
                    self._privileges(
                        "device_gps.privilege_receive_fix",
                        "integration.privilege_keep_inbound_exchange",
                    ),
                )
            ],
        )
        self.assertEqual(self._logs().create_uid, principal)

    def test_a_tracker_fix_is_filed_by_the_device_receiver_without_su(self):
        token = self.device.credential_id.sudo().credential_value
        self.env.flush_all()

        response, seen = self._authority_of(
            lambda: self.url_open(
                "/remote/gps/webhook",
                data=_fix(),
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
            )
        )

        self.assertEqual(response.content, TRACKER_ACK)
        receiver = self.env.ref("device.user_device_receiver")
        self.assertEqual([uid for uid, *_rest in seen], [receiver.id])
        self.assertFalse(seen[0][1])
        self.assertIn(self.env.ref("device_gps.privilege_receive_fix").id, seen[0][2])
        self.assertEqual(self._logs().create_uid, receiver)
