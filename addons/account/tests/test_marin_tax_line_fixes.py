from psycopg import IntegrityError

from odoo import Command, fields
from odoo.exceptions import ValidationError
from odoo.modules.module import get_module_path, load_script
from odoo.tests import new_test_user, tagged
from odoo.tools import mute_logger

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
    def test_resync_overwrites_a_manually_edited_tax_line_label(self):
        tax = self.company_data["default_tax_sale"]
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
                            "tax_ids": [Command.set(tax.ids)],
                        }
                    )
                ],
            }
        )
        tax_line = invoice.line_ids.filtered(lambda line: line.display_type == "tax")
        invoice.write(
            {"line_ids": [Command.update(tax_line.id, {"name": "Edited label"})]}
        )
        self.assertEqual(tax_line.name, "Edited label")
        invoice.invoice_line_ids.price_unit = 200.0
        self.assertEqual(
            invoice.line_ids.filtered(lambda line: line.display_type == "tax"),
            tax_line,
        )
        self.assertEqual(tax_line.name, tax.name)
