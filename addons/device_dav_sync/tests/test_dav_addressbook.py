from odoo.addons.device.tests.common import DeviceTransactionCase


class TestDAVAddressbook(DeviceTransactionCase):
    def setUp(self):
        super().setUp()

        self.test_user = self.env["res.users"].create(
            {
                "name": "Test User",
                "login": "test_addressbook_user",
                "email": "test@example.com",
            }
        )

        self.contact1 = self.env["res.partner"].create(
            {
                "name": "Contact 1",
                "email": "contact1@example.com",
            }
        )
        self.contact2 = self.env["res.partner"].create(
            {
                "name": "Contact 2",
                "email": "contact2@example.com",
            }
        )

    def test_create_addressbook(self):
        addressbook = self.env["dav.addressbook"].create(
            {
                "name": "Test Addressbook",
                "user_id": self.test_user.id,
                "description": "Test addressbook for unit testing",
            }
        )

        self.assertEqual(addressbook.name, "Test Addressbook")
        self.assertEqual(addressbook.user_id, self.test_user)
        self.assertTrue(addressbook.active)

    def test_get_contacts(self):
        addressbook = self.env["dav.addressbook"].create(
            {
                "name": "Test Addressbook",
                "user_id": self.test_user.id,
            }
        )

        contacts = addressbook.get_contacts()

        self.assertIsInstance(contacts, type(self.env["res.partner"]))

    def test_ctag_computation(self):
        addressbook = self.env["dav.addressbook"].create(
            {
                "name": "Test Addressbook",
                "user_id": self.test_user.id,
            }
        )

        ctag1 = addressbook.ctag
        self.assertIsNotNone(ctag1)

        addressbook.invalidate_model()
        ctag2 = addressbook.ctag

        self.assertIsInstance(ctag2, str)
