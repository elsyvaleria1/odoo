from collections import defaultdict
from unittest.mock import patch

from odoo import Command
from odoo.exceptions import RedirectWarning, UserError, ValidationError
from odoo.modules.neutralize import get_neutralization_queries
from odoo.tests.common import tagged

from .common import TestAccountAvataxCommon
from .mocked_refund_1_response import generate_response as generate_response_refund_1


class TestAccountAvalaraInternalCommon(TestAccountAvataxCommon):
    def assertInvoice(self, invoice, test_exact_response):
        self.assertEqual(
            len(invoice.invoice_line_ids.tax_ids),
            0,
            "There should be no tax rate on the line.",
        )

        self.assertRecordValues(
            invoice,
            [
                {
                    "amount_total": 90.0,
                    "amount_untaxed": 90.0,
                    "amount_tax": 0.0,
                }
            ],
        )
        invoice.action_post()

        if test_exact_response:
            self.assertRecordValues(
                invoice,
                [
                    {
                        "amount_total": 96.54,
                        "amount_untaxed": 90.0,
                        "amount_tax": 6.54,
                    }
                ],
            )

            avatax_mapping = {
                avatax_line["lineNumber"]: avatax_line
                for avatax_line in test_exact_response["lines"]
            }
            for line in invoice.invoice_line_ids:
                line_number = f"account.move.line,{line.id}"
                self.assertIn(line_number, avatax_mapping)
                avatax_line = avatax_mapping[line_number]
                self.assertEqual(
                    line.price_total,
                    avatax_line["tax"] + avatax_line["lineAmount"],
                    f"Tax-included price doesn't match tax returned by Avatax for line {line.id} (product: {line.product_id.display_name}).",
                )
                self.assertEqual(
                    line.price_subtotal,
                    avatax_line["lineAmount"],
                    f"Wrong Avatax amount for {line.id} (product: {line.product_id.display_name}), there is probably a mismatch between the test SO and the mocked response.",
                )

        else:
            for line in invoice.invoice_line_ids:
                product_name = line.product_id.display_name
                self.assertGreater(
                    len(line.tax_ids),
                    0,
                    "Line with %s did not get any taxes set." % product_name,
                )

            self.assertGreater(
                invoice.amount_tax, 0.0, "Invoice has a tax_amount of 0.0."
            )


@tagged("-at_install", "post_install")
class TestAccountAvalaraInternal(TestAccountAvalaraInternalCommon):
    def test_01_odoo_invoice(self):
        invoice, response = self._create_invoice_01_and_expected_response()
        with self._capture_request(return_value=response):
            self.assertInvoice(invoice, test_exact_response=response)

        with patch(
            "odoo.addons.account_avatax.models.mixin_account_external_tax.MixinAccountExternalTax._uncommit_external_taxes"
        ) as mocked_uncommit:
            invoice.action_draft()
            mocked_uncommit.assert_called()

    def test_02_odoo_invoice(self):
        invoice, response = self._create_invoice_02_and_expected_response()
        with self._capture_request(return_value=response):
            self.assertInvoice(invoice, test_exact_response=response)

        with patch(
            "odoo.addons.account_avatax.models.mixin_account_external_tax.MixinAccountExternalTax._uncommit_external_taxes"
        ) as mocked_uncommit:
            invoice.action_draft()
            mocked_uncommit.assert_called()

    def test_03_odoo_invoice(self):
        invoice, response = self._create_invoice_03_and_expected_response()
        self.assertRecordValues(
            invoice,
            [
                {
                    "amount_total": 30.0,
                    "amount_untaxed": 30.0,
                    "amount_tax": 0.0,
                }
            ],
        )

        with self._capture_request(return_value=response):
            invoice.action_post()

        self.assertEqual(
            invoice.amount_total,
            32.7,
            "Wrong total amount, it should be $30.00 + $2.70 of taxes.",
        )

    def test_04_odoo_invoice(self):
        invoice, response = self._create_invoice_03_and_expected_response()
        self.assertRecordValues(
            invoice,
            [
                {
                    "amount_total": 30.0,
                    "amount_untaxed": 30.0,
                    "amount_tax": 0.0,
                }
            ],
        )
        response["summary"] = []
        response["lines"][0]["details"] = []

        with self._capture_request(return_value=response):
            invoice.action_post()

        self.assertEqual(
            invoice.amount_total, 30.0, "Wrong total amount, it should remain $30.00."
        )

    def test_01_odoo_refund(self):
        invoice, response = self._create_invoice_01_and_expected_response()

        with self._capture_request(return_value=response):
            invoice.action_post()

        move_reversal = (
            self.env["wizard.account.move.reverse"]
            .with_context(active_model="account.move", active_ids=invoice.ids)
            .create({"journal_id": invoice.journal_id.id})
        )
        refund = self.env["account.move"].browse(move_reversal.refund_moves()["res_id"])

        lines = [
            refund._prepare_avatax_document_line_service_call(line_data, True)
            for line_data in refund._prepare_line_data_for_external_taxes()
        ]
        for line in lines:
            if "Discount" in line["description"]:
                self.assertGreater(line["amount"], 0)
            else:
                self.assertLess(line["amount"], 0)

    def test_02_odoo_refund(self):
        refund = self.env["account.move"].create(
            {
                "move_type": "out_refund",
                "partner_id": self.partner.id,
                "fiscal_position_id": self.fp_avatax.id,
                "invoice_date": "2024-01-24",
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product_user.id,
                            "tax_ids": None,
                            "price_unit": self.product_user.list_price,
                        },
                    ),
                ],
            }
        )
        response = generate_response_refund_1(refund.invoice_line_ids)
        with self._capture_request(return_value=response):
            refund.button_external_tax_calculation()

        self.assertEqual(
            refund.invoice_line_ids[0].price_subtotal,
            self.product_user.list_price,
            "Subtotal shouldn't have changed on this refund",
        )
        self.assertEqual(
            refund.invoice_line_ids[0].price_total,
            abs(response["lines"][0]["tax"] + response["lines"][0]["lineAmount"]),
            "Total amount should match the absolute value of what Avatax returned (which is negative for refunds)",
        )

    def test_unlink(self):
        invoice, _ = self._create_invoice_01_and_expected_response()

        mock_response = {
            "error": {
                "code": "EntityNotFoundError",
                "details": [
                    {
                        "code": "EntityNotFoundError",
                        "description": "The Document with code 'Journal Entry "
                        "2180' was not found.",
                        "faultCode": "Client",
                        "helpLink": "http://developer.avalara.com/avatax/errors/EntityNotFoundError",
                        "message": "Document not found.",
                        "number": 4,
                        "severity": "Error",
                    }
                ],
                "message": "Document not found.",
                "target": "HttpRequest",
            }
        }

        with self._capture_request(return_value=mock_response) as capture:
            invoice.unlink()

        self.assertEqual(
            capture.val["json"]["code"],
            "DocVoided",
            "Should have tried to void without raising on EntityNotFoundError.",
        )

    def test_journal_entry(self):
        entry, _ = self._create_invoice_01_and_expected_response()
        entry.move_type = "entry"

        with self._capture_request(
            return_value={"lines": [], "summary": []}
        ) as capture:
            entry.action_post()

        self.assertIsNone(capture.val, "Journal entries should not be sent to Avatax.")

    def test_vendor_bill(self):
        vendor_bill = self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "invoice_date": "2017-01-01",
                "partner_id": self.partner.id,
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product_user.id,
                            "price_unit": 123.0,
                            "tax_ids": [],
                        },
                    )
                ],
            }
        )

        with self._capture_request(
            return_value={"lines": [], "summary": []}
        ) as capture:
            vendor_bill.action_post()
            self.assertIsNone(
                capture.val, "Posting a vendor bill should not send anything to Avatax."
            )

            vendor_bill.action_draft()
            self.assertIsNone(
                capture.val,
                "Resetting a vendor bill to draft should not send anything to Avatax.",
            )

            vendor_bill.unlink()
            self.assertIsNone(
                capture.val,
                "Deleting a vendor bill should not send anything to Avatax.",
            )

    def test_invoice_multi_company(self):
        invoice, response = self._create_invoice_01_and_expected_response()

        company_2 = self.setup_other_company()["company"]
        company_2.tax_config_id.account_fiscal_country_id = self.env.ref("base.be")
        self.env.user.company_id = company_2
        with self._capture_request(return_value=response):
            invoice.button_external_tax_calculation()

    def test_invoice_branch_company(self):
        branch = self.env["res.company"].create(
            {
                "name": "Branch A",
                "parent_id": self.env.company.id,
            }
        )
        child_branch = self.env["res.company"].create(
            {
                "name": "Branch B",
                "parent_id": branch.id,
            }
        )
        self.cr.precommit.run()

        invoice = self._create_invoice(post=False, company_id=child_branch.id)

        with self._capture_request(return_value={"lines": [], "summary": []}):
            invoice.button_external_tax_calculation()

        self.env.company.avalara_api_id = False
        with self.assertRaises(
            RedirectWarning, msg="Please add your AvaTax credentials"
        ):
            with self._capture_request(return_value={"lines": [], "summary": []}):
                invoice.button_external_tax_calculation()

        child_branch.write(
            {
                "avalara_api_id": "AVALARA_LOGIN_ID",
                "avalara_api_key": "AVALARA_API_KEY",
                "avalara_environment": "sandbox",
                "avalara_commit": True,
            }
        )
        with self._capture_request(return_value={"lines": [], "summary": []}):
            invoice.button_external_tax_calculation()

    def test_posted_invoice(self):
        invoice, _ = self._create_invoice_01_and_expected_response()

        with self._capture_request(return_value={"lines": [], "summary": []}):
            invoice.action_post()

        with self._capture_request(
            return_value={"lines": [], "summary": []}
        ) as capture:
            invoice.button_external_tax_calculation()

        self.assertIsNone(capture.val, "Should not update taxes of posted invoices.")

    def test_check_address_constraint(self):
        invoice, _ = self._create_invoice_01_and_expected_response()
        partner_no_zip = self.env["res.partner"].create(
            {
                "name": "Test no zip",
                "state_id": self.env.ref("base.state_us_5").id,
                "country_id": self.env.ref("base.us").id,
                "zip": False,
                "property_account_position_id": self.fp_avatax.id,
            }
        )

        with self.assertRaises(ValidationError):
            invoice.partner_id = partner_no_zip

    def test_negative_quantities(self):
        base_line = defaultdict(lambda: False)
        base_line["product_id"] = self.product_accounting
        base_line["quantity"] = -1
        base_line["record"] = self.env["account.move.line"]
        base_line["tax_details"] = defaultdict(lambda: False)

        line_data = defaultdict(lambda: False)
        line_data["base_line"] = base_line
        res = self.env[
            "mixin.account.external.tax"
        ]._prepare_avatax_document_line_service_call(line_data, False)
        self.assertEqual(
            res["quantity"], 1, "Quantities sent to Avatax should always be positive."
        )

    def test_multi_currency_exempted_tax(self):
        currency = self.setup_other_currency("EUR")
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner.id,
                "fiscal_position_id": self.fp_avatax.id,
                "currency_id": currency.id,
                "invoice_date": "2021-01-01",
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product_user.id,
                            "tax_ids": None,
                            "price_unit": 100.00,
                        },
                    ),
                ],
            }
        )
        lines = [
            {
                "details": [
                    {
                        "jurisCode": "06",
                        "nonTaxableAmount": 0.0,
                        "rate": 0.04,
                        "taxableAmount": 100.0,
                        "taxName": "CA STATE TAX",
                        "tax": 4.0,
                    },
                    {
                        "jurisCode": "075",
                        "nonTaxableAmount": 100.0,
                        "rate": 0.06,
                        "taxableAmount": 0.0,
                        "taxName": "CA COUNTY TAX",
                        "tax": 0.0,
                    },
                ],
                "lineAmount": 100.0,
                "lineNumber": "account.move.line," + str(invoice.invoice_line_ids.id),
                "tax": 4.0,
            }
        ]
        summary = [
            {
                "jurisCode": "06",
                "nonTaxable": 0.0,
                "rate": 0.04,
                "tax": 4.0,
                "taxCalculated": 4.0,
                "taxName": "CA STATE TAX",
                "taxable": 100.0,
            },
            {
                "country": "US",
                "jurisCode": "075",
                "nonTaxable": 100.0,
                "rate": 0.06,
                "tax": 0.0,
                "taxCalculated": 0.0,
                "taxName": "CA COUNTY TAX",
                "taxable": 0.0,
            },
        ]
        with self._capture_request(return_value={"lines": lines, "summary": summary}):
            invoice.action_post()
        self.assertRecordValues(
            invoice,
            [{"amount_tax": 4.0, "amount_total": 104.0, "amount_untaxed": 100.0}],
        )
        tax_line = invoice.line_ids.filtered(
            lambda l: l.tax_line_id.name == "CA STATE 4%"
        )
        self.assertRecordValues(
            tax_line,
            [{"amount_currency": -4.0, "balance": -2.0, "debit": 0.0, "credit": 2.0}],
        )
        exempted_tax_line = invoice.line_ids.filtered(
            lambda l: l.tax_line_id.name == "CA COUNTY 6%"
        )
        self.assertRecordValues(
            exempted_tax_line,
            [{"amount_currency": 0.0, "balance": 0.0, "debit": 0.0, "credit": 0.0}],
        )

    def test_invoice_multi_taxline(self):
        self.env["account.fiscal.position"].search([("is_avatax", "=", True)]).write(
            {
                "avatax_invoice_account_id": False,
                "avatax_refund_account_id": False,
            }
        )

        default_plan = self.env["account.analytic.plan"].create({"name": "Default"})
        analytic_account_a = self.env["account.analytic.account"].create(
            {
                "name": "analytic_account_a",
                "plan_id": default_plan.id,
                "company_id": False,
            }
        )
        analytic_account_b = self.env["account.analytic.account"].create(
            {
                "name": "analytic_account_b",
                "plan_id": default_plan.id,
                "company_id": False,
            }
        )
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner.id,
                "fiscal_position_id": self.fp_avatax.id,
                "invoice_date": "2021-01-01",
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_accounting.id,
                            "tax_ids": None,
                            "price_unit": 295.00,
                            "analytic_distribution": {
                                analytic_account_a.id: 100,
                            },
                        }
                    ),
                    Command.create(
                        {
                            "product_id": self.product_accounting.id,
                            "tax_ids": None,
                            "price_unit": 295.00,
                            "analytic_distribution": {
                                analytic_account_b.id: 100,
                            },
                        }
                    ),
                ],
            }
        )
        response = {
            "lines": [
                {
                    "details": [
                        {
                            "jurisCode": "06",
                            "rate": 0.06,
                            "taxName": "CA STATE TAX",
                            "tax": 17.7,
                        },
                        {
                            "jurisCode": "075",
                            "rate": 0.0025,
                            "taxName": "CA COUNTY TAX",
                            "tax": 0.74,
                        },
                        {
                            "jurisCode": "EMAK0",
                            "rate": 0.03,
                            "taxName": "CA SPECIAL TAX",
                            "tax": 8.85,
                        },
                        {
                            "jurisCode": "EMTV0",
                            "rate": 0.01,
                            "taxName": "CA SPECIAL TAX",
                            "tax": 2.95,
                        },
                    ],
                    "lineAmount": 295.0,
                    "lineNumber": "account.move.line," + str(line.id),
                    "tax": 30.24,
                }
                for line in invoice.invoice_line_ids
            ],
            "summary": [
                {
                    "jurisCode": "06",
                    "nonTaxable": 0.0,
                    "rate": 0.06,
                    "tax": 35.4,
                    "taxCalculated": 35.4,
                    "taxName": "CA STATE TAX",
                    "taxable": 590.0,
                },
                {
                    "jurisCode": "075",
                    "nonTaxable": 0.0,
                    "rate": 0.0025,
                    "tax": 1.48,
                    "taxCalculated": 1.48,
                    "taxName": "CA COUNTY TAX",
                    "taxable": 590.0,
                },
            ],
        }

        with self._capture_request(return_value=response):
            invoice.button_external_tax_calculation()
        tax_lines = invoice.line_ids.filtered(
            lambda l: l.tax_line_id.name == "CA STATE 6%"
        )
        self.assertEqual(
            len(tax_lines), 2, "Multiple tax lines should have been created"
        )
        self.assertRecordValues(
            invoice,
            [{"amount_tax": 60.48, "amount_total": 650.48, "amount_untaxed": 590.0}],
        )
        self.assertRecordValues(
            tax_lines, [{"amount_currency": -17.7}, {"amount_currency": -17.7}]
        )

    def test_fully_discounted_invoice(self):
        invoice = self.env["account.move"].create(
            [
                {
                    "move_type": "out_invoice",
                    "partner_id": self.partner.id,
                    "fiscal_position_id": self.fp_avatax.id,
                    "invoice_date": "2021-01-01",
                    "invoice_line_ids": [
                        Command.create(
                            {
                                "product_id": self.product_accounting.id,
                                "tax_ids": None,
                                "price_unit": 295.00,
                            }
                        ),
                        Command.create(
                            {
                                "product_id": self.product_user_discound.id,
                                "tax_ids": None,
                                "price_unit": -295.00,
                            }
                        ),
                    ],
                }
            ]
        )
        self.assertEqual(
            invoice.amount_total, 0.00, "Invoice should be $0 before tax calculation."
        )

        response = {
            "lines": [
                {
                    "details": [
                        {
                            "jurisCode": "06",
                            "rate": 0.06,
                            "tax": 17.7,
                            "taxName": "CA STATE TAX",
                        },
                        {
                            "jurisCode": "075",
                            "rate": 0.0025,
                            "tax": 0.74,
                            "taxName": "CA COUNTY TAX",
                        },
                        {
                            "jurisCode": "EMAK0",
                            "rate": 0.03,
                            "tax": 8.85,
                            "taxName": "CA SPECIAL TAX",
                        },
                        {
                            "jurisCode": "EMTV0",
                            "rate": 0.01,
                            "tax": 2.95,
                            "taxName": "CA SPECIAL TAX",
                        },
                    ],
                    "lineAmount": 295.0,
                    "lineNumber": f"account.move.line,{invoice.invoice_line_ids[0].id}",
                    "tax": 30.24,
                },
                {
                    "details": [
                        {
                            "jurisCode": "06",
                            "rate": 0.06,
                            "tax": 0.00,
                            "taxName": "CA STATE TAX",
                        },
                        {
                            "jurisCode": "075",
                            "rate": 0.0025,
                            "tax": 0.00,
                            "taxName": "CA COUNTY TAX",
                        },
                        {
                            "jurisCode": "EMAK0",
                            "rate": 0.03,
                            "tax": 0.00,
                            "taxName": "CA SPECIAL TAX",
                        },
                        {
                            "jurisCode": "EMTV0",
                            "rate": 0.01,
                            "tax": 0.00,
                            "taxName": "CA SPECIAL TAX",
                        },
                    ],
                    "lineAmount": -295.0,
                    "lineNumber": f"account.move.line,{invoice.invoice_line_ids[1].id}",
                    "tax": 0.00,
                },
            ],
            "summary": [
                {
                    "jurisCode": "06",
                    "rate": 0.06,
                    "tax": 17.7,
                    "taxName": "CA STATE TAX",
                    "taxable": 295.0,
                },
                {
                    "jurisCode": "075",
                    "rate": 0.0025,
                    "tax": 0.74,
                    "taxName": "CA COUNTY TAX",
                    "taxable": 295.0,
                },
                {
                    "jurisCode": "EMAK0",
                    "rate": 0.03,
                    "tax": 8.85,
                    "taxName": "CA SPECIAL TAX",
                    "taxable": 295.0,
                },
                {
                    "jurisCode": "EMAK0",
                    "rate": 0.01,
                    "tax": 2.95,
                    "taxName": "CA SPECIAL TAX",
                    "taxable": 295.0,
                },
            ],
        }

        with self._capture_request(return_value=response):
            invoice.button_external_tax_calculation()

        self.assertRecordValues(
            invoice.line_ids.sorted("balance"),
            [
                {"name": "Accounting", "balance": -295.00},
                {"name": "CA STATE 6%", "balance": -17.7},
                {"name": "CA SPECIAL 3%", "balance": -8.85},
                {"name": "CA SPECIAL 1%", "balance": -2.95},
                {"name": "CA COUNTY 0.25%", "balance": -0.74},
                {
                    "name": False,
                    "balance": sum(t["tax"] for t in response["summary"]),
                },
                {
                    "name": "Odoo User Initial Discount",
                    "balance": 295.00,
                },
            ],
        )


@tagged("external_l10n", "external", "-at_install", "post_install", "-standard")
class TestAccountAvalaraInternalIntegration(TestAccountAvalaraInternalCommon):
    def test_integration_01_odoo_invoice(self):
        with self._skip_no_credentials():
            invoice, _ = self._create_invoice_01_and_expected_response()
            self.assertInvoice(invoice, test_exact_response=False)
            invoice.action_draft()

    def test_integration_02_odoo_invoice(self):
        with self._skip_no_credentials():
            invoice, _ = self._create_invoice_02_and_expected_response()
            self.assertInvoice(invoice, test_exact_response=False)
            invoice.action_draft()


@tagged("-at_install", "post_install")
class TestAccountAvalaraSalesTaxAdministration(TestAccountAvataxCommon):
    """https://developer.avalara.com/certification/avatax/sales-tax-badge/"""

    @classmethod
    def setUpClass(cls):
        res = super().setUpClass()
        cls.config = cls.env["res.config.settings"].create({})
        return res

    def test_disable_document_recording(self):
        self.env.company.avalara_commit = False
        invoice, response = self._create_invoice_01_and_expected_response()
        with self._capture_request(return_value=response) as capture:
            invoice.action_post()

        self.assertFalse(
            capture.val["json"]["createTransactionModel"]["commit"],
            "Should not have committed.",
        )

    def test_disable_avatax(self):
        self.fp_avatax.is_avatax = False
        with patch(
            "odoo.addons.account_avatax.lib.avatax_client.AvataxClient.request"
        ) as mocked_request:
            self._create_invoice()
            mocked_request.assert_not_called()

    def test_disable_avatax_neutralize(self):
        self.cr.execute(next(get_neutralization_queries(["account_avatax"])))
        with patch(
            "odoo.addons.account_avatax.lib.avatax_client.AvataxClient.request"
        ) as mocked_request:
            self._create_invoice()
            mocked_request.assert_not_called()

    def test_integration_connect_button(self):
        with (
            self._skip_no_credentials(),
            self.assertRaisesRegex(UserError, "'version'"),
        ):
            self.config.avatax_ping()
