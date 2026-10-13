from odoo.tests import TransactionCase


class TestLetterAddress(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create(
            {"name": "Recipient", "street": "1 Old St", "city": "Paris"}
        )

    def _letter(self, partner, state="pending"):
        letter = self.env["snailmail.letter"].create(
            {"model": partner._name, "res_id": partner.id, "partner_id": partner.id}
        )
        letter.state = state
        return letter

    def test_an_unsent_letter_follows_its_recipient_address(self):
        pending = self._letter(self.partner)
        failed = self._letter(self.partner, "error")
        sent = self._letter(self.partner, "sent")
        canceled = self._letter(self.partner, "canceled")
        self.partner.write({"street": "2 New St", "city": "Lyon"})
        self.assertEqual(
            (pending | failed | sent | canceled).mapped("street"),
            ["2 New St", "2 New St", "1 Old St", "1 Old St"],
        )
        self.assertEqual((pending | failed).mapped("city"), ["Lyon", "Lyon"])

    def test_a_letter_sent_in_the_transaction_stops_following(self):
        letter = self._letter(self.partner)
        self.partner.write({"street": "2 New St"})
        letter.state = "sent"
        self.partner.write({"street": "3 Later St"})
        self.assertEqual(letter.street, "2 New St")
        resent = self._letter(self.partner)
        self.partner.write({"street": "4 Last St"})
        self.assertEqual(resent.street, "4 Last St")
        self.assertEqual(letter.street, "2 New St")

    def test_moving_many_recipients_one_by_one_reads_their_letters_once(self):
        partners = self.env["res.partner"].create(
            [{"name": f"Recipient {index}"} for index in range(10)]
        )
        letters = self._letter(partners[0]) | self._letter(partners[-1])
        self.env.flush_all()
        self.env.invalidate_all()
        partners = partners.browse(partners.ids)
        with self.capturedQueries() as queries:
            for index, partner in enumerate(partners):
                partner.write({"street": f"{index} Moved St"})
        self.assertEqual(
            len([query for query in queries if 'FROM "snailmail_letter"' in query]),
            1,
        )
        self.assertEqual(letters.mapped("street"), ["0 Moved St", "9 Moved St"])
