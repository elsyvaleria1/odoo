from odoo.tests import Form, common


class TestResPartnerBank(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

    def test_res_partner_bank_account_employee_view(self):
        partner_1, partner_2 = self.env["res.partner"].create(
            [{"name": "Ralph"}, {"name": "Bella"}]
        )
        self.env["hr.employee"].create(
            [
                {
                    "name": "Ralph",
                    "partner_id": partner_1.id,
                },
                {
                    "name": "Bella",
                    "partner_id": partner_2.id,
                },
            ]
        )
        res_partner_bank_account_1 = self.env["res.partner.bank.account"].create(
            [
                {
                    "acc_number": "0144748555",
                    "partner_id": partner_1.id,
                }
            ]
        )
        partner_bank_form = (
            "hr_payroll_account.view_partner_bank_form_inherit_hr_payroll_account"
        )
        partner = self.env["res.partner.bank.account"].with_context(
            from_employee_bank_account=True
        )

        with Form(partner, view=partner_bank_form) as partner_bank:
            partner_bank.acc_number = "12111121232"
            partner_bank.partner_id = partner_1
            self.assertTrue(partner_bank.has_alt_bank_account)
            p_bank = partner_bank.save()
            self.assertNotIn(
                res_partner_bank_account_1,
                partner_1.employee_ids[0].salary_bank_account_ids,
            )
            self.assertIn(p_bank, partner_1.employee_ids[0].salary_bank_account_ids)

        self.assertFalse(partner_2.employee_ids[0].salary_bank_account_ids)
        with Form(partner, view=partner_bank_form) as partner_bank:
            partner_bank.acc_number = "23298957"
            partner_bank.partner_id = partner_2
            self.assertFalse(partner_bank.has_alt_bank_account)
            p_bank = partner_bank.save()
            self.assertIn(p_bank, partner_2.employee_ids[0].salary_bank_account_ids)

    def test_has_alt_bank_account_invalidates_on_sibling_creation(self):
        partner = self.env["res.partner"].create({"name": "Cyril"})
        bank_a = self.env["res.partner.bank.account"].create(
            {"acc_number": "BE1234567890", "partner_id": partner.id}
        )
        self.assertFalse(bank_a.has_alt_bank_account)

        self.env["res.partner.bank.account"].create(
            {"acc_number": "BE0987654321", "partner_id": partner.id}
        )
        self.assertTrue(bank_a.has_alt_bank_account)
