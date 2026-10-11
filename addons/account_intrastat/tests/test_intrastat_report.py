from freezegun import freeze_time

from odoo import Command, fields
from odoo.tests import tagged

from odoo.addons.account.tests.common_report_engine import TestAccountReportsCommon


@tagged("post_install", "-at_install")
class TestIntrastatReport(TestAccountReportsCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        country = cls.env["res.country"].create(
            {
                "name": "Squamuglia",
                "code": "SQ",
            }
        )
        intrastat_country_group = cls.env.ref("account.intrastat")
        intrastat_country_group.country_ids |= country
        cls.company_data["company"].country_id = country
        cls.company_data["company"].currency_id = cls.env.ref("base.EUR").id
        cls.company_data["currency"] = cls.env.ref("base.EUR")
        cls.report = cls.env.ref("account_intrastat.intrastat_report")
        cls.env.company.account_config_id.totals_below_sections = False
        cls.partner_a = cls.env["res.partner"].create(
            {"name": "Yoyodyne BE", "country_id": cls.env.ref("base.be").id}
        )

        cls.product_no_supplementary_unit = cls.env["product.product"].create(
            {
                "name": "stamp collection",
                "intrastat_code_id": cls.env.ref(
                    "account_intrastat.commodity_code_2018_97040000"
                ).id,
                "intrastat_supplementary_unit_amount": None,
            }
        )
        cls.product_unit_supplementary_unit = cls.env["product.product"].create(
            {
                "name": "rocket",
                "intrastat_code_id": cls.env.ref(
                    "account_intrastat.commodity_code_2018_93012000"
                ).id,
                "intrastat_supplementary_unit_amount": 1,
            }
        )
        cls.product_100_unit_supplementary_unit = cls.env["product.product"].create(
            {
                "name": "Imipolex G Tooth",
                "intrastat_code_id": cls.env.ref(
                    "account_intrastat.commodity_code_2018_90212110"
                ).id,
                "intrastat_supplementary_unit_amount": 0.01,
            }
        )
        cls.product_metre_supplementary_unit = cls.env["product.product"].create(
            {
                "name": "Proper Gander Film",
                "intrastat_code_id": cls.env.ref(
                    "account_intrastat.commodity_code_2018_37061020"
                ).id,
                "intrastat_supplementary_unit_amount": 1,
                "uom_id": cls.env.ref("base.product_uom_meter").id,
            }
        )
        cls.spanish_rioja = cls.env["product.product"].create(
            {
                "name": "rioja",
                "intrastat_code_id": cls.env.ref(
                    "account_intrastat.commodity_code_2018_22042176"
                ).id,
                "intrastat_origin_country_id": cls.env.ref("base.es").id,
            }
        )

        code_vals = [
            {"type": type, "name": f"{type}"}
            for type in ("commodity", "transaction", "region")
        ]
        cls.intrastat_codes = {}
        create_vals_list = []
        for i, vals in enumerate(code_vals, 100):
            vals["code"] = str(i)
            create_vals_list.append(vals)
        cls.intrastat_codes = {
            x.name: x
            for x in cls.env["account.intrastat.code"].sudo().create(create_vals_list)
        }

        cls.company_data["company"].intrastat_region_id = cls.intrastat_codes[
            "region"
        ].id

        cls.product_1 = cls.env["product.product"].create(
            {
                "name": "product_a",
                "uom_id": cls.env.ref("base.product_uom_unit").id,
                "lst_price": 100.0,
                "standard_price": 80.0,
                "property_account_income_id": cls.company_data[
                    "default_account_revenue"
                ].id,
                "property_account_expense_id": cls.company_data[
                    "default_account_expense"
                ].id,
                "taxes_id": [Command.set(cls.tax_sale_a.ids)],
                "supplier_taxes_id": [Command.set(cls.tax_purchase_a.ids)],
                "intrastat_code_id": cls.intrastat_codes["commodity"].id,
                "weight": 0.3,
            }
        )

        cls.product_2 = cls.env["product.product"].create(
            {
                "name": "product_2",
                "uom_id": cls.env.ref("base.product_uom_unit").id,
                "lst_price": 150.0,
                "standard_price": 120.0,
                "property_account_income_id": cls.company_data[
                    "default_account_revenue"
                ].id,
                "property_account_expense_id": cls.company_data[
                    "default_account_expense"
                ].id,
                "taxes_id": [Command.set(cls.tax_sale_a.ids)],
                "supplier_taxes_id": [Command.set(cls.tax_purchase_a.ids)],
                "intrastat_code_id": cls.intrastat_codes["commodity"].id,
                "weight": 0.6,
            }
        )

        cls.product_3 = cls.env["product.product"].create(
            {
                "name": "product_3",
                "uom_id": cls.env.ref("base.product_uom_unit").id,
                "lst_price": 1000.0,
                "standard_price": 950.0,
                "property_account_income_id": cls.company_data[
                    "default_account_revenue"
                ].id,
                "property_account_expense_id": cls.company_data[
                    "default_account_expense"
                ].id,
                "taxes_id": [Command.set(cls.tax_sale_a.ids)],
                "supplier_taxes_id": [Command.set(cls.tax_purchase_a.ids)],
                "intrastat_code_id": cls.intrastat_codes["commodity"].id,
                "weight": 0.5,
            }
        )

    @classmethod
    def _create_invoices(cls, code_type=None):
        moves = cls.env["account.move"].create(
            [
                {
                    "move_type": "out_invoice",
                    "partner_id": cls.partner_a.id,
                    "invoice_date": "2022-01-01",
                    "intrastat_country_id": cls.env.ref("base.nl").id,
                    "invoice_line_ids": [
                        Command.create(
                            {
                                "name": "line_1",
                                "product_id": cls.product_1.id,
                                "intrastat_transaction_id": cls.intrastat_codes[
                                    code_type
                                ].id
                                if code_type
                                else None,
                                "product_uom_id": cls.env.ref(
                                    "base.product_uom_unit"
                                ).id,
                                "quantity": 1.0,
                                "account_id": cls.company_data[
                                    "default_account_revenue"
                                ].id,
                                "price_unit": 80.0,
                                "tax_ids": [],
                            }
                        ),
                        Command.create(
                            {
                                "name": "line_2",
                                "product_id": cls.product_2.id,
                                "intrastat_transaction_id": cls.intrastat_codes[
                                    code_type
                                ].id
                                if code_type
                                else None,
                                "product_uom_id": cls.env.ref(
                                    "base.product_uom_unit"
                                ).id,
                                "quantity": 2.0,
                                "account_id": cls.company_data[
                                    "default_account_revenue"
                                ].id,
                                "price_unit": 120.0,
                                "tax_ids": [],
                            }
                        ),
                    ],
                },
                {
                    "move_type": "in_invoice",
                    "partner_id": cls.partner_a.id,
                    "invoice_date": "2022-01-01",
                    "intrastat_country_id": cls.env.ref("base.nl").id,
                    "invoice_line_ids": [
                        Command.create(
                            {
                                "name": "line_3",
                                "product_id": cls.product_3.id,
                                "intrastat_transaction_id": cls.intrastat_codes[
                                    code_type
                                ].id
                                if code_type
                                else None,
                                "product_uom_id": cls.env.ref(
                                    "base.product_uom_unit"
                                ).id,
                                "quantity": 1.0,
                                "account_id": cls.company_data[
                                    "default_account_expense"
                                ].id,
                                "price_unit": 950.0,
                                "tax_ids": [],
                            }
                        ),
                    ],
                },
            ]
        )
        moves.action_post()

    @freeze_time("2022-02-01")
    def test_intrastat_report_values(self):
        self._create_invoices(code_type="transaction")
        options = self._generate_options(self.report, "2022-01-01", "2022-01-31")
        lines = self.report._get_lines(options)
        self.assertLinesValues(
            lines,
            [1, 2, 3, 4, 5, 6, 10, 12],
            [
                ("", "", "", "", "", "", "", 1270.0),
                (
                    "29 (Arrival)",
                    "Netherlands",
                    "101",
                    "102",
                    "100",
                    "QV",
                    "0.5",
                    950.0,
                ),
                (
                    "19 (Dispatch)",
                    "Netherlands",
                    "101",
                    "102",
                    "100",
                    "QV",
                    "1.5",
                    320.0,
                ),
            ],
            options,
        )
        options["intrastat_type"][1]["selected"] = True
        options = self._generate_options(
            self.report, "2022-01-01", "2022-01-31", options
        )
        lines = self.report._get_lines(options)
        self.assertLinesValues(
            lines,
            [0, 1, 12],
            [
                ("Intrastat", "", 320.0),
                ("Dispatch - QV999999999999 - 100 - NL", "19 (Dispatch)", 320.0),
            ],
            options,
        )

    def test_unfold_intrastat_report_lines(self):
        partner_be, partner_no_vat = self.env["res.partner"].create(
            [
                {
                    "name": "BE Partner",
                    "country_id": self.env.ref("base.be").id,
                    "vat": "BE0477472701",
                },
                {
                    "name": "FR No VAT Partner",
                    "country_id": self.env.ref("base.fr").id,
                    "vat": None,
                },
            ]
        )
        moves = self.env["account.move"].create(
            [
                {
                    "move_type": "out_invoice",
                    "partner_id": partner_be.id,
                    "invoice_date": "2022-01-01",
                    "date": "2022-01-01",
                    "intrastat_country_id": self.env.ref("base.be").id,
                    "invoice_line_ids": [
                        Command.create(
                            {
                                "name": "line_1",
                                "product_id": self.spanish_rioja.id,
                                "intrastat_transaction_id": None,
                                "product_uom_id": self.env.ref(
                                    "base.product_uom_unit"
                                ).id,
                                "quantity": 1.0,
                                "account_id": self.company_data[
                                    "default_account_revenue"
                                ].id,
                                "price_unit": 80.0,
                                "tax_ids": [],
                            }
                        ),
                    ],
                },
                {
                    "move_type": "out_invoice",
                    "partner_id": partner_be.id,
                    "invoice_date": "2022-01-02",
                    "date": "2022-01-02",
                    "intrastat_country_id": self.env.ref("base.be").id,
                    "invoice_line_ids": [
                        Command.create(
                            {
                                "name": "line_1",
                                "product_id": self.spanish_rioja.id,
                                "intrastat_transaction_id": None,
                                "product_uom_id": self.env.ref(
                                    "base.product_uom_unit"
                                ).id,
                                "quantity": 1.0,
                                "account_id": self.company_data[
                                    "default_account_revenue"
                                ].id,
                                "price_unit": 80.0,
                                "tax_ids": [],
                            }
                        ),
                    ],
                },
                {
                    "move_type": "out_invoice",
                    "partner_id": partner_no_vat.id,
                    "invoice_date": "2022-01-03",
                    "date": "2022-01-03",
                    "intrastat_country_id": self.env.ref("base.fr").id,
                    "invoice_line_ids": [
                        Command.create(
                            {
                                "name": "line_1",
                                "product_id": self.product_1.id,
                                "intrastat_transaction_id": self.intrastat_codes[
                                    "transaction"
                                ].id,
                                "product_uom_id": self.env.ref(
                                    "base.product_uom_unit"
                                ).id,
                                "quantity": 1.0,
                                "account_id": self.company_data[
                                    "default_account_revenue"
                                ].id,
                                "price_unit": 50.0,
                                "tax_ids": [],
                            }
                        ),
                    ],
                },
            ]
        )
        moves.action_post()

        options = self._generate_options(
            self.report,
            "2022-01-01",
            "2022-01-31",
            default_options={"unfold_all": True},
        )
        lines = self.report._get_lines(options)
        self.assertLinesValues(
            lines,
            [0, 1, 2, 3, 4, 5, 6, 12],
            [
                ("Intrastat", "", "", "", "", "", "", 210.0),
                (
                    "Dispatch - BE0477472701 - 22042176 - BE",
                    "19 (Dispatch)",
                    "Belgium",
                    "",
                    "102",
                    "22042176",
                    "ES",
                    160.0,
                ),
                (
                    "INV/2022/00002",
                    "19 (Dispatch)",
                    "Belgium",
                    "",
                    "102",
                    "22042176",
                    "ES",
                    80.0,
                ),
                (
                    "INV/2022/00001",
                    "19 (Dispatch)",
                    "Belgium",
                    "",
                    "102",
                    "22042176",
                    "ES",
                    80.0,
                ),
                (
                    "Dispatch - QV999999999999 - 100 - FR",
                    "19 (Dispatch)",
                    "France",
                    "101",
                    "102",
                    "100",
                    "QV",
                    50.0,
                ),
                (
                    "INV/2022/00003",
                    "19 (Dispatch)",
                    "France",
                    "101",
                    "102",
                    "100",
                    "QV",
                    50.0,
                ),
            ],
            options,
        )

    def test_unfold_with_product_origin_country_united_kingdom(self):
        move = self.env["account.move"].create(
            [
                {
                    "move_type": "out_invoice",
                    "partner_id": self.partner_a.id,
                    "invoice_date": "2022-01-04",
                    "date": "2022-01-04",
                    "intrastat_country_id": self.env.ref("base.fr").id,
                    "invoice_line_ids": [
                        Command.create(
                            {
                                "name": "line_1",
                                "product_id": self.product_1.id,
                                "intrastat_transaction_id": self.intrastat_codes[
                                    "transaction"
                                ].id,
                                "intrastat_product_origin_country_id": self.env.ref(
                                    "base.uk"
                                ).id,
                                "quantity": 1.0,
                                "account_id": self.company_data[
                                    "default_account_revenue"
                                ].id,
                                "price_unit": 50.0,
                            }
                        ),
                    ],
                },
                {
                    "move_type": "out_invoice",
                    "partner_id": self.partner_a.id,
                    "invoice_date": "2022-01-05",
                    "date": "2022-01-05",
                    "intrastat_country_id": self.env.ref("base.fr").id,
                    "invoice_line_ids": [
                        Command.create(
                            {
                                "name": "line_1",
                                "product_id": self.product_1.id,
                                "intrastat_transaction_id": self.intrastat_codes[
                                    "transaction"
                                ].id,
                                "intrastat_product_origin_country_id": self.env.ref(
                                    "base.uk"
                                ).id,
                                "quantity": 1.0,
                                "account_id": self.company_data[
                                    "default_account_revenue"
                                ].id,
                                "price_unit": 50.0,
                            }
                        ),
                    ],
                },
            ]
        )
        move.action_post()

        options = self._generate_options(
            self.report,
            "2022-01-01",
            "2022-01-31",
            default_options={"unfold_all": True},
        )
        self.assertLinesValues(
            self.report._get_lines(options),
            [0, 2, 6, 12],
            [
                ("Intrastat", "", "", 100.0),
                ("Dispatch - QV999999999999 - 100 - FR", "France", "XU", 100.0),
                ("INV/2022/00002", "France", "XU", 50.0),
                ("INV/2022/00001", "France", "XU", 50.0),
            ],
            options,
        )

    def test_unfold_dispatch_arrival_intrastrat_report_lines(self):
        self._create_invoices("transaction")
        options = self._generate_options(
            self.report,
            "2022-01-01",
            "2022-01-31",
            default_options={"unfold_all": True},
        )

        self.assertLinesValues(
            self.report._get_lines(options),
            [0, 1, 2, 3, 4, 5, 6, 10, 12],
            [
                ("Intrastat", "", "", "", "", "", "", "", 1270.0),
                (
                    "Arrival - QV999999999999 - 100 - NL",
                    "29 (Arrival)",
                    "Netherlands",
                    "101",
                    "102",
                    "100",
                    "QV",
                    "0.5",
                    950.0,
                ),
                (
                    "BILL/2022/01/0001",
                    "29 (Arrival)",
                    "Netherlands",
                    "101",
                    "102",
                    "100",
                    "QV",
                    "0.5",
                    950.0,
                ),
                (
                    "Dispatch - QV999999999999 - 100 - NL",
                    "19 (Dispatch)",
                    "Netherlands",
                    "101",
                    "102",
                    "100",
                    "QV",
                    "1.5",
                    320.0,
                ),
                (
                    "INV/2022/00001",
                    "19 (Dispatch)",
                    "Netherlands",
                    "101",
                    "102",
                    "100",
                    "QV",
                    "0.3",
                    80.0,
                ),
                (
                    "INV/2022/00001",
                    "19 (Dispatch)",
                    "Netherlands",
                    "101",
                    "102",
                    "100",
                    "QV",
                    "1.2",
                    240.0,
                ),
            ],
            options,
        )

    def test_intrastat_report_lines_with_unique_id(self):

        def move_vals(move_values=None, invoice_line_values=None):
            move_values = move_values or {}
            invoice_line_values = invoice_line_values or {}
            return {
                "move_type": "out_invoice",
                "partner_id": self.partner_a.id,
                "invoice_date": "2022-01-01",
                "currency_id": self.env.ref("base.EUR").id,
                **move_values,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": product_with_nothing.id,
                            "account_id": self.company_data[
                                "default_account_revenue"
                            ].id,
                            "price_unit": 20.0,
                            **invoice_line_values,
                        }
                    ),
                ],
            }

        self.env.ref("base.SEK").active = True
        (
            product_with_nothing,
            product_with_commodity_code,
            product_with_origin_country_id,
        ) = self.env["product.product"].create(
            [
                {
                    "name": "A product with nothing",
                    "intrastat_code_id": None,
                    "intrastat_origin_country_id": None,
                },
                {
                    "name": "A product with commodity code",
                    "intrastat_code_id": self.env.ref(
                        "account_intrastat.account_intrastat_transaction_11"
                    ).id,
                    "intrastat_origin_country_id": None,
                },
                {
                    "name": "A product with origine id",
                    "intrastat_code_id": None,
                    "intrastat_origin_country_id": self.env.ref("base.nl").id,
                },
            ]
        )
        partner_vat_be = self.env["res.partner"].create(
            {
                "name": "BE Partner",
                "country_id": self.env.ref("base.be").id,
                "vat": "BE0477472701",
            }
        )
        moves = self.env["account.move"].create(
            [
                move_vals(),
                move_vals(
                    move_values={
                        "invoice_incoterm_id": self.env.ref("incoterm.incoterm_CFR").id
                    },
                    invoice_line_values={"price_unit": 21.0},
                ),
                move_vals(
                    invoice_line_values={
                        "intrastat_transaction_id": self.intrastat_codes[
                            "transaction"
                        ].id,
                        "price_unit": 22.0,
                    }
                ),
                move_vals(
                    move_values={
                        "intrastat_transport_mode_id": self.env.ref(
                            "account_intrastat.account_intrastat_transport_1"
                        ).id
                    },
                    invoice_line_values={"price_unit": 23.0},
                ),
                move_vals(
                    invoice_line_values={
                        "product_id": product_with_commodity_code.id,
                        "price_unit": 24.0,
                    }
                ),
                move_vals(
                    invoice_line_values={
                        "product_id": product_with_origin_country_id.id,
                        "price_unit": 25.0,
                    }
                ),
                move_vals(
                    move_values={"intrastat_country_id": self.env.ref("base.es").id},
                    invoice_line_values={"price_unit": 26.0},
                ),
                move_vals(
                    move_values={"partner_id": partner_vat_be.id},
                    invoice_line_values={"price_unit": 27.0},
                ),
                move_vals(
                    move_values={"currency_id": self.env.ref("base.SEK").id},
                    invoice_line_values={"price_unit": 28.0},
                ),
            ]
        )
        moves.action_post()

        options = self._generate_options(
            self.report,
            "2022-01-01",
            "2022-01-31",
            default_options={"unfold_all": True},
        )
        lines = self.report._get_lines(options)

        existing_ids = [line["id"] for line in lines]
        unique_ids = set(existing_ids)
        self.assertEqual(
            len(existing_ids),
            len(unique_ids),
            f"We should have {len(existing_ids)} different IDs because we don't have exact same lines.",
        )

        self.assertLinesValues(
            lines,
            [0, 12],
            [
                ("Intrastat", 216.0),
                ("Dispatch - QV999999999999 - None - BE", 22.0),
                ("INV/2022/00003", 22.0),
                ("Dispatch - QV999999999999 - None - BE", 23.0),
                ("INV/2022/00004", 23.0),
                ("Dispatch - QV999999999999 - 11 - BE", 24.0),
                ("INV/2022/00005", 24.0),
                ("Dispatch - BE0477472701 - None - BE", 27.0),
                ("INV/2022/00008", 27.0),
                ("Dispatch - QV999999999999 - None - BE", 21.0),
                ("INV/2022/00002", 21.0),
                ("Dispatch - QV999999999999 - None - BE", 25.0),
                ("INV/2022/00006", 25.0),
                ("Dispatch - QV999999999999 - None - BE", 20.0),
                ("INV/2022/00001", 20.0),
                ("Dispatch - QV999999999999 - None - BE", 28.0),
                ("INV/2022/00009", 28.0),
                ("Dispatch - QV999999999999 - None - ES", 26.0),
                ("INV/2022/00007", 26.0),
            ],
            options,
        )

    def test_intrastat_multi_currency(self):
        moves = self.env["account.move"].create(
            [
                {
                    "move_type": "out_invoice",
                    "partner_id": self.partner_a.id,
                    "invoice_date": "2016-04-01",
                    "intrastat_country_id": self.env.ref("base.be").id,
                    "currency_id": self.other_currency.id,
                    "invoice_line_ids": [
                        Command.create(
                            {
                                "product_id": self.spanish_rioja.id,
                                "product_uom_id": self.env.ref(
                                    "base.product_uom_unit"
                                ).id,
                                "quantity": 1.0,
                                "account_id": self.company_data[
                                    "default_account_revenue"
                                ].id,
                                "price_unit": 80.0,
                            }
                        ),
                    ],
                },
                {
                    "move_type": "out_invoice",
                    "partner_id": self.partner_a.id,
                    "invoice_date": "2017-04-01",
                    "intrastat_country_id": self.env.ref("base.be").id,
                    "currency_id": self.other_currency.id,
                    "invoice_line_ids": [
                        Command.create(
                            {
                                "product_id": self.spanish_rioja.id,
                                "product_uom_id": self.env.ref(
                                    "base.product_uom_unit"
                                ).id,
                                "quantity": 1.0,
                                "account_id": self.company_data[
                                    "default_account_revenue"
                                ].id,
                                "price_unit": 80.0,
                            }
                        ),
                    ],
                },
                {
                    "move_type": "out_refund",
                    "partner_id": self.partner_a.id,
                    "invoice_date": "2017-05-01",
                    "intrastat_country_id": self.env.ref("base.be").id,
                    "currency_id": self.other_currency.id,
                    "invoice_line_ids": [
                        Command.create(
                            {
                                "product_id": self.spanish_rioja.id,
                                "product_uom_id": self.env.ref(
                                    "base.product_uom_unit"
                                ).id,
                                "quantity": 1.0,
                                "account_id": self.company_data[
                                    "default_account_revenue"
                                ].id,
                                "price_unit": 80.0,
                            }
                        ),
                    ],
                },
            ]
        )
        moves.action_post()

        options = self._generate_options(
            self.report,
            "2016-01-01",
            "2017-12-31",
            default_options={"unfold_all": True},
        )
        self.assertLinesValues(
            self.report._get_lines(options),
            [0, 12],
            [
                ("Intrastat", 106.67),
                ("Arrival - QV999999999999 - 22042176 - BE", 40.00),
                ("RINV/2017/00001", 40.00),
                ("Dispatch - QV999999999999 - 22042176 - BE", 66.67),
                ("INV/2017/00001", 40.00),
                ("INV/2016/00001", 26.67),
            ],
            options,
        )

    def test_intrastat_report_only_one_line_even_with_different_warnings(self):
        transaction_code = self.intrastat_codes["transaction"]
        transaction_code.expiry_date = fields.Date.from_string("2022-01-14")
        moves = self.env["account.move"].create(
            [
                {
                    "move_type": "out_invoice",
                    "partner_id": self.partner_a.id,
                    "invoice_date": "2022-01-05",
                    "currency_id": self.env.ref("base.EUR").id,
                    "invoice_line_ids": [
                        Command.create(
                            {
                                "product_id": self.spanish_rioja.id,
                                "account_id": self.company_data[
                                    "default_account_revenue"
                                ].id,
                                "price_unit": 20.0,
                                "intrastat_transaction_id": transaction_code.id,
                            }
                        ),
                    ],
                },
                {
                    "move_type": "out_invoice",
                    "partner_id": self.partner_a.id,
                    "invoice_date": "2022-01-15",
                    "currency_id": self.env.ref("base.EUR").id,
                    "invoice_line_ids": [
                        Command.create(
                            {
                                "product_id": self.spanish_rioja.id,
                                "account_id": self.company_data[
                                    "default_account_revenue"
                                ].id,
                                "price_unit": 21.0,
                                "intrastat_transaction_id": transaction_code.id,
                            }
                        ),
                    ],
                },
            ]
        )
        moves.action_post()

        options = self._generate_options(
            self.report,
            "2022-01-01",
            "2022-01-31",
            default_options={"unfold_all": True},
        )
        self.assertLinesValues(
            self.report._get_lines(options),
            [0, 12],
            [
                ("Intrastat", 41.0),
                ("Dispatch - QV999999999999 - 22042176 - BE", 41.0),
                ("INV/2022/00002", 21.0),
                ("INV/2022/00001", 20.0),
            ],
            options,
        )

    def test_intrastat_invoice_having_minus_quantity(self):
        move = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner_a.id,
                "invoice_date": "2022-01-15",
                "intrastat_country_id": self.env.ref("base.be").id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": self.spanish_rioja.id,
                            "product_uom_id": self.env.ref("base.product_uom_unit").id,
                            "quantity": 10.0,
                            "account_id": self.company_data[
                                "default_account_revenue"
                            ].id,
                            "price_unit": 80.0,
                        }
                    ),
                    Command.create(
                        {
                            "product_id": self.spanish_rioja.id,
                            "product_uom_id": self.env.ref("base.product_uom_unit").id,
                            "quantity": -1.0,
                            "account_id": self.company_data[
                                "default_account_revenue"
                            ].id,
                            "price_unit": 80.0,
                        }
                    ),
                ],
            }
        )
        move.action_post()

        options = self._generate_options(
            self.report,
            "2022-01-01",
            "2022-01-31",
            default_options={"unfold_all": True},
        )
        self.assertLinesValues(
            self.report._get_lines(options),
            [0, 12],
            [
                ("Intrastat", 720.0),
                ("Dispatch - QV999999999999 - 22042176 - BE", 720.0),
                ("INV/2022/00001", 800.0),
                ("INV/2022/00001", -80.0),
            ],
            options,
        )

    def test_no_supplementary_units(self):
        no_supplementary_units_invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner_a.id,
                "invoice_date": "2022-05-15",
                "date": "2022-05-15",
                "company_id": self.company_data["company"].id,
                "intrastat_country_id": self.env.ref("base.be").id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_no_supplementary_unit.id,
                            "quantity": 1,
                            "product_uom_id": self.env.ref("base.product_uom_unit").id,
                            "price_unit": 10,
                            "tax_ids": [],
                        }
                    )
                ],
            }
        )
        no_supplementary_units_invoice.action_post()
        options = self._generate_options(
            self.report,
            date_from=fields.Date.from_string("2022-05-01"),
            date_to=fields.Date.from_string("2022-05-31"),
        )
        lines = self.report._get_lines(options)
        self.assertLinesValues(
            lines,
            [0, 1, 2, 5, 11],
            [
                ("Intrastat", "", "", "", ""),
                (
                    "Dispatch - QV999999999999 - 97040000 - BE",
                    "19 (Dispatch)",
                    "Belgium",
                    "97040000",
                    "",
                ),
            ],
            options,
        )

    def test_unitary_supplementary_units(self):
        unitary_supplementary_units_invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner_a.id,
                "invoice_date": "2022-05-15",
                "date": "2022-05-15",
                "company_id": self.company_data["company"].id,
                "intrastat_country_id": self.env.ref("base.be").id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_unit_supplementary_unit.id,
                            "quantity": 123,
                            "product_uom_id": self.env.ref("base.product_uom_unit").id,
                            "price_unit": 10,
                            "tax_ids": [],
                        }
                    ),
                    Command.create(
                        {
                            "product_id": self.product_unit_supplementary_unit.id,
                            "quantity": 20,
                            "product_uom_id": self.env.ref("base.product_uom_dozen").id,
                            "price_unit": 10,
                            "tax_ids": [],
                        }
                    ),
                    Command.create(
                        {
                            "product_id": self.product_100_unit_supplementary_unit.id,
                            "quantity": 123,
                            "product_uom_id": self.env.ref("base.product_uom_unit").id,
                            "price_unit": 10,
                            "tax_ids": [],
                        }
                    ),
                    Command.create(
                        {
                            "product_id": self.product_100_unit_supplementary_unit.id,
                            "quantity": 20,
                            "product_uom_id": self.env.ref("base.product_uom_dozen").id,
                            "price_unit": 10,
                            "tax_ids": [],
                        }
                    ),
                ],
            }
        )
        unitary_supplementary_units_invoice.action_post()
        options = self._generate_options(
            self.report,
            date_from=fields.Date.from_string("2022-05-01"),
            date_to=fields.Date.from_string("2022-05-31"),
        )
        lines = self.report._get_lines(options)
        self.assertLinesValues(
            lines,
            [0, 1, 2, 5, 11],
            [
                ("Intrastat", "", "", "", ""),
                (
                    "Dispatch - QV999999999999 - 90212110 - BE",
                    "19 (Dispatch)",
                    "Belgium",
                    "90212110",
                    "3.63",
                ),
                (
                    "Dispatch - QV999999999999 - 93012000 - BE",
                    "19 (Dispatch)",
                    "Belgium",
                    "93012000",
                    "363.0",
                ),
            ],
            options,
        )

    def test_metres_supplementary_units(self):
        metre_supplementary_units_invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner_a.id,
                "invoice_date": "2022-05-15",
                "date": "2022-05-15",
                "company_id": self.company_data["company"].id,
                "intrastat_country_id": self.env.ref("base.be").id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_metre_supplementary_unit.id,
                            "quantity": 1.23,
                            "product_uom_id": self.env.ref("base.product_uom_km").id,
                            "price_unit": 10,
                            "tax_ids": [],
                        }
                    ),
                ],
            }
        )
        metre_supplementary_units_invoice.action_post()
        options = self._generate_options(
            self.report,
            date_from=fields.Date.from_string("2022-05-01"),
            date_to=fields.Date.from_string("2022-05-31"),
        )
        lines = self.report._get_lines(options)
        self.assertLinesValues(
            lines,
            [0, 1, 2, 5, 11],
            [
                ("Intrastat", "", "", "", ""),
                (
                    "Dispatch - QV999999999999 - 37061020 - BE",
                    "19 (Dispatch)",
                    "Belgium",
                    "37061020",
                    "1230.0",
                ),
            ],
            options,
        )

    def test_xlsx_output(self):
        belgian_invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner_a.id,
                "invoice_date": "2022-05-15",
                "date": "2022-05-15",
                "company_id": self.company_data["company"].id,
                "intrastat_country_id": self.env.ref("base.be").id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": self.spanish_rioja.product_variant_ids.id,
                            "quantity": 1,
                            "price_unit": 20,
                            "tax_ids": [],
                        }
                    )
                ],
            }
        )
        dutch_bill = self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": self.partner_a.id,
                "invoice_date": "2022-05-15",
                "date": "2022-05-15",
                "company_id": self.company_data["company"].id,
                "intrastat_country_id": self.env.ref("base.nl").id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": self.spanish_rioja.product_variant_ids.id,
                            "quantity": 2,
                            "price_unit": 20,
                            "tax_ids": [],
                        }
                    )
                ],
            }
        )
        belgian_invoice.action_post()
        dutch_bill.action_post()
        options = self._generate_options(
            self.report,
            "2022-05-01",
            "2022-05-31",
            default_options={"country_format": "code", "commodity_flow": "code"},
        )
        lines = self.report._get_lines(options)
        self.assertLinesValues(
            lines,
            [0, 1, 2, 5, 6],
            [
                ("Intrastat", "", "", "", ""),
                (
                    "Arrival - QV999999999999 - 22042176 - NL",
                    "29 (Arrival)",
                    "NL",
                    "22042176",
                    "ES",
                ),
                (
                    "Dispatch - QV999999999999 - 22042176 - BE",
                    "19 (Dispatch)",
                    "BE",
                    "22042176",
                    "ES",
                ),
            ],
            options,
        )

    def test_xi_invoice_with_xu_product(self):
        self.product_no_supplementary_unit.product_tmpl_id.intrastat_origin_country_id = self.env.ref(
            "base.uk"
        ).id
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner_a.id,
                "invoice_date": "2024-01-10",
                "date": "2024-01-10",
                "company_id": self.company_data["company"].id,
                "intrastat_country_id": self.env.ref("base.xi").id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_no_supplementary_unit.id,
                            "quantity": 1,
                            "product_uom_id": self.env.ref("base.product_uom_unit").id,
                            "price_unit": 10,
                        }
                    ),
                ],
            }
        )
        invoice.action_post()
        options = self._generate_options(
            self.report,
            "2024-01-01",
            "2024-01-31",
            default_options={"country_format": "code"},
        )
        lines = self.report._get_lines(options)
        self.assertLinesValues(
            lines,
            [0, 1, 2, 6],
            [
                ("Intrastat", "", "", ""),
                (
                    "Dispatch - QV999999999999 - 97040000 - XI",
                    "19 (Dispatch)",
                    "XI",
                    "XU",
                ),
            ],
            options,
        )

    def test_intrastat_custom_engine_aggregate(self):
        belgian_invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner_a.id,
                "invoice_date": "2022-05-15",
                "date": "2022-05-15",
                "company_id": self.company_data["company"].id,
                "intrastat_country_id": self.env.ref("base.be").id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": self.spanish_rioja.product_variant_ids.id,
                            "quantity": 1,
                            "price_unit": 20,
                            "tax_ids": [],
                        }
                    )
                ],
            }
        )
        dutch_bill = self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": self.partner_a.id,
                "invoice_date": "2022-05-15",
                "date": "2022-05-15",
                "company_id": self.company_data["company"].id,
                "intrastat_country_id": self.env.ref("base.nl").id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": self.spanish_rioja.product_variant_ids.id,
                            "quantity": 2,
                            "price_unit": 20,
                            "tax_ids": [],
                        }
                    )
                ],
            }
        )
        belgian_invoice.action_post()
        dutch_bill.action_post()
        options = self._generate_options(
            self.report,
            "2022-05-01",
            "2022-05-31",
            default_options={"country_format": "code", "commodity_flow": "code"},
        )

        self.assertLinesValues(
            self.report._get_lines(options),
            [0, 2, 5],
            [
                ("Intrastat", "", ""),
                ("Arrival - QV999999999999 - 22042176 - NL", "NL", "22042176"),
                ("Dispatch - QV999999999999 - 22042176 - BE", "BE", "22042176"),
            ],
            options,
        )

    def test_dynamic_line_generator_aggregate_intrastat_type(self):
        belgian_invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner_a.id,
                "invoice_date": "2022-05-15",
                "date": "2022-05-15",
                "company_id": self.company_data["company"].id,
                "intrastat_country_id": self.env.ref("base.be").id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": self.spanish_rioja.product_variant_ids.id,
                            "quantity": 1,
                            "price_unit": 20,
                            "tax_ids": [],
                        }
                    )
                ],
            }
        )
        dutch_bill = self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": self.partner_a.id,
                "invoice_date": "2022-05-15",
                "date": "2022-05-15",
                "company_id": self.company_data["company"].id,
                "intrastat_country_id": self.env.ref("base.nl").id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": self.spanish_rioja.product_variant_ids.id,
                            "quantity": 2,
                            "price_unit": 20,
                            "tax_ids": [],
                        }
                    )
                ],
            }
        )
        belgian_invoice.action_post()
        dutch_bill.action_post()
        default_type = [
            {"name": ("Arrival"), "selected": False, "id": "arrival"},
            {"name": ("Dispatch"), "selected": True, "id": "dispatch"},
        ]
        default_options = {
            "country_format": "code",
            "commodity_flow": "code",
            "intrastat_type": default_type,
        }
        options = self._generate_options(
            self.report, "2022-05-01", "2022-05-31", default_options=default_options
        )

        self.assertLinesValues(
            self.report._get_lines(options),
            [0, 1, 2, 5, 12],
            [
                ("Intrastat", "", "", "", 20),
                (
                    "Dispatch - QV999999999999 - 22042176 - BE",
                    "19 (Dispatch)",
                    "BE",
                    "22042176",
                    20,
                ),
            ],
            options,
        )

    def test_intrastat_comparison_period(self):

        def create_invoice_comparison(partner, date):
            return (
                self.env["account.move"]
                .create(
                    {
                        "move_type": "out_invoice",
                        "partner_id": partner.id,
                        "invoice_date": date,
                        "date": date,
                        "company_id": self.company_data["company"].id,
                        "intrastat_country_id": self.env.ref("base.be").id,
                        "invoice_line_ids": [
                            Command.create(
                                {
                                    "product_id": self.spanish_rioja.product_variant_ids.id,
                                    "quantity": 1,
                                    "price_unit": 20,
                                }
                            )
                        ],
                    }
                )
                .action_post()
            )

        partner_be_1, partner_be_2, partner_nl = self.env["res.partner"].create(
            [
                {
                    "name": "BE Partner 1",
                    "country_id": self.env.ref("base.be").id,
                    "vat": "BE0477472701",
                },
                {
                    "name": "BE Partner 2",
                    "country_id": self.env.ref("base.be").id,
                    "vat": "BE0475646428",
                },
                {
                    "name": "NL Partner",
                    "country_id": self.env.ref("base.nl").id,
                    "vat": "NL000099998B57",
                },
            ]
        )

        create_invoice_comparison(partner_be_1, "2024-06-01")
        create_invoice_comparison(partner_be_1, "2024-07-01")
        create_invoice_comparison(partner_be_2, "2024-06-01")
        create_invoice_comparison(partner_nl, "2024-07-01")

        default_options = {
            "comparison": {"filter": "last_month", "number_period": 1},
        }

        options = self._generate_options(
            self.report, "2024-07-01", "2024-07-31", default_options
        )
        options = self._update_comparison_filter(
            options, self.report, "previous_period", 1
        )
        options["unfold_all"] = True

        self.assertLinesValues(
            self.report._get_lines(options),
            [0, 12, 25],
            [
                ("Intrastat", 40.0, 40.0),
                ("Dispatch - BE0475646428 - 22042176 - BE", 0, 20.00),
                ("INV/2024/00003", 0, 20.00),
                ("Dispatch - BE0477472701 - 22042176 - BE", 20.00, 20.00),
                ("INV/2024/00002", 20.00, 0),
                ("INV/2024/00001", 0, 20.00),
                ("Dispatch - NL000099998B57 - 22042176 - BE", 20.00, 0),
                ("INV/2024/00004", 20.00, 0),
            ],
            options,
        )

    def test_intrastat_grouping_key(self):
        options = self._generate_options(self.report, "2022-01-01", "2022-01-31")
        self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner_a.id,
                "invoice_date": "2022-01-04",
                "date": "2022-01-04",
                "intrastat_country_id": self.env.ref("base.fr").id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "line_1",
                            "product_id": self.product_1.id,
                            "intrastat_transaction_id": self.intrastat_codes[
                                "transaction"
                            ].id,
                            "intrastat_product_origin_country_id": self.env.ref(
                                "base.uk"
                            ).id,
                            "quantity": 1.0,
                            "account_id": self.company_data[
                                "default_account_revenue"
                            ].id,
                            "price_unit": 100.0,
                        }
                    ),
                    Command.create(
                        {
                            "name": "line_2",
                            "product_id": self.product_1.id,
                            "intrastat_transaction_id": self.intrastat_codes[
                                "commodity"
                            ].id,
                            "intrastat_product_origin_country_id": self.env.ref(
                                "base.uk"
                            ).id,
                            "quantity": 1.0,
                            "account_id": self.company_data[
                                "default_account_revenue"
                            ].id,
                            "price_unit": 200.0,
                        }
                    ),
                ],
            }
        ).action_post()

        self.env.ref(
            "account_intrastat.intrastat_line"
        ).user_groupby = "move_id, intrastat_grouping, id"
        options["unfold_all"] = True

        report_lines = self.report._get_lines(options)

        self.assertLinesValues(
            report_lines,
            [0, 12],
            [
                ("Intrastat", 300),
                ("INV/2022/00001", 300),
                ("Dispatch - QV999999999999 - 100 - FR", 200),
                ("INV/2022/00001", 200),
                ("Dispatch - QV999999999999 - 100 - FR", 100),
                ("INV/2022/00001", 100),
            ],
            options,
        )
        self.env.ref(
            "account_intrastat.intrastat_line"
        ).user_groupby = "intrastat_grouping, id"

    def test_intrastat_report_load_more(self):
        partner_be = self.env["res.partner"].create(
            [
                {
                    "name": "BE Partner",
                    "country_id": self.env.ref("base.be").id,
                    "vat": "BE0477472701",
                },
            ]
        )

        moves = self.env["account.move"].create(
            [
                {
                    "move_type": "out_invoice",
                    "partner_id": partner_be.id,
                    "invoice_date": "2022-01-01",
                    "date": "2022-01-01",
                    "intrastat_country_id": self.env.ref("base.be").id,
                    "invoice_line_ids": [
                        Command.create(
                            {
                                "name": "line_1",
                                "product_id": self.spanish_rioja.id,
                                "intrastat_transaction_id": None,
                                "product_uom_id": self.env.ref(
                                    "base.product_uom_unit"
                                ).id,
                                "quantity": 1.0,
                                "account_id": self.company_data[
                                    "default_account_revenue"
                                ].id,
                                "price_unit": 80.0,
                                "tax_ids": [],
                            }
                        ),
                    ],
                },
                {
                    "move_type": "out_invoice",
                    "partner_id": partner_be.id,
                    "invoice_date": "2022-01-02",
                    "date": "2022-01-02",
                    "intrastat_country_id": self.env.ref("base.be").id,
                    "invoice_line_ids": [
                        Command.create(
                            {
                                "name": "line_1",
                                "product_id": self.spanish_rioja.id,
                                "intrastat_transaction_id": None,
                                "product_uom_id": self.env.ref(
                                    "base.product_uom_unit"
                                ).id,
                                "quantity": 1.0,
                                "account_id": self.company_data[
                                    "default_account_revenue"
                                ].id,
                                "price_unit": 80.0,
                                "tax_ids": [],
                            }
                        ),
                    ],
                },
                {
                    "move_type": "out_invoice",
                    "partner_id": partner_be.id,
                    "invoice_date": "2022-01-03",
                    "date": "2022-01-03",
                    "intrastat_country_id": self.env.ref("base.be").id,
                    "invoice_line_ids": [
                        Command.create(
                            {
                                "name": "line_1",
                                "product_id": self.spanish_rioja.id,
                                "intrastat_transaction_id": None,
                                "product_uom_id": self.env.ref(
                                    "base.product_uom_unit"
                                ).id,
                                "quantity": 1.0,
                                "account_id": self.company_data[
                                    "default_account_revenue"
                                ].id,
                                "price_unit": 50.0,
                                "tax_ids": [],
                            }
                        ),
                    ],
                },
            ]
        )
        moves.action_post()

        options = self._generate_options(
            self.report,
            "2022-01-01",
            "2022-01-31",
            default_options={"unfold_all": True},
        )
        lines = self.report._get_lines(options)
        self.assertLinesValues(
            lines,
            [0, 12],
            [
                ("Intrastat", 210.0),
                ("Dispatch - BE0477472701 - 22042176 - BE", 210.0),
                ("INV/2022/00003", 50.0),
                ("INV/2022/00002", 80.0),
                ("INV/2022/00001", 80.0),
            ],
            options,
        )

        self.report.load_more_limit = 1
        lines = self.report._get_lines(options)
        self.assertLinesValues(
            lines,
            [0, 12],
            [
                ("Intrastat", 210.0),
                ("Dispatch - BE0477472701 - 22042176 - BE", 210.0),
                ("INV/2022/00003", 50.0),
                ("Load more...", ""),
            ],
            options,
        )

        load_more_1 = self.report.get_expanded_lines(
            options,
            lines[1]["id"],
            lines[3]["groupby"],
            lines[3]["expand_function"],
            lines[3]["progress"],
            lines[3]["offset"],
            None,
        )

        self.assertLinesValues(
            load_more_1,
            [0, 12],
            [("INV/2022/00002", 80.0), ("Load more...", "")],
            options,
        )

        load_more_2 = self.report.get_expanded_lines(
            options,
            lines[1]["id"],
            load_more_1[1]["groupby"],
            load_more_1[1]["expand_function"],
            load_more_1[1]["progress"],
            load_more_1[1]["offset"],
            None,
        )

        self.assertLinesValues(
            load_more_2,
            [0, 12],
            [("INV/2022/00001", 80.0)],
            options,
        )

    def test_reverse_move_default_intrastat_code(self):
        self.env.company.intrastat_default_invoice_transaction_code_id = (
            self.intrastat_codes["commodity"]
        )
        self.env.company.intrastat_default_refund_transaction_code_id = (
            self.intrastat_codes["transaction"]
        )
        invoice_to_be_refund = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner_a.id,
                "invoice_date": "2022-01-15",
                "intrastat_country_id": self.env.ref("base.be").id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": self.spanish_rioja.id,
                            "product_uom_id": self.env.ref("base.product_uom_unit").id,
                            "quantity": 1.0,
                            "account_id": self.company_data[
                                "default_account_revenue"
                            ].id,
                            "price_unit": 100.0,
                        }
                    ),
                ],
            }
        )
        invoice_to_be_refund.action_post()
        self.assertEqual(
            invoice_to_be_refund.line_ids.intrastat_transaction_id,
            self.intrastat_codes["commodity"],
        )

        credit_note_wizard = (
            self.env["wizard.account.move.reverse"]
            .with_context(
                {
                    "active_ids": invoice_to_be_refund.ids,
                    "active_id": invoice_to_be_refund.id,
                    "active_model": "account.move",
                }
            )
            .create(
                {
                    "reason": "reason test create",
                    "journal_id": invoice_to_be_refund.journal_id.id,
                }
            )
        )
        action = credit_note_wizard.reverse_moves()
        credit_note = self.env["account.move"].browse(action["res_id"])
        self.assertEqual(
            credit_note.line_ids.intrastat_transaction_id,
            self.intrastat_codes["transaction"],
        )

    @freeze_time("2022-02-01")
    def test_weight_decimal_separator_depending_on_language(self):
        self.product_3.weight = 1230.5
        self._create_invoices(code_type="transaction")
        options = self._generate_options(
            self.report, "2022-01-01", "2022-01-31", {"intrastat_grouped": True}
        )
        self.assertLinesValues(
            self.report._get_lines(options),
            [10],
            [
                ("",),
                ("1230.5",),
                ("1.5",),
            ],
            options,
        )
        self.env["res.lang"]._activate_lang("fr_BE")
        self.env.user.lang = "fr_BE"
        report_fr = self.report.with_context(lang="fr_BE")
        self.assertLinesValues(
            report_fr._get_lines(options),
            [10],
            [
                ("",),
                ("1230,5",),
                ("1,5",),
            ],
            options,
        )
