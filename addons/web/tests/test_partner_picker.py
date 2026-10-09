from odoo.tests import TransactionCase, tagged


@tagged("web_unit", "web_partner")
class TestPartnerPickerHidesBanks(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bank = cls.env["res.bank"].create({"name": "Zyzzyva Bank"})
        cls.customer = cls.env["res.partner"].create({"name": "Zyzzyva Customer"})
        cls.spec = {"display_name": {}}

    def _picked(self, partners, **kwargs):
        return {
            row["id"]
            for row in partners.web_name_search("Zyzzyva", self.spec, **kwargs)
        }

    def test_the_picker_offers_the_customer_and_not_the_bank(self):
        self.assertEqual(self._picked(self.env["res.partner"]), {self.customer.id})

    def test_a_caller_asking_for_banks_gets_them(self):
        self.assertEqual(
            self._picked(self.env["res.partner"], domain=[("is_bank", "=", True)]),
            {self.bank.partner_id.id},
        )
        self.assertEqual(
            self._picked(self.env["res.partner"].with_context(show_bank_partners=True)),
            {self.customer.id, self.bank.partner_id.id},
        )

    def test_name_search_outside_the_picker_still_finds_the_bank(self):
        found = {pid for pid, _name in self.env["res.partner"].name_search("Zyzzyva")}
        self.assertEqual(found, {self.customer.id, self.bank.partner_id.id})

    def test_the_bank_stays_reachable_as_a_bank(self):
        found = {bid for bid, _name in self.env["res.bank"].name_search("Zyzzyva")}
        self.assertEqual(found, {self.bank.id})


@tagged("web_unit", "web_partner")
class TestPickersLeaveOutServicePrincipals(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        group_user = cls.env.ref("base.group_user")
        cls.person, cls.service = cls.env["res.users"].create(
            [
                {
                    "name": "Quokka Person",
                    "login": "quokka_person",
                    "group_ids": [(6, 0, group_user.ids)],
                },
                {
                    "name": "Quokka Receiver",
                    "login": "quokka_receiver",
                    "principal_type": "service",
                    "group_ids": [(6, 0, group_user.ids)],
                },
            ]
        )
        cls.spec = {"display_name": {}}

    def _picked(self, model, **kwargs):
        return {
            row["id"]
            for row in self.env[model].web_name_search("Quokka", self.spec, **kwargs)
        }

    def test_the_user_picker_offers_people(self):
        self.assertEqual(self._picked("res.users"), {self.person.id})

    def test_a_field_asking_for_service_principals_gets_them(self):
        self.assertEqual(
            self._picked("res.users", domain=[("principal_type", "=", "service")]),
            {self.service.id},
        )

    def test_the_partner_picker_leaves_out_a_service_principals_partner(self):
        self.assertEqual(self._picked("res.partner"), {self.person.partner_id.id})

    def test_name_search_outside_the_picker_still_finds_the_service_principal(self):
        found = {uid for uid, _name in self.env["res.users"].name_search("Quokka")}
        self.assertEqual(found, {self.person.id, self.service.id})
