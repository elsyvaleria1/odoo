from datetime import timedelta

from odoo import fields
from odoo.libs.json import dumps as json_dumps
from odoo.tests import common, tagged


@tagged("post_install", "-at_install")
class TestDwellNotification(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

    def setUp(self):
        super().setUp()
        self.config = self.env["device.profile"].create({"name": "Dwell Test Config"})
        self.device = self.env["device.device"].create(
            {
                "name": "Dwell Tracker",
                "identifier": "DWELL-001",
                "config_id": self.config.id,
                "comm_protocol": "http",
                "imei": "TEST-IMEI-DWELL-001",
                "device_category_id": self.env.ref("device.device_category_gps").id,
            }
        )
        self.salesperson = self.env["res.users"].create(
            {
                "name": "Test Salesperson",
                "login": "dwell.salesperson@test.example",
            }
        )
        self.fallback_user = self.env["res.users"].create(
            {
                "name": "Test Sales Lead",
                "login": "dwell.fallback@test.example",
            }
        )
        self.env["ir.config_parameter"].sudo().set_param(
            "device_gps_geoengine.dwell_fallback_user_login",
            self.fallback_user.login,
        )

    def _place_history(self, latitude, longitude, *, minutes_ago=()):
        now = fields.Datetime.now()
        logs = self.env["device.data.log.gps"].create(
            [
                {
                    "device_id": self.device.id,
                    "latitude": latitude,
                    "longitude": longitude,
                    "timestamp": now - timedelta(minutes=minutes),
                }
                for minutes in minutes_ago
            ]
        )
        newest = logs.sorted("timestamp", reverse=True)[0]
        self.device.sudo().write(
            {"log_gps_last_id": newest.id, "dwell_notification_sent": False}
        )
        self.env.flush_all()

    def _dwell_since_35_minutes(self, latitude, longitude):
        self._place_history(latitude, longitude, minutes_ago=(35, 20, 10, 2, 0))

    def test_no_notification_when_on_mapped_parcel(self):
        self.env["device.geo.fence"].create(
            {
                "name": "Mapped Parcel",
                "area_type": "parcel",
                "geofence_type": "polygon",
                "schedule_type": "always",
                "partner_id": self.salesperson.partner_id.id,
                "polygon_points": json_dumps(
                    [
                        [19.39, -99.11],
                        [19.41, -99.11],
                        [19.41, -99.09],
                        [19.39, -99.09],
                    ]
                ),
            }
        )
        self._dwell_since_35_minutes(19.40, -99.10)

        self.assertFalse(
            self.device._is_unmapped_dwell(),
            "a device sitting on a mapped parcel should never raise a mapping request",
        )

    def test_not_enough_history_does_not_dwell(self):
        self._place_history(19.20, -99.20, minutes_ago=(2, 0))

        self.assertFalse(
            self.device._is_unmapped_dwell(),
            "a couple of minutes of history cannot prove a 30-minute dwell",
        )

    def test_notifies_nearest_client_salesperson(self):
        client = self.env["res.partner"].create(
            {
                "name": "Nearby Client",
                "partner_latitude": 19.2001,
                "partner_longitude": -99.2001,
                "user_id": self.salesperson.id,
            }
        )
        self._dwell_since_35_minutes(19.2000, -99.2000)

        self.assertTrue(self.device._is_unmapped_dwell())
        self.device._notify_unmapped_dwell()

        activities = self.env["mail.activity"].search(
            [("res_model", "=", "res.partner"), ("res_id", "=", client.id)]
        )
        self.assertTrue(activities, "the client's own salesperson never got a to-do")
        self.assertEqual(activities.user_id, self.salesperson)

    def test_falls_back_to_configured_user_when_the_nearby_client_has_no_salesperson(
        self,
    ):
        orphan_client = self.env["res.partner"].create(
            {
                "name": "Orphan Client",
                "partner_latitude": 19.3001,
                "partner_longitude": -99.3001,
            }
        )
        self._dwell_since_35_minutes(19.3000, -99.3000)

        self.device._notify_unmapped_dwell()

        activities = self.env["mail.activity"].search(
            [("res_model", "=", "res.partner"), ("res_id", "=", orphan_client.id)]
        )
        self.assertTrue(
            activities,
            "a client was found nearby, so the to-do belongs on that client "
            "even though it has to fall back to the sales lead",
        )
        self.assertEqual(activities.user_id, self.fallback_user)

    def test_falls_back_to_configured_user_when_no_client_is_nearby_at_all(self):
        self._dwell_since_35_minutes(10.0, -140.0)

        self.device._notify_unmapped_dwell()

        activities = self.env["mail.activity"].search(
            [("res_model", "=", "device.device"), ("res_id", "=", self.device.id)]
        )
        self.assertTrue(
            activities,
            "with no client at all to attach it to, the to-do should land "
            "on the device itself, still for the sales lead",
        )
        self.assertEqual(activities.user_id, self.fallback_user)

    def test_does_not_duplicate_while_still_dwelling(self):
        self.env["res.partner"].create(
            {
                "name": "Nearby Client",
                "partner_latitude": 19.4001,
                "partner_longitude": -99.4001,
                "user_id": self.salesperson.id,
            }
        )
        self._dwell_since_35_minutes(19.4000, -99.4000)

        self.env["device.device"]._cron_check_unmapped_dwell()
        after_first_run = self.env["mail.activity"].search_count(
            [("res_model", "=", "res.partner")]
        )
        self.env["device.device"]._cron_check_unmapped_dwell()
        after_second_run = self.env["mail.activity"].search_count(
            [("res_model", "=", "res.partner")]
        )

        self.assertEqual(
            after_first_run,
            after_second_run,
            "a vehicle that has not moved must not re-notify every cron run",
        )

    def test_resets_once_the_device_moves_on(self):
        self.env["res.partner"].create(
            {
                "name": "Nearby Client",
                "partner_latitude": 19.5001,
                "partner_longitude": -99.5001,
                "user_id": self.salesperson.id,
            }
        )
        self._dwell_since_35_minutes(19.5000, -99.5000)
        self.env["device.device"]._cron_check_unmapped_dwell()
        self.assertTrue(self.device.dwell_notification_sent)

        far_log = self.env["device.data.log.gps"].create(
            {
                "device_id": self.device.id,
                "latitude": 19.6000,
                "longitude": -99.6000,
                "timestamp": fields.Datetime.now(),
            }
        )
        self.device.sudo().log_gps_last_id = far_log.id
        self.env.flush_all()
        self.env["device.device"]._cron_check_unmapped_dwell()

        self.assertFalse(
            self.device.dwell_notification_sent,
            "moving away must clear the flag so a new stop elsewhere can notify again",
        )

    def _clear_the_configured_fallback(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "device_gps_geoengine.dwell_fallback_user_login", ""
        )

    def _geofence_editor(self, login):
        return self.env["res.users"].create(
            {
                "name": login,
                "login": login,
                "group_ids": [
                    (
                        4,
                        self.env.ref(
                            "device_gps_geoengine.group_device_gps_geofence_editor"
                        ).id,
                    )
                ],
            }
        )

    def test_falls_back_to_a_geofence_editor_when_nothing_is_configured(self):
        self._clear_the_configured_fallback()
        editor = self._geofence_editor("dwell.editor@test.example")
        self._dwell_since_35_minutes(10.0, -140.0)

        self.device._notify_unmapped_dwell()

        activities = self.env["mail.activity"].search(
            [("res_model", "=", "device.device"), ("res_id", "=", self.device.id)]
        )
        self.assertEqual(
            activities.user_id,
            editor,
            "with no configured login the request belongs to whoever the "
            "geofence editor group says maps parcels, not to a name compiled "
            "into the module",
        )

    def test_a_configured_login_nobody_has_falls_through_to_the_group(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "device_gps_geoengine.dwell_fallback_user_login",
            "someone.who.left@test.example",
        )
        editor = self._geofence_editor("dwell.editor.two@test.example")
        self._dwell_since_35_minutes(10.0, -140.0)

        self.device._notify_unmapped_dwell()

        activities = self.env["mail.activity"].search(
            [("res_model", "=", "device.device"), ("res_id", "=", self.device.id)]
        )
        self.assertEqual(
            activities.user_id,
            editor,
            "a stale login used to drop the request in silence",
        )

    def test_nobody_to_tell_is_logged_rather_than_dropped_silently(self):
        self._clear_the_configured_fallback()
        self.assertFalse(
            self.env.ref("device_gps_geoengine.group_device_gps_geofence_editor")
            .sudo()
            .all_user_ids,
            "this test only says anything while the group is empty; if a data "
            "record ever puts a user in it, fail here rather than go vacuous",
        )
        self._dwell_since_35_minutes(10.0, -140.0)

        with self.assertLogs(
            "odoo.addons.device_gps_geoengine.models.device_device", "WARNING"
        ) as captured:
            self.device._notify_unmapped_dwell()

        self.assertTrue(
            any("mapping request is dropped" in line for line in captured.output)
        )
