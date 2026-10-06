from datetime import timedelta

from odoo import fields
from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads
from odoo.tests import common, tagged


@tagged("post_install", "-at_install")
class TestGeofenceAlerts(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

    def setUp(self):
        super().setUp()
        self.config = self.env["device.profile"].create(
            {"name": "Geofence Alert Config"}
        )
        self.device = self.env["device.device"].create(
            {
                "name": "Fenced Tracker",
                "identifier": "FENCE-001",
                "config_id": self.config.id,
                "comm_protocol": "http",
            }
        )
        self.fence = self.env["device.geo.fence"].create(
            {
                "name": "Yard",
                "geofence_type": "polygon",
                "schedule_type": "always",
                "alert_on_enter": True,
                "alert_on_exit": True,
                "polygon_points": json_dumps(
                    [
                        [19.39, -99.11],
                        [19.41, -99.11],
                        [19.41, -99.09],
                        [19.39, -99.09],
                    ]
                ),
                "device_ids": [fields.Command.set([self.device.id])],
            }
        )

    def _place(self, latitude, longitude):
        log = self.env["device.data.log.gps"].create(
            {
                "device_id": self.device.id,
                "latitude": latitude,
                "longitude": longitude,
                "timestamp": fields.Datetime.now() - timedelta(seconds=5),
            }
        )
        self.device.sudo().log_gps_last_id = log.id
        self.env.flush_all()

    def _messages(self):
        return self.env["mail.message"].search(
            [("model", "=", "device.device"), ("res_id", "=", self.device.id)]
        )

    def test_entering_posts_to_the_devices_chatter(self):
        self._place(19.40, -99.10)
        before = len(self._messages())

        self.env["device.geo.fence"]._cron_process_geofence_alerts()

        posted = self._messages()
        self.assertGreater(
            len(posted),
            before,
            "entering a geofence produced no record anywhere but the log file",
        )
        self.assertTrue(
            any("Yard" in (message.body or "") for message in posted),
            f"the geofence is not named in any alert: {posted.mapped('body')}",
        )

    def test_leaving_posts_too(self):
        self._place(19.40, -99.10)
        self.env["device.geo.fence"]._cron_process_geofence_alerts()
        self.assertIn(self.device, self.fence.devices_inside_last_ids)

        before = len(self._messages())
        self._place(19.50, -99.50)
        self.env["device.geo.fence"]._cron_process_geofence_alerts()

        self.assertGreater(len(self._messages()), before)
        self.assertNotIn(self.device, self.fence.devices_inside_last_ids)

    def test_staying_inside_alerts_once(self):
        self._place(19.40, -99.10)
        self.env["device.geo.fence"]._cron_process_geofence_alerts()
        after_entry = len(self._messages())

        self.env["device.geo.fence"]._cron_process_geofence_alerts()

        self.assertEqual(
            len(self._messages()),
            after_entry,
            "a device that has not moved must not re-alert every five minutes",
        )

    def test_the_alert_reaches_the_bus(self):
        self._place(19.40, -99.10)
        self.env["bus.bus"].sudo().search([]).unlink()

        self.env["device.geo.fence"]._cron_process_geofence_alerts()
        self.env.cr.precommit.run()

        sent = [
            json_loads(record.message)
            for record in self.env["bus.bus"].sudo().search([])
        ]
        self.assertTrue(
            [m for m in sent if m.get("type") == "device_device/geofence_alert"],
            "an open map has no way to learn about the crossing",
        )
