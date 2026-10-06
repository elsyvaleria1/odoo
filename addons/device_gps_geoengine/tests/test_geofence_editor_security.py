from odoo.fields import Command
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestGeofenceEditorSecurity(TransactionCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        editor_group = cls.env.ref(
            "device_gps_geoengine.group_device_gps_geofence_editor"
        )
        cls.user_editor = cls.env["res.users"].create(
            {
                "name": "Test Geofence Editor",
                "login": "test_geofence_editor",
                "email": "test_geofence_editor@test.com",
                "group_ids": [
                    Command.set([cls.env.ref("base.group_user").id, editor_group.id])
                ],
            }
        )

    def test_can_manage_geofences(self) -> None:
        geo_fence = self.env["device.geo.fence"].with_user(self.user_editor)
        self.assertTrue(geo_fence.has_access("read"))
        self.assertTrue(geo_fence.has_access("create"))
        self.assertTrue(geo_fence.has_access("write"))

    def test_cannot_delete_geofences(self) -> None:
        geo_fence = self.env["device.geo.fence"].with_user(self.user_editor)
        self.assertFalse(geo_fence.has_access("unlink"))

    def test_no_device_or_iot_admin_overreach(self) -> None:
        for model in ("device.device", "device.profile"):
            records = self.env[model].with_user(self.user_editor)
            self.assertFalse(
                records.has_access("create"), f"{model}: create must be denied"
            )
            self.assertFalse(
                records.has_access("write"), f"{model}: write must be denied"
            )
            self.assertFalse(
                records.has_access("unlink"), f"{model}: unlink must be denied"
            )
