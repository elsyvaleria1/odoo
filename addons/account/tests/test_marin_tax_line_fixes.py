from odoo import Command, fields
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestMarinTaxLineFixes(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.other_currency = cls.setup_other_currency("EUR")
        cls.tax_sale = cls.company_data["default_tax_sale"]
        cls.tax_purchase = cls.company_data["default_tax_purchase"]
        cls.rounding_account = cls.company_data["default_account_revenue"].copy()

    def _invoice(self, lines, move_type="out_invoice", **move_vals):
        return self.env["account.move"].create(
            {
                "move_type": move_type,
                "partner_id": self.partner_a.id,
                "invoice_date": "2026-01-01",
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": name,
                            "quantity": 1,
                            "price_unit": price_unit,
                            "tax_ids": [Command.set(taxes.ids)],
                        }
                    )
                    for name, price_unit, taxes in lines
                ],
                **move_vals,
            }
        )

    def _tax_lines(self, move):
        return move.line_ids.filtered(lambda line: line.display_type == "tax")

    def _set_tax_amount(self, move, amount_currency):
        tax_line = self._tax_lines(move)
        tax_line.check_singleton()
        move.write(
            {
                "line_ids": [
                    Command.update(tax_line.id, {"amount_currency": amount_currency})
                ]
            }
        )
        self.assertAlmostEqual(self._tax_lines(move).amount_currency, amount_currency)

    def _invoice_with_manual_tax(self):
        self.assertEqual(self.tax_sale.amount, 15.0)
        invoice = self._invoice(
            [("taxed", 10.0, self.tax_sale), ("untaxed", 5.0, self.env["account.tax"])]
        )
        self.assertAlmostEqual(self._tax_lines(invoice).amount_currency, -1.50)
        self._set_tax_amount(invoice, -1.60)
        return invoice

    def test_manual_tax_kept_when_untaxed_line_is_edited(self):
        invoice = self._invoice_with_manual_tax()
        untaxed = invoice.invoice_line_ids.filtered(lambda line: line.name == "untaxed")
        invoice.write(
            {"invoice_line_ids": [Command.update(untaxed.id, {"price_unit": 6.0})]}
        )
        self.assertAlmostEqual(self._tax_lines(invoice).amount_currency, -1.60)
        self.assertAlmostEqual(invoice.amount_total, 17.60)

    def test_manual_tax_kept_when_untaxed_line_is_removed(self):
        invoice = self._invoice_with_manual_tax()
        untaxed = invoice.invoice_line_ids.filtered(lambda line: line.name == "untaxed")
        invoice.write({"invoice_line_ids": [Command.unlink(untaxed.id)]})
        self.assertAlmostEqual(self._tax_lines(invoice).amount_currency, -1.60)
        self.assertAlmostEqual(invoice.amount_total, 11.60)

    def test_manual_tax_kept_when_untaxed_line_is_added(self):
        invoice = self._invoice_with_manual_tax()
        invoice.write(
            {
                "invoice_line_ids": [
                    Command.create({"name": "new", "quantity": 1, "price_unit": 7.0})
                ]
            }
        )
        self.assertAlmostEqual(self._tax_lines(invoice).amount_currency, -1.60)

    def test_manual_tax_recomputed_when_taxed_line_is_edited(self):
        invoice = self._invoice_with_manual_tax()
        taxed = invoice.invoice_line_ids.filtered(lambda line: line.name == "taxed")
        invoice.write(
            {"invoice_line_ids": [Command.update(taxed.id, {"price_unit": 20.0})]}
        )
        self.assertAlmostEqual(self._tax_lines(invoice).amount_currency, -3.00)

    def test_misc_entry_tax_and_untaxed_line_edited_in_one_write(self):
        income = self.company_data["default_account_revenue"]
        receivable = self.company_data["default_account_receivable"]
        entry = self.env["account.move"].create(
            {
                "move_type": "entry",
                "journal_id": self.company_data["default_journal_misc"].id,
                "date": fields.Date.from_string("2026-01-01"),
                "line_ids": [
                    Command.create(
                        {
                            "name": "base",
                            "account_id": income.id,
                            "balance": -100.0,
                            "tax_ids": [Command.set(self.tax_sale.ids)],
                        }
                    ),
                    Command.create(
                        {
                            "name": "counterpart",
                            "account_id": receivable.id,
                            "balance": 115.0,
                        }
                    ),
                ],
            }
        )
        tax_line = entry.line_ids.filtered("tax_line_id")
        counterpart = entry.line_ids.filtered(lambda line: line.name == "counterpart")
        entry.write(
            {
                "line_ids": [
                    Command.update(
                        tax_line.id, {"balance": -15.01, "amount_currency": -15.01}
                    ),
                    Command.update(
                        counterpart.id, {"balance": 115.01, "amount_currency": 115.01}
                    ),
                ]
            }
        )
        self.assertAlmostEqual(tax_line.balance, -15.01)
        self.assertFalse(
            entry.line_ids.filtered(lambda line: line.display_type == "balancing")
        )

    def _biggest_tax_rounding(self, rounding):
        return self.env["account.cash.rounding"].create(
            {
                "name": "biggest tax %s" % rounding,
                "rounding": rounding,
                "strategy": "biggest_tax",
                "rounding_method": "HALF-UP",
                "profit_account_id": self.rounding_account.id,
                "loss_account_id": self.rounding_account.id,
            }
        )

    def _rounding_line(self, move):
        return move.line_ids.filtered(lambda line: line.display_type == "rounding")

    def test_biggest_tax_rounding_line_not_merged_into_tax_line(self):
        invoice = self._invoice(
            [("taxed", 10.33, self.tax_sale)],
            invoice_cash_rounding_id=self._biggest_tax_rounding(1.0).id,
        )
        self.assertAlmostEqual(self._tax_lines(invoice).amount_currency, -1.55)
        self.assertAlmostEqual(self._rounding_line(invoice).amount_currency, -0.12)
        invoice.write(
            {
                "invoice_line_ids": [
                    Command.create(
                        {"name": "untaxed", "quantity": 1, "price_unit": 0.21}
                    )
                ]
            }
        )
        self.assertAlmostEqual(self._tax_lines(invoice).amount_currency, -1.55)
        self.assertAlmostEqual(self._rounding_line(invoice).amount_currency, 0.09)
        self.assertAlmostEqual(invoice.amount_total, 12.0)

    def test_biggest_tax_manual_group_amount_lands_on_tax_line(self):
        invoice = self._invoice(
            [("taxed", 10.03, self.tax_sale)],
            invoice_cash_rounding_id=self._biggest_tax_rounding(0.05).id,
        )
        self.assertAlmostEqual(self._tax_lines(invoice).amount_currency, -1.50)
        self.assertAlmostEqual(self._rounding_line(invoice).amount_currency, -0.02)
        self.assertAlmostEqual(invoice.tax_totals["tax_amount_currency"], 1.52)

        tax_totals = invoice.tax_totals
        tax_totals["subtotals"][0]["tax_groups"][0]["tax_amount_currency"] = 1.57
        invoice.tax_totals = tax_totals
        self.assertAlmostEqual(self._tax_lines(invoice).amount_currency, -1.55)
        self.assertAlmostEqual(self._rounding_line(invoice).amount_currency, -0.02)
        invoice.action_post()
        invoice.invalidate_recordset(["tax_totals"])
        self.assertAlmostEqual(invoice.tax_totals["tax_amount_currency"], 1.57)
        self.assertAlmostEqual(invoice.amount_total, 11.60)

    def test_biggest_tax_rounding_follows_swapped_tax(self):
        invoice = self._invoice(
            [("taxed", 10.03, self.tax_sale)],
            invoice_cash_rounding_id=self._biggest_tax_rounding(0.05).id,
        )
        rounding_line = self._rounding_line(invoice)
        self.assertEqual(rounding_line.tax_line_id, self.tax_sale)
        tax_copy = self.tax_sale.copy({"name": "swapped"})
        invoice.invoice_line_ids.tax_ids = [Command.set(tax_copy.ids)]
        self.assertEqual(self._rounding_line(invoice), rounding_line)
        self.assertGreater(self._tax_lines(invoice).id, rounding_line.id)
        self.assertEqual(rounding_line.tax_line_id, tax_copy)
        self.assertEqual(
            rounding_line.tax_repartition_line_id,
            self._tax_lines(invoice).tax_repartition_line_id,
        )

        tax_totals = invoice.tax_totals
        tax_totals["subtotals"][0]["tax_groups"][0]["tax_amount_currency"] = 1.57
        invoice.tax_totals = tax_totals
        self.assertAlmostEqual(self._tax_lines(invoice).amount_currency, -1.55)
        self.assertAlmostEqual(rounding_line.amount_currency, -0.02)
        self.assertAlmostEqual(invoice.amount_total, 11.60)

    def _posted_invoice_with_manual_tax(self):
        invoice = self._invoice(
            [("A", 10.0, self.tax_sale), ("C", 30.0, self.tax_sale)]
        )
        self._set_tax_amount(invoice, -6.10)
        invoice.action_post()
        return invoice

    def test_aggregated_taxes_follow_posted_tax_lines(self):
        invoice = self._posted_invoice_with_manual_tax()
        results = invoice._prepare_invoice_aggregated_taxes()
        self.assertAlmostEqual(results["tax_amount_currency"], 6.10)

        results = invoice._prepare_invoice_aggregated_taxes(
            filter_tax_values_to_apply=lambda base_line, tax_data: True
        )
        self.assertAlmostEqual(results["tax_amount_currency"], 6.10)

        results = invoice._prepare_invoice_aggregated_taxes(round_from_tax_lines=False)
        self.assertAlmostEqual(results["tax_amount_currency"], 6.00)

    def test_aggregated_taxes_line_filter_gets_its_share(self):
        invoice = self._posted_invoice_with_manual_tax()
        line_a = invoice.invoice_line_ids.filtered(lambda line: line.name == "A")
        only_a = invoice._prepare_invoice_aggregated_taxes(
            filter_invl_to_apply=lambda line: line == line_a
        )
        without_a = invoice._prepare_invoice_aggregated_taxes(
            filter_invl_to_apply=lambda line: line != line_a
        )
        self.assertAlmostEqual(only_a["base_amount_currency"], 10.0)
        self.assertAlmostEqual(only_a["tax_amount_currency"], 1.5, delta=0.1)
        self.assertAlmostEqual(without_a["tax_amount_currency"], 4.5, delta=0.1)
        self.assertAlmostEqual(
            only_a["tax_amount_currency"] + without_a["tax_amount_currency"], 6.10
        )

    def _non_deductible_bill_vals(self, currency, move_type="in_invoice"):
        self.assertEqual(self.tax_purchase.amount, 15.0)
        return {
            "move_type": move_type,
            "partner_id": self.partner_a.id,
            "currency_id": currency.id,
            "invoice_date": "2026-01-01",
            "invoice_line_ids": [
                Command.create(
                    {
                        "name": "half deductible",
                        "quantity": 1,
                        "price_unit": 1000.0,
                        "deductible_amount": 50.0,
                        "tax_ids": [Command.set(self.tax_purchase.ids)],
                    }
                )
            ],
        }

    def _non_deductible_amounts(self, tax_totals):
        return [
            (
                tax_group["tax_amount_currency"],
                tax_group["tax_amount"],
                tax_group.get("non_deductible_tax_amount_currency"),
                tax_group.get("non_deductible_tax_amount"),
            )
            for subtotal in tax_totals["subtotals"]
            for tax_group in subtotal["tax_groups"]
        ]

    def _term_amounts(self, move):
        return sorted(
            (values["amount_currency"], values["balance"])
            for values in move.needed_terms.values()
        )

    def test_unsaved_non_deductible_bill_matches_saved(self):
        for move_type, term_sign in (("in_invoice", -1), ("in_refund", 1)):
            for currency in (self.company_data["currency"], self.other_currency):
                with self.subTest(move_type=move_type, currency=currency.name):
                    vals = self._non_deductible_bill_vals(currency, move_type)
                    unsaved = self.env["account.move"].new(vals)
                    saved = self.env["account.move"].create(vals)
                    self.assertEqual(
                        self._non_deductible_amounts(unsaved.tax_totals),
                        self._non_deductible_amounts(saved.tax_totals),
                    )
                    self.assertEqual(
                        self._term_amounts(unsaved), self._term_amounts(saved)
                    )
                    term = term_sign * 1150.0
                    rate = saved.invoice_currency_rate
                    self.assertEqual(
                        self._term_amounts(saved),
                        [(term, saved.company_currency_id.round(term / rate))],
                    )

    def test_tax_merge_remaps_move_lines(self):
        tax_copy = self.tax_sale.copy({"name": "remap source"})
        invoice = self._invoice([("A", 100.0, tax_copy)])
        invoice.action_post()
        RepartitionLine = self.env["account.tax.repartition.line"]
        source = tax_copy.repartition_line_ids._sorted_for_positional_pairing()
        target = self.tax_sale.repartition_line_ids._sorted_for_positional_pairing()
        mapping = {old.id: new.id for old, new in zip(source, target, strict=True)}
        self.assertEqual(RepartitionLine._remap_move_lines({}), 0)
        self.assertEqual(
            RepartitionLine._remap_move_lines(mapping, company_ids=[]),
            0,
        )
        self.assertEqual(
            self._tax_lines(invoice).tax_repartition_line_id.tax_id, tax_copy
        )
        self.assertEqual(
            RepartitionLine._remap_move_lines(
                mapping, company_ids=[invoice.company_id.id]
            ),
            1,
        )
        self.assertEqual(
            self._tax_lines(invoice).tax_repartition_line_id.tax_id, self.tax_sale
        )

    def test_show_tax_exigibility_follows_cash_basis_setting(self):
        config = self.env.company.account_config_id
        config.tax_exigibility = False
        self.tax_sale.invalidate_recordset(["show_tax_exigibility"])
        self.assertFalse(self.tax_sale.show_tax_exigibility)
        config.tax_exigibility = True
        self.tax_sale.invalidate_recordset(["show_tax_exigibility"])
        self.assertTrue(self.tax_sale.show_tax_exigibility)

    def test_tax_totals_amounts_carry_no_float_noise(self):
        invoice = self._invoice([("A", 10.2, self.tax_sale)])
        tax_totals = invoice.tax_totals
        self.assertEqual(tax_totals["total_amount_currency"], 11.73)
        self.assertEqual(tax_totals["total_amount"], 11.73)
        self.assertEqual(tax_totals["subtotals"][0]["base_amount_currency"], 10.2)
