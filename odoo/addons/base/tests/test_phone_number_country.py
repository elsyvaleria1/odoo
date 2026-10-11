from unittest.mock import patch

from odoo import Command
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestPhoneNumberCountry(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.romania = cls.env.ref("base.ro")
        cls.belgium = cls.env.ref("base.be")
        cls.Phone = cls.env["phone.number"]
        cls.contact = cls.env["res.partner"].create(
            {
                "name": "Bucharest office",
                "country_id": cls.romania.id,
                "phone_ids": [Command.create({"number": "021 209 99 99"})],
            }
        )

    def test_a_number_created_on_a_contact_takes_the_contacts_country(self):
        phone = self.contact.phone_ids

        self.assertEqual(phone.country_id, self.romania)
        self.assertTrue(phone.country_inferred)

    def test_a_number_created_alone_has_no_country_to_infer(self):
        phone = self.Phone.create({"number": "021 209 99 98"})

        self.assertFalse(phone.country_id)
        self.assertTrue(phone.country_inferred)

    def test_a_number_given_a_country_keeps_it_as_chosen(self):
        phone = self.Phone.create(
            {
                "number": "021 209 99 97",
                "country_id": self.belgium.id,
                "partner_ids": [Command.link(self.contact.id)],
            }
        )

        self.assertEqual(phone.country_id, self.belgium)
        self.assertFalse(phone.country_inferred)

    def test_setting_a_country_on_the_number_makes_it_chosen(self):
        phone = self.contact.phone_ids

        phone.country_id = self.belgium

        self.assertFalse(phone.country_inferred)

    def test_a_contacts_new_country_is_read_into_its_own_number(self):
        phone = self.contact.phone_ids

        self.contact.country_id = self.belgium

        self.assertEqual(phone.country_id, self.belgium)
        self.assertTrue(phone.country_inferred)

    def test_a_number_created_alone_takes_the_country_of_its_first_contact(self):
        phone = self.Phone.create({"number": "021 209 99 96"})

        self.contact.phone_ids = [Command.link(phone.id)]

        self.assertEqual(phone.country_id, self.romania)
        self.assertTrue(phone.country_inferred)

    def test_a_shared_number_keeps_its_country_when_one_contact_moves(self):
        phone = self.contact.phone_ids
        branch = self.env["res.partner"].create(
            {
                "name": "Bucharest branch",
                "country_id": self.romania.id,
                "phone_ids": [Command.link(phone.id)],
            }
        )

        branch.country_id = self.belgium

        self.assertEqual(phone.country_id, self.romania)

    def test_an_archived_second_contact_still_shares_the_number(self):
        phone = self.contact.phone_ids
        self.env["res.partner"].create(
            {
                "name": "Former branch",
                "active": False,
                "country_id": self.romania.id,
                "phone_ids": [Command.link(phone.id)],
            }
        )

        self.contact.country_id = self.belgium

        self.assertEqual(phone.country_id, self.romania)

    def test_a_chosen_country_is_never_overwritten_by_the_contact(self):
        phone = self.contact.phone_ids
        phone.country_id = self.romania

        self.contact.country_id = self.belgium

        self.assertEqual(phone.country_id, self.romania)

    def test_a_contact_losing_its_country_leaves_the_number_as_read(self):
        phone = self.contact.phone_ids

        self.contact.country_id = False

        self.assertEqual(phone.country_id, self.romania)

    def test_a_contact_creator_who_may_not_write_contacts_still_has_it_read(self):
        creators = self.env["res.groups"].create({"name": "Contact creators"})
        self.env["ir.access"].create(
            {
                "name": "Contact creators create contacts",
                "model_id": self.env["ir.model"]._get_id("res.partner"),
                "group_id": creators.id,
                "kind": "permission",
                "operation": "c",
            }
        )
        creator = new_test_user(
            self.env, login="contact_creator", groups="base.group_user"
        )
        creator.group_ids = [Command.link(creators.id)]
        phone = self.Phone.create({"number": "021 209 99 94"})

        self.env["res.partner"].with_user(creator).create(
            {
                "name": "Brussels desk",
                "country_id": self.belgium.id,
                "phone_ids": [Command.link(phone.id)],
            }
        )

        self.assertEqual(phone.country_id, self.belgium)

    def test_a_number_whose_value_stays_looks_for_no_other_holder(self):
        contact = self.env["res.partner"].create(
            {
                "name": "Bucharest desk",
                "country_id": self.romania.id,
                "phone_ids": [Command.create({"number": "+40 21 209 88 12"})],
            }
        )
        phone = contact.phone_ids
        sanitized = phone.sanitized
        executed = []
        execute = type(self.env.cr).execute

        def spy(cr, query, *args, **kwargs):
            executed.append(str(getattr(query, "code", query)))
            return execute(cr, query, *args, **kwargs)

        with patch.object(type(self.env.cr), "execute", spy):
            contact.country_id = self.belgium
            self.env.flush_all()

        self.assertEqual(phone.country_id, self.belgium)
        self.assertEqual(phone.sanitized, sanitized)
        self.assertFalse([q for q in executed if "sanitized = ANY" in q])
