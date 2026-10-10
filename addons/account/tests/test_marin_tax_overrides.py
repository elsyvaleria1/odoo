import copy
import importlib.util
from pathlib import Path

from odoo import Command
from odoo.tests import Form, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestMarinTaxOverrides(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.other_currency = cls.setup_other_currency("EUR")
        cls.tax_purchase = cls.company_data["default_tax_purchase"]
        cls.tax_sale = cls.company_data["default_tax_sale"]
        cls.rounding_account = cls.company_data["default_account_revenue"].copy()

    def _move(self, move_type="in_invoice", taxed=10.0, untaxed=5.0, **vals):
        tax = self.tax_purchase if move_type.startswith("in_") else self.tax_sale
        self.assertEqual(tax.amount, 15.0)
        lines = [
            Command.create(
                {
                    "name": "taxed",
                    "quantity": 1,
                    "price_unit": taxed,
                    "tax_ids": [Command.set(tax.ids)],
                }
            )
        ]
        if untaxed:
            lines.append(
                Command.create(
                    {
                        "name": "untaxed",
                        "quantity": 1,
                        "price_unit": untaxed,
                        "tax_ids": [Command.clear()],
                    }
                )
            )
        return self.env["account.move"].create(
            {
                "move_type": move_type,
                "partner_id": self.partner_a.id,
                "invoice_date": "2026-01-01",
                "invoice_line_ids": lines,
                **vals,
            }
        )

    def _tax_line(self, move):
        return move.line_ids.filtered(lambda line: line.display_type == "tax")

    def _group(self, tax_totals):
        return tax_totals["subtotals"][0]["tax_groups"][0]

    def _with_group_amount(self, tax_totals, amount):
        tax_totals = copy.deepcopy(tax_totals)
        self._group(tax_totals)["tax_amount_currency"] = amount
        return tax_totals

    def _line_index(self, move, name):
        return move.invoice_line_ids.mapped("name").index(name)

    def _assert_tax(self, move, amount, total):
        self.assertAlmostEqual(
            self._tax_line(move).amount_currency, amount * move.direction_sign
        )
        self.assertAlmostEqual(
            self._group(move.tax_totals)["tax_amount_currency"], amount
        )
        self.assertAlmostEqual(move.amount_total, total)

    def _messages(self, move):
        return move.message_ids.mapped("body")

    def test_widget_edit_then_untaxed_line_edit_before_save_keeps_manual_tax(self):
        for move_type in ("in_invoice", "in_refund"):
            with self.subTest(move_type=move_type):
                bill = self._move(move_type)
                with Form(bill) as bill_form:
                    bill_form.tax_totals = self._with_group_amount(
                        bill_form.tax_totals, 1.60
                    )
                    with bill_form.invoice_line_ids.edit(
                        self._line_index(bill, "untaxed")
                    ) as line_form:
                        line_form.price_unit = 6.0
                    self.assertAlmostEqual(
                        self._group(bill_form.tax_totals)["tax_amount_currency"], 1.60
                    )
                self._assert_tax(bill, 1.60, 17.60)
                self.assertRecordValues(
                    bill.tax_override_ids,
                    [
                        {
                            "tax_id": self.tax_purchase.id,
                            "amount_currency": 1.60,
                            "amount_computed_currency": 1.50,
                            "amount_base_currency": 10.0,
                        }
                    ],
                )

    def test_widget_edit_saved_then_untaxed_line_edit_keeps_manual_tax(self):
        bill = self._move()
        with Form(bill) as bill_form:
            bill_form.tax_totals = self._with_group_amount(bill_form.tax_totals, 1.60)
        self._assert_tax(bill, 1.60, 16.60)
        with Form(bill) as bill_form:
            with bill_form.invoice_line_ids.edit(
                self._line_index(bill, "untaxed")
            ) as line_form:
                line_form.price_unit = 6.0
            self.assertAlmostEqual(
                self._group(bill_form.tax_totals)["tax_amount_currency"], 1.60
            )
        self._assert_tax(bill, 1.60, 17.60)

    def test_written_tax_totals_survive_untaxed_line_write(self):
        bill = self._move()
        bill.tax_totals = self._with_group_amount(bill.tax_totals, 1.60)
        untaxed = bill.invoice_line_ids.filtered(lambda line: line.name == "untaxed")
        bill.write(
            {"invoice_line_ids": [Command.update(untaxed.id, {"price_unit": 6.0})]}
        )
        self._assert_tax(bill, 1.60, 17.60)
        bill.write({"invoice_line_ids": [Command.unlink(untaxed.id)]})
        self._assert_tax(bill, 1.60, 11.60)

    def test_journal_item_edit_is_recorded_as_override(self):
        bill = self._move()
        tax_line = self._tax_line(bill)
        bill.write(
            {
                "line_ids": [
                    Command.update(
                        tax_line.id, {"amount_currency": 1.60 * bill.direction_sign}
                    )
                ]
            }
        )
        self.assertRecordValues(
            bill.tax_override_ids,
            [{"amount_currency": 1.60, "amount_computed_currency": 1.50}],
        )
        self._assert_tax(bill, 1.60, 16.60)

    def test_taxed_line_write_drops_override_with_notice(self):
        bill = self._move()
        bill.tax_totals = self._with_group_amount(bill.tax_totals, 1.60)
        taxed = bill.invoice_line_ids.filtered(lambda line: line.name == "taxed")
        bill.write(
            {"invoice_line_ids": [Command.update(taxed.id, {"price_unit": 20.0})]}
        )
        self._assert_tax(bill, 3.00, 28.00)
        self.assertFalse(bill.tax_override_ids)
        self.assertTrue(
            any(
                "1.60" in body and self.tax_purchase.name in body
                for body in self._messages(bill)
            ),
            self._messages(bill),
        )

    def test_taxed_line_edit_in_form_drops_override(self):
        bill = self._move()
        bill.tax_totals = self._with_group_amount(bill.tax_totals, 1.60)
        with Form(bill) as bill_form:
            with bill_form.invoice_line_ids.edit(
                self._line_index(bill, "taxed")
            ) as line_form:
                line_form.price_unit = 20.0
            self.assertAlmostEqual(
                self._group(bill_form.tax_totals)["tax_amount_currency"], 3.00
            )
        self._assert_tax(bill, 3.00, 28.00)
        self.assertFalse(bill.tax_override_ids)

    def test_tax_removed_from_line_drops_override(self):
        bill = self._move()
        bill.tax_totals = self._with_group_amount(bill.tax_totals, 1.60)
        taxed = bill.invoice_line_ids.filtered(lambda line: line.name == "taxed")
        taxed.tax_ids = [Command.clear()]
        self.assertFalse(self._tax_line(bill))
        self.assertFalse(bill.tax_override_ids)
        self.assertAlmostEqual(bill.amount_total, 15.0)

    def test_partner_change_keeps_override(self):
        bill = self._move()
        with Form(bill) as bill_form:
            bill_form.tax_totals = self._with_group_amount(bill_form.tax_totals, 1.60)
            bill_form.partner_id = self.partner_b
            self.assertAlmostEqual(
                self._group(bill_form.tax_totals)["tax_amount_currency"], 1.60
            )
        self._assert_tax(bill, 1.60, 16.60)

    def test_currency_change_drops_override(self):
        bill = self._move()
        bill.tax_totals = self._with_group_amount(bill.tax_totals, 1.60)
        with Form(bill) as bill_form:
            bill_form.currency_id = self.other_currency
            self.assertAlmostEqual(
                self._group(bill_form.tax_totals)["tax_amount_currency"], 1.50
            )
        self.assertFalse(bill.tax_override_ids)
        self._assert_tax(bill, 1.50, 16.50)

        bill.tax_totals = self._with_group_amount(bill.tax_totals, 1.60)
        bill.currency_id = self.company_data["currency"]
        self.assertFalse(bill.tax_override_ids)
        self._assert_tax(bill, 1.50, 16.50)

    def test_rate_change_keeps_override_and_reconverts_balance(self):
        bill = self._move(currency_id=self.other_currency.id)
        bill.tax_totals = self._with_group_amount(bill.tax_totals, 1.60)
        bill.invoice_currency_rate = 4.0
        tax_line = self._tax_line(bill)
        self.assertAlmostEqual(tax_line.amount_currency, 1.60 * bill.direction_sign)
        self.assertAlmostEqual(tax_line.balance, 0.40 * bill.direction_sign)
        self.assertTrue(bill.tax_override_ids)

    def test_reset_to_computed_removes_override(self):
        bill = self._move()
        with Form(bill) as bill_form:
            bill_form.tax_totals = self._with_group_amount(bill_form.tax_totals, 1.60)
        group = self._group(bill.tax_totals)
        self.assertTrue(group["manual_tax_amount"])
        self.assertAlmostEqual(group["computed_tax_amount_currency"], 1.50)
        with Form(bill) as bill_form:
            bill_form.tax_totals = self._with_group_amount(
                bill_form.tax_totals,
                self._group(bill_form.tax_totals)["computed_tax_amount_currency"],
            )
            self.assertNotIn("manual_tax_amount", self._group(bill_form.tax_totals))
        self.assertFalse(bill.tax_override_ids)
        self._assert_tax(bill, 1.50, 16.50)
        bodies = self._messages(bill)
        self.assertEqual(len([body for body in bodies if "1.60" in body]), 2, bodies)

    def test_unsaved_record_and_terms_follow_override(self):
        bill = self._move()
        bill.tax_totals = self._with_group_amount(bill.tax_totals, 1.60)
        unsaved = bill.new(origin=bill)
        unsaved.invoice_line_ids.filtered(
            lambda line: line.name == "untaxed"
        ).price_unit = 6.0
        self.assertAlmostEqual(
            self._group(unsaved.tax_totals)["tax_amount_currency"], 1.60
        )
        self.assertEqual(
            [values["amount_currency"] for values in unsaved.needed_terms.values()],
            [-17.60],
        )

    def test_aggregated_taxes_follow_override(self):
        invoice = self._move("out_invoice", taxed=10.0, untaxed=0.0)
        invoice.tax_totals = self._with_group_amount(invoice.tax_totals, 1.60)
        results = invoice._prepare_invoice_aggregated_taxes()
        self.assertAlmostEqual(results["tax_amount_currency"], 1.60)
        base_lines, _tax_lines = invoice._get_rounded_base_and_tax_lines()
        self.assertAlmostEqual(
            sum(
                tax_data["tax_amount_currency"]
                for base_line in base_lines
                for tax_data in base_line["tax_details"]["taxes_data"]
            ),
            1.60,
        )
        invoice.action_post()
        results = invoice._prepare_invoice_aggregated_taxes()
        self.assertAlmostEqual(results["tax_amount_currency"], 1.60)

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

    def test_biggest_tax_rounding_with_override_and_untaxed_edit(self):
        bill = self._move(
            taxed=10.03,
            untaxed=0.0,
            invoice_cash_rounding_id=self._biggest_tax_rounding(0.05).id,
        )
        self.assertAlmostEqual(
            self._group(bill.tax_totals)["tax_amount_currency"], 1.52
        )
        with Form(bill) as bill_form:
            bill_form.tax_totals = self._with_group_amount(bill_form.tax_totals, 1.57)
            with bill_form.invoice_line_ids.new() as line_form:
                line_form.name = "untaxed"
                line_form.price_unit = 1.0
                line_form.tax_ids.clear()
        rounding_line = bill.line_ids.filtered(
            lambda line: line.display_type == "rounding"
        )
        self.assertAlmostEqual(
            self._tax_line(bill).amount_currency, 1.55 * bill.direction_sign
        )
        self.assertAlmostEqual(
            rounding_line.amount_currency, 0.02 * bill.direction_sign
        )
        self.assertAlmostEqual(bill.amount_total, 12.60)
        self.assertRecordValues(bill.tax_override_ids, [{"amount_currency": 1.55}])

    def _override_notes(self, move):
        return [body for body in self._messages(move) if "Manual tax amount" in body]

    def test_plain_copy_records_no_override(self):
        for move_type in ("in_invoice", "out_invoice", "in_refund", "out_refund"):
            with self.subTest(move_type=move_type):
                duplicate = self._move(move_type).copy()
                self.assertFalse(duplicate.tax_override_ids)
                self.assertFalse(self._override_notes(duplicate))
                self._assert_tax(duplicate, 1.50, 16.50)

    def test_copy_carries_a_manual_tax_amount(self):
        for move_type in ("in_invoice", "out_invoice"):
            with self.subTest(move_type=move_type):
                move = self._move(move_type)
                move.tax_totals = self._with_group_amount(move.tax_totals, 1.60)
                duplicate = move.copy()
                self.assertRecordValues(
                    duplicate.tax_override_ids,
                    [
                        {
                            "amount_currency": 1.60,
                            "amount_computed_currency": 1.50,
                            "amount_base_currency": 10.0,
                        }
                    ],
                )
                self._assert_tax(duplicate, 1.60, 16.60)
                self.assertEqual(len(self._override_notes(duplicate)), 1)

    def test_plain_reversal_records_no_override(self):
        for move_type in ("in_invoice", "out_invoice"):
            with self.subTest(move_type=move_type):
                move = self._move(move_type)
                move.action_post()
                reversal = move._reverse_moves()
                self.assertFalse(reversal.tax_override_ids)
                self.assertFalse(self._override_notes(reversal))
                self._assert_tax(reversal, 1.50, 16.50)

    def test_reversal_carries_the_manual_tax_amount(self):
        for move_type in ("in_invoice", "out_invoice"):
            with self.subTest(move_type=move_type):
                move = self._move(move_type)
                move.tax_totals = self._with_group_amount(move.tax_totals, 1.60)
                move.action_post()
                reversal = move._reverse_moves([{"invoice_date": move.invoice_date}])
                self.assertRecordValues(
                    reversal.tax_override_ids,
                    [
                        {
                            "amount_currency": 1.60,
                            "amount_computed_currency": 1.50,
                            "amount_base_currency": 10.0,
                        }
                    ],
                )
                self._assert_tax(reversal, 1.60, 16.60)
                reversal.action_post()
                self.assertAlmostEqual(
                    sum(self._tax_line(move | reversal).mapped("amount_currency")), 0.0
                )

    def test_misc_entry_tax_line_edit_creates_no_override(self):
        income = self.company_data["default_account_revenue"]
        receivable = self.company_data["default_account_receivable"]
        entry = self.env["account.move"].create(
            {
                "move_type": "entry",
                "date": "2026-01-01",
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
        tax_line.write({"balance": -15.01, "amount_currency": -15.01})
        self.assertFalse(entry.tax_override_ids)
        self.assertAlmostEqual(tax_line.balance, -15.01)

    def _drop_override_rows(self, move):
        self.env.cr.execute(
            "DELETE FROM account_move_tax_override WHERE move_id = %s", [move.id]
        )
        move.invalidate_recordset(["tax_override_ids"])

    def test_reset_to_draft_materializes_posted_drift(self):
        bill = self._move()
        bill.tax_totals = self._with_group_amount(bill.tax_totals, 1.60)
        bill.action_post()
        self._drop_override_rows(bill)
        bill.action_draft()
        self.assertRecordValues(bill.tax_override_ids, [{"amount_currency": 1.60}])
        untaxed = bill.invoice_line_ids.filtered(lambda line: line.name == "untaxed")
        bill.write(
            {"invoice_line_ids": [Command.update(untaxed.id, {"price_unit": 6.0})]}
        )
        self._assert_tax(bill, 1.60, 17.60)

    def test_migration_creates_overrides_for_drifted_drafts(self):
        drifted = self._move()
        drifted.tax_totals = self._with_group_amount(drifted.tax_totals, 1.60)
        self._drop_override_rows(drifted)
        posted = self._move()
        posted.tax_totals = self._with_group_amount(posted.tax_totals, 1.60)
        posted.action_post()
        self._drop_override_rows(posted)
        clean = self._move()

        script = Path(__file__).parents[1] / "migrations/1.40/post-20-tax_overrides.py"
        spec = importlib.util.spec_from_file_location("post_20_tax_overrides", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.migrate(self.env.cr, "19.0.1.39")
        (drifted | posted | clean).invalidate_recordset(["tax_override_ids"])

        self.assertRecordValues(
            drifted.tax_override_ids,
            [{"amount_currency": 1.60, "amount_computed_currency": 1.50}],
        )
        self.assertFalse(posted.tax_override_ids)
        self.assertFalse(clean.tax_override_ids)
