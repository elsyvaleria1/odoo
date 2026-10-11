from odoo import Command
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestPhoneNumberReuse(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.romania = cls.env.ref("base.ro")
        cls.first = cls.env["res.partner"].create(
            {
                "name": "Bucharest office",
                "country_id": cls.romania.id,
                "phone_ids": [Command.create({"number": "(021) 209.99.99"})],
            }
        )

    def test_a_local_number_added_to_a_second_contact_reuses_the_first(self):
        second = self.env["res.partner"].create(
            {"name": "Bucharest branch", "country_id": self.romania.id}
        )
        second.phone_ids = [Command.create({"number": "(021) 209.99.99"})]
        self.env.flush_all()
        self.assertEqual(second.phone_ids, self.first.phone_ids)
        self.assertEqual(second.phone_ids.sanitized, "+40212099999")
        self.assertEqual(
            self.env["phone.number"].search_count([("sanitized", "=", "+40212099999")]),
            1,
        )

    def test_a_contact_rewriting_its_own_number_keeps_one_row(self):
        self.first.write({"phone_ids": [Command.create({"number": "(021) 209.99.99"})]})
        self.env.flush_all()
        self.assertEqual(len(self.first.phone_ids), 1)

    def test_a_bank_reuses_its_partners_number_through_the_inherited_field(self):
        bank = self.env["res.bank"].create(
            {"name": "Alpha Bank", "country_id": self.romania.id}
        )
        bank.write({"phone_ids": [Command.create({"number": "(021) 209.99.99"})]})
        self.env.flush_all()
        self.assertEqual(bank.phone_ids, self.first.phone_ids)
        self.assertIn(bank.partner_id, bank.phone_ids.partner_ids)

    def test_a_contact_whose_country_is_corrected_has_its_number_reread(self):
        contact = self.env["res.partner"].create(
            {
                "name": "Mislabelled office",
                "country_id": self.romania.id,
                "phone_ids": [Command.create({"number": "02 209 99 99"})],
            }
        )
        self.env.flush_all()

        contact.country_id = self.env.ref("base.be")
        self.env.flush_all()

        self.assertEqual(contact.phone_ids.sanitized, "+3222099999")

    def _mislabelled(self, **extra):
        contact = self.env["res.partner"].create(
            {
                "name": "Mislabelled office",
                "country_id": self.romania.id,
                "phone_ids": [Command.create({"number": "02 209 99 99"})],
                **extra,
            }
        )
        self.env.flush_all()
        return contact

    def _brussels_number(self):
        brussels = self.env["res.partner"].create(
            {
                "name": "Brussels office",
                "country_id": self.env.ref("base.be").id,
                "phone_ids": [
                    Command.create({"number": "+32 2 209 99 99", "note": "Desk 4"})
                ],
            }
        )
        self.env.flush_all()
        return brussels.phone_ids

    def test_a_corrected_country_that_rereads_into_a_held_number_links_to_it(self):
        held = self._brussels_number()
        contact = self._mislabelled()
        duplicate = contact.phone_ids

        contact.country_id = self.env.ref("base.be")
        self.env.flush_all()

        self.assertEqual(contact.phone_ids, held)
        self.assertEqual(held.sanitized, "+3222099999")
        self.assertFalse(duplicate.exists())
        self.assertEqual(contact.main_mobile_id, held)

    def test_a_merged_number_stays_preferred_by_its_contact(self):
        held = self._brussels_number()
        contact = self._mislabelled()
        contact.preferred_phone_id = contact.phone_ids

        contact.country_id = self.env.ref("base.be")
        self.env.flush_all()

        self.assertEqual(contact.preferred_phone_id, held)

    def test_a_shared_number_is_not_reread_when_one_contact_moves(self):
        contact = self._mislabelled()
        phone = contact.phone_ids
        sanitized = phone.sanitized
        self.env["res.partner"].create(
            {
                "name": "Mislabelled branch",
                "country_id": self.romania.id,
                "phone_ids": [Command.link(phone.id)],
            }
        )

        contact.country_id = self.env.ref("base.be")
        self.env.flush_all()

        self.assertEqual(phone.sanitized, sanitized)
        self.assertEqual(phone.country_id, self.romania)

    def test_a_chosen_country_is_not_reread(self):
        contact = self.env["res.partner"].create(
            {
                "name": "Chosen office",
                "country_id": self.romania.id,
                "phone_ids": [
                    Command.create(
                        {"number": "021 209 99 98", "country_id": self.romania.id}
                    )
                ],
            }
        )
        self.env.flush_all()

        contact.country_id = self.env.ref("base.be")
        self.env.flush_all()

        self.assertEqual(contact.phone_ids.sanitized, "+40212099998")

    def test_a_number_typed_before_its_contact_reads_the_contacts_country(self):
        phone = self.env["phone.number"].create({"number": "02 209 99 98"})
        contact = self.env["res.partner"].create(
            {
                "name": "Brussels annex",
                "country_id": self.env.ref("base.be").id,
                "phone_ids": [Command.link(phone.id)],
            }
        )
        self.env.flush_all()

        self.assertEqual(contact.phone_ids.sanitized, "+3222099998")

    def test_a_portal_user_cannot_pull_a_number_it_cannot_read_onto_itself(self):
        held = self._brussels_number()
        contact = self._mislabelled()
        mine = contact.phone_ids
        portal = new_test_user(
            self.env,
            login="mislabelled_portal",
            groups="base.group_portal",
            partner_id=contact.id,
        )
        self.assertFalse(held.with_user(portal).has_access("read"))

        contact.with_user(portal).sudo().write(
            {"country_id": self.env.ref("base.be").id}
        )
        self.env.flush_all()

        self.assertEqual(contact.phone_ids, mine)
        self.assertNotIn(contact, held.partner_ids)

    def test_a_contact_writer_who_may_not_delete_numbers_still_merges(self):
        held = self._brussels_number()
        held.active = False
        contact = self._mislabelled()
        writers = self.env["res.groups"].create({"name": "Contact writers"})
        self.env["ir.access"].create(
            {
                "name": "Contact writers write contacts",
                "model_id": self.env["ir.model"]._get_id("res.partner"),
                "group_id": writers.id,
                "kind": "permission",
                "operation": "cu",
            }
        )
        writer = new_test_user(
            self.env, login="contact_writer", groups="base.group_user"
        )
        writer.group_ids = [Command.link(writers.id)]
        self.assertFalse(contact.phone_ids.with_user(writer).has_access("unlink"))

        contact.with_user(writer).country_id = self.env.ref("base.be")
        self.env.flush_all()

        self.assertEqual(contact.phone_ids, held)
        self.assertTrue(held.active)
