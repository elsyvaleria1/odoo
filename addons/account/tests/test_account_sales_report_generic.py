# pylint: disable=C0326

from freezegun import freeze_time

from odoo import Command
from odoo.tests import tagged
from odoo.tools.misc import NON_BREAKING_SPACE

from odoo.addons.account.tests.account_sales_report_common import (
    AccountSalesReportCommon,
)


@tagged("post_install", "-at_install")
class AccountSalesReportTest(AccountSalesReportCommon):
    @classmethod
    def collect_company_accounting_data(cls, company):
        res = super().collect_company_accounting_data(company)
        res["company"].update(
            {
                "country_id": cls.env.ref("base.us").id,
                "vat": "US123456789047",
                #  Country outside of EU to avoid local reports being chosen over this one (wanted behaviour)
            }
        )
        return res

    @freeze_time("2019-12-31")
    def test_ec_sales_report(self):
        l_tax = self.env["account.tax"].create(
            {
                "name": "goods",
                "amount_type": "percent",
                "amount": 0,
                "type_tax_use": "sale",
                "price_include_override": "tax_excluded",
                "include_base_amount": False,
            }
        )
        t_tax = self.env["account.tax"].create(
            {
                "name": "triangular",
                "amount_type": "percent",
                "amount": 0,
                "type_tax_use": "purchase",
                "price_include_override": "tax_excluded",
                "include_base_amount": False,
            }
        )
        s_tax = self.env["account.tax"].create(
            {
                "name": "services",
                "amount_type": "percent",
                "amount": 0,
                "type_tax_use": "sale",
                "price_include_override": "tax_excluded",
                "include_base_amount": False,
            }
        )
        bad_tax_1 = self.env["account.tax"].create(
            {
                "name": "bad_1",
                "amount_type": "fixed",
                "amount": 0,
                "type_tax_use": "sale",
                "price_include_override": "tax_excluded",
                "include_base_amount": False,
            }
        )
        bad_tax_2 = self.env["account.tax"].create(
            {
                "name": "bad_2",
                "amount_type": "percent",
                "amount": 10,
                "type_tax_use": "sale",
                "price_include_override": "tax_excluded",
                "include_base_amount": False,
            }
        )
        self._create_invoices(
            [
                (self.partner_a, l_tax[:1], 100),
                (self.partner_a, l_tax[:1], 200),
                (
                    self.partner_a,
                    t_tax[:1],
                    300,
                ),  # Should be ignored due to purchase tax
                (
                    self.partner_b,
                    t_tax[:1],
                    100,
                ),  # Should be ignored due to purchase tax
                (self.partner_a, s_tax[:1], 400),
                (self.partner_b, s_tax[:1], 500),
                (
                    self.partner_b,
                    bad_tax_1[:1],
                    700,
                ),  # Should be ignored due to fixed amount
                (
                    self.partner_b,
                    bad_tax_2[:1],
                    700,
                ),  # Should be ignored due to non-null amount
            ]
        )
        report = self.env.ref("account.generic_ec_sales_report")
        options = self._generate_options(report, "2019-12-01", "2019-12-31")

        self.assertLinesValues(
            report._get_lines(options),
            # pylint: disable=C0326
            #   Partner,                country code,             VAT Number,               Amount
            [0, 1, 2, 3],
            [
                (
                    self.partner_a.name,
                    self.partner_a.vat[:2],
                    self.partner_a.vat[2:],
                    f"${NON_BREAKING_SPACE}700.00",
                ),
                (
                    self.partner_b.name,
                    self.partner_b.vat[:2],
                    self.partner_b.vat[2:],
                    f"${NON_BREAKING_SPACE}500.00",
                ),
                ("Total", "", "", f"${NON_BREAKING_SPACE}1,200.00"),
            ],
            options,
        )

    @freeze_time("2019-12-31")
    def test_ec_sales_report_includes_every_selected_company(self):
        company_2 = self.company_data_2["company"]
        goods_taxes = self.env["account.tax"].create(
            [
                {
                    "name": "goods",
                    "amount_type": "percent",
                    "amount": 0,
                    "type_tax_use": "sale",
                    "company_ids": [Command.set(company.ids)],
                }
                for company in self.company + company_2
            ]
        )
        self._create_invoices([(self.partner_a, goods_taxes[0], 100)])
        invoice_2 = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "company_id": company_2.id,
                "journal_id": self.company_data_2["default_journal_sale"].id,
                "partner_id": self.partner_b.id,
                "invoice_date": "2019-12-01",
                "currency_id": self.company_data["currency"].id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "line_1",
                            "price_unit": 300.0,
                            "account_id": self.company_data_2[
                                "default_account_revenue"
                            ].id,
                            "tax_ids": [Command.set(goods_taxes[1].ids)],
                        }
                    )
                ],
            }
        )
        invoice_2.action_post()

        report = self.env.ref("account.generic_ec_sales_report").with_context(
            allowed_company_ids=(self.company + company_2).ids
        )
        options = self._generate_options(report, "2019-12-01", "2019-12-31")

        self.assertLessEqual(
            set(goods_taxes.ids), set(options["sales_report_taxes"]["goods"])
        )
        self.assertEqual(
            [line["name"] for line in report._get_lines(options)],
            [self.partner_a.name, self.partner_b.name, "Total"],
        )

    @freeze_time("2019-12-31")
    def test_ec_sales_report_excludes_each_company_own_country(self):
        company_2 = self.company_data_2["company"]
        company_2.tax_config_id.account_fiscal_country_id = self.partner_a.country_id
        goods_taxes = self.env["account.tax"].create(
            [
                {
                    "name": "goods",
                    "amount_type": "percent",
                    "amount": 0,
                    "type_tax_use": "sale",
                    "company_ids": [Command.set(company.ids)],
                    "country_id": company.tax_config_id.account_fiscal_country_id.id,
                    "tax_group_id": self.env["account.tax.group"]
                    .create(
                        {
                            "name": "goods",
                            "company_ids": [Command.set(company.ids)],
                            "country_id": company.tax_config_id.account_fiscal_country_id.id,
                        }
                    )
                    .id,
                }
                for company in self.company + company_2
            ]
        )
        self._create_invoices([(self.partner_b, goods_taxes[0], 100)])
        domestic_invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "company_id": company_2.id,
                "journal_id": self.company_data_2["default_journal_sale"].id,
                "partner_id": self.partner_a.id,
                "invoice_date": "2019-12-01",
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "line_1",
                            "price_unit": 300.0,
                            "account_id": self.company_data_2[
                                "default_account_revenue"
                            ].id,
                            "tax_ids": [Command.set(goods_taxes[1].ids)],
                        }
                    )
                ],
            }
        )
        domestic_invoice.action_post()

        report = self.env.ref("account.generic_ec_sales_report").with_context(
            allowed_company_ids=(self.company + company_2).ids
        )
        options = self._generate_options(report, "2019-12-01", "2019-12-31")

        self.assertEqual(
            [line["name"] for line in report._get_lines(options)],
            [self.partner_b.name, "Total"],
        )

    @freeze_time("2019-12-31")
    def test_ec_sales_report_with_northern_irish_customer(self):
        """
        Ensure that partners located in Northern Ireland are included in the EC sales report.
        """
        northern_ireland = self.env.ref("base.xi", raise_if_not_found=False)

        if not northern_ireland:
            self.skipTest("`account_intrastat` module not installed")

        self.partner_a.write(
            {
                "country_id": northern_ireland.id,
                "vat": "IE1234567FA",
            }
        )
        self.tax_sale_a.amount = 0

        self._create_invoices(
            [
                (self.partner_a, self.tax_sale_a, 100),
            ]
        )
        report = self.env.ref("account.generic_ec_sales_report")
        options = self._generate_options(report, "2019-12-01", "2019-12-31")

        self.assertLinesValues(
            report._get_lines(options),
            #   Partner,                country code,             VAT Number,               Amount
            [0, 1, 2, 3],
            [
                (
                    self.partner_a.name,
                    self.partner_a.vat[:2],
                    self.partner_a.vat[2:],
                    f"${NON_BREAKING_SPACE}100.00",
                ),
                ("Total", "", "", f"${NON_BREAKING_SPACE}100.00"),
            ],
            options,
        )

    def test_ec_sales_set_as_main(self):
        """Test setting a partner as the main in EC Sales Report when two partners share the same VAT.

        Scenario:
        - Two partners have the same VAT.
        - Set one partner as the main partner.
        - Validate that the second partner is linked correctly as a child and that moves are updated.
        """
        # Prepare partners
        partner_main = self.partner_a
        partner_duplicate = self.partner_b
        partner_duplicate.vat = partner_main.vat

        move_vals = {
            "move_type": "out_invoice",
            "invoice_date": "2025-04-29",
            "invoice_line_ids": [
                Command.create(
                    {
                        "quantity": 1,
                        "price_unit": 500.0,
                        "tax_ids": [],
                    }
                )
            ],
        }
        # Create and post invoice for the main partner
        move_main = self.env["account.move"].create(
            {**move_vals, "partner_id": partner_main.id}
        )
        move_main.action_post()
        # Create and post invoice for the duplicate partner
        move_duplicate = self.env["account.move"].create(
            {**move_vals, "partner_id": partner_duplicate.id}
        )
        move_duplicate.action_post()

        # Call with context
        partner_main.with_context(
            duplicated_partners_vat=[partner_main.vat, partner_duplicate.vat]
        ).set_commercial_partner_main()

        # Assertions: partner relationships
        self.assertEqual(
            partner_duplicate.commercial_partner_id,
            partner_main,
            "Duplicate partner's commercial partner should be the main partner.",
        )
        self.assertEqual(
            partner_duplicate.parent_id,
            partner_main,
            "Duplicate partner's parent should be set to the main partner.",
        )

        # Assertions: accounting move reassignment
        self.assertEqual(
            move_duplicate.commercial_partner_id,
            partner_main,
            "The move's commercial partner should also be reassigned.",
        )

        # Assertions: journal items (move lines)
        self.assertEqual(
            move_duplicate.line_ids.partner_id,
            partner_main,
            "Each move line should now be assigned to the main partner.",
        )
