from psycopg import IntegrityError

from odoo import Command, fields
from odoo.exceptions import ValidationError
from odoo.modules.module import get_module_path, load_script
from odoo.tests import Form, new_test_user, tagged
from odoo.tools import mute_logger

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.account.tests.common_report_engine import TestAccountReportsCommon


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
        self.tax_sale.invalidate_recordset(["is_tax_exigibility_enabled"])
        self.assertFalse(self.tax_sale.is_tax_exigibility_enabled)
        config.tax_exigibility = True
        self.tax_sale.invalidate_recordset(["is_tax_exigibility_enabled"])
        self.assertTrue(self.tax_sale.is_tax_exigibility_enabled)

    def test_tax_totals_amounts_carry_no_float_noise(self):
        invoice = self._invoice([("A", 10.2, self.tax_sale)])
        tax_totals = invoice.tax_totals
        self.assertEqual(tax_totals["total_amount_currency"], 11.73)
        self.assertEqual(tax_totals["total_amount"], 11.73)
        self.assertEqual(tax_totals["subtotals"][0]["base_amount_currency"], 10.2)


@tagged("post_install", "-at_install")
class TestMarinTaxLineGroupingKeyOrder(AccountTestInvoicingCommon):
    def _tag(self, name):
        return self.env["account.account.tag"].create(
            {
                "name": name,
                "applicability": "taxes",
                "country_id": self.env.company.tax_config_id.account_fiscal_country_id.id,
            }
        )

    def _repartition(self, base_tags=None, tax_tags=None):
        tax_account = self.company_data["default_account_tax_sale"]
        return [
            Command.create(
                {
                    "repartition_type": "base",
                    "tag_ids": [Command.set((base_tags or self._tag_model()).ids)],
                }
            ),
            Command.create(
                {
                    "repartition_type": "tax",
                    "account_id": tax_account.id,
                    "tag_ids": [Command.set((tax_tags or self._tag_model()).ids)],
                }
            ),
        ]

    def _tag_model(self):
        return self.env["account.account.tag"]

    def _tax(self, name, sequence, amount, base_tags=None, tax_tags=None, **vals):
        return self.env["account.tax"].create(
            {
                "name": name,
                "sequence": sequence,
                "amount_type": "percent",
                "amount": amount,
                "type_tax_use": "sale",
                "invoice_repartition_line_ids": self._repartition(base_tags, tax_tags),
                "refund_repartition_line_ids": self._repartition(base_tags, tax_tags),
                **vals,
            }
        )

    def _assert_tax_lines_survive_resync(self, taxes):
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner_a.id,
                "invoice_date": "2026-01-01",
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "line",
                            "quantity": 1,
                            "price_unit": 100.0,
                            "tax_ids": [Command.set(taxes.ids)],
                        }
                    )
                ],
            }
        )
        tax_lines = invoice.line_ids.filtered("tax_repartition_line_id")
        self.assertEqual(len(tax_lines), len(taxes))
        invoice.invoice_line_ids.price_unit = 200.0
        self.assertEqual(
            invoice.line_ids.filtered("tax_repartition_line_id"), tax_lines
        )
        self.assertTrue(tax_lines.exists() == tax_lines)

    def test_tax_line_kept_when_own_tag_sorts_after_subsequent_base_tag(self):
        later_base_tag = self._tag("later base")
        own_tax_tag = self._tag("own tax")
        self.assertGreater(own_tax_tag.id, later_base_tag.id)
        affecting = self._tax(
            "affecting", 1, 10.0, tax_tags=own_tax_tag, include_base_amount=True
        )
        affected = self._tax("affected", 2, 15.0, base_tags=later_base_tag)
        self._assert_tax_lines_survive_resync(affecting + affected)

    def test_tax_line_kept_when_several_taxes_are_affected(self):
        affecting = self._tax("affecting", 1, 10.0, include_base_amount=True)
        first = self._tax("first", 2, 15.0)
        second = self._tax("second", 3, 5.0)
        self._assert_tax_lines_survive_resync(affecting + first + second)


@tagged("post_install", "-at_install")
class TestMarinTaxIsUsed(AccountTestInvoicingCommon):
    def test_tax_referenced_only_by_a_tax_line_is_used(self):
        tax = self.company_data["default_tax_sale"].copy({"name": "tax line only"})
        tax_rep = tax.invoice_repartition_line_ids.filtered(
            lambda line: line.repartition_type == "tax"
        )
        entry = self.env["account.move"].create(
            {
                "move_type": "entry",
                "journal_id": self.company_data["default_journal_misc"].id,
                "date": "2026-01-01",
                "line_ids": [
                    Command.create(
                        {
                            "name": "tax",
                            "account_id": tax_rep.account_id.id,
                            "balance": -15.0,
                            "tax_repartition_line_id": tax_rep.id,
                        }
                    ),
                    Command.create(
                        {
                            "name": "counterpart",
                            "account_id": self.company_data[
                                "default_account_receivable"
                            ].id,
                            "balance": 15.0,
                        }
                    ),
                ],
            }
        )
        self.assertEqual(entry.line_ids.tax_line_id, tax)
        self.assertFalse(entry.line_ids.tax_ids)
        self.assertTrue(tax.is_used)
        with self.assertRaisesRegex(ValidationError, "currently in use"):
            tax.unlink()


@tagged("post_install", "-at_install")
class TestMarinTaxUnitHorizontalGroup(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.members = cls.env["res.company"].create(
            [{"name": "Unit member B"}, {"name": "Unit member C"}]
        )
        cls.env.user.company_ids = [Command.link(company.id) for company in cls.members]

    def _unit(self, name, country="base.be", vat="BE0999999922"):
        return self.env["account.tax.unit"].create(
            {
                "name": name,
                "country_id": self.env.ref(country).id,
                "vat": vat,
                "company_ids": [Command.set(self.members.ids)],
                "main_company_id": self.members[0].id,
            }
        )

    def _group(self, unit):
        return self.env["account.report.horizontal.group"].search(
            [
                (
                    "rule_ids.domain",
                    "=",
                    f"[('account_config_id.account_tax_unit_ids', 'in', {unit.id})]",
                ),
            ]
        )

    def test_renaming_a_unit_renames_its_horizontal_group(self):
        unit = self._unit("Unit before")
        group = self._group(unit)
        self.assertEqual(group.name, "Unit before")
        unit.name = "Unit after"
        self.assertEqual(group.name, "Unit after")
        self.assertFalse(
            self.env["account.report.horizontal.group"].search(
                [("name", "=", "Unit before")]
            )
        )

    def test_deleting_a_unit_deletes_its_horizontal_group(self):
        unit = self._unit("Unit deleted")
        group = self._group(unit)
        tax_report = self.env.ref("account.generic_tax_report")
        self.assertIn(group, tax_report.horizontal_group_ids)
        unit.unlink()
        self.assertFalse(group.exists())
        self.assertTrue(self._unit("Unit deleted"))

    def test_moving_a_unit_moves_its_group_between_country_variants(self):
        be_variant, nl_variant = self.env["report.formula"].create(
            [
                {
                    "name": f"tax report {country.code}",
                    "root_report_id": self.env.ref("account.generic_tax_report").id,
                    "country_id": country.id,
                }
                for country in (self.env.ref("base.be"), self.env.ref("base.nl"))
            ]
        )
        unit = self._unit("Unit moved")
        group = self._group(unit)
        self.assertIn(group, be_variant.horizontal_group_ids)
        self.assertNotIn(group, nl_variant.horizontal_group_ids)
        unit.write({"country_id": self.env.ref("base.nl").id, "vat": "NL000099998B57"})
        self.assertNotIn(group, be_variant.horizontal_group_ids)
        self.assertIn(group, nl_variant.horizontal_group_ids)

    def test_unit_is_linked_to_the_horizontal_group_it_creates(self):
        unit = self._unit("Unit linked")
        self.assertEqual(unit.horizontal_group_id, self._group(unit))
        self.assertEqual(unit.horizontal_group_id.name, "Unit linked")

    def test_edited_rule_domain_keeps_the_group_linked(self):
        unit = self._unit("Unit edited domain")
        group = unit.horizontal_group_id
        group.rule_ids.domain = (
            f"[('account_config_id.account_tax_unit_ids', 'in', [{unit.id}])]"
        )
        unit.name = "Unit edited domain renamed"
        self.assertEqual(group.name, "Unit edited domain renamed")
        unit.unlink()
        self.assertFalse(group.exists())

    def _foreign_group(self, name):
        return self.env["account.report.horizontal.group"].create(
            {
                "name": name,
                "rule_ids": [
                    Command.create({"field_name": "company_id", "domain": "[]"})
                ],
            }
        )

    def test_renaming_a_unit_to_a_taken_group_name_is_refused(self):
        self._foreign_group("Unit taken")
        unit = self._unit("Unit free")
        with self.assertRaisesRegex(ValidationError, "Unit taken"):
            unit.name = "Unit taken"
        self.assertEqual(unit.horizontal_group_id.name, "Unit free")

    def test_member_company_manager_renames_a_unit_and_its_group(self):
        unit = self._unit("Unit managed")
        self._foreign_group("Unit managed taken")
        manager = new_test_user(
            self.env,
            login="tax_unit_member_manager",
            groups="account.group_account_manager",
            company_id=self.members[0].id,
            company_ids=self.members.ids,
        )
        managed = unit.with_user(manager)
        managed.name = "Unit managed renamed"
        self.assertEqual(unit.horizontal_group_id.name, "Unit managed renamed")
        with self.assertRaisesRegex(ValidationError, "Unit managed taken"):
            managed.name = "Unit managed taken"

    def test_creating_a_unit_with_a_taken_group_name_is_refused(self):
        self._foreign_group("Unit taken at create")
        with self.assertRaisesRegex(ValidationError, "Unit taken at create"):
            self._unit("Unit taken at create")

    def _unlink_groups_and_migrate(self, units):
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE account_tax_unit SET horizontal_group_id = NULL WHERE id = ANY(%s)",
            [units.ids],
        )
        self.env.invalidate_all()
        self.assertFalse(units.horizontal_group_id)
        script = load_script(
            f"{get_module_path('account')}/migrations/1.46/post-10-tax_unit_horizontal_group.py",
            "odoo.addons.account.migrations.post_10_tax_unit_horizontal_group_1_46",
        )
        script.migrate(self.env.cr, "1.45")
        self.env.invalidate_all()

    def test_migration_links_a_unit_to_its_group_by_rule_domain(self):
        linked = self._unit("Unit migrated")
        linked_group = linked.horizontal_group_id
        self._unlink_groups_and_migrate(linked)
        self.assertEqual(linked.horizontal_group_id, linked_group)

    def test_migration_links_a_unit_with_an_edited_domain_by_group_name(self):
        edited = self._unit("Unit edited before upgrade")
        renamed = self._unit("Unit renamed before upgrade", "base.nl", "NL000099998B57")
        edited_group = edited.horizontal_group_id
        edited_group.rule_ids.domain = (
            f"[('account_config_id.account_tax_unit_ids', 'in', [{edited.id}])]"
        )
        renamed.horizontal_group_id.rule_ids.domain = "[]"
        renamed.horizontal_group_id.name = "Group renamed by hand"
        self._unlink_groups_and_migrate(edited | renamed)
        self.assertEqual(edited.horizontal_group_id, edited_group)
        self.assertFalse(renamed.horizontal_group_id)

    def test_migration_leaves_a_group_named_like_two_units_unlinked(self):
        first = self._unit("Unit twin")
        second = self._unit("Unit twin second", "base.nl", "NL000099998B57")
        (first | second).horizontal_group_id.rule_ids.domain = "[]"
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE account_tax_unit SET name = 'Unit twin' WHERE id = %s",
            [second.id],
        )
        self._unlink_groups_and_migrate(first | second)
        self.assertFalse((first | second).horizontal_group_id)

    def _orphan(self, unit):
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE account_tax_unit SET horizontal_group_id = NULL WHERE id = %s",
            [unit.id],
        )
        self.env.invalidate_all()

    def test_unit_without_a_group_renames_freely(self):
        unit = self._unit("Unit orphaned")
        self._orphan(unit)
        unit.name = "Unit orphaned renamed"
        unit.name = "Unit orphaned"
        self._foreign_group("Unit orphaned foreign")
        unit.name = "Unit orphaned foreign"
        self.assertEqual(unit.name, "Unit orphaned foreign")

    def test_group_names_are_checked_against_their_source_value(self):
        self.env["res.lang"]._activate_lang("fr_FR")
        foreign = self._foreign_group("Unit english source")
        foreign.update_field_translations("name", {"fr_FR": "Unite traduite"})
        french = self.env(context=dict(self.env.context, lang="fr_FR"))
        units = self.env["account.tax.unit"].with_env(french)
        with self.assertRaisesRegex(ValidationError, "Unit english source"):
            units.create(
                {
                    "name": "Unit english source",
                    "country_id": self.env.ref("base.be").id,
                    "vat": "BE0999999922",
                    "company_ids": [Command.set(self.members.ids)],
                    "main_company_id": self.members[0].id,
                }
            )
        unit = units.create(
            {
                "name": "Unite traduite",
                "country_id": self.env.ref("base.nl").id,
                "vat": "NL000099998B57",
                "company_ids": [Command.set(self.members.ids)],
                "main_company_id": self.members[0].id,
            }
        )
        self.assertEqual(
            unit.horizontal_group_id.with_context(lang="en_US").name,
            "Unite traduite",
        )

    def test_renaming_a_unit_in_another_language_renames_every_group_value(self):
        unit = self._unit("Unit before french rename")
        self.env["res.lang"]._activate_lang("fr_FR")
        unit.with_context(lang="fr_FR").name = "Unit after french rename"
        group = unit.horizontal_group_id
        self.assertEqual(
            group.with_context(lang="en_US").name, "Unit after french rename"
        )
        self.assertEqual(
            group.with_context(lang="fr_FR").name, "Unit after french rename"
        )
        self.assertTrue(
            self._unit("Unit before french rename", "base.nl", "NL000099998B57")
        )


@tagged("post_install", "-at_install")
class TestMarinFiscalPositionAccountMapping(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.src = cls.company_data["default_account_revenue"]
        cls.dest_1 = cls.src.copy()
        cls.dest_2 = cls.src.copy()
        cls.fiscal_position = cls.env["account.fiscal.position"].create(
            {
                "name": "mapping",
                "account_ids": [
                    Command.create(
                        {"account_src_id": cls.src.id, "account_dest_id": cls.dest_1.id}
                    )
                ],
            }
        )

    def test_one_source_account_maps_to_one_destination(self):
        with self.assertRaises(IntegrityError), mute_logger("odoo.db.cursor"):
            self.fiscal_position.account_ids = [
                Command.create(
                    {"account_src_id": self.src.id, "account_dest_id": self.dest_2.id}
                )
            ]
            self.env.flush_all()

    def test_chart_reload_redirects_an_existing_mapping(self):
        self.env["ir.model.data"]._update_xmlids(
            [
                {"xml_id": "account.marin_fp_src", "record": self.src},
                {"xml_id": "account.marin_fp_dest", "record": self.dest_2},
            ]
        )
        command = self.env["account.chart.template"]._reload_account_mapping_command(
            self.fiscal_position,
            Command.create(
                {
                    "account_src_id": "account.marin_fp_src",
                    "account_dest_id": "account.marin_fp_dest",
                }
            ),
        )
        self.assertEqual(
            command,
            Command.update(
                self.fiscal_position.account_ids.id,
                {"account_dest_id": "account.marin_fp_dest"},
            ),
        )


@tagged("post_install", "-at_install")
class TestMarinTaxLineAggregationFlags(AccountTestInvoicingCommon):
    def _base_lines(self, tax, price_units):
        AccountTax = self.env["account.tax"]
        company = self.env.company
        base_lines = [
            AccountTax._prepare_base_line_for_taxes_computation(
                None,
                tax_ids=tax,
                price_unit=price_unit,
                quantity=1.0,
                currency_id=company.currency_id,
                partner_id=self.partner_a,
                account_id=self.company_data["default_account_revenue"],
            )
            for price_unit in price_units
        ]
        AccountTax._add_tax_details_in_base_lines(base_lines, company)
        AccountTax._round_base_lines_tax_details(base_lines, company)
        AccountTax._add_accounting_data_in_base_lines_tax_details(base_lines, company)
        return base_lines

    def test_keep_zero_line_flag_does_not_split_the_aggregation(self):
        tax = self.company_data["default_tax_sale"]
        self.assertEqual(tax.amount, 15.0)
        base_lines = self._base_lines(tax, (100.0, 200.0))
        for tax_data in base_lines[1]["tax_details"]["taxes_data"]:
            for tax_rep_data in tax_data["tax_reps_data"]:
                tax_rep_data["grouping_key"] = {
                    **tax_rep_data["grouping_key"],
                    "__keep_zero_line": True,
                }
        tax_lines = self.env["account.tax"]._prepare_tax_lines(
            base_lines, self.env.company
        )["tax_lines_to_add"]
        self.assertEqual(len(tax_lines), 1)
        self.assertAlmostEqual(tax_lines[0]["amount_currency"], 45.0)
        self.assertAlmostEqual(tax_lines[0]["tax_base_amount"], 300.0)
        self.assertFalse([key for key in tax_lines[0] if key.startswith("__")])

    def test_keep_zero_line_flag_survives_merging_with_an_unflagged_entry(self):
        tax = self.company_data["default_tax_sale"].copy(
            {"name": "zero rate", "amount": 0.0}
        )
        base_lines = self._base_lines(tax, (100.0, 200.0))
        AccountTax = self.env["account.tax"]
        self.assertFalse(
            AccountTax._prepare_tax_lines(base_lines, self.env.company)[
                "tax_lines_to_add"
            ]
        )
        for tax_data in base_lines[1]["tax_details"]["taxes_data"]:
            for tax_rep_data in tax_data["tax_reps_data"]:
                tax_rep_data["grouping_key"] = {
                    **tax_rep_data["grouping_key"],
                    "__keep_zero_line": True,
                }
        tax_lines = AccountTax._prepare_tax_lines(base_lines, self.env.company)[
            "tax_lines_to_add"
        ]
        self.assertEqual(len(tax_lines), 1)
        self.assertAlmostEqual(tax_lines[0]["tax_base_amount"], 300.0)

    def test_base_line_grouping_key_ignores_tax_order(self):
        AccountTax = self.env["account.tax"]
        taxes = self.company_data["default_tax_sale"] | self.tax_sale_b
        keys = [
            AccountTax._prepare_base_line_grouping_key(
                AccountTax._prepare_base_line_for_taxes_computation(
                    None,
                    tax_ids=ordered,
                    currency_id=self.env.company.currency_id,
                    partner_id=self.partner_a,
                )
            )
            for ordered in (taxes, taxes.browse(reversed(taxes.ids)))
        ]
        self.assertEqual(keys[0], keys[1])


@tagged("post_install", "-at_install")
class TestMarinTaxLineLabelOnResync(AccountTestInvoicingCommon):
    def _invoice(self, tax):
        return self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner_a.id,
                "invoice_date": "2026-01-01",
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "line",
                            "quantity": 1,
                            "price_unit": 100.0,
                            "tax_ids": [Command.set(tax.ids)],
                        }
                    )
                ],
            }
        )

    @staticmethod
    def _tax_line(invoice):
        return invoice.line_ids.filtered(lambda line: line.display_type == "tax")

    def test_resync_keeps_a_manually_edited_tax_line_label(self):
        tax = self.company_data["default_tax_sale"]
        invoice = self._invoice(tax)
        tax_line = self._tax_line(invoice)
        self.assertFalse(tax_line.is_name_manual)
        invoice.write(
            {"line_ids": [Command.update(tax_line.id, {"name": "Edited label"})]}
        )
        self.assertTrue(tax_line.is_name_manual)
        invoice.invoice_line_ids.price_unit = 200.0
        self.assertEqual(self._tax_line(invoice), tax_line)
        self.assertEqual(tax_line.name, "Edited label")
        self.assertAlmostEqual(tax_line.amount_currency, -200.0 * tax.amount / 100)

    def test_resync_rewrites_an_unedited_tax_line_label_from_the_tax(self):
        tax = self.company_data["default_tax_sale"]
        invoice = self._invoice(tax)
        tax_line = self._tax_line(invoice)
        tax.name = "Renamed tax"
        invoice.invoice_line_ids.price_unit = 200.0
        self.assertEqual(tax_line.name, "Renamed tax")
        self.assertFalse(tax_line.is_name_manual)

    def test_changed_tax_recreates_the_line_with_the_new_tax_label(self):
        tax = self.company_data["default_tax_sale"]
        other_tax = tax.copy({"name": "Other tax", "amount": 10.0})
        invoice = self._invoice(tax)
        self._tax_line(invoice).name = "Edited label"
        invoice.invoice_line_ids.tax_ids = other_tax
        new_tax_line = self._tax_line(invoice)
        self.assertEqual(new_tax_line.tax_line_id, other_tax)
        self.assertEqual(new_tax_line.name, "Other tax")
        self.assertFalse(new_tax_line.is_name_manual)

    def test_label_edited_in_the_form_survives_a_price_change(self):
        tax = self.company_data["default_tax_sale"]
        invoice = self._invoice(tax)
        tax_line = self._tax_line(invoice)
        index = invoice.line_ids.ids.index(tax_line.id)
        with Form(invoice) as move_form:
            with move_form.line_ids.edit(index) as line_form:
                line_form.name = "Edited in form"
        self.assertEqual(tax_line.name, "Edited in form")
        self.assertTrue(tax_line.is_name_manual)
        with Form(invoice) as move_form:
            with move_form.invoice_line_ids.edit(0) as line_form:
                line_form.price_unit = 300.0
        self.assertEqual(self._tax_line(invoice), tax_line)
        self.assertEqual(tax_line.name, "Edited in form")
        self.assertAlmostEqual(tax_line.amount_currency, -300.0 * tax.amount / 100)

    def test_label_edited_in_the_form_survives_a_price_change_in_the_same_form(self):
        tax = self.company_data["default_tax_sale"]
        invoice = self._invoice(tax)
        tax_line = self._tax_line(invoice)
        index = invoice.line_ids.ids.index(tax_line.id)
        with Form(invoice) as move_form:
            with move_form.line_ids.edit(index) as line_form:
                line_form.name = "Edited in form"
            with move_form.invoice_line_ids.edit(0) as line_form:
                line_form.price_unit = 300.0
        self.assertEqual(self._tax_line(invoice), tax_line)
        self.assertEqual(tax_line.name, "Edited in form")
        self.assertTrue(tax_line.is_name_manual)
        self.assertAlmostEqual(tax_line.amount_currency, -300.0 * tax.amount / 100)

    def test_clearing_an_edited_label_gives_the_label_back_to_the_tax(self):
        tax = self.company_data["default_tax_sale"]
        invoice = self._invoice(tax)
        tax_line = self._tax_line(invoice)
        tax_line.name = "Edited label"
        tax_line.name = False
        self.assertFalse(tax_line.is_name_manual)
        invoice.invoice_line_ids.price_unit = 200.0
        self.assertEqual(tax_line.name, tax.name)

    def test_typing_the_tax_label_back_follows_later_tax_renames(self):
        tax = self.company_data["default_tax_sale"]
        invoice = self._invoice(tax)
        tax_line = self._tax_line(invoice)
        tax_line.name = "Edited label"
        tax_line.name = tax.name
        self.assertFalse(tax_line.is_name_manual)
        tax.name = "Renamed tax"
        invoice.invoice_line_ids.price_unit = 200.0
        self.assertEqual(tax_line.name, "Renamed tax")
        self.assertFalse(tax_line.is_name_manual)

    def test_tax_label_in_another_installed_language_is_not_manual(self):
        self.env["res.lang"]._activate_lang("es_ES")
        tax = self.company_data["default_tax_sale"]
        tax.with_context(lang="es_ES").name = "Impuesto de venta"
        invoice = self._invoice(tax)
        tax_line = self._tax_line(invoice)
        tax_line.name = "Impuesto de venta"
        self.assertFalse(tax_line.is_name_manual)
        invoice.invoice_line_ids.price_unit = 200.0
        self.assertEqual(tax_line.name, tax.with_context(lang="en_US").name)

    def _journal_entry(self, tax):
        tax_rep = tax.invoice_repartition_line_ids.filtered(
            lambda rep: rep.repartition_type == "tax"
        )
        rate = tax.amount / 100
        return self.env["account.move"].create(
            {
                "move_type": "entry",
                "line_ids": [
                    Command.create(
                        {
                            "name": "base",
                            "account_id": self.company_data[
                                "default_account_revenue"
                            ].id,
                            "balance": -100.0,
                            "tax_ids": [Command.set(tax.ids)],
                        }
                    ),
                    Command.create(
                        {
                            "name": tax.name,
                            "account_id": tax_rep.account_id.id,
                            "balance": -100.0 * rate,
                            "tax_repartition_line_id": tax_rep.id,
                        }
                    ),
                    Command.create(
                        {
                            "name": "counterpart",
                            "account_id": self.company_data[
                                "default_account_receivable"
                            ].id,
                            "balance": 100.0 * (1 + rate),
                        }
                    ),
                ],
            }
        )

    def test_resync_keeps_an_edited_label_on_a_journal_entry_tax_line(self):
        tax = self.company_data["default_tax_sale"]
        rate = tax.amount / 100
        entry = self._journal_entry(tax)
        base_line, tax_line, counterpart = entry.line_ids.sorted("id")
        self.assertEqual(tax_line.display_type, "product")
        tax_line.name = "Edited label"
        self.assertTrue(tax_line.is_name_manual)
        entry.write(
            {
                "line_ids": [
                    Command.update(base_line.id, {"balance": -200.0}),
                    Command.update(counterpart.id, {"balance": 200.0 * (1 + rate)}),
                ]
            }
        )
        self.assertEqual(entry.line_ids.filtered("tax_repartition_line_id"), tax_line)
        self.assertAlmostEqual(tax_line.balance, -200.0 * rate)
        self.assertEqual(tax_line.name, "Edited label")

    def _tax_and_base_lines(self, move):
        return move.line_ids.filtered(
            lambda line: line.tax_repartition_line_id or line.tax_ids
        )

    def test_journal_entry_lines_relabelled_and_repartnered_in_one_write(self):
        entry = self._journal_entry(self.company_data["default_tax_sale"])
        base_line, tax_line, counterpart = entry.line_ids.sorted("id")
        entry.line_ids.write({"name": "Relabelled", "partner_id": self.partner_b.id})
        self.assertEqual(entry.line_ids.filtered("tax_repartition_line_id"), tax_line)
        self.assertEqual(entry.line_ids.mapped("name"), ["Relabelled"] * 3)
        self.assertEqual(entry.line_ids.partner_id, self.partner_b)
        self.assertTrue(tax_line.is_name_manual)
        self.assertFalse((base_line + counterpart).filtered("is_name_manual"))

    def test_journal_entry_lines_relabelled_and_moved_in_one_write(self):
        tax = self.company_data["default_tax_sale"]
        account = self.copy_account(self.company_data["default_account_revenue"])
        for vals in (
            {"account_id": account.id},
            {"name": "Relabelled", "account_id": account.id},
        ):
            with self.subTest(fields=sorted(vals)):
                entry = self._journal_entry(tax)
                base_line, tax_line = self._tax_and_base_lines(entry).sorted("id")
                tax_account = tax_line.account_id
                (base_line + tax_line).write(vals)
                self.assertEqual(base_line.name, vals.get("name", "base"))
                self.assertEqual(base_line.account_id, account)
                self.assertFalse(tax_line.exists())
                new_tax_line = entry.line_ids.filtered("tax_repartition_line_id")
                self.assertEqual(new_tax_line.account_id, tax_account)
                self.assertEqual(new_tax_line.name, tax.name)
                self.assertFalse(new_tax_line.is_name_manual)

    def test_journal_entry_lines_relabelled_and_retaxed_in_one_write(self):
        tax = self.company_data["default_tax_sale"]
        other_tax = tax.copy({"name": "Other tax", "amount": 10.0})
        entry = self._journal_entry(tax)
        base_line, tax_line = self._tax_and_base_lines(entry).sorted("id")
        (base_line + tax_line).write(
            {"name": "Relabelled", "tax_ids": [Command.set(other_tax.ids)]}
        )
        self.assertEqual(base_line.name, "Relabelled")
        self.assertEqual(base_line.tax_ids, other_tax)
        self.assertFalse(tax_line.exists())
        new_tax_line = entry.line_ids.filtered("tax_repartition_line_id")
        self.assertEqual(new_tax_line.tax_line_id, other_tax)
        self.assertEqual(new_tax_line.name, "Other tax")
        self.assertFalse(new_tax_line.is_name_manual)
        self.assertAlmostEqual(new_tax_line.balance, -10.0)

    def test_invoice_lines_relabelled_and_repartnered_in_one_write(self):
        invoice = self._invoice(self.company_data["default_tax_sale"])
        product_line = invoice.invoice_line_ids
        tax_line = self._tax_line(invoice)
        (product_line + tax_line).write(
            {"name": "Relabelled", "partner_id": self.partner_b.id}
        )
        self.assertEqual(self._tax_line(invoice), tax_line)
        self.assertEqual((product_line + tax_line).mapped("name"), ["Relabelled"] * 2)
        self.assertEqual((product_line + tax_line).partner_id, self.partner_b)
        self.assertTrue(tax_line.is_name_manual)
        self.assertFalse(product_line.is_name_manual)

    def test_invoice_lines_relabelled_and_moved_in_one_write(self):
        tax = self.company_data["default_tax_sale"]
        invoice = self._invoice(tax)
        product_line = invoice.invoice_line_ids
        tax_line = self._tax_line(invoice)
        tax_account = tax_line.account_id
        account = self.copy_account(self.company_data["default_account_revenue"])
        (product_line + tax_line).write(
            {"name": "Relabelled", "account_id": account.id}
        )
        self.assertEqual(product_line.name, "Relabelled")
        self.assertEqual(product_line.account_id, account)
        self.assertFalse(tax_line.exists())
        new_tax_line = self._tax_line(invoice)
        self.assertEqual(new_tax_line.account_id, tax_account)
        self.assertEqual(new_tax_line.name, tax.name)
        self.assertFalse(new_tax_line.is_name_manual)

    def test_invoice_lines_relabelled_and_retaxed_in_one_write(self):
        tax = self.company_data["default_tax_sale"]
        other_tax = tax.copy({"name": "Other tax", "amount": 10.0})
        invoice = self._invoice(tax)
        product_line = invoice.invoice_line_ids
        tax_line = self._tax_line(invoice)
        (product_line + tax_line).write(
            {"name": "Relabelled", "tax_ids": [Command.set(other_tax.ids)]}
        )
        self.assertEqual(product_line.name, "Relabelled")
        self.assertEqual(product_line.tax_ids, other_tax)
        self.assertFalse(tax_line.exists())
        new_tax_line = self._tax_line(invoice)
        self.assertEqual(new_tax_line.tax_line_id, other_tax)
        self.assertEqual(new_tax_line.name, "Other tax")
        self.assertFalse(new_tax_line.is_name_manual)
        self.assertAlmostEqual(invoice.amount_tax, 10.0)

    def test_journal_entry_tax_line_retaxed_alone_keeps_the_amounts(self):
        tax = self.company_data["default_tax_sale"]
        other_tax = tax.copy({"name": "Other tax", "amount": 10.0})
        entry = self._journal_entry(tax)
        base_line, tax_line = self._tax_and_base_lines(entry).sorted("id")
        tax_line.tax_ids = other_tax
        self.assertEqual(entry.line_ids.filtered("tax_repartition_line_id"), tax_line)
        self.assertEqual(tax_line.tax_ids, other_tax)
        self.assertAlmostEqual(tax_line.balance, -15.0)
        self.assertAlmostEqual(base_line.balance, -100.0)

    def test_invoice_tax_line_retaxed_alone_keeps_the_amounts(self):
        tax = self.company_data["default_tax_sale"]
        other_tax = tax.copy({"name": "Other tax", "amount": 10.0})
        invoice = self._invoice(tax)
        tax_line = self._tax_line(invoice)
        tax_line.tax_ids = other_tax
        self.assertEqual(self._tax_line(invoice), tax_line)
        self.assertEqual(tax_line.tax_ids, other_tax)
        self.assertAlmostEqual(invoice.amount_tax, 15.0)

    def _affected_tax_chain(self):
        include_tax = self.env["account.tax"].create(
            {
                "name": "Included 10%",
                "amount": 10.0,
                "type_tax_use": "sale",
                "include_base_amount": True,
            }
        )
        affected_tax = self.env["account.tax"].create(
            {
                "name": "Affected 20%",
                "amount": 20.0,
                "type_tax_use": "sale",
                "is_base_affected": True,
            }
        )
        return include_tax, affected_tax

    @staticmethod
    def _tax_repartition_line(tax):
        return tax.invoice_repartition_line_ids.filtered(
            lambda rep: rep.repartition_type == "tax"
        )

    def _tax_line_balances(self, move):
        return {
            line.tax_line_id: line.balance
            for line in move.line_ids.filtered("tax_repartition_line_id")
        }

    def test_journal_entry_affected_tax_chain_built_by_the_sync(self):
        include_tax, affected_tax = self._affected_tax_chain()
        entry = self.env["account.move"].create(
            {
                "move_type": "entry",
                "line_ids": [
                    Command.create(
                        {
                            "name": "base",
                            "account_id": self.company_data[
                                "default_account_revenue"
                            ].id,
                            "balance": -100.0,
                            "tax_ids": [Command.set((include_tax + affected_tax).ids)],
                        }
                    ),
                    Command.create(
                        {
                            "name": "counterpart",
                            "account_id": self.company_data[
                                "default_account_receivable"
                            ].id,
                            "balance": 100.0,
                        }
                    ),
                ],
            }
        )
        include_tax_line = entry.line_ids.filtered(
            lambda line: line.tax_line_id == include_tax
        )
        self.assertEqual(include_tax_line.tax_ids, affected_tax)
        entry.line_ids.filtered(lambda line: line.name == "base").balance = -200.0
        self.assertEqual(
            self._tax_line_balances(entry),
            {include_tax: -20.0, affected_tax: -44.0},
        )

    def test_journal_entry_encoded_affected_tax_chain_is_not_counted_twice(self):
        include_tax, affected_tax = self._affected_tax_chain()
        revenue = self.company_data["default_account_revenue"]
        entry = self.env["account.move"].create(
            {
                "move_type": "entry",
                "line_ids": [
                    Command.create(
                        {
                            "name": "base",
                            "account_id": revenue.id,
                            "balance": -100.0,
                            "tax_ids": [Command.set((include_tax + affected_tax).ids)],
                        }
                    ),
                    Command.create(
                        {
                            "name": include_tax.name,
                            "account_id": revenue.id,
                            "balance": -10.0,
                            "tax_repartition_line_id": self._tax_repartition_line(
                                include_tax
                            ).id,
                            "tax_ids": [Command.set(affected_tax.ids)],
                        }
                    ),
                    Command.create(
                        {
                            "name": affected_tax.name,
                            "account_id": revenue.id,
                            "balance": -22.0,
                            "tax_repartition_line_id": self._tax_repartition_line(
                                affected_tax
                            ).id,
                        }
                    ),
                    Command.create(
                        {
                            "name": "counterpart",
                            "account_id": self.company_data[
                                "default_account_receivable"
                            ].id,
                            "balance": 132.0,
                        }
                    ),
                ],
            }
        )
        entry.line_ids.filtered(lambda line: line.name == "base").balance = -200.0
        self.assertEqual(
            self._tax_line_balances(entry),
            {include_tax: -20.0, affected_tax: -44.0},
        )

    def _relabelled_tax_line(self, move):
        tax_line = move.line_ids.filtered("tax_repartition_line_id")
        tax_line.name = "Edited label"
        return tax_line

    def test_reversed_and_duplicated_journal_entry_keep_the_edited_label(self):
        entry = self._journal_entry(self.company_data["default_tax_sale"])
        self._relabelled_tax_line(entry)
        entry.action_post()
        for move in (entry._reverse_moves(), entry.copy()):
            tax_line = move.line_ids.filtered("tax_repartition_line_id")
            self.assertEqual(tax_line.name, "Edited label")
            self.assertTrue(tax_line.is_name_manual)

    def test_credit_note_takes_the_tax_label_and_a_duplicated_invoice_keeps_it(self):
        tax = self.company_data["default_tax_sale"]
        invoice = self._invoice(tax)
        self._relabelled_tax_line(invoice)
        invoice.action_post()
        credit_note_tax_line = self._tax_line(invoice._reverse_moves())
        self.assertEqual(credit_note_tax_line.name, tax.name)
        self.assertFalse(credit_note_tax_line.is_name_manual)
        copy_tax_line = self._tax_line(invoice.copy())
        self.assertEqual(copy_tax_line.name, "Edited label")
        self.assertTrue(copy_tax_line.is_name_manual)


@tagged("post_install", "-at_install")
class TestMarinHandEncodedTaxEntry(TestAccountReportsCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        country = cls.env.company.account_fiscal_country_id
        cls.report = cls.env["report.formula"].create(
            {
                "name": "Hand-encoded grids",
                "country_id": country.id,
                "filter_date_range": True,
                "column_ids": [
                    Command.create({"name": "balance", "expression_label": "balance"})
                ],
                "line_ids": [
                    Command.create(
                        {
                            "name": grid,
                            "sequence": sequence,
                            "expression_ids": [
                                Command.create(
                                    {
                                        "label": "balance",
                                        "engine": "tax_tags",
                                        "formula": grid,
                                        "date_scope": "strict_range",
                                    }
                                )
                            ],
                        }
                    )
                    for sequence, grid in enumerate(("HB", "HT"))
                ],
            }
        )
        tags = cls.env["account.account.tag"].search(
            [
                ("applicability", "=", "taxes"),
                ("country_id", "=", country.id),
                ("name", "in", ["HB", "HT"]),
            ]
        )
        cls.base_tag = tags.filtered(lambda tag: tag.name == "HB")
        cls.tax_tag = tags.filtered(lambda tag: tag.name == "HT")
        cls.tax = cls.env["account.tax"].create(
            {
                "name": "Grid tax 10%",
                "amount": 10.0,
                "type_tax_use": "sale",
                "country_id": country.id,
                "invoice_repartition_line_ids": [
                    Command.create(
                        {
                            "repartition_type": "base",
                            "tag_ids": [Command.set(cls.base_tag.ids)],
                        }
                    ),
                    Command.create(
                        {
                            "repartition_type": "tax",
                            "tag_ids": [Command.set(cls.tax_tag.ids)],
                        }
                    ),
                ],
                "refund_repartition_line_ids": [
                    Command.create({"repartition_type": "base"}),
                    Command.create({"repartition_type": "tax"}),
                ],
            }
        )
        cls.tax_rep = cls.tax.invoice_repartition_line_ids.filtered(
            lambda rep: rep.repartition_type == "tax"
        )
        cls.revenue = cls.company_data["default_account_revenue"]
        cls.receivable = cls.company_data["default_account_receivable"]

    def _entry_lines(self, tax_balance=-10.0, base_balance=-100.0):
        return [
            {
                "name": "base",
                "account_id": self.revenue.id,
                "partner_id": self.partner_a.id,
                "balance": base_balance,
                "tax_ids": [Command.set(self.tax.ids)],
            },
            {
                "name": self.tax.name,
                "account_id": self.revenue.id,
                "partner_id": self.partner_a.id,
                "balance": tax_balance,
                "tax_repartition_line_id": self.tax_rep.id,
            },
            {
                "name": "counterpart",
                "account_id": self.receivable.id,
                "partner_id": self.partner_a.id,
                "balance": -base_balance - tax_balance,
            },
        ]

    def _hand_encoded_entry(self, date="2026-01-15", **kwargs):
        return self.env["account.move"].create(
            {
                "move_type": "entry",
                "date": date,
                "line_ids": [
                    Command.create(vals) for vals in self._entry_lines(**kwargs)
                ],
            }
        )

    def _synced_entry(self, date):
        base, _tax, counterpart = self._entry_lines()
        return self.env["account.move"].create(
            {
                "move_type": "entry",
                "date": date,
                "line_ids": [Command.create(base), Command.create(counterpart)],
            }
        )

    def _grids(self, date_from, date_to):
        options = self._generate_options(self.report, date_from, date_to)
        return {
            line["name"]: line["columns"][0]["no_format"]
            for line in self.report._get_lines(options)
        }

    @staticmethod
    def _base_and_tax_line(move):
        return (
            move.line_ids.filtered("tax_ids"),
            move.line_ids.filtered("tax_repartition_line_id"),
        )

    def test_hand_encoded_entry_lines_carry_the_tax_grids(self):
        entry = self._hand_encoded_entry()
        base_line, tax_line = self._base_and_tax_line(entry)
        self.assertEqual(base_line.tax_tag_ids, self.base_tag)
        self.assertEqual(tax_line.tax_tag_ids, self.tax_tag)
        synced = self._synced_entry("2026-02-15")
        synced_base_line, synced_tax_line = self._base_and_tax_line(synced)
        self.assertEqual(synced_base_line.tax_tag_ids, self.base_tag)
        self.assertEqual(synced_tax_line.tax_tag_ids, self.tax_tag)
        self.assertAlmostEqual(
            tax_line.tax_base_amount, synced_tax_line.tax_base_amount
        )
        (entry + synced).action_post()
        january = self._grids("2026-01-01", "2026-01-31")
        self.assertTrue(all(january.values()), january)
        self.assertEqual(january, self._grids("2026-02-01", "2026-02-28"))

    def test_hand_encoded_entry_keeps_its_typed_amounts(self):
        entry = self._hand_encoded_entry(tax_balance=-10.01)
        base_line, tax_line = self._base_and_tax_line(entry)
        self.assertAlmostEqual(base_line.balance, -100.0)
        self.assertAlmostEqual(tax_line.balance, -10.01)
        self.assertEqual(tax_line.tax_tag_ids, self.tax_tag)
        entry.action_post()
        self.assertAlmostEqual(
            abs(self._grids("2026-01-01", "2026-01-31")["HT"]), 10.01
        )

    def test_hand_encoded_tax_line_survives_a_rebase_with_its_edited_label(self):
        entry = self._hand_encoded_entry()
        base_line, tax_line = self._base_and_tax_line(entry)
        counterpart = entry.line_ids - base_line - tax_line
        tax_line.name = "Edited label"
        self.assertTrue(tax_line.is_name_manual)
        entry.write(
            {
                "line_ids": [
                    Command.update(base_line.id, {"balance": -200.0}),
                    Command.update(counterpart.id, {"balance": 220.0}),
                ]
            }
        )
        self.assertEqual(entry.line_ids.filtered("tax_repartition_line_id"), tax_line)
        self.assertEqual(tax_line.name, "Edited label")
        self.assertTrue(tax_line.is_name_manual)
        self.assertAlmostEqual(tax_line.balance, -20.0)
        self.assertEqual(tax_line.tax_tag_ids, self.tax_tag)

    def test_imported_journal_entry_carries_the_tax_grids(self):
        lines = self._entry_lines()
        result = self.env["account.move"].load(
            [
                "ref",
                "date",
                "journal_id/.id",
                "line_ids/name",
                "line_ids/account_id/.id",
                "line_ids/partner_id/.id",
                "line_ids/debit",
                "line_ids/credit",
                "line_ids/tax_ids/.id",
                "line_ids/tax_repartition_line_id/.id",
            ],
            [
                [
                    "imported" if index == 0 else "",
                    "2026-01-15" if index == 0 else "",
                    str(self.company_data["default_journal_misc"].id)
                    if index == 0
                    else "",
                    vals["name"],
                    str(vals["account_id"]),
                    str(vals["partner_id"]),
                    str(max(vals["balance"], 0.0)),
                    str(max(-vals["balance"], 0.0)),
                    str(self.tax.id) if "tax_ids" in vals else "",
                    str(vals.get("tax_repartition_line_id", "")),
                ]
                for index, vals in enumerate(lines)
            ],
        )
        self.assertFalse(result["messages"])
        entry = self.env["account.move"].browse(result["ids"])
        base_line, tax_line = self._base_and_tax_line(entry)
        self.assertEqual(base_line.tax_tag_ids, self.base_tag)
        self.assertEqual(tax_line.tax_tag_ids, self.tax_tag)
        self.assertAlmostEqual(tax_line.balance, -10.0)

    def _load_journal_items(self, move, fields, row):
        lines = move.line_ids.sorted("id")
        return lines, self.env["account.move.line"].load(
            [".id", *fields], [[str(line.id), *row] for line in lines]
        )

    def test_import_updating_journal_items_partner_and_label_applies_every_row(self):
        for entry in (self._synced_entry("2026-01-15"), self._hand_encoded_entry()):
            _base_line, tax_line = self._base_and_tax_line(entry)
            lines, result = self._load_journal_items(
                entry,
                ["name", "partner_id/.id"],
                ["Reimported", str(self.partner_b.id)],
            )
            self.assertFalse(result["messages"])
            self.assertEqual(entry.line_ids, lines)
            self.assertEqual(entry.line_ids.mapped("name"), ["Reimported"] * 3)
            self.assertEqual(entry.line_ids.partner_id, self.partner_b)
            self.assertTrue(tax_line.is_name_manual)
            self.assertAlmostEqual(tax_line.balance, -10.0)

    def test_import_updating_journal_items_partner_applies_every_row(self):
        entry = self._synced_entry("2026-01-15")
        lines, result = self._load_journal_items(
            entry, ["partner_id/.id"], [str(self.partner_b.id)]
        )
        self.assertFalse(result["messages"])
        self.assertEqual(entry.line_ids, lines)
        self.assertEqual(entry.line_ids.partner_id, self.partner_b)
