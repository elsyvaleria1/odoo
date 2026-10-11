from unittest.mock import patch

from odoo import Command, models, tests
from odoo.exceptions import UserError

from .common import TestInterCompanyRulesCommon
from odoo.addons.account.tests.common_posting_obligation import (
    holding_invoice_posting,
)


@tests.tagged("post_install", "-at_install")
class TestInterCompanyInvoice(TestInterCompanyRulesCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        (cls.company_a + cls.company_b).write(
            {
                "intercompany_generate_bills_refund": True,
            }
        )
        cls.env.user.company_id = cls.company_b
        cls.env["account.chart.template"].try_loading(
            "generic_coa", cls.company_b, install_demo=False
        )
        cls.env.user.company_id = cls.company_a
        cls.env["account.chart.template"].try_loading(
            "generic_coa", cls.company_a, install_demo=False
        )

    def _configure_analytic(self, product=None, company=None, partner=None):
        display_name = "Inter Company"
        if company:
            self.env.user.company_id = company
            display_name = company.display_name
        analytic_plan = self.env["account.analytic.plan"].create(
            {"name": f"Analytic Plan {display_name}"}
        )
        analytic_account = self.env["account.analytic.account"].create(
            {
                "name": f"Account {display_name}",
                "company_id": company and company.id,
                "plan_id": analytic_plan.id,
            }
        )
        self.env["account.analytic.distribution.model"].create(
            {
                "analytic_distribution": {analytic_account.id: 100},
                "product_id": product and product.id,
                "company_id": company and company.id,
                "partner_id": partner and partner.id,
            }
        )
        return analytic_account

    def _create_post_invoice(self, product_id, analytic_distribution=None):
        invoice_line_vals = {
            "product_id": product_id,
            "price_unit": 100.0,
            "quantity": 1.0,
        }
        if analytic_distribution:
            invoice_line_vals["analytic_distribution"] = analytic_distribution

        customer_invoice = (
            self.env["account.move"]
            .with_user(self.res_users_company_a)
            .create(
                {
                    "move_type": "out_invoice",
                    "partner_id": self.company_b.partner_id.id,
                    "invoice_line_ids": [(0, 0, invoice_line_vals)],
                }
            )
        )
        customer_invoice.with_user(self.res_users_company_a).action_post()
        return customer_invoice

    def _get_generated_bill(self, customer_invoice, user=None):
        moves = self.env["account.move"]
        if user:
            moves = moves.with_user(user)
        bill = moves.search([("auto_invoice_id", "=", customer_invoice.id)])
        self.assertEqual(len(bill), 1, "exactly one bill is generated per invoice")
        return bill

    def test_00_inter_company_invoice_flow(self):

        self.env.ref("base.EUR").active = True

        self.res_users_company_a.company_ids = [(4, self.company_b.id)]
        customer_invoice = (
            self.env["account.move"]
            .with_user(self.res_users_company_a)
            .create(
                {
                    "move_type": "out_invoice",
                    "partner_id": self.company_b.partner_id.id,
                    "currency_id": self.env.ref("base.EUR").id,
                    "invoice_line_ids": [
                        (
                            0,
                            0,
                            {
                                "product_id": self.product_consultant.id,
                                "price_unit": 450.0,
                                "quantity": 1.0,
                                "name": "test",
                            },
                        )
                    ],
                }
            )
        )

        self.assertEqual(
            customer_invoice.state,
            "draft",
            'Initially customer invoice should be in the "Draft" state',
        )

        customer_invoice.with_user(self.res_users_company_a).action_post()

        self.assertEqual(
            customer_invoice.state, "posted", "Invoice should be in Open state."
        )

        supplier_invoice = self._get_generated_bill(
            customer_invoice, user=self.res_users_company_b
        )

        self.assertTrue(
            supplier_invoice.invoice_line_ids[0].quantity == 1,
            "Quantity in invoice line is incorrect.",
        )
        self.assertTrue(
            supplier_invoice.invoice_line_ids[0].product_id.id
            == self.product_consultant.id,
            "Product in line is incorrect.",
        )
        self.assertTrue(
            supplier_invoice.invoice_line_ids[0].price_unit == 450,
            "Unit Price in invoice line is incorrect.",
        )
        self.assertTrue(
            supplier_invoice.invoice_line_ids[0].account_id.company_ids
            == self.company_b,
            "Applied account in created invoice line is not relevant to company.",
        )
        self.assertTrue(
            supplier_invoice.state == "draft", "invoice should be in draft state."
        )
        self.assertEqual(
            supplier_invoice.amount_total, 517.5, "Total amount is incorrect."
        )
        self.assertTrue(
            supplier_invoice.company_id.id == self.company_b.id,
            "Applied company in created invoice is incorrect.",
        )

    def test_default_analytic_distribution_company_b(self):
        analytic_account_company_b = self._configure_analytic(
            company=self.company_b, product=self.product_a
        )
        inter_company_analytic_account = self._configure_analytic(
            product=self.product_b
        )

        customer_invoice = self._create_post_invoice(
            product_id=self.product_a.id,
            analytic_distribution={inter_company_analytic_account.id: 100},
        )
        supplier_invoice = self._get_generated_bill(
            customer_invoice, user=self.res_users_company_b
        )

        self.assertEqual(
            supplier_invoice.invoice_line_ids.analytic_distribution,
            {
                str(analytic_account_company_b.id): 100,
                str(inter_company_analytic_account.id): 100,
            },
        )

    def test_no_default_analytic_distribution_company_b(self):
        inter_company_analytic_account = self._configure_analytic(
            product=self.product_b
        )

        customer_invoice = self._create_post_invoice(
            product_id=self.product_a.id,
            analytic_distribution={inter_company_analytic_account.id: 100},
        )
        supplier_invoice = self._get_generated_bill(
            customer_invoice, user=self.res_users_company_b
        )

        self.assertEqual(
            supplier_invoice.invoice_line_ids.analytic_distribution,
            {str(inter_company_analytic_account.id): 100},
        )

    def test_multi_analytic_account_distribution_company_b(self):
        analytic_account_company_a = self._configure_analytic(
            company=self.company_a, product=self.product_a
        )
        inter_company_analytic_account = self._configure_analytic(
            product=self.product_a
        )

        customer_invoice = self._create_post_invoice(
            product_id=self.product_a.id,
            analytic_distribution={
                analytic_account_company_a.id: 50,
                inter_company_analytic_account.id: 50,
                f"{analytic_account_company_a.id},{inter_company_analytic_account.id}": 100,
            },
        )
        supplier_invoice = self._get_generated_bill(
            customer_invoice, user=self.res_users_company_b
        )

        self.assertEqual(
            supplier_invoice.invoice_line_ids.analytic_distribution,
            {str(inter_company_analytic_account.id): 50},
        )

    def test_default_analytic_distribution_company_a(self):
        analytic_account_company_a = self._configure_analytic(
            company=self.company_a, product=self.product_a
        )

        customer_invoice = self._create_post_invoice(
            product_id=self.product_a.id,
            analytic_distribution={analytic_account_company_a.id: 100},
        )
        supplier_invoice = self._get_generated_bill(
            customer_invoice, user=self.res_users_company_b
        )

        self.assertFalse(
            supplier_invoice.invoice_line_ids.analytic_distribution,
            "Analytic distribution should not be set on the invoice line.",
        )

    def test_inter_company_invoice_flow_sub_companies(self):
        self.company_a.write(
            {
                "child_ids": [
                    Command.create({"name": "Branch 1 of company a"}),
                    Command.create({"name": "Branch 2 of company a"}),
                ]
            }
        )
        self.cr.precommit.run()

        branch_1, branch_2 = self.company_a.child_ids
        (branch_1 + branch_2).write(
            {
                "intercompany_generate_bills_refund": True,
            }
        )

        for branch in [branch_1, branch_2]:
            branch.intercompany_purchase_journal_id = self.env[
                "account.journal"
            ].create(
                {
                    "name": "Purchases - Test",
                    "code": "TEXJ",
                    "type": "purchase",
                    "company_id": branch.id,
                }
            )

        self.env.user.write(
            {
                "company_ids": [Command.set((branch_1 + branch_2).ids)],
                "company_id": branch_1.id,
            }
        )

        customer_invoice = (
            self.env["account.move"]
            .with_context(allowed_company_ids=branch_1.ids)
            .create(
                {
                    "move_type": "out_invoice",
                    "invoice_date": "2023-05-01",
                    "partner_id": branch_2.partner_id.id,
                    "invoice_line_ids": [
                        Command.create(
                            {
                                "product_id": self.product_a.id,
                                "price_unit": 100.0,
                                "quantity": 1.0,
                                "tax_ids": False,
                            }
                        )
                    ],
                }
            )
        )

        customer_invoice.action_post()
        bill = self._get_generated_bill(customer_invoice)

        self.assertRecordValues(
            bill,
            [
                {
                    "partner_id": branch_1.partner_id.id,
                    "company_id": branch_2.id,
                    "payment_reference": customer_invoice.payment_reference,
                }
            ],
        )

    def test_inter_company_invoice_product_not_accessible(self):
        self.product_a.company_id = self.company_a
        customer_invoice = self._create_post_invoice(self.product_a.id)
        supplier_invoice = self._get_generated_bill(
            customer_invoice, user=self.res_users_company_b
        )
        self.assertFalse(
            supplier_invoice.invoice_line_ids.product_id, "No product should be set"
        )
        self.assertEqual(supplier_invoice.invoice_line_ids.name, self.product_a.name)

    def test_analytic_distribution_model_partner(self):
        inter_company_analytic_account = self._configure_analytic(
            product=self.product_b
        )
        analytic_account_company_b = self._configure_analytic(
            company=self.company_b, partner=self.company_a.partner_id
        )
        customer_invoice = self._create_post_invoice(
            product_id=self.product_a.id,
            analytic_distribution={inter_company_analytic_account.id: 100},
        )

        supplier_invoice = self._get_generated_bill(
            customer_invoice, user=self.res_users_company_b
        )

        expected_distribution = {
            str(inter_company_analytic_account.id): 100,
            str(analytic_account_company_b.id): 100,
        }
        self.assertEqual(
            supplier_invoice.invoice_line_ids.analytic_distribution,
            expected_distribution,
        )

    def test_inter_company_attachment_with_contact_as_partner(self):
        company_partner = self.env["res.partner"].create(
            {
                "name": "company partner",
                "parent_id": self.company_b.partner_id.id,
            }
        )

        customer_invoice = self.env["account.move"].create(
            {
                "company_id": self.company_a.id,
                "move_type": "out_invoice",
                "invoice_date": "2023-05-01",
                "partner_id": company_partner.id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_a.id,
                            "price_unit": 100.0,
                            "quantity": 1.0,
                            "tax_ids": False,
                        }
                    )
                ],
            }
        )

        customer_invoice.action_post()

        self.env["wizard.account.move.send"].with_context(
            active_model="account.move", active_ids=customer_invoice.id
        )._generate_and_send_invoices(customer_invoice)

        bill = self._get_generated_bill(customer_invoice)
        self.assertTrue(bill.attachment_ids)

    def test_purchase_journal_resolved_when_the_compute_missed_it(self):
        self.company_b.intercompany_purchase_journal_id = False
        self.assertTrue(
            self.env["account.journal"]
            .sudo()
            .search(
                [("type", "=", "purchase"), ("company_id", "=", self.company_b.id)]
            ),
            "company_b owns a purchase journal the empty stored field ignores",
        )
        fallback = self.company_b._get_intercompany_purchase_journal()
        self.assertTrue(fallback, "the fallback must resolve the company's journal")

        self._create_post_invoice(self.product_a.id)

        bill = (
            self.env["account.move"].sudo().search([("auto_invoice_id", "!=", False)])
        )
        self.assertEqual(len(bill), 1)
        self.assertEqual(bill.journal_id, fallback)

    def test_generation_requires_an_intercompany_user(self):
        self.company_b.intercompany_user_id = False
        customer_invoice = (
            self.env["account.move"]
            .with_user(self.res_users_company_a)
            .create(
                {
                    "move_type": "out_invoice",
                    "invoice_date": "2024-05-01",
                    "partner_id": self.company_b.partner_id.id,
                    "invoice_line_ids": [
                        Command.create(
                            {
                                "product_id": self.product_a.id,
                                "price_unit": 100.0,
                                "quantity": 1.0,
                                "tax_ids": False,
                            }
                        )
                    ],
                }
            )
        )
        with self.assertRaisesRegex(UserError, "No user is set"):
            customer_invoice.with_user(self.res_users_company_a).action_post()

    def test_generation_requires_a_purchase_journal(self):
        self.company_a.write(
            {"child_ids": [Command.create({"name": "Branch without journal"})]}
        )
        self.cr.precommit.run()
        branch = self.company_a.child_ids[-1]
        branch.intercompany_generate_bills_refund = True
        self.assertEqual(
            self.env["res.company"]
            .sudo()
            ._find_company_from_partner(branch.partner_id.id),
            branch,
            "the fixture must resolve to the branch, not to its parent",
        )
        self.assertFalse(branch._get_intercompany_purchase_journal())

        customer_invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "company_id": self.company_a.id,
                "invoice_date": "2024-05-01",
                "partner_id": branch.partner_id.id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_a.id,
                            "price_unit": 100.0,
                            "quantity": 1.0,
                            "tax_ids": False,
                        }
                    )
                ],
            }
        )
        with self.assertRaisesRegex(UserError, "No purchase journal"):
            customer_invoice.action_post()

    def test_reposting_does_not_duplicate_the_bill(self):
        self._create_post_invoice(self.product_a.id)
        customer_invoice = self.env["account.move"].search(
            [("move_type", "=", "out_invoice"), ("company_id", "=", self.company_a.id)]
        )
        self.assertEqual(len(customer_invoice), 1)
        mirrors = (
            self.env["account.move"]
            .sudo()
            .search([("auto_invoice_id", "=", customer_invoice.id)])
        )
        self.assertEqual(len(mirrors), 1)

        customer_invoice.action_draft()
        customer_invoice.action_post()

        self.assertEqual(
            self.env["account.move"]
            .sudo()
            .search([("auto_invoice_id", "=", customer_invoice.id)]),
            mirrors,
            "re-posting must not generate a second vendor bill",
        )

    def test_no_mirror_for_an_invoice_to_your_own_company(self):
        customer_invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "company_id": self.company_a.id,
                "invoice_date": "2024-05-01",
                "partner_id": self.company_a.partner_id.id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_a.id,
                            "price_unit": 100.0,
                            "quantity": 1.0,
                            "tax_ids": False,
                        }
                    )
                ],
            }
        )
        customer_invoice.action_post()

        self.assertFalse(
            self.env["account.move"]
            .sudo()
            .search([("auto_invoice_id", "=", customer_invoice.id)]),
            "a company must not generate a vendor bill against itself",
        )

    def test_posting_context_defaults_do_not_reach_the_bill(self):
        customer_invoice = (
            self.env["account.move"]
            .with_user(self.res_users_company_a)
            .create(
                {
                    "move_type": "out_invoice",
                    "invoice_date": "2024-05-01",
                    "partner_id": self.company_b.partner_id.id,
                    "invoice_line_ids": [
                        Command.create(
                            {
                                "product_id": self.product_a.id,
                                "price_unit": 100.0,
                                "quantity": 1.0,
                                "tax_ids": False,
                            }
                        )
                    ],
                }
            )
        )
        customer_invoice.with_context(
            default_narration="LEAKED", default_ref="LEAKED"
        ).action_post()

        bill = (
            self.env["account.move"]
            .sudo()
            .search([("auto_invoice_id", "=", customer_invoice.id)])
        )
        self.assertEqual(len(bill), 1)
        self.assertFalse(bill.narration, "default_narration must not cross over")
        self.assertEqual(
            bill.ref,
            customer_invoice.name,
            "ref is set explicitly from the source and must win over a default",
        )

    def test_target_company_is_resolved_once_per_move(self):
        customer_invoice = (
            self.env["account.move"]
            .with_user(self.res_users_company_a)
            .create(
                {
                    "move_type": "out_invoice",
                    "invoice_date": "2024-05-01",
                    "partner_id": self.company_b.partner_id.id,
                    "invoice_line_ids": [
                        Command.create(
                            {
                                "product_id": self.product_a.id,
                                "price_unit": 100.0,
                                "quantity": 1.0,
                                "tax_ids": False,
                            }
                        )
                        for _i in range(3)
                    ],
                }
            )
        )
        company_model = self.env.registry["res.company"]
        original = company_model._find_company_from_partner
        calls = []

        def spy(records, partner_id):
            calls.append(partner_id)
            return original(records, partner_id)

        with patch.object(company_model, "_find_company_from_partner", spy):
            customer_invoice.with_user(self.res_users_company_a).action_post()

        self.assertEqual(len(customer_invoice.invoice_line_ids), 3)
        self.assertEqual(
            len(calls), 1, "the target company is constant per move: resolve it once"
        )
        bill = (
            self.env["account.move"]
            .sudo()
            .search([("auto_invoice_id", "=", customer_invoice.id)])
        )
        self.assertEqual(len(bill.invoice_line_ids), 3)

    def test_prepared_values_are_writable(self):
        customer_invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "company_id": self.company_a.id,
                "invoice_date": "2024-05-01",
                "partner_id": self.company_b.partner_id.id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_a.id,
                            "price_unit": 100.0,
                            "quantity": 1.0,
                            "tax_ids": False,
                        }
                    )
                ],
            }
        )
        vals = customer_invoice._inter_company_prepare_invoice_data(
            "in_invoice", self.company_b
        )
        for key, value in vals.items():
            if key.endswith("_id"):
                self.assertNotIsInstance(
                    value, models.Model, f"{key} must hold an id, not a recordset"
                )
        bill = self.env["account.move"].sudo().create(vals)
        self.assertEqual(bill.company_id, self.company_b)

    def _intercompany_branches(self):
        self.company_a.write(
            {
                "child_ids": [
                    Command.create({"name": "Branch 1 of company a"}),
                    Command.create({"name": "Branch 2 of company a"}),
                ]
            }
        )
        self.cr.precommit.run()
        branch_1, branch_2 = self.company_a.child_ids[-2:]
        (branch_1 + branch_2).write({"intercompany_generate_bills_refund": True})
        for index, branch in enumerate((branch_1, branch_2)):
            branch.intercompany_purchase_journal_id = self.env[
                "account.journal"
            ].create(
                {
                    "name": "Purchases - Test",
                    "code": f"BRJ{index}",
                    "type": "purchase",
                    "company_id": branch.id,
                }
            )
        self.env.user.write(
            {
                "company_ids": [Command.set((branch_1 + branch_2).ids)],
                "company_id": branch_1.id,
            }
        )
        return branch_1, branch_2

    def _post_branch_invoice(self, branch_1, branch_2, line_vals):
        customer_invoice = (
            self.env["account.move"]
            .with_context(allowed_company_ids=branch_1.ids)
            .create(
                {
                    "move_type": "out_invoice",
                    "company_id": branch_1.id,
                    "invoice_date": "2024-05-01",
                    "partner_id": branch_2.partner_id.id,
                    "invoice_line_ids": [Command.create(line_vals)],
                }
            )
        )
        customer_invoice.with_context(allowed_company_ids=branch_1.ids).action_post()
        bill = (
            self.env["account.move"]
            .sudo()
            .search([("auto_invoice_id", "=", customer_invoice.id)])
        )
        self.assertEqual(len(bill), 1)
        return bill

    def test_product_owned_by_a_shared_parent_is_mirrored(self):
        branch_1, branch_2 = self._intercompany_branches()
        product = (
            self.env["product.product"]
            .sudo()
            .create(
                {
                    "name": "Parent Owned",
                    "type": "service",
                    "company_id": self.company_a.id,
                }
            )
        )
        bill = self._post_branch_invoice(
            branch_1,
            branch_2,
            {
                "product_id": product.id,
                "price_unit": 100.0,
                "quantity": 1.0,
                "tax_ids": False,
            },
        )
        self.assertEqual(bill.invoice_line_ids.product_id, product)
        self.assertTrue(bill.invoice_line_ids.product_uom_id)

    def test_analytic_account_owned_by_a_shared_parent_is_mirrored(self):
        branch_1, branch_2 = self._intercompany_branches()
        plan = self.env["account.analytic.plan"].sudo().create({"name": "Parent plan"})
        account = (
            self.env["account.analytic.account"]
            .sudo()
            .create(
                {
                    "name": "Parent analytic account",
                    "plan_id": plan.id,
                    "company_id": self.company_a.id,
                }
            )
        )
        bill = self._post_branch_invoice(
            branch_1,
            branch_2,
            {
                "product_id": self.product_a.id,
                "price_unit": 100.0,
                "quantity": 1.0,
                "tax_ids": False,
                "analytic_distribution": {str(account.id): 100},
            },
        )
        self.assertEqual(
            bill.invoice_line_ids.analytic_distribution,
            {str(account.id): 100},
        )

    def test_attachment_reaches_a_bill_billed_to_a_nested_contact(self):
        branch_office = self.env["res.partner"].create(
            {
                "name": "Branch office",
                "is_company": True,
                "parent_id": self.company_b.partner_id.id,
            }
        )
        contact = self.env["res.partner"].create(
            {"name": "A contact", "parent_id": branch_office.id}
        )
        self.assertNotEqual(
            contact.commercial_partner_id,
            self.company_b.partner_id,
            "the fixture must be a partner the old prefilter would have missed",
        )

        customer_invoice = self.env["account.move"].create(
            {
                "company_id": self.company_a.id,
                "move_type": "out_invoice",
                "invoice_date": "2024-05-01",
                "partner_id": contact.id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_a.id,
                            "price_unit": 100.0,
                            "quantity": 1.0,
                            "tax_ids": False,
                        }
                    )
                ],
            }
        )
        customer_invoice.action_post()
        self.env["wizard.account.move.send"].with_context(
            active_model="account.move", active_ids=customer_invoice.id
        )._generate_and_send_invoices(customer_invoice)

        bill = (
            self.env["account.move"]
            .sudo()
            .search([("auto_invoice_id", "=", customer_invoice.id)])
        )
        self.assertEqual(len(bill), 1)
        self.assertTrue(bill.message_main_attachment_id, "the PDF must be copied over")

    def test_resending_does_not_stack_pdfs_on_the_bill(self):
        customer_invoice = self.env["account.move"].create(
            {
                "company_id": self.company_a.id,
                "move_type": "out_invoice",
                "invoice_date": "2024-05-01",
                "partner_id": self.company_b.partner_id.id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_a.id,
                            "price_unit": 100.0,
                            "quantity": 1.0,
                            "tax_ids": False,
                        }
                    )
                ],
            }
        )
        customer_invoice.action_post()
        wizard = self.env["wizard.account.move.send"].with_context(
            active_model="account.move", active_ids=customer_invoice.id
        )

        wizard._generate_and_send_invoices(customer_invoice)
        bill = (
            self.env["account.move"]
            .sudo()
            .search([("auto_invoice_id", "=", customer_invoice.id)])
        )
        copies = (
            self.env["ir.attachment"]
            .sudo()
            .search([("res_model", "=", "account.move"), ("res_id", "=", bill.id)])
        )
        self.assertEqual(len(copies), 1)

        wizard._generate_and_send_invoices(customer_invoice)

        self.assertEqual(
            self.env["ir.attachment"]
            .sudo()
            .search([("res_model", "=", "account.move"), ("res_id", "=", bill.id)]),
            copies,
            "a second send must not add another copy of the same PDF",
        )
        self.assertEqual(bill.message_main_attachment_id, copies)

    def test_no_mirror_when_generation_is_disabled(self):
        self.company_b.intercompany_generate_bills_refund = False
        self._create_post_invoice(self.product_a.id)
        customer_invoice = self.env["account.move"].search(
            [("move_type", "=", "out_invoice"), ("company_id", "=", self.company_a.id)]
        )
        self.assertEqual(len(customer_invoice), 1)
        self.assertFalse(
            self.env["account.move"]
            .sudo()
            .search([("auto_invoice_id", "=", customer_invoice.id)])
        )

    def test_mirror_is_posted_when_automation_says_so(self):
        self.company_b.intercompany_document_state = "posted"
        self._create_post_invoice(self.product_a.id)
        customer_invoice = self.env["account.move"].search(
            [("move_type", "=", "out_invoice"), ("company_id", "=", self.company_a.id)]
        )
        bill = (
            self.env["account.move"]
            .sudo()
            .search([("auto_invoice_id", "=", customer_invoice.id)])
        )
        self.assertEqual(len(bill), 1)
        self.assertEqual(bill.state, "posted")

    def test_a_mirror_needing_approval_waits_in_draft(self):
        self.company_b.intercompany_document_state = "posted"
        with holding_invoice_posting(
            self.env, holds=lambda move: move.company_id == self.company_b
        ):
            customer_invoice = self._create_post_invoice(self.product_a.id)

        self.assertEqual(customer_invoice.state, "posted")
        bill = self._get_generated_bill(customer_invoice).sudo()
        self.assertEqual(bill.state, "draft")
        self.assertTrue(
            bill.message_ids.filtered(lambda message: "Left in draft" in message.body)
        )

    def test_credit_note_generates_a_refund(self):
        self._create_post_invoice(self.product_a.id)
        customer_invoice = self.env["account.move"].search(
            [("move_type", "=", "out_invoice"), ("company_id", "=", self.company_a.id)]
        )
        refund = customer_invoice._reverse_moves([{"invoice_date": "2024-05-02"}])
        refund.action_post()

        mirror = (
            self.env["account.move"]
            .sudo()
            .search([("auto_invoice_id", "=", refund.id)])
        )
        self.assertEqual(len(mirror), 1)
        self.assertEqual(mirror.move_type, "in_refund")
        self.assertEqual(mirror.company_id, self.company_b)

    def test_send_skips_the_attachment_copy_without_crashing_the_batch(self):
        customer_invoice = self._create_post_invoice(self.product_a.id)
        bill = self._get_generated_bill(customer_invoice)
        self.company_b.intercompany_user_id = False

        wizard = (
            self.env["wizard.account.move.send"]
            .with_context(active_model="account.move", active_ids=customer_invoice.id)
            .with_user(self.res_users_company_a)
        )
        wizard._generate_and_send_invoices(customer_invoice)

        self.assertFalse(
            bill.message_main_attachment_id,
            "no inter-company user is configured, so the copy must be skipped"
            " rather than crash",
        )

    def test_attachment_existence_check_is_batched_across_mirrors(self):
        customer_invoices = self.env["account.move"]
        for _i in range(3):
            customer_invoices += self._create_post_invoice(self.product_a.id)

        attachment_model = self.env.registry["ir.attachment"]
        original_search = attachment_model.search
        existence_check_domains = []

        def spy(self_, domain, *args, **kwargs):
            terms = list(domain) if isinstance(domain, (list, tuple)) else []
            if (
                terms
                and terms[0] == ("res_model", "=", "account.move")
                and any(
                    isinstance(term, (list, tuple)) and term[0] == "name"
                    for term in terms
                )
            ):
                existence_check_domains.append(terms)
            return original_search(self_, domain, *args, **kwargs)

        wizard = self.env["wizard.account.move.send"].with_context(
            active_model="account.move", active_ids=customer_invoices.ids
        )
        with patch.object(attachment_model, "search", spy):
            wizard._generate_and_send_invoices(customer_invoices)

        self.assertEqual(
            len(existence_check_domains),
            0,
            "the per-move ('name', '=', ...) existence search must be gone:"
            " one batched search feeds a Python dict lookup instead",
        )
        for customer_invoice in customer_invoices:
            self.assertTrue(
                self._get_generated_bill(customer_invoice).message_main_attachment_id
            )

    def test_purchase_journal_ignores_a_foreign_company_journal(self):
        foreign_journal = (
            self.env["account.journal"]
            .sudo()
            .search(
                [("type", "=", "purchase"), ("company_id", "=", self.company_a.id)],
                limit=1,
            )
        )
        own_journal = (
            self.env["account.journal"]
            .sudo()
            .search(
                [("type", "=", "purchase"), ("company_id", "=", self.company_b.id)],
                limit=1,
            )
        )
        self.assertTrue(foreign_journal and own_journal)
        self.assertNotEqual(foreign_journal, own_journal)

        self.company_b.intercompany_purchase_journal_id = foreign_journal.id
        self.assertEqual(
            self.company_b._get_intercompany_purchase_journal(),
            own_journal,
            "a foreign company's journal must not be trusted",
        )

        self._create_post_invoice(self.product_a.id)
        bill = (
            self.env["account.move"].sudo().search([("auto_invoice_id", "!=", False)])
        )
        self.assertEqual(len(bill), 1)
        self.assertEqual(bill.journal_id, own_journal)
