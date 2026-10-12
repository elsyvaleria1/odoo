from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPhoneNumberRekey(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Phone = cls.env["phone.number"]

    def _keyed_by_an_older_normalizer(self, phone, number, sanitized):
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE phone_number SET number = %s, sanitized = %s WHERE id = %s",
            [number, sanitized, phone.id],
        )
        self.env.invalidate_all()

    def _rekey(self):
        self.Phone._rekey_sanitized()
        self.env.flush_all()

    def test_a_number_keyed_anew_into_a_held_key_joins_its_holder(self):
        held = self.Phone.create({"number": "+40 21 209 77 01"})
        contact = self.env["res.partner"].create(
            {
                "name": "Bucharest office",
                "phone_ids": [Command.create({"number": "+40 21 209 77 91"})],
            }
        )
        stale = contact.phone_ids
        contact.preferred_phone_id = stale
        self._keyed_by_an_older_normalizer(stale, "+40 21 209 77 01", "0212097701")

        self._rekey()

        self.assertFalse(stale.exists())
        self.assertEqual(contact.phone_ids, held)
        self.assertEqual(contact.preferred_phone_id, held)
        self.assertEqual(held.sanitized, "+40212097701")

    def test_numbers_keyed_anew_into_one_key_become_one(self):
        first = self.Phone.create({"number": "+40 21 209 77 92", "active": False})
        second = self.Phone.create({"number": "+40 21 209 77 93"})
        self._keyed_by_an_older_normalizer(first, "+40 21 209 77 02", "0212097702")
        self._keyed_by_an_older_normalizer(second, "+40 21 209 77 02", "212097702")

        self._rekey()

        self.assertTrue(first.exists())
        self.assertFalse(second.exists())
        self.assertEqual(first.sanitized, "+40212097702")
        self.assertTrue(first.active)

    def test_a_number_takes_a_key_another_is_leaving(self):
        leaving = self.Phone.create({"number": "+40 21 209 77 03"})
        taking = self.Phone.create({"number": "+40 21 209 77 94"})
        self._keyed_by_an_older_normalizer(leaving, "+40 21 209 77 04", "+40212097703")
        self._keyed_by_an_older_normalizer(taking, "+40 21 209 77 03", "0212097703")

        self._rekey()

        self.assertEqual(taking.sanitized, "+40212097703")
        self.assertEqual(leaving.sanitized, "+40212097704")

    def test_a_known_number_created_without_contacts_keeps_its_contacts(self):
        contact = self.env["res.partner"].create(
            {
                "name": "Bucharest desk",
                "phone_ids": [Command.create({"number": "+40 21 209 77 06"})],
            }
        )

        again = self.Phone.create({"number": "+40212097706", "partner_ids": False})

        self.assertEqual(again, contact.phone_ids)
        self.assertEqual(again.partner_ids, contact)
