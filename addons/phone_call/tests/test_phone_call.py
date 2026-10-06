from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPhoneCall(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.xiuman = cls.env["res.company"].create({"name": "Xiuman"})
        cls.agent = cls.env["res.users"].create(
            {
                "name": "Agent",
                "login": "phone_call_agent",
                "company_id": cls.xiuman.id,
                "company_ids": [(6, 0, [cls.xiuman.id, cls.env.company.id])],
            }
        )

    def _call(self, **vals):
        return self.env["phone.call"].create(
            {"phone_number": "+52 55 1234 5678", **vals}
        )

    def test_a_call_belongs_to_the_company_its_user_works_in(self):
        main = self.env.company
        for company in (main, self.xiuman):
            call = (
                self.env["phone.call"]
                .with_company(company)
                .create({"phone_number": "+52 55 1234 5678", "user_id": self.agent.id})
            )
            self.assertEqual(call.company_id, company)

    def test_a_call_filed_from_outside_its_users_companies_takes_their_default(self):
        elsewhere = self.env["res.company"].create({"name": "Elsewhere"})
        call = (
            self.env["phone.call"]
            .with_company(elsewhere)
            .create({"phone_number": "+52 55 1234 5678", "user_id": self.agent.id})
        )
        self.assertEqual(call.company_id, self.xiuman)

    def test_a_line_company_outlives_a_change_of_user(self):
        call = self._call(user_id=self.agent.id, company_id=self.env.company.id)
        call.user_id = self.env.user
        self.assertEqual(call.company_id, self.env.company)

    def test_the_outcome_names_the_call(self):
        partner = self.env["res.partner"].create({"name": "Rancho Xiuman"})
        names = {
            (state, direction): self._call(
                state=state, direction=direction, partner_id=partner.id
            ).display_name
            for state, direction in (
                ("terminated", "incoming"),
                ("terminated", "outgoing"),
                ("missed", "incoming"),
                ("voicemail", "incoming"),
            )
        }
        self.assertEqual(names[("terminated", "incoming")], "Call from Rancho Xiuman")
        self.assertEqual(names[("terminated", "outgoing")], "Call to Rancho Xiuman")
        self.assertEqual(
            names[("missed", "incoming")], "Missed call from +52 55 1234 5678"
        )
        self.assertEqual(
            names[("voicemail", "incoming")], "Voicemail from +52 55 1234 5678"
        )

    def test_calls_to_the_same_number_are_counted_together(self):
        first = self._call()
        self._call()
        self._call(phone_number="+52 33 0000 0000")
        self.assertEqual(first.call_count, 2)

    def test_a_user_reads_only_the_calls_they_are_responsible_for(self):
        own = self._call(user_id=self.agent.id)
        other = self._call(user_id=self.env.user.id, company_id=self.xiuman.id)
        self.assertTrue(own.with_user(self.agent).has_access("read"))
        self.assertFalse(other.with_user(self.agent).has_access("read"))

    def test_a_user_counts_only_the_calls_they_may_read(self):
        own = self._call(user_id=self.agent.id, company_id=self.xiuman.id)
        self._call(user_id=self.env.user.id, company_id=self.xiuman.id)
        self.assertEqual(own.call_count, 2)
        self.assertEqual(own.with_user(self.agent).call_count, 1)

    def test_a_company_call_nobody_answered_is_read_by_that_company(self):
        missed = self._call(
            state="missed", channel="pbx", user_id=False, company_id=self.xiuman.id
        )
        self.assertTrue(missed.with_user(self.agent).has_access("read"))
        ownerless = self._call(user_id=False, company_id=self.xiuman.id)
        self.assertFalse(
            ownerless.with_user(self.agent).has_access("read"),
            "a handset's or softphone's call with no owner stays private",
        )
        outsider = self.env["res.users"].create(
            {
                "name": "Outsider",
                "login": "phone_call_outsider",
                "company_id": self.env.company.id,
                "company_ids": [(6, 0, [self.env.company.id])],
            }
        )
        self.assertFalse(missed.with_user(outsider).has_access("read"))

    def test_the_calls_of_a_numberless_call_are_its_own(self):
        numberless = self._call(phone_number=False, contact_name="Withheld")
        self._call(phone_number=False, contact_name="Another")
        domain = numberless.action_view_calls()["domain"]
        self.assertEqual(self.env["phone.call"].search(domain), numberless)
