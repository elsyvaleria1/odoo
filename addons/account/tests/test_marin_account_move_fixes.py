from datetime import timedelta
from unittest.mock import patch

from lxml import etree

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tools.safe_eval import safe_eval

from odoo.addons.account.tests.common import (
    AccountTestInvoicingCommon,
    AccountTestInvoicingHttpCommon,
)
from odoo.addons.account.tests.common_reconcile import TestBankRecWidgetCommon
from odoo.addons.account.tests.test_sequence_mixin import TestSequenceMixinCommon


@tagged("post_install", "-at_install")
class TestAbnormalDateAnchor(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(
            context={**cls.env.context, "disable_abnormal_invoice_detection": False}
        )

    def _bill_vals(self, invoice_date=False, date=None):
        vals = {
            "move_type": "in_invoice",
            "partner_id": self.partner_a.id,
            "invoice_date": invoice_date,
            "line_ids": [
                Command.create(
                    {"name": "product", "price_unit": 100, "tax_ids": [Command.clear()]}
                )
            ],
        }
        if date is not None:
            vals["date"] = date
        return vals

    def _monthly_history(self):
        today = fields.Date.context_today(self.env["account.move"])
        start = today - timedelta(days=30 * 31)
        bills = self.env["account.move"].create(
            [
                self._bill_vals(invoice_date=start + timedelta(days=30 * i))
                for i in range(31)
            ]
        )
        bills.action_post()
        return max(bills.mapped("invoice_date"))

    def test_abnormal_date_flagged_when_invoice_date_is_set(self):
        too_soon = self._monthly_history() + timedelta(days=5)
        bill = self.env["account.move"].create(
            self._bill_vals(invoice_date=too_soon, date=too_soon)
        )
        self.assertTrue(
            bill.abnormal_date_warning,
            "five days into a thirty-day cadence is the anomaly this warns about",
        )

    def test_abnormal_date_flagged_when_only_date_is_set(self):
        too_soon = self._monthly_history() + timedelta(days=5)
        bill = self.env["account.move"].create(
            self._bill_vals(invoice_date=False, date=too_soon)
        )
        self.assertFalse(bill.invoice_date)
        self.assertEqual(bill.date, too_soon)
        self.assertTrue(
            bill.abnormal_date_warning,
            "a bill whose only date is `date` must be judged against `date`, the "
            "anchor its own SQL window used",
        )


@tagged("post_install", "-at_install")
class TestPaymentReferenceFollowsTheNumber(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.other_sale_journal = cls.company_data["default_journal_sale"].copy(
            {"name": "Second Sale Journal", "code": "SAJ2"}
        )

    def _invoice(self, **extra):
        return self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner_a.id,
                "invoice_date": "2026-06-01",
                "journal_id": self.company_data["default_journal_sale"].id,
                "line_ids": [
                    Command.create(
                        {
                            "name": "product",
                            "price_unit": 100,
                            "tax_ids": [Command.clear()],
                        }
                    )
                ],
                **extra,
            }
        )

    def _term_line(self, move):
        return move.line_ids.filtered(lambda line: line.display_type == "payment_term")

    def test_computed_reference_follows_a_journal_change(self):
        invoice = self._invoice()
        invoice.action_post()
        self.assertEqual(invoice.payment_reference, invoice.name)

        invoice.action_draft()
        invoice.write({"name": "/", "journal_id": self.other_sale_journal.id})
        invoice.action_post()

        self.assertEqual(
            invoice.payment_reference,
            invoice.name,
            "the reference was computed from the old number and must be recomputed "
            "from the new one, not left quoting a number that is gone",
        )
        self.assertEqual(
            self._term_line(invoice).name,
            invoice.name,
            "the payment term item labels itself from the move's payment reference",
        )

    def test_computed_reference_survives_an_unchanged_number(self):
        invoice = self._invoice()
        invoice.action_post()
        reference = invoice.payment_reference

        invoice.action_draft()
        invoice.write({"name": "/"})
        invoice.action_post()

        self.assertEqual(invoice.payment_reference, reference)
        self.assertEqual(invoice.payment_reference, invoice.name)

    def test_user_reference_is_never_discarded(self):
        invoice = self._invoice(payment_reference="CUSTOMER-REF-42")
        invoice.action_post()
        self.assertEqual(invoice.payment_reference, "CUSTOMER-REF-42")

        invoice.action_draft()
        invoice.write({"name": "/", "journal_id": self.other_sale_journal.id})
        invoice.action_post()

        self.assertEqual(
            invoice.payment_reference,
            "CUSTOMER-REF-42",
            "renumbering must not touch a reference the compute did not write",
        )


@tagged("post_install", "-at_install")
class TestMarinAccountMoveAuditFixes(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_data_2 = cls.setup_other_company()

    def _entry(self, amount=100.0, account=None, date="2026-01-15", journal=None):
        account = account or self.company_data["default_account_receivable"]
        return self.env["account.move"].create(
            {
                "move_type": "entry",
                "date": date,
                "journal_id": (journal or self.company_data["default_journal_misc"]).id,
                "line_ids": [
                    Command.create(
                        {
                            "name": "debit",
                            "account_id": account.id,
                            "partner_id": self.partner_a.id,
                            "balance": amount,
                        }
                    ),
                    Command.create(
                        {
                            "name": "credit",
                            "account_id": self.company_data[
                                "default_account_revenue"
                            ].id,
                            "balance": -amount,
                        }
                    ),
                ],
            }
        )

    def _bill(self, name, account, invoice_date, partner=None, deductible=None):
        line_vals = {
            "name": name,
            "account_id": account.id,
            "price_unit": 100.0,
            "tax_ids": [Command.set(self.tax_purchase_a.ids)],
        }
        if deductible is not None:
            line_vals["deductible_amount"] = deductible
        return self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": (partner or self.partner_a).id,
                "invoice_date": invoice_date,
                "invoice_line_ids": [Command.create(line_vals)],
            }
        )

    def test_posted_bill_with_non_deductible_lines_can_be_relabelled(self):
        bill = self._bill(
            "Partial item",
            self.company_data["default_account_expense"],
            "2026-01-10",
            deductible=75.0,
        )
        bill.action_post()
        non_deductible = bill.line_ids.filtered(
            lambda line: line.display_type == "non_deductible_product"
        )
        self.assertTrue(non_deductible)

        bill.invoice_line_ids.name = "Relabelled item"

        self.assertEqual(bill.state, "posted")
        self.assertEqual(
            bill.line_ids.filtered(
                lambda line: line.display_type == "non_deductible_product"
            ),
            non_deductible,
            "a posted bill keeps its non-deductible lines when a label changes",
        )

    def test_cash_rounding_accounts_come_from_the_invoice_company(self):
        company_2 = self.company_data_2["company"]
        self.cash_rounding_a.with_company(company_2).write(
            {
                "profit_account_id": self.company_data_2["default_account_revenue"].id,
                "loss_account_id": self.company_data_2["default_account_expense"].id,
            }
        )
        self.assertEqual(self.env.company, self.company_data["company"])

        move = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "company_id": company_2.id,
                "partner_id": self.partner_a.id,
                "invoice_cash_rounding_id": self.cash_rounding_a.id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_a.id,
                            "price_unit": 100.42,
                            "tax_ids": [Command.clear()],
                        }
                    )
                ],
            }
        )

        rounding_line = move.line_ids.filtered(
            lambda line: line.display_type == "rounding"
        )
        self.assertEqual(
            rounding_line.account_id,
            self.company_data_2["default_account_revenue"],
        )

    def test_biggest_tax_rounding_without_tax_line_is_kept_across_writes(self):
        self.cash_rounding_a.strategy = "biggest_tax"
        move = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner_a.id,
                "invoice_date": "2026-01-10",
                "invoice_cash_rounding_id": self.cash_rounding_a.id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "untaxed",
                            "price_unit": 100.42,
                            "tax_ids": [Command.clear()],
                        }
                    )
                ],
            }
        )
        rounding_line = move.line_ids.filtered(
            lambda line: line.display_type == "rounding"
        )
        self.assertTrue(rounding_line)

        move.ref = "touch"
        move.invoice_line_ids.name = "still untaxed"

        self.assertEqual(
            move.line_ids.filtered(lambda line: line.display_type == "rounding"),
            rounding_line,
            "the rounding line of a biggest-tax rounding with no tax line is "
            "updated in place, not recreated on every write",
        )

    def test_signer_is_fixed_when_the_invoice_is_posted(self):
        signer_1 = self.env.user
        signer_2 = self.env.user.copy({"login": "o1e_signer_2"})
        config = self.company_data["company"].account_config_id
        config.signing_user = signer_1
        invoice = self.init_invoice("out_invoice", amounts=[100.0], post=True)
        self.assertEqual(invoice.signing_user, signer_1)

        config.signing_user = signer_2
        self.env.flush_all()
        invoice.invalidate_recordset(["signing_user"])

        self.assertEqual(invoice.signing_user, signer_1)

    def test_the_company_representative_signs_an_invoice_posted_by_a_portal_user(
        self,
    ):
        representative = self.env.user
        self.company_data["company"].account_config_id.signing_user = representative
        portal_user = self.env["res.users"].create(
            {
                "name": "Portal poster",
                "login": "wp3_portal_poster",
                "group_ids": [Command.set(self.env.ref("base.group_portal").ids)],
            }
        )
        invoice = self.init_invoice("out_invoice", amounts=[100.0])

        invoice.with_user(portal_user).sudo().action_post()

        self.assertEqual(invoice.signing_user, representative)

    def test_quick_edit_suggests_expense_accounts_for_vendor_credit_notes(self):
        expense = self.company_data["default_account_expense"]
        self._bill("service", expense, "2026-01-10").action_post()

        _count, account_id, _taxes = self.env[
            "account.move"
        ]._get_frequent_account_and_taxes(
            self.company_data["company"].id, self.partner_a.id, "in_refund"
        )

        self.assertEqual(account_id, expense.id)

    def test_quick_edit_suggests_the_other_income_account_a_customer_uses(self):
        other_income = self.env["account.account"].create(
            {
                "code": "O1EOTHINC",
                "name": "Other income",
                "account_type": "income_other",
            }
        )
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner_a.id,
                "invoice_date": "2026-01-10",
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "rent",
                            "account_id": other_income.id,
                            "price_unit": 100.0,
                            "tax_ids": [],
                        }
                    )
                ],
            }
        )
        invoice.action_post()

        _count, account_id, _taxes = self.env[
            "account.move"
        ]._get_frequent_account_and_taxes(
            self.company_data["company"].id, self.partner_a.id, "out_invoice"
        )

        self.assertEqual(account_id, other_income.id)

    def test_sequence_number_of_an_unlinked_last_move_is_reused(self):
        self._entry().action_post()
        self._entry().action_post()
        first = self._entry()
        first.action_post()
        first_name = first.name
        first.action_draft()
        first.unlink()

        second = self._entry()
        second.action_post()

        self.assertEqual(second.name, first_name)

    def test_outstanding_credit_of_a_branch_is_offered_on_the_parent_invoice(self):
        root = self.company_data["company"]
        root.write({"child_ids": [Command.create({"name": "Branch O1E"})]})
        self.cr.precommit.run()
        branch = root.child_ids.filtered(lambda company: company.name == "Branch O1E")

        refund = self.env["account.move"].create(
            {
                "move_type": "out_refund",
                "company_id": branch.id,
                "partner_id": self.partner_a.id,
                "invoice_date": "2026-01-10",
                "invoice_line_ids": [
                    Command.create(
                        {"name": "credit", "price_unit": 50.0, "tax_ids": []}
                    )
                ],
            }
        )
        refund.action_post()
        invoice = self.init_invoice(
            "out_invoice", amounts=[100.0], invoice_date="2026-01-12", post=True
        )

        self.assertIn(
            refund.id,
            [
                content["move_id"]
                for content in (
                    invoice.with_context(
                        allowed_company_ids=(root + branch).ids
                    ).invoice_outstanding_credits_debits_widget
                    or {}
                ).get("content", [])
            ],
        )

        refund_line = refund.line_ids.filtered(
            lambda line: line.account_id.account_type == "asset_receivable"
        )
        invoice.with_context(
            allowed_company_ids=(root + branch).ids
        ).js_add_outstanding_line(refund_line.id)

        self.assertEqual(invoice.amount_residual, 50.0)

    def test_outstanding_credit_of_an_unrelated_company_cannot_be_added(self):
        foreign_refund = self.env["account.move"].create(
            {
                "move_type": "out_refund",
                "company_id": self.company_data_2["company"].id,
                "partner_id": self.partner_a.id,
                "invoice_date": "2026-01-10",
                "invoice_line_ids": [
                    Command.create(
                        {"name": "credit", "price_unit": 50.0, "tax_ids": []}
                    )
                ],
            }
        )
        foreign_refund.action_post()
        invoice = self.init_invoice(
            "out_invoice", amounts=[100.0], invoice_date="2026-01-12", post=True
        )
        foreign_line = foreign_refund.line_ids.filtered(
            lambda line: line.account_id.account_type == "asset_receivable"
        )

        with self.assertRaises(UserError):
            invoice.js_add_outstanding_line(foreign_line.id)

    def test_reversing_several_entries_posts_and_reconciles_each(self):
        entries = self._entry() + self._entry(amount=40.0)
        entries.action_post()

        wizard = self.env["wizard.account.move.reverse"].create(
            {
                "move_ids": entries.ids,
                "date": "2026-01-20",
                "journal_id": entries[0].journal_id.id,
            }
        )
        wizard.refund_moves()

        reversals = entries.reversal_move_ids
        self.assertEqual(len(reversals), 2)
        self.assertEqual(set(reversals.mapped("state")), {"posted"})
        receivable_lines = entries.line_ids.filtered(
            lambda line: (
                line.account_id == self.company_data["default_account_receivable"]
            )
        )
        self.assertTrue(all(receivable_lines.mapped("reconciled")))

    def test_invoice_reader_without_accounting_rights_reads_cash_rounded_totals(self):
        readers = self.env["res.groups"].create({"name": "o1e invoice readers"})
        self.env["ir.access"].create(
            [
                {
                    "name": f"o1e read {model}",
                    "model_id": self.env["ir.model"]._get_id(model),
                    "group_id": readers.id,
                    "kind": "permission",
                    "operation": "r",
                }
                for model in ("account.move", "account.move.line")
            ]
        )
        reader = self.env["res.users"].create(
            {
                "name": "o1e reader",
                "login": "o1e_reader",
                "company_id": self.env.company.id,
                "company_ids": [Command.set(self.env.company.ids)],
                "group_ids": [
                    Command.set((self.env.ref("base.group_user") + readers).ids)
                ],
            }
        )
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner_a.id,
                "invoice_date": "2026-01-10",
                "invoice_cash_rounding_id": self.cash_rounding_a.id,
                "invoice_line_ids": [
                    Command.create({"name": "item", "price_unit": 100.0, "tax_ids": []})
                ],
            }
        )
        invoice.action_post()
        self.env.invalidate_all()

        totals = invoice.with_user(reader).tax_totals

        self.assertTrue(totals)

    def test_prediction_learns_from_the_most_recent_bills(self):
        partner = self.env["res.partner"].create({"name": "o1e predicted vendor"})
        old_account, new_account = self.env["account.account"].create(
            [
                {"code": "O1EOLD", "name": "Old", "account_type": "expense"},
                {"code": "O1ENEW", "name": "New", "account_type": "expense"},
            ]
        )
        self._bill("Consulting fees", old_account, "2020-01-10", partner).action_post()
        self._bill("Consulting fees", new_account, "2026-01-10", partner).action_post()
        self.env["ir.config_parameter"].sudo().set_param(
            "account.bill.predict.history.limit", "1"
        )
        draft = self.env["account.move"].create(
            {"move_type": "in_invoice", "partner_id": partner.id}
        )

        predicted = self.env["account.move.line"]._predict_specific_account(
            draft, "Consulting fees", partner
        )

        self.assertEqual(predicted, new_account.id)

    def test_preferred_payment_channel_follows_the_money_direction(self):
        self.partner_a.write(
            {
                "property_inbound_payment_channel_id": self.inbound_payment_channel.id,
                "property_outbound_payment_channel_id": self.outbound_payment_channel.id,
            }
        )
        expected = {
            "out_invoice": self.inbound_payment_channel,
            "out_receipt": self.inbound_payment_channel,
            "in_refund": self.inbound_payment_channel,
            "in_invoice": self.outbound_payment_channel,
            "out_refund": self.outbound_payment_channel,
        }
        for move_type, channel in expected.items():
            move = self.env["account.move"].new(
                {"move_type": move_type, "partner_id": self.partner_a.id}
            )
            self.assertEqual(move.preferred_payment_channel_id, channel, move_type)

    def test_the_visible_payment_channel_field_admits_the_computed_channel(self):
        self.partner_a.write(
            {
                "property_inbound_payment_channel_id": self.inbound_payment_channel.id,
                "property_outbound_payment_channel_id": self.outbound_payment_channel.id,
            }
        )
        arch = etree.fromstring(
            self.env["account.move"].get_view(
                self.env.ref("account.view_move_form").id, "form"
            )["arch"]
        )
        nodes = arch.xpath("//field[@name='preferred_payment_channel_id']")
        self.assertEqual(len(nodes), 2)
        for move_type in ("out_invoice", "out_refund", "in_invoice", "in_refund"):
            move = self.env["account.move"].new(
                {"move_type": move_type, "partner_id": self.partner_a.id}
            )
            visible = [
                node
                for node in nodes
                if not safe_eval(node.get("invisible"), {"move_type": move_type})
            ]
            self.assertEqual(len(visible), 1, move_type)
            self.assertIn(
                f"'payment_type', '=', '{move.preferred_payment_channel_id.payment_type}'",
                visible[0].get("domain"),
                move_type,
            )

    def test_batch_send_summary_uses_the_translated_sending_method_label(self):
        self.partner_a.write(
            {"email": "partner_a@example.com", "invoice_sending_method": "email"}
        )
        invoice = self.init_invoice("out_invoice", amounts=[100.0], post=True)
        Selection = type(self.env["res.partner"]._fields["invoice_sending_method"])
        describe = Selection._description_selection

        def translated(field, env):
            if field.name == "invoice_sending_method":
                return [("manual", "Manual"), ("email", "por correo")]
            return describe(field, env)

        with patch.object(Selection, "_description_selection", translated):
            wizard = self.env["wizard.account.move.send.batch"].create(
                {"move_ids": [Command.set(invoice.ids)]}
            )
            summary = wizard.summary_data

        self.assertEqual(summary["email"]["label"], "por correo")

    def test_adjusting_entry_origin_action_is_named_after_its_single_origin(self):
        invoice = self.init_invoice("out_invoice", amounts=[100.0], post=True)
        adjusting = self._entry()
        adjusting.adjusting_entry_origin_move_ids = invoice

        action = adjusting.open_adjusting_entry_origin_moves()

        self.assertEqual(action["name"], adjusting.adjusting_entry_origin_label)
        self.assertEqual(action["name"], "Customer Invoice")


@tagged("post_install", "-at_install")
class TestMarinDeferralLinks(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        config = cls.company.account_config_id
        config.deferred_expense_journal_id = cls.company_data["default_journal_misc"]
        config.deferred_revenue_journal_id = cls.company_data["default_journal_misc"]
        config.deferred_expense_account_id = cls.company_data[
            "default_account_deferred_expense"
        ]
        config.deferred_revenue_account_id = cls.company_data[
            "default_account_deferred_revenue"
        ]
        cls.revenue_account = cls.env["account.account"].create(
            {"name": "O1E Revenue", "code": "O1EREV", "account_type": "income"}
        )

    def _deferred_invoice(self, amount=1680.0, date="2023-03-15", currency=None):
        vals = {
            "move_type": "out_invoice",
            "partner_id": self.partner_a.id,
            "date": date,
            "invoice_date": date,
            "invoice_line_ids": [
                Command.create(
                    {
                        "name": "deferred",
                        "account_id": self.revenue_account.id,
                        "price_unit": amount,
                        "tax_ids": [Command.clear()],
                        "deferred_start_date": "2023-01-01",
                        "deferred_end_date": "2023-03-31",
                    }
                )
            ],
        }
        if currency:
            vals["currency_id"] = currency.id
        move = self.env["account.move"].create(vals)
        move.action_post()
        return move

    def test_resetting_several_invoices_keeps_each_deferral_with_its_own_invoice(self):
        invoice_a = self._deferred_invoice()
        invoice_b = self._deferred_invoice(amount=900.0)
        self.company.account_config_id.fiscalyear_lock_date = "2023-02-15"

        (invoice_a + invoice_b).action_draft()

        for invoice in invoice_a + invoice_b:
            self.assertTrue(invoice.deferred_move_ids)
            self.assertEqual(
                invoice.deferred_move_ids.deferred_original_move_ids,
                invoice,
                "a reversal is linked only to the invoice whose deferral it reverses",
            )

    def test_deleting_one_deferral_keeps_the_others_linked(self):
        invoice = self._deferred_invoice()
        deferrals = invoice.deferred_move_ids
        self.assertGreater(len(deferrals), 1)
        self.company.account_config_id.restrictive_audit_trail = True
        deleted = deferrals.filtered(lambda move: move.state == "posted")[-1:]

        deleted.unlink()

        self.assertEqual(invoice.deferred_move_ids, deferrals - deleted)

    def test_deferral_of_a_coarse_currency_invoice_leaves_nothing_behind(self):
        coarse = self.setup_other_currency(
            "JPY", rounding=1.0, rates=[("1900-01-01", 1.0)]
        )
        invoice = self._deferred_invoice(amount=100.0, currency=coarse)

        deferred_account = self.company_data["default_account_deferred_revenue"]
        self.assertAlmostEqual(
            sum(
                invoice.deferred_move_ids.line_ids.filtered(
                    lambda line: line.account_id == deferred_account
                ).mapped("balance")
            ),
            0.0,
            places=2,
        )


@tagged("post_install", "-at_install")
class TestMarinStatementPartialRemoval(TestBankRecWidgetCommon):
    def test_removing_one_statement_payment_keeps_the_other(self):
        st_line_1 = self._create_st_line(50.0, partner_id=self.partner_a.id)
        st_line_2 = self._create_st_line(50.0, partner_id=self.partner_a.id)
        invoice = self.init_invoice(
            "out_invoice",
            invoice_date="2019-01-01",
            amounts=[100.0],
            partner=self.partner_a,
            post=True,
        )
        for st_line in st_line_1 + st_line_2:
            invoice.js_add_outstanding_line(
                st_line.move_id.line_ids.filtered(
                    lambda line: line.account_id.account_type == "asset_cash"
                ).id
            )
        partial = invoice.line_ids.matched_credit_ids.filtered(
            lambda partial: partial.credit_move_id.move_id == st_line_1.move_id
        )
        self.assertTrue(partial)

        st_line_1.move_id.js_remove_outstanding_partial(partial.id)

        self.assert_invoice_outstanding_reconciled_widget(
            invoice, {st_line_2.move_id.id: 50.0}
        )

    def test_removing_a_partial_of_another_document_is_refused(self):
        st_line = self._create_st_line(50.0, partner_id=self.partner_a.id)
        other = self._create_st_line(50.0, partner_id=self.partner_a.id)
        invoice = self.init_invoice(
            "out_invoice",
            invoice_date="2019-01-01",
            amounts=[100.0],
            partner=self.partner_a,
            post=True,
        )
        invoice.js_add_outstanding_line(
            st_line.move_id.line_ids.filtered(
                lambda line: line.account_id.account_type == "asset_cash"
            ).id
        )
        partial = invoice.line_ids.matched_credit_ids

        with self.assertRaises(UserError):
            other.move_id.js_remove_outstanding_partial(partial.id)

    def test_credit_warning_excludes_a_foreign_statement_payment_once(self):
        foreign = self.setup_other_currency("EUR", rates=[("1900-01-01", 2.0)])
        foreign_journal = self.company_data["default_journal_bank"].copy(
            {"currency_id": foreign.id}
        )
        invoice = self._create_invoice_line(
            "out_invoice",
            currency_id=foreign.id,
            invoice_line_ids=[{"price_unit": 2000.0, "tax_ids": []}],
        ).move_id
        st_line = self._create_st_line(
            600.0,
            date="2017-01-01",
            partner_id=self.partner_a.id,
            journal_id=foreign_journal.id,
        )
        invoice.js_add_outstanding_line(
            st_line.move_id.line_ids.filtered(
                lambda line: line.account_id.account_type == "asset_cash"
            ).id
        )
        invoice.action_draft()
        self.assertFalse(invoice.line_ids.matched_credit_ids)
        self.assertAlmostEqual(invoice.pending_payment_amount, 300.0)

        self.env.invalidate_all()
        credit, _credit_to_invoice = invoice._get_partner_credit_exposure()
        self.assertAlmostEqual(credit, -300.0, msg="the open payment counts once")
        self.assertAlmostEqual(
            invoice._get_partner_credit_warning_exclude_amount(), 0.0
        )


@tagged("post_install", "-at_install")
class TestMarinSequenceGapSuffix(TestSequenceMixinCommon):
    def _sequence_moves(self, suffix, count=3):
        moves = self.env["account.move"]
        for number in range(1, 1 + count):
            moves += self.create_move(name=f"NEW/00000{number}{suffix}", post=True)
        return moves

    def test_a_gap_in_one_suffix_does_not_flag_another(self):
        plain = self._sequence_moves("")
        suffixed = self._sequence_moves("A")

        middle = suffixed[1]
        middle.action_draft()
        middle.name = "NEW/000004A"
        middle.action_post()

        self.assertEqual(
            suffixed.sorted("sequence_number").mapped("made_sequence_gap"),
            [False, True, False],
        )
        self.assertEqual(plain.mapped("made_sequence_gap"), [False, False, False])

    def test_other_suffixes_do_not_fill_the_neighbour_window(self):
        self._sequence_moves("SPACER", count=9)
        first = self.create_move(name="NEW/000001A", post=True)
        ninth = self.create_move(name="NEW/000009A", post=True)

        self.assertFalse(first.made_sequence_gap)
        self.assertTrue(ninth.made_sequence_gap)

    def test_like_wildcards_in_a_suffix_are_literal(self):
        plain = self._sequence_moves("A")
        wild = self._sequence_moves("_A")
        middle = wild[1]
        middle.action_draft()
        middle.name = "NEW/000004_A"
        middle.action_post()

        self.assertEqual(
            wild.sorted("sequence_number").mapped("made_sequence_gap"),
            [False, True, False],
        )
        self.assertEqual(plain.mapped("made_sequence_gap"), [False, False, False])


@tagged("post_install", "-at_install")
class TestMarinDueDateDefault(AccountTestInvoicingCommon):
    def _invoice(self, **vals):
        return self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner_a.id,
                "invoice_date": "2020-01-01",
                "invoice_payment_term_id": False,
                "invoice_line_ids": [
                    Command.create({"name": "line", "price_unit": 100.0})
                ],
                **vals,
            }
        )

    def test_an_invoice_without_terms_is_due_on_its_invoice_date(self):
        invoice = self._invoice()

        self.assertEqual(str(invoice.invoice_date_due), "2020-01-01")
        invoice.action_post()
        self.assertEqual(
            invoice.line_ids.filtered("date_maturity").mapped("date_maturity"),
            [invoice.invoice_date],
        )

    def test_an_explicit_due_date_is_kept(self):
        invoice = self._invoice(invoice_date_due="2020-02-15")

        self.assertEqual(str(invoice.invoice_date_due), "2020-02-15")

    def test_a_payment_term_still_sets_the_due_date(self):
        term = self.env.ref(
            "payment_term.account_payment_term_30days", False
        ) or self.env["account.payment.term"].create(
            {
                "name": "30 days",
                "line_ids": [
                    Command.create(
                        {"value": "percent", "value_amount": 100.0, "nb_days": 30}
                    )
                ],
            }
        )

        invoice = self._invoice(invoice_payment_term_id=term.id)

        self.assertEqual(str(invoice.invoice_date_due), "2020-01-31")


@tagged("post_install", "-at_install")
class TestMarinPredictionCommercialPartner(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company.account_config_id.predict_bill_product = True
        cls.acme = cls.env["res.partner"].create(
            {"name": "Acme", "is_company": True, "company_id": False}
        )
        cls.john, cls.jane = cls.env["res.partner"].create(
            [
                {"name": "John", "parent_id": cls.acme.id, "type": "contact"},
                {"name": "Jane", "parent_id": cls.acme.id, "type": "contact"},
            ]
        )
        cls.chairs_account = cls.env["account.account"].create(
            {"code": "B1CHAIR", "name": "Seating", "account_type": "expense"}
        )

    def _posted_bill(self, partner, **line_vals):
        bill = self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": partner.id,
                "invoice_date": "2026-01-10",
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "Ergonomic office chairs",
                            "price_unit": 100.0,
                            "account_id": self.chairs_account.id,
                            "tax_ids": [Command.set(self.tax_purchase_b.ids)],
                            **line_vals,
                        }
                    )
                ],
            }
        )
        bill.action_post()
        return bill

    def _draft_line(self, partner):
        bill = self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": partner.id,
                "invoice_date": "2026-02-10",
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "Ergonomic office chairs",
                            "price_unit": 100.0,
                            "tax_ids": [Command.clear()],
                        }
                    )
                ],
            }
        )
        return bill.invoice_line_ids

    def test_taxes_are_predicted_on_a_bill_addressed_to_a_contact(self):
        self._posted_bill(self.acme)
        self._posted_bill(self.john)
        line = self._draft_line(self.john)

        self.assertEqual(line.partner_id, self.acme)
        self.assertEqual(line._predict_taxes(), self.tax_purchase_b.ids)

    def test_specific_tax_is_predicted_for_a_contact(self):
        self._posted_bill(self.john)
        draft = self._draft_line(self.jane).move_id

        predicted = self.env["account.move.line"]._predict_specific_tax(
            draft,
            "Ergonomic office chairs",
            self.jane,
            self.tax_purchase_b.amount_type,
            self.tax_purchase_b.amount,
            "purchase",
        )

        self.assertEqual(predicted, self.tax_purchase_b.ids)

    def test_account_is_learned_from_another_contact_of_the_vendor(self):
        self._posted_bill(self.john)
        line = self._draft_line(self.jane)

        predicted = self.env["account.move.line"]._predict_specific_account(
            line.move_id, line.name, line.partner_id
        )

        self.assertEqual(predicted, self.chairs_account.id)

    def test_product_is_learned_from_another_contact_of_the_vendor(self):
        self._posted_bill(self.john, product_id=self.product_a.id)
        line = self._draft_line(self.acme)

        self.assertEqual(line._predict_product(), self.product_a.id)

    def test_deductible_amount_is_predicted_on_a_bill_addressed_to_a_contact(self):
        self.env.user.group_ids += self.env.ref(
            "account.group_partial_purchase_deductibility"
        )
        self._posted_bill(self.john, deductible_amount=40.0)
        line = self._draft_line(self.john)
        line.account_id = self.chairs_account

        self.assertEqual(line._predict_deductible_amount(), 40.0)


@tagged("post_install", "-at_install")
class TestMarinMoveBatchBFixes(AccountTestInvoicingCommon):
    def _receivable_entry(self, balance, partner=None, post=True):
        entry = self.env["account.move"].create(
            {
                "move_type": "entry",
                "date": "2026-01-15",
                "journal_id": self.company_data["default_journal_misc"].id,
                "line_ids": [
                    Command.create(
                        {
                            "name": "receivable",
                            "account_id": self.company_data[
                                "default_account_receivable"
                            ].id,
                            "partner_id": partner.id if partner else False,
                            "balance": balance,
                        }
                    ),
                    Command.create(
                        {
                            "name": "counterpart",
                            "account_id": self.company_data[
                                "default_account_revenue"
                            ].id,
                            "balance": -balance,
                        }
                    ),
                ],
            }
        )
        if post:
            entry.action_post()
        return entry

    def _reconcile_receivables(self, moves):
        moves.line_ids.filtered(
            lambda line: (
                line.account_id == self.company_data["default_account_receivable"]
            )
        ).reconcile()

    def test_partially_paid_invoice_has_reconciled_entries(self):
        invoice = self.init_invoice(
            "out_invoice", amounts=[1000.0], invoice_date="2026-01-10", post=True
        )
        payment = self._receivable_entry(-400.0, partner=self.partner_a)
        self._reconcile_receivables(invoice + payment)

        self.assertEqual(invoice.payment_state, "partial")
        self.assertTrue(invoice.has_reconciled_entries)
        self.assertTrue(payment.has_reconciled_entries)

    def test_partially_used_entry_has_reconciled_entries(self):
        invoice = self.init_invoice(
            "out_invoice", amounts=[300.0], invoice_date="2026-01-10", post=True
        )
        payment = self._receivable_entry(-400.0, partner=self.partner_a)
        self._reconcile_receivables(invoice + payment)

        payment_line = payment.line_ids.filtered("matched_debit_ids")
        self.assertFalse(payment_line.reconciled)
        self.assertTrue(payment.has_reconciled_entries)
        receivable = invoice.line_ids.filtered("matched_credit_ids")
        self.assertCountEqual(
            payment.line_ids._reconciled_lines(), (payment_line + receivable).ids
        )

    def test_unreconciled_entry_has_no_reconciled_entries(self):
        invoice = self.init_invoice(
            "out_invoice", amounts=[1000.0], invoice_date="2026-01-10", post=True
        )

        self.assertFalse(invoice.has_reconciled_entries)
        self.assertEqual(invoice.line_ids._reconciled_lines(), [])

    def test_zip_export_of_an_invoice_without_pdf_is_empty(self):
        invoice = self.init_invoice(
            "out_invoice", amounts=[100.0], invoice_date="2026-01-10", post=True
        )
        entry = self._receivable_entry(100.0, partner=self.partner_a)

        self.assertFalse(invoice.invoice_pdf_report_id)
        self.assertEqual(invoice._get_invoice_legal_documents_all(), [])
        self.assertEqual(invoice._get_move_zip_export_docs(), [])
        self.assertEqual(entry._get_move_zip_export_docs(), [])

    def test_self_billing_placeholder_follows_the_partner(self):
        journal = self.env["account.journal"].create(
            {
                "name": "Self billing",
                "code": "SBIL",
                "type": "purchase",
                "is_self_billing": True,
            }
        )
        bill = self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "journal_id": journal.id,
                "partner_id": self.partner_a.id,
                "invoice_date": "2026-01-10",
            }
        )
        self.assertIn(str(self.partner_a.id).zfill(5), bill.name_placeholder)

        bill.partner_id = self.partner_b

        self.assertIn(str(self.partner_b.id).zfill(5), bill.name_placeholder)

    def test_self_billing_highest_name_follows_the_partner(self):
        journal = self.env["account.journal"].create(
            {
                "name": "Self billing",
                "code": "SBIL",
                "type": "purchase",
                "is_self_billing": True,
            }
        )
        vals = {
            "move_type": "in_invoice",
            "journal_id": journal.id,
            "partner_id": self.partner_a.id,
            "invoice_date": "2026-01-10",
            "invoice_line_ids": [Command.create({"name": "x", "price_unit": 10.0})],
        }
        posted = self.env["account.move"].create(vals)
        posted.action_post()
        draft = self.env["account.move"].create(vals)
        self.assertEqual(draft.highest_name, posted.name)

        draft.partner_id = self.partner_b

        self.assertFalse(draft.highest_name)

    def test_partnerless_draft_invoice_lists_no_outstanding_credits(self):
        self._receivable_entry(-100.0)
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "invoice_date": "2026-01-10",
                "invoice_line_ids": [
                    Command.create({"name": "line", "price_unit": 100.0})
                ],
            }
        )

        self.assertTrue(invoice._get_receivable_payable_lines())
        self.assertFalse(invoice.invoice_outstanding_credits_debits_widget)
        self.assertFalse(invoice.invoice_has_outstanding)

    def test_a_posted_partnerless_receipt_still_lists_partnerless_credits(self):
        credit = self._receivable_entry(-100.0)
        receipt = self.env["account.move"].create(
            {
                "move_type": "out_receipt",
                "invoice_date": "2026-01-10",
                "invoice_line_ids": [
                    Command.create({"name": "line", "price_unit": 100.0})
                ],
            }
        )
        receipt.action_post()

        self.assertTrue(receipt.invoice_has_outstanding)
        listed = receipt.invoice_outstanding_credits_debits_widget["content"]
        self.assertIn(
            credit.line_ids.filtered(lambda line: line.credit).id,
            [line["id"] for line in listed],
        )


@tagged("post_install", "-at_install")
class TestMarinMoveAttachmentsDownload(AccountTestInvoicingHttpCommon):
    def test_a_download_with_no_document_is_not_found(self):
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner_a.id,
                "invoice_line_ids": [Command.create({"price_unit": 100.0})],
            }
        )
        invoice.action_post()
        self.authenticate(self.env.user.login, self.env.user.login)

        res = self.url_open(f"/account/download_move_attachments/{invoice.id}")

        self.assertEqual(res.status_code, 404)

    def test_a_move_without_documents_does_not_break_the_zip(self):
        with_pdf, without_pdf = self.env["account.move"].create(
            [
                {
                    "move_type": "out_invoice",
                    "partner_id": self.partner_a.id,
                    "invoice_line_ids": [Command.create({"price_unit": price})],
                }
                for price in (100.0, 200.0)
            ]
        )
        (with_pdf + without_pdf).action_post()
        with_pdf._generate_and_send()
        self.assertTrue(with_pdf.invoice_pdf_report_id)
        self.assertFalse(without_pdf.invoice_pdf_report_id)
        self.authenticate(self.env.user.login, self.env.user.login)

        res = self.url_open(
            f"/account/download_move_attachments/{with_pdf.id},{without_pdf.id}"
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers["Content-Type"], "application/zip")


@tagged("post_install", "-at_install")
class TestMarinPaymentReceiptPartials(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.eur = cls.setup_other_currency("EUR")

    def _invoice_paid_twice(
        self, payment_currency, invoice_date="2016-01-01", payment_date="2017-01-01"
    ):
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner_a.id,
                "invoice_date": invoice_date,
                "date": invoice_date,
                "currency_id": self.eur.id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "line",
                            "price_unit": 1200.0,
                            "tax_ids": [Command.clear()],
                        }
                    )
                ],
            }
        )
        invoice.action_post()
        amount = 600.0 if payment_currency == self.eur else 300.0
        payments = self.env["account.payment"]
        for _i in range(2):
            payments |= (
                self.env["wizard.account.move.line.pay"]
                .with_context(active_model="account.move", active_ids=invoice.ids)
                .create(
                    {
                        "amount": amount,
                        "currency_id": payment_currency.id,
                        "payment_date": payment_date,
                    }
                )
                ._create_payments()
            )
        return invoice, payments

    def _render(self, payment):
        return (
            self.env["ir.actions.report"]
            ._render_qweb_html("account.report_payment_receipt", payment.ids)[0]
            .decode()
        )

    def test_receipt_lists_payments_but_not_exchange_differences(self):
        invoice, payments = self._invoice_paid_twice(
            self.eur, invoice_date="2017-01-01", payment_date="2016-06-01"
        )
        exchange_moves = invoice.line_ids.matched_credit_ids.credit_move_id.move_id - (
            payments.move_id
        )
        self.assertEqual(len(exchange_moves), 2)
        html = self._render(payments[1])
        for payment in payments:
            self.assertIn(payment.move_id.name, html)
        for exchange_move in exchange_moves:
            self.assertNotIn(exchange_move.name, html)
        self.assertEqual(html.count("-\ufeff600.00"), 2)

    def test_a_billing_user_of_one_company_renders_the_receipt(self):
        _invoice, payments = self._invoice_paid_twice(
            self.eur, invoice_date="2017-01-01", payment_date="2016-06-01"
        )
        company = self.company_data["company"]
        user = self._create_new_internal_user(
            login="receipt_billing",
            groups="account.group_account_invoice",
            company_id=company.id,
            company_ids=[Command.set(company.ids)],
        )
        html = (
            self.env["ir.actions.report"]
            .with_user(user)
            ._render_qweb_html("account.report_payment_receipt", payments[1].ids)[0]
            .decode()
        )
        for payment in payments:
            self.assertIn(payment.move_id.name, html)

    def test_receipt_shows_the_matched_amount_in_the_payment_currency(self):
        invoice, payments = self._invoice_paid_twice(self.company_data["currency"])
        html = self._render(payments[0])
        self.assertIn("Amount In Currency", html)
        self.assertEqual(html.count("-\ufeff200.00"), 2)
        self.assertEqual(html.count("-\ufeff600.00"), 2)
        self.assertEqual(invoice.amount_residual, 0.0)


@tagged("post_install", "-at_install")
class TestMarinTermAccountFallback(AccountTestInvoicingCommon):
    def _invoice_vals(self):
        return {
            "move_type": "out_invoice",
            "partner_id": self.partner_a.id,
            "invoice_date": "2026-06-01",
            "invoice_line_ids": [
                Command.create(
                    {"name": "line", "price_unit": 100.0, "tax_ids": [Command.clear()]}
                )
            ],
        }

    def _recompute_term_accounts(self, moves):
        term_lines = moves.line_ids.filtered(
            lambda line: line.display_type == "payment_term"
        )
        self.env.invalidate_all()
        with self.capturedQueries() as queries:
            term_lines._update_account_id_on_term_lines()
        return term_lines, [
            query
            for query in queries
            if '"account_account"' in query and "account_type" in query
        ]

    def test_partner_accounts_need_no_fallback_search(self):
        moves = self.env["account.move"].create(
            [self._invoice_vals() for _i in range(20)]
        )
        term_lines, fallback_queries = self._recompute_term_accounts(moves)
        self.assertEqual(fallback_queries, [])
        self.assertEqual(
            term_lines.account_id, self.partner_a.property_account_receivable_id
        )

    def test_fallback_is_searched_once_per_company_and_type(self):
        moves = self.env["account.move"].create(
            [self._invoice_vals() for _i in range(20)]
        )
        company = self.company_data["company"]
        for partner in (self.partner_a, company.partner_id):
            partner.with_company(company).property_account_receivable_id = False
        self.assertFalse(
            company.partner_id.with_company(company).property_account_receivable_id
        )
        expected = self.env["account.account"].search(
            [
                ("company_ids", "in", company.ids),
                ("account_type", "=", "asset_receivable"),
            ],
            order="id",
            limit=1,
        )
        term_lines, fallback_queries = self._recompute_term_accounts(moves)
        self.assertEqual(len(fallback_queries), 1)
        self.assertEqual(term_lines.account_id, expected)


@tagged("post_install", "-at_install")
class TestMarinJournalInvoiceTemplate(AccountTestInvoicingHttpCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.journal_report = cls.env.ref("account.account_invoices_without_payment")
        cls.journal_report.write(
            {
                "is_invoice_report": True,
                "print_report_name": "'Journal_%s' % object._get_report_base_filename()",
            }
        )
        cls.company_data[
            "default_journal_sale"
        ].invoice_template_pdf_report_id = cls.journal_report
        cls.user_portal = cls._create_new_portal_user()
        cls.invoice = cls.init_invoice(
            "out_invoice", amounts=[100], partner=cls.user_portal.partner_id, post=True
        )

    def test_filename_follows_the_journal_template(self):
        self.assertEqual(
            self.env["mixin.account.move.send"]._get_default_pdf_report_id(
                self.invoice
            ),
            self.journal_report,
        )
        self.assertEqual(
            self.invoice._get_invoice_report_filename(),
            f"Journal_{self.invoice._get_report_base_filename().replace('/', '_')}.pdf",
        )

    def test_portal_renders_the_journal_template(self):
        rendered = []
        Report = type(self.env["ir.actions.report"])
        original = Report._render_qweb_html

        def recording(report_self, report_ref, *args, **kwargs):
            rendered.append(report_ref)
            return original(report_self, report_ref, *args, **kwargs)

        self.authenticate(self.user_portal.login, self.user_portal.login)
        with patch.object(Report, "_render_qweb_html", recording):
            res = self.url_open(f"/my/invoices/{self.invoice.id}?report_type=html")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(rendered[0], self.journal_report.report_name)


@tagged("post_install", "-at_install")
class TestMarinSelfBillingCommercialPartner(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.journal = cls.env["account.journal"].create(
            {
                "name": "Self billing",
                "code": "SBIL",
                "type": "purchase",
                "is_self_billing": True,
            }
        )
        cls.contact = cls.env["res.partner"].create(
            {"name": "Contact", "parent_id": cls.partner_a.id}
        )

    def _vals(self, partner):
        return {
            "move_type": "in_invoice",
            "journal_id": self.journal.id,
            "partner_id": partner.id,
            "invoice_date": "2026-01-10",
            "invoice_line_ids": [Command.create({"name": "x", "price_unit": 10.0})],
        }

    def test_placeholder_follows_a_reparented_contact(self):
        bill = self.env["account.move"].create(self._vals(self.contact))
        self.assertIn(str(self.partner_a.id).zfill(5), bill.name_placeholder)

        self.contact.parent_id = self.partner_b

        self.assertIn(str(self.partner_b.id).zfill(5), bill.name_placeholder)

    def test_highest_name_follows_a_reparented_contact(self):
        posted = self.env["account.move"].create(self._vals(self.partner_a))
        posted.action_post()
        draft = self.env["account.move"].create(self._vals(self.contact))
        self.assertEqual(draft.highest_name, posted.name)

        self.contact.parent_id = self.partner_b

        self.assertFalse(draft.highest_name)


@tagged("post_install", "-at_install")
class TestMarinEarlyPaymentDiscountSync(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.epd_term = cls.env["account.payment.term"].create(
            {
                "name": "10% within 10 days",
                "early_discount": True,
                "discount_percentage": 10,
                "discount_days": 10,
                "early_pay_discount_computation": "mixed",
                "line_ids": [
                    Command.create(
                        {"value": "percent", "nb_days": 0, "value_amount": 100}
                    )
                ],
            }
        )
        cls.taxes = cls.env["account.tax"].create(
            [
                {"name": "EPD 15", "amount": 15, "sequence": 20},
                {"name": "EPD 5", "amount": 5, "sequence": 10},
            ]
        )
        plan = cls.env["account.analytic.plan"].create({"name": "EPD plan"})
        cls.analytic = cls.env["account.analytic.account"].create(
            {"name": "EPD analytic", "plan_id": plan.id}
        )

    def _invoice(self, **line_vals):
        return self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner_a.id,
                "invoice_date": "2026-01-01",
                "invoice_payment_term_id": self.epd_term.id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "line",
                            "price_unit": 1000.0,
                            "tax_ids": [Command.set(self.taxes.ids)],
                            **line_vals,
                        }
                    )
                ],
            }
        )

    @staticmethod
    def _epd_lines(invoice):
        return invoice.line_ids.filtered(lambda line: line.display_type == "epd")

    def test_existing_keys_are_the_needed_keys(self):
        for line_vals in ({}, {"analytic_distribution": {self.analytic.id: 100}}):
            with self.subTest(line_vals=line_vals):
                invoice = self._invoice(**line_vals)
                needed = {
                    key
                    for line in invoice.invoice_line_ids
                    for key in (line.epd_needed or {})
                }
                self.assertEqual(len(needed), 2)
                self.assertEqual(
                    set(self._epd_lines(invoice).mapped("epd_key")), needed
                )

    def test_epd_lines_are_updated_in_place(self):
        invoice = self._invoice(analytic_distribution={self.analytic.id: 100})
        roles = {line.id: line.tax_ids for line in self._epd_lines(invoice)}
        self.assertEqual(sorted(len(taxes) for taxes in roles.values()), [0, 2])

        invoice.invoice_line_ids.price_unit = 2000.0

        epd_lines = self._epd_lines(invoice)
        self.assertEqual({line.id: line.tax_ids for line in epd_lines}, roles)
        self.assertEqual(sorted(epd_lines.mapped("balance")), [-200.0, 200.0])


@tagged("post_install", "-at_install")
class TestMarinSequenceFollowsTheJournal(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.journal = cls.env["account.journal"].create(
            {"name": "Fresh sales", "code": "FRSH", "type": "sale"}
        )

    def _move(self, move_type="out_invoice"):
        return self.env["account.move"].create(
            {
                "move_type": move_type,
                "journal_id": self.journal.id,
                "partner_id": self.partner_a.id,
                "invoice_date": "2026-01-10",
                "invoice_line_ids": [Command.create({"name": "x", "price_unit": 10.0})],
            }
        )

    def test_placeholder_follows_the_journal_code(self):
        draft = self._move()
        self.assertRegex(draft.name_placeholder, r"^FRSH/")

        self.journal.code = "NEWC"

        self.assertRegex(draft.name_placeholder, r"^NEWC/")

    def test_placeholder_follows_the_refund_sequence_flag(self):
        self.journal.refund_sequence = False
        refund = self._move("out_refund")
        self.assertRegex(refund.name_placeholder, r"^FRSH/")

        self.journal.refund_sequence = True

        self.assertRegex(refund.name_placeholder, r"^RFRSH/")

    def test_highest_name_follows_the_refund_sequence_flag(self):
        self.journal.refund_sequence = True
        posted = self._move("out_refund")
        posted.action_post()
        draft = self._move()
        self.assertFalse(draft.highest_name)

        self.journal.refund_sequence = False

        self.assertEqual(draft.highest_name, posted.name)
