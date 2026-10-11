from odoo import Command
from odoo.tests import common, tagged


@tagged("-at_install", "post_install")
class TestVoipResPartner(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.min_length = cls.env["res.partner"]._phone_search_min_length
        cls.partner1 = cls.env["res.partner"].create(
            {
                "name": "Partner 1",
                "phone_ids": [
                    Command.create(
                        {"number": "1" * (cls.min_length + 1), "type": "landline"}
                    )
                ],
            }
        )
        cls.partner2 = cls.env["res.partner"].create(
            {
                "name": "No matched name",
                "phone_ids": [
                    Command.create(
                        {"number": "2" * (cls.min_length + 1), "type": "landline"}
                    )
                ],
                "email": "partner2@example.com",
            }
        )
        cls.partner3 = cls.env["res.partner"].create(
            {
                "name": "No matched name, no email",
                "phone_ids": [
                    Command.create(
                        {"number": "3" * (cls.min_length + 1), "type": "landline"}
                    )
                ],
            }
        )
        cls.partner4 = cls.env["res.partner"].create(
            {
                "name": "partner 4",
                "phone_ids": [Command.clear()],
                "email": "partner4@example.com",
            }
        )

    def assertIdInStoreData(self, id, store_data):
        ids = [record["id"] for record in store_data.get("res.partner", [])]
        self.assertIn(id, ids)

    def assertIdNotInStoreData(self, id, store_data):
        ids = [record["id"] for record in store_data.get("res.partner", [])]
        self.assertNotIn(id, ids)

    def test_voip_get_contacts_search_by_name_or_email(self):
        store_data = self.env["res.partner"].get_contacts(
            offset=0,
            limit=10,
            search_terms="partner",
        )
        self.assertIdInStoreData(self.partner1.id, store_data)
        self.assertIdInStoreData(self.partner2.id, store_data)
        self.assertIdNotInStoreData(self.partner3.id, store_data)
        self.assertIdNotInStoreData(self.partner4.id, store_data)

    def test_voip_get_contacts_search_by_phone(self):
        store_data = self.env["res.partner"].get_contacts(
            offset=0,
            limit=10,
            search_terms="3" * self.min_length,
        )
        self.assertIdInStoreData(self.partner3.id, store_data)
        self.assertIdNotInStoreData(self.partner1.id, store_data)
        self.assertIdNotInStoreData(self.partner2.id, store_data)

    def test_voip_get_contacts_search_by_T9_name(self):
        store_data = self.env["res.partner"].get_contacts(
            offset=0,
            limit=10,
            search_terms="7278637",
            t9_search=True,
        )
        self.assertIdInStoreData(self.partner1.id, store_data)
        self.assertIdNotInStoreData(self.partner4.id, store_data)
        self.assertIdNotInStoreData(self.partner2.id, store_data)
        self.assertIdNotInStoreData(self.partner3.id, store_data)

    def test_voip_get_contacts_phone_search_min_length(self):
        if self.min_length <= 1:
            self.skipTest("_phone_search_min_length is set to 1, skipping test.")

        store_data = self.env["res.partner"].get_contacts(
            offset=0,
            limit=10,
            search_terms="1" * self.min_length,
        )
        self.assertIdInStoreData(self.partner1.id, store_data)

        store_data = self.env["res.partner"].get_contacts(
            offset=0,
            limit=10,
            search_terms="1" * (self.min_length - 1),
        )
        self.assertIdNotInStoreData(self.partner1.id, store_data)
