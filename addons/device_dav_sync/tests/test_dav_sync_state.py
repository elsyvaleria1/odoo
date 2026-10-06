from psycopg import IntegrityError

from odoo.addons.device.tests.common import DeviceTransactionCase


class TestDAVSyncState(DeviceTransactionCase):
    def setUp(self):
        super().setUp()

        self.test_user = self.env["res.users"].create(
            {
                "name": "Test DAV User",
                "login": "test_dav_user",
                "email": "test@example.com",
            }
        )

        self.dav_category = self.env["device.kind"].create(
            {
                "name": "DAV Client Test",
                "code": "dav_client",
                "description": "Test DAV client category",
            }
        )

        self.test_config = self.env["device.profile"].create(
            {
                "name": "Test DAV Config",
                "protocol": "http",
            }
        )

        self.test_device = self.env["device.device"].create(
            {
                "name": "Test DAV Device",
                "identifier": "test-dav-device-001",
                "device_category_id": self.dav_category.id,
                "config_id": self.test_config.id,
                "dav_sync_enabled": True,
                "dav_user_id": self.test_user.id,
            }
        )

        self.test_contact = self.env["res.partner"].create(
            {
                "name": "Test Contact",
                "email": "contact@example.com",
            }
        )

    def test_create_sync_state(self):
        sync_state = self.env["dav.sync.state"].create(
            {
                "device_id": self.test_device.id,
                "resource_type": "contact",
                "resource_model": "res.partner",
                "resource_id": self.test_contact.id,
                "resource_uid": f"contact-{self.test_contact.id}@odoo",
                "etag": '"test-etag-123"',
                "last_modified": self.test_contact.write_date,
                "sync_status": "synced",
            }
        )

        self.assertEqual(sync_state.device_id, self.test_device)
        self.assertEqual(sync_state.user_id, self.test_user)
        self.assertEqual(sync_state.resource_type, "contact")
        self.assertEqual(sync_state.sync_status, "synced")

    def test_unique_constraint(self):
        self.env["dav.sync.state"].create(
            {
                "device_id": self.test_device.id,
                "resource_type": "contact",
                "resource_model": "res.partner",
                "resource_id": self.test_contact.id,
                "resource_uid": f"contact-{self.test_contact.id}@odoo",
                "etag": '"test-etag-123"',
                "last_modified": self.test_contact.write_date,
                "sync_status": "synced",
            }
        )

        with self.assertRaises(IntegrityError):
            self.env["dav.sync.state"].create(
                {
                    "device_id": self.test_device.id,
                    "resource_type": "contact",
                    "resource_model": "res.partner",
                    "resource_id": self.test_contact.id,
                    "resource_uid": f"contact-{self.test_contact.id}@odoo-2",
                    "etag": '"test-etag-456"',
                    "last_modified": self.test_contact.write_date,
                    "sync_status": "synced",
                }
            )

    def test_get_or_create_sync_state(self):
        sync_state = self.env["dav.sync.state"].get_or_create_sync_state(
            self.test_device, "contact", "res.partner", self.test_contact.id
        )

        self.assertTrue(sync_state.exists())
        self.assertEqual(sync_state.device_id, self.test_device)
        self.assertEqual(sync_state.resource_id, self.test_contact.id)

        sync_state2 = self.env["dav.sync.state"].get_or_create_sync_state(
            self.test_device, "contact", "res.partner", self.test_contact.id
        )

        self.assertEqual(sync_state.id, sync_state2.id)

    def test_update_sync_state(self):
        sync_state = self.env["dav.sync.state"].get_or_create_sync_state(
            self.test_device, "contact", "res.partner", self.test_contact.id
        )

        sync_state.update_sync_state(status="synced")
        self.assertEqual(sync_state.sync_status, "synced")

        sync_state.update_sync_state(status="error", error_msg="Test error")
        self.assertEqual(sync_state.sync_status, "error")
        self.assertEqual(sync_state.error_message, "Test error")

    def test_get_etag(self):
        etag = self.env["dav.sync.state"]._get_etag(self.test_contact)

        self.assertFalse(etag.startswith('"'))
        self.assertEqual(etag, etag.strip('"'))
        self.assertGreater(len(etag), 10)

        etag2 = self.env["dav.sync.state"]._get_etag(self.test_contact)
        self.assertEqual(etag, etag2)

    def test_display_name(self):
        sync_state = self.env["dav.sync.state"].get_or_create_sync_state(
            self.test_device, "contact", "res.partner", self.test_contact.id
        )

        self.assertIn("Contact", sync_state.display_name)
        self.assertIn(str(self.test_contact.id), sync_state.display_name)
