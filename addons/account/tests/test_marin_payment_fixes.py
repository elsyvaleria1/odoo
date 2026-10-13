from unittest.mock import patch

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestMarinPaymentFixes(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bank_journal = cls.company_data["default_journal_bank"]
        cls.cash_journal = cls.company_data["default_journal_cash"]
        cls.other_currency = cls.setup_other_currency("EUR")

    def _payment(self, post=False, **vals):
        payment = self.env["account.payment"].create(
            {
                "amount": 100.0,
                "date": "2026-08-01",
                "partner_id": self.partner_a.id,
                "partner_type": "customer",
                "payment_type": "inbound",
                "journal_id": self.bank_journal.id,
                **vals,
            }
        )
        if post:
            payment.action_post()
        return payment

    def _register(self, moves, **vals):
        return (
            self.env["wizard.account.move.line.pay"]
            .with_context(active_model="account.move", active_ids=moves.ids)
            .create(vals)
        )

    def test_confirming_a_selection_leaves_a_canceled_cash_payment_canceled(self):
        self.cash_journal.inbound_payment_channel_ids.payment_account_id = (
            self.cash_journal.default_account_id
        )
        payment = self._payment(journal_id=self.cash_journal.id)
        self.assertEqual(
            payment.liquidity_account_id.account_type,
            "asset_cash",
            "the premise: a cash payment goes straight to paid on confirm",
        )
        payment.action_cancel()
        other = self._payment(journal_id=self.cash_journal.id)

        (payment + other).action_post()

        self.assertEqual(payment.state, "canceled")
        self.assertFalse(payment.move_id)
        self.assertEqual(other.state, "paid")

    def test_mass_edit_skips_payments_that_carry_no_entry(self):
        with_move = self._payment(post=True)
        self.assertTrue(with_move.move_id)
        with patch.object(
            type(self.env["account.payment"]),
            "_liquidity_account_is_mandatory",
            lambda self: False,
        ):
            self.bank_journal.inbound_payment_channel_ids.payment_account_id = False
            without_move = self._payment()
            self.assertFalse(without_move.liquidity_account_id)
            self.assertFalse(without_move.move_id)

            (with_move + without_move).write({"memo": "edited"})

        self.assertEqual(without_move.memo, "edited")
        self.assertEqual(with_move.memo, "edited")

    def test_register_wizard_warns_about_a_confirmed_payment_of_the_same_amount(self):
        invoice = self.init_invoice(
            "out_invoice", post=True, invoice_date="2026-08-01", amounts=[100.0]
        )
        existing = self._payment(post=True)
        self.assertEqual(existing.state, "in_process")

        wizard = self._register(invoice, payment_date="2026-08-01")

        self.assertEqual(wizard.amount, 100.0)
        self.assertIn(existing, wizard.duplicate_payment_ids)

    def test_register_wizard_compares_payments_in_its_own_currency(self):
        invoice = self.init_invoice(
            "out_invoice",
            post=True,
            invoice_date="2026-08-01",
            amounts=[100.0],
            currency=self.other_currency,
        )
        existing = self._payment(currency_id=self.other_currency.id)
        same_figure_other_currency = self._payment()

        wizard = self._register(invoice, payment_date="2026-08-01")

        self.assertEqual(wizard.currency_id, self.other_currency)
        self.assertIn(existing, wizard.duplicate_payment_ids)
        self.assertNotIn(same_figure_other_currency, wizard.duplicate_payment_ids)

    def test_editing_a_saved_payment_warns_on_the_edited_values(self):
        saved = self._payment()
        twin_of_the_edit = self._payment(amount=200.0)
        self.assertNotIn(twin_of_the_edit, saved.duplicate_payment_ids)

        edited = saved.new({"amount": 200.0}, origin=saved)

        self.assertIn(twin_of_the_edit, edited.duplicate_payment_ids._origin)

    def test_moveless_allocation_books_the_payment_currency(self):
        invoice = self.init_invoice(
            "out_invoice",
            post=True,
            invoice_date="2026-08-01",
            amounts=[100.0],
            currency=self.other_currency,
        )
        payment = self._payment(amount=30.0, invoice_ids=[Command.set(invoice.ids)])
        self.assertFalse(payment.move_id)

        vals_list = payment._get_amls_for_payment_without_move()

        against_invoice = [v for v in vals_list if v.get("reconciled_lines_ids")]
        self.assertTrue(against_invoice)
        for vals in against_invoice:
            self.assertEqual(vals["currency_id"], payment.currency_id.id)
            self.assertAlmostEqual(abs(vals["amount_currency"]), 30.0)

    def test_moveless_leftover_goes_to_the_payment_destination_account(self):
        invoice = self.init_invoice(
            "out_invoice", post=True, invoice_date="2026-08-01", amounts=[100.0]
        )
        other_receivable = self.company_data["default_account_receivable"].copy(
            {"code": "121099"}
        )
        payment = self._payment(
            amount=150.0,
            invoice_ids=[Command.set(invoice.ids)],
            counterpart_account_id=other_receivable.id,
        )

        vals_list = payment._get_amls_for_payment_without_move()

        leftover = [v for v in vals_list if not v.get("reconciled_lines_ids")]
        self.assertEqual(len(leftover), 1)
        self.assertEqual(leftover[0]["account_id"], other_receivable.id)

    def test_superseding_an_outbound_payment_shrinks_it(self):
        bill = self.init_invoice(
            "in_invoice", post=True, invoice_date="2026-08-01", amounts=[100.0]
        )
        term_line = bill.line_ids.filtered(lambda l: l.display_type == "payment_term")
        payment = self._payment(
            payment_type="outbound",
            partner_type="supplier",
            invoice_ids=[Command.set(bill.ids)],
        )
        self.assertEqual(payment.amount_signed, -100.0)
        self._payment(
            post=True,
            amount=40.0,
            payment_type="outbound",
            partner_type="supplier",
            invoice_ids=[Command.set(bill.ids)],
        )

        payment._supersede_with_payment_move(term_line, -40.0)

        self.assertEqual(payment.amount, 60.0)

    def test_statement_match_of_a_partly_matched_liquidity_line_uses_its_residual(self):
        payment = self._payment(post=True)
        liquidity = payment._seek_for_lines()[0]
        self.assertTrue(liquidity.account_id.reconcile)
        partial = self.env["account.move"].create(
            {
                "move_type": "entry",
                "date": "2026-08-01",
                "line_ids": [
                    Command.create(
                        {
                            "account_id": liquidity.account_id.id,
                            "partner_id": self.partner_a.id,
                            "balance": -40.0,
                        }
                    ),
                    Command.create(
                        {
                            "account_id": self.company_data[
                                "default_account_revenue"
                            ].id,
                            "balance": 40.0,
                        }
                    ),
                ],
            }
        )
        partial.action_post()
        (
            liquidity
            + partial.line_ids.filtered(lambda l: l.account_id == liquidity.account_id)
        ).reconcile()
        self.assertEqual(liquidity.amount_residual, 60.0)
        st_line = self.env["account.bank.statement.line"].create(
            {
                "journal_id": self.bank_journal.id,
                "date": "2026-08-01",
                "payment_ref": "PARTLY",
                "amount": 60.0,
                "partner_id": self.partner_a.id,
            }
        )

        amls, _has_exchange_diff = payment._get_amls_for_reconciliation(st_line)

        self.assertEqual(len(amls), 1)
        self.assertAlmostEqual(amls[0]["balance"], -60.0)
        self.assertAlmostEqual(amls[0]["amount_currency"], -60.0)

    def test_duplicate_bank_accounts_are_found_whatever_the_spacing(self):
        partner_1 = self.env["res.partner"].create({"name": "Spaced"})
        partner_2 = self.env["res.partner"].create({"name": "Packed"})
        spaced = self.env["res.partner.bank.account"].create(
            {
                "acc_number": "BE71 0961 2345 6769",
                "partner_id": partner_1.id,
                "company_id": False,
            }
        )
        self.env["res.partner.bank.account"].create(
            {
                "acc_number": "BE71096123456769",
                "partner_id": partner_2.id,
                "company_id": False,
            }
        )

        self.assertEqual(spaced.duplicate_bank_partner_ids, partner_2)

    def test_a_shared_payment_term_in_use_elsewhere_cannot_be_deleted(self):
        company_b = self.setup_other_company()["company"]
        term = self.env["account.payment.term"].create(
            {
                "name": "Shared term",
                "company_id": False,
                "line_ids": [
                    Command.create(
                        {"value": "percent", "value_amount": 100, "nb_days": 30}
                    )
                ],
            }
        )
        invoice = self.init_invoice(
            "out_invoice",
            invoice_date="2026-08-01",
            amounts=[100.0],
            company=company_b,
        )
        invoice.invoice_payment_term_id = term
        user_a = self.env["res.users"].create(
            {
                "name": "Company A accountant",
                "login": "company_a_accountant",
                "company_id": self.env.company.id,
                "company_ids": [Command.set(self.env.company.ids)],
                "group_ids": [
                    Command.set(self.env.ref("account.group_account_manager").ids)
                ],
            }
        )

        with self.assertRaises(UserError):
            term.with_user(user_a).unlink()
        self.assertTrue(term.exists())

    def test_group_memo_is_not_drawn_while_the_wizard_is_edited(self):
        invoices = self.init_invoice(
            "out_invoice", post=True, invoice_date="2026-08-01", amounts=[100.0]
        ) + self.init_invoice(
            "out_invoice", post=True, invoice_date="2026-08-01", amounts=[50.0]
        )
        Company = type(self.env["res.company"])
        draw = Company.acquire_next_batch_payment_communication
        drawn = []

        def counting_draw(company):
            drawn.append(company)
            return draw(company)

        with patch.object(
            Company, "acquire_next_batch_payment_communication", counting_draw
        ):
            wizard = self._register(invoices, group_payment=True)
            wizard.communication
            wizard.amount = 120.0
            wizard.communication
            wizard.amount = 150.0
            wizard.communication
            self.assertEqual(drawn, [])

            payment = wizard._create_payments()

        self.assertEqual(len(drawn), 1)
        self.assertTrue(payment.memo.startswith("GROUP/"))

    def test_group_memo_shows_the_next_number_without_consuming_it(self):
        invoices = self.init_invoice(
            "out_invoice", post=True, invoice_date="2026-08-01", amounts=[100.0]
        ) + self.init_invoice(
            "out_invoice", post=True, invoice_date="2026-08-01", amounts=[50.0]
        )
        wizard = self._register(invoices, group_payment=True)
        preview = wizard.communication
        self.assertTrue(preview.startswith("GROUP/"))
        wizard.amount = 120.0
        self.assertEqual(wizard.communication, preview)

        payment = wizard._create_payments()

        self.assertEqual(payment.memo, preview)

    def test_a_cleared_memo_stays_empty(self):
        single = self.init_invoice(
            "out_invoice", post=True, invoice_date="2026-08-01", amounts=[100.0]
        )
        grouped = self.init_invoice(
            "out_invoice", post=True, invoice_date="2026-08-01", amounts=[40.0]
        ) + self.init_invoice(
            "out_invoice", post=True, invoice_date="2026-08-01", amounts=[60.0]
        )
        for moves, vals in ((single, {}), (grouped, {"group_payment": True})):
            wizard = self._register(moves, **vals)
            self.assertTrue(wizard.communication)
            wizard.communication = False

            payment = wizard._create_payments()

            self.assertFalse(payment.memo)

    def test_an_edited_group_memo_is_kept_and_draws_no_number(self):
        invoices = self.init_invoice(
            "out_invoice", post=True, invoice_date="2026-08-01", amounts=[100.0]
        ) + self.init_invoice(
            "out_invoice", post=True, invoice_date="2026-08-01", amounts=[50.0]
        )
        wizard = self._register(invoices, group_payment=True)
        wizard.communication = "customer reference 42"
        Company = type(self.env["res.company"])
        with patch.object(
            Company,
            "acquire_next_batch_payment_communication",
            side_effect=AssertionError("drew a GROUP number"),
        ):
            payment = wizard._create_payments()

        self.assertEqual(payment.memo, "customer reference 42")

    def test_duplicate_warning_of_several_edited_payments_at_once(self):
        first, second = self._payment(), self._payment(amount=300.0)
        twin = self._payment(amount=200.0)
        edits = first.new({"amount": 200.0}, origin=first) | second.new(
            {"amount": 200.0}, origin=second
        )

        duplicates = edits.mapped("duplicate_payment_ids")._origin

        self.assertIn(twin, duplicates)

    def test_moveless_refund_leftovers_follow_the_partner_type(self):
        for partner_type, payment_type, account_type in (
            ("customer", "outbound", "asset_receivable"),
            ("supplier", "inbound", "liability_payable"),
        ):
            payment = self._payment(
                amount=40.0, partner_type=partner_type, payment_type=payment_type
            )

            vals_list = payment._get_amls_for_payment_without_move()

            accounts = self.env["account.account"].browse(
                [v["account_id"] for v in vals_list]
            )
            self.assertEqual(set(accounts.mapped("account_type")), {account_type})

    def test_confirming_a_selection_leaves_a_rejected_cash_payment_rejected(self):
        self.cash_journal.inbound_payment_channel_ids.payment_account_id = (
            self.cash_journal.default_account_id
        )
        payment = self._payment(post=True, journal_id=self.cash_journal.id)
        self.assertEqual(payment.state, "paid")
        payment.action_reject()

        (payment + self._payment(journal_id=self.cash_journal.id)).action_post()

        self.assertEqual(payment.state, "rejected")

    def test_a_detached_channel_is_named_without_a_journal(self):
        channel = self.bank_journal.inbound_payment_channel_ids[:1]
        self.assertEqual(
            channel.display_name, f"{channel.name} ({self.bank_journal.name})"
        )
        payment = self._payment(payment_channel_id=channel.id)

        channel.unlink()

        self.assertTrue(channel.exists())
        self.assertFalse(channel.journal_id)
        self.assertEqual(payment.payment_channel_id.display_name, channel.name)

    def test_unknown_payment_method_code_yields_a_domain(self):
        self.assertTrue(
            self.env["account.payment.method"]._get_domain_payment_method(
                "no_such_method_code"
            )
        )


@tagged("post_install", "-at_install")
class TestMarinPayWizardBatches(AccountTestInvoicingCommon):
    def _register(self, moves, **vals):
        return (
            self.env["wizard.account.move.line.pay"]
            .with_context(active_model="account.move", active_ids=moves.ids)
            .create(vals)
        )

    def _bank_account(self, acc_number, trusted):
        return self.env["res.partner.bank.account"].create(
            {
                "acc_number": acc_number,
                "partner_id": self.partner_a.id,
                "acc_type": "bank",
                "allow_out_payment": trusted,
            }
        )

    def _needing_bank_account(self):
        return patch.object(
            type(self.env["account.payment"]),
            "_get_method_codes_needing_bank_account",
            lambda records: ["manual"],
        )

    def test_trust_check_reads_the_bank_account_chosen_in_the_wizard(self):
        untrusted = self._bank_account("111111", trusted=False)
        trusted = self._bank_account("222222", trusted=True)
        bill = self.init_invoice(
            "in_invoice",
            partner=self.partner_a,
            invoice_date="2017-01-01",
            amounts=[100],
        )
        bill.bank_account_id = untrusted
        bill.action_post()

        with self._needing_bank_account():
            wizard = self._register(bill, bank_account_id=trusted.id)
            self.assertTrue(wizard.require_partner_bank_account)
            self.assertEqual(wizard.untrusted_payments_count, 0)
            payment = wizard._create_payments()

        self.assertEqual(payment.bank_account_id, trusted)
        self.assertEqual(
            bill.payment_state, self.env["account.move"]._get_invoice_in_payment_state()
        )

    def test_an_inbound_payment_is_not_held_to_a_trusted_recipient_account(self):
        invoice = self.init_invoice(
            "out_invoice",
            partner=self.partner_a,
            invoice_date="2017-01-01",
            amounts=[100],
            post=True,
        )

        with self._needing_bank_account():
            wizard = self._register(invoice)
            self.assertTrue(wizard.require_partner_bank_account)
            self.assertFalse(wizard.missing_account_partners)
            payment = wizard._create_payments()

        self.assertEqual(payment.payment_type, "inbound")
        self.assertNotEqual(payment.state, "draft")

    def test_payment_count_counts_moves_not_installments(self):
        invoices = self.init_invoice(
            "out_invoice",
            partner=self.partner_b,
            invoice_date="2017-01-01",
            amounts=[100],
            post=True,
        ) + self.init_invoice(
            "out_invoice",
            partner=self.partner_b,
            invoice_date="2017-01-01",
            amounts=[200],
            post=True,
        )
        self.assertEqual(
            len(invoices.line_ids.filtered(lambda l: l.display_type == "payment_term")),
            4,
        )

        wizard = self._register(invoices, payment_date="2026-01-01")
        self.assertFalse(wizard.group_payment)
        self.assertEqual(wizard.total_payments_amount, 2)

        payments = wizard._create_payments()
        self.assertEqual(len(payments), 2)

    def test_payment_count_of_several_partners_counts_moves(self):
        invoices = self.init_invoice(
            "out_invoice",
            partner=self.partner_b,
            invoice_date="2017-01-01",
            amounts=[100],
            post=True,
        ) + self.init_invoice(
            "out_invoice",
            partner=self.partner_a,
            invoice_date="2017-01-01",
            amounts=[200],
            post=True,
        )

        wizard = self._register(invoices, payment_date="2026-01-01")
        self.assertFalse(wizard.can_edit_wizard)
        self.assertFalse(wizard.can_group_payments)
        self.assertEqual(wizard.total_payments_amount, 2)
        self.assertEqual(len(wizard._create_payments()), 2)

    def test_untrusted_count_counts_moves_not_installments(self):
        untrusted = self._bank_account("333333", trusted=False)
        bills = self.env["account.move"]
        for amount in (100, 200):
            bill = self.init_invoice(
                "in_invoice",
                partner=self.partner_a,
                invoice_date="2017-01-01",
                amounts=[amount],
            )
            bill.invoice_payment_term_id = self.pay_terms_b
            bill.bank_account_id = untrusted
            bill.action_post()
            bills += bill

        with self._needing_bank_account():
            wizard = self._register(bills, payment_date="2026-01-01")
            self.assertFalse(wizard.group_payment)
            self.assertEqual(wizard.total_payments_amount, 2)
            self.assertEqual(wizard.untrusted_payments_count, 2)

    def test_several_payments_go_to_the_account_the_trust_check_read(self):
        archived = self._bank_account("444444", trusted=False)
        trusted = self._bank_account("555555", trusted=True)
        bills = self.env["account.move"]
        for amount in (100, 200):
            bill = self.init_invoice(
                "in_invoice",
                partner=self.partner_a,
                invoice_date="2017-01-01",
                amounts=[amount],
            )
            bill.bank_account_id = archived
            bill.action_post()
            bills += bill
        archived.action_archive()

        with self._needing_bank_account():
            wizard = self._register(bills, payment_date="2026-01-01")
            self.assertFalse(wizard.group_payment)
            self.assertEqual(wizard.untrusted_payments_count, 0)
            payments = wizard._create_payments()

        self.assertEqual(len(payments), 2)
        self.assertEqual(payments.bank_account_id, trusted)

    def _outbound_method_needing_a_bank_account(self):
        Method = type(self.env["account.payment.method"])
        information = Method._get_payment_method_information

        def _get_payment_method_information(records):
            return {
                **information(records),
                "marin_wire": {"mode": "multi", "type": ("bank",)},
            }

        method_patch = patch.object(
            Method, "_get_payment_method_information", _get_payment_method_information
        )
        method_patch.start()
        self.addCleanup(method_patch.stop)
        self.env["account.payment.method"].sudo().create(
            {"name": "Marin Wire", "code": "marin_wire", "payment_type": "outbound"}
        )
        journal = self.company_data["default_journal_bank"]
        journal.outbound_payment_channel_ids.filtered(
            lambda channel: channel.code == "marin_wire"
        ).sequence = 0
        self.assertEqual(
            journal._get_available_payment_channels("outbound")[:1].code, "marin_wire"
        )
        return patch.object(
            type(self.env["account.payment"]),
            "_get_method_codes_needing_bank_account",
            lambda records: ["marin_wire"],
        )

    def _mixed_direction_moves(self, refund_bank_account):
        invoice = self.init_invoice(
            "out_invoice",
            partner=self.partner_a,
            invoice_date="2017-01-01",
            amounts=[100],
            post=True,
        )
        refund = self.init_invoice(
            "out_refund",
            partner=self.partner_b,
            invoice_date="2017-01-01",
            amounts=[200],
        )
        refund.bank_account_id = refund_bank_account
        refund.action_post()
        return invoice, refund

    def test_a_swapped_method_is_held_to_its_own_bank_account_requirement(self):
        untrusted = self.env["res.partner.bank.account"].create(
            {
                "acc_number": "666666",
                "partner_id": self.partner_b.id,
                "acc_type": "bank",
                "allow_out_payment": False,
            }
        )
        invoice, refund = self._mixed_direction_moves(untrusted)

        with self._outbound_method_needing_a_bank_account():
            wizard = self._register(invoice + refund, payment_date="2026-01-01")
            self.assertFalse(wizard.can_edit_wizard)
            self.assertEqual(wizard.payment_type, "inbound")
            self.assertFalse(wizard.require_partner_bank_account)
            self.assertEqual(wizard.untrusted_payments_count, 1)
            self.assertEqual(wizard.untrusted_bank_account_ids, untrusted)
            payments = wizard._create_payments()

        self.assertEqual(payments.payment_type, "inbound")
        self.assertEqual(payments.partner_id, self.partner_a)
        self.assertEqual(refund.payment_state, "not_paid")

    def test_a_swapped_method_needing_a_bank_account_reports_a_missing_one(self):
        invoice, refund = self._mixed_direction_moves(
            self.env["res.partner.bank.account"]
        )

        with self._outbound_method_needing_a_bank_account():
            wizard = self._register(invoice + refund, payment_date="2026-01-01")
            self.assertEqual(wizard.missing_account_partners, self.partner_b)

    def test_a_swapped_method_pays_a_trusted_account(self):
        trusted = self.env["res.partner.bank.account"].create(
            {
                "acc_number": "777777",
                "partner_id": self.partner_b.id,
                "acc_type": "bank",
                "allow_out_payment": True,
            }
        )
        invoice, refund = self._mixed_direction_moves(trusted)

        with self._outbound_method_needing_a_bank_account():
            wizard = self._register(invoice + refund, payment_date="2026-01-01")
            self.assertEqual(wizard.untrusted_payments_count, 0)
            payments = wizard._create_payments()

        outbound = payments.filtered(lambda p: p.payment_type == "outbound")
        self.assertEqual(outbound.payment_method_code, "marin_wire")
        self.assertEqual(outbound.bank_account_id, trusted)
        self.assertEqual(len(payments), 2)


@tagged("post_install", "-at_install")
class TestMarinPaymentReclassification(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.receivable = cls.company_data["default_account_receivable"]
        cls.other_receivable = cls.copy_account(cls.receivable, {"name": "AR RC"})

    def _payment(self):
        payment = self.env["account.payment"].create(
            {
                "amount": 100.0,
                "date": "2026-08-01",
                "partner_id": self.partner_a.id,
                "partner_type": "customer",
                "payment_type": "inbound",
                "journal_id": self.company_data["default_journal_bank"].id,
                "counterpart_account_id": self.other_receivable.id,
            }
        )
        payment.action_post()
        return payment

    def _reclassify(self, payment, account):
        wizard = (
            self.env["wizard.account.payment.correct.accounts"]
            .with_context(default_payment_id=payment.id)
            .create({"date": "2026-09-05"})
        )
        self.assertTrue(wizard.is_locked)
        wizard.counterpart_account_id = account
        wizard.action_correct()
        return self.env["account.move"].search(
            [("reclassified_payment_id", "=", payment.id)]
        )

    def test_a_reclassified_payment_is_not_reclassified_twice(self):
        payment = self._payment()
        self.env.company.account_config_id.fiscalyear_lock_date = "2026-08-31"
        self.assertEqual(len(self._reclassify(payment, self.receivable)), 1)

        with self.assertRaises(UserError):
            self._reclassify(payment, self.receivable)
        self.assertEqual(
            self.env["account.move"].search_count(
                [("reclassified_payment_id", "=", payment.id)]
            ),
            1,
        )

    def test_a_reversed_reclassification_can_be_done_again(self):
        payment = self._payment()
        self.env.company.account_config_id.fiscalyear_lock_date = "2026-08-31"
        first = self._reclassify(payment, self.receivable)
        first._reverse_moves([{"date": "2026-09-06"}], cancel=True)

        self.assertEqual(len(self._reclassify(payment, self.receivable) - first), 1)

    def test_the_liquidity_account_can_be_reclassified_after_the_counterpart(self):
        payment = self._payment()
        self.env.company.account_config_id.fiscalyear_lock_date = "2026-08-31"
        self._reclassify(payment, self.receivable)
        other_liquidity = self.copy_account(
            payment.liquidity_account_id, {"name": "Other liquidity"}
        )
        wizard = (
            self.env["wizard.account.payment.correct.accounts"]
            .with_context(default_payment_id=payment.id)
            .create({"date": "2026-09-05"})
        )
        wizard.liquidity_account_id = other_liquidity

        wizard.action_correct()

        self.assertEqual(
            len(
                self.env["account.move"].search(
                    [("reclassified_payment_id", "=", payment.id)]
                )
            ),
            2,
        )

    def test_reclassification_moves_only_the_open_part_of_the_counterpart(self):
        payment = self._payment()
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner_a.id,
                "invoice_date": "2026-08-01",
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "goods",
                            "price_unit": 60.0,
                            "tax_ids": [Command.clear()],
                        }
                    )
                ],
            }
        )
        term_line = invoice.line_ids.filtered(
            lambda line: line.display_type == "payment_term"
        )
        term_line.account_id = self.other_receivable
        invoice.action_post()
        counterpart = payment._seek_for_lines()[1]
        (counterpart + term_line).reconcile()
        self.assertAlmostEqual(counterpart.amount_residual, -40.0)
        self.env.company.account_config_id.fiscalyear_lock_date = "2026-08-31"

        reclass = self._reclassify(payment, self.receivable)

        self.assertEqual(
            sorted(reclass.line_ids.mapped(lambda l: (l.account_id.id, l.balance))),
            sorted([(self.other_receivable.id, 40.0), (self.receivable.id, -40.0)]),
        )
        self.assertTrue(counterpart.reconciled)
        self.assertFalse(
            reclass.line_ids.filtered(
                lambda l: l.account_id == self.other_receivable and not l.reconciled
            )
        )


@tagged("post_install", "-at_install")
class TestMarinPaymentReclassificationChain(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.account_a = cls.copy_account(
            cls.company_data["default_account_receivable"], {"name": "AR A"}
        )
        cls.account_b = cls.copy_account(cls.account_a, {"name": "AR B"})
        cls.account_c = cls.copy_account(cls.account_a, {"name": "AR C"})

    def _payment(self):
        payment = self.env["account.payment"].create(
            {
                "amount": 100.0,
                "date": "2026-08-01",
                "partner_id": self.partner_a.id,
                "partner_type": "customer",
                "payment_type": "inbound",
                "journal_id": self.company_data["default_journal_bank"].id,
                "counterpart_account_id": self.account_a.id,
            }
        )
        payment.action_post()
        self.env.company.account_config_id.fiscalyear_lock_date = "2026-08-31"
        return payment

    def _wizard(self, payment):
        return (
            self.env["wizard.account.payment.correct.accounts"]
            .with_context(default_payment_id=payment.id)
            .create({"date": "2026-09-05"})
        )

    def _reclassify(self, payment, **accounts):
        wizard = self._wizard(payment)
        before = self._entries(payment)
        for fname, account in accounts.items():
            wizard[fname] = account
        wizard.action_correct()
        return self._entries(payment) - before

    def _entries(self, payment):
        return self.env["account.move"].search(
            [("reclassified_payment_id", "=", payment.id)]
        )

    def _lines(self, account):
        return self.env["account.move.line"].search(
            [("account_id", "=", account.id), ("parent_state", "=", "posted")]
        )

    def _net(self, account):
        return sum(self._lines(account).mapped("balance"))

    def _open(self, account):
        return sum(self._lines(account).mapped("amount_residual"))

    def _invoice_on(self, account, amount):
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner_a.id,
                "invoice_date": "2026-09-01",
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "goods",
                            "price_unit": amount,
                            "tax_ids": [Command.clear()],
                        }
                    )
                ],
            }
        )
        term_line = invoice.line_ids.filtered(
            lambda line: line.display_type == "payment_term"
        )
        term_line.account_id = account
        invoice.action_post()
        return term_line

    def test_a_reclassified_account_can_be_reclassified_again(self):
        payment = self._payment()
        first = self._reclassify(payment, counterpart_account_id=self.account_b)
        wizard = self._wizard(payment)
        self.assertEqual(wizard.counterpart_account_id, self.account_b)

        second = self._reclassify(payment, counterpart_account_id=self.account_c)

        self.assertEqual(len(second), 1)
        self.assertEqual(
            sorted(second.line_ids.mapped(lambda l: (l.account_id.id, l.balance))),
            sorted([(self.account_b.id, 100.0), (self.account_c.id, -100.0)]),
        )
        self.assertTrue(payment._seek_for_lines()[1].reconciled)
        self.assertTrue(
            first.line_ids.filtered(lambda l: l.account_id == self.account_b).reconciled
        )
        self.assertEqual(self._net(self.account_a), 0.0)
        self.assertEqual(self._net(self.account_b), 0.0)
        self.assertEqual(self._net(self.account_c), -100.0)
        self.assertEqual(self._open(self.account_c), -100.0)
        self.assertEqual(self._wizard(payment).counterpart_account_id, self.account_c)
        self.assertEqual(payment.counterpart_account_id, self.account_a)

    def test_a_partly_matched_reclassification_moves_only_its_open_part(self):
        payment = self._payment()
        first = self._reclassify(payment, counterpart_account_id=self.account_b)
        first_b_line = first.line_ids.filtered(lambda l: l.account_id == self.account_b)
        (first_b_line + self._invoice_on(self.account_b, 60.0)).reconcile()
        self.assertAlmostEqual(first_b_line.amount_residual, -40.0)

        second = self._reclassify(payment, counterpart_account_id=self.account_c)

        self.assertEqual(
            sorted(second.line_ids.mapped(lambda l: (l.account_id.id, l.balance))),
            sorted([(self.account_b.id, 40.0), (self.account_c.id, -40.0)]),
        )
        self.assertTrue(first_b_line.reconciled)
        self.assertEqual(self._net(self.account_a), 0.0)
        self.assertEqual(self._net(self.account_b), 0.0)
        self.assertEqual(self._open(self.account_b), 0.0)
        self.assertEqual(self._net(self.account_c), -40.0)
        self.assertEqual(self._open(self.account_c), -40.0)

    def test_a_fully_matched_reclassification_has_nothing_to_move(self):
        payment = self._payment()
        first = self._reclassify(payment, counterpart_account_id=self.account_b)
        (
            first.line_ids.filtered(lambda l: l.account_id == self.account_b)
            + self._invoice_on(self.account_b, 100.0)
        ).reconcile()

        with self.assertRaisesRegex(UserError, "Nothing is left open"):
            self._reclassify(payment, counterpart_account_id=self.account_c)

    def test_a_reversed_link_of_the_chain_is_redone_from_its_source(self):
        payment = self._payment()
        self._reclassify(payment, counterpart_account_id=self.account_b)
        second = self._reclassify(payment, counterpart_account_id=self.account_c)
        second._reverse_moves([{"date": "2026-09-06"}], cancel=True)
        self.assertEqual(self._wizard(payment).counterpart_account_id, self.account_b)
        self.assertEqual(self._open(self.account_c), 0.0)

        third = self._reclassify(payment, counterpart_account_id=self.account_c)

        self.assertEqual(
            sorted(third.line_ids.mapped(lambda l: (l.account_id.id, l.balance))),
            sorted([(self.account_b.id, 100.0), (self.account_c.id, -100.0)]),
        )
        self.assertEqual(self._net(self.account_a), 0.0)
        self.assertEqual(self._net(self.account_b), 0.0)
        self.assertEqual(self._net(self.account_c), -100.0)
        self.assertEqual(self._open(self.account_c), -100.0)

    def test_a_chain_broken_by_reversing_its_first_link_is_refused(self):
        payment = self._payment()
        first = self._reclassify(payment, counterpart_account_id=self.account_b)
        self._reclassify(payment, counterpart_account_id=self.account_c)
        first._reverse_moves([{"date": "2026-09-06"}], cancel=True)

        with self.assertRaisesRegex(UserError, "reverse"):
            self._reclassify(
                payment,
                counterpart_account_id=self.company_data["default_account_receivable"],
            )

    def test_the_liquidity_account_is_reclassified_twice(self):
        payment = self._payment()
        liquidity = payment.liquidity_account_id
        second_liquidity = self.copy_account(liquidity, {"name": "Liquidity 2"})
        third_liquidity = self.copy_account(liquidity, {"name": "Liquidity 3"})
        self._reclassify(
            payment,
            counterpart_account_id=self.account_b,
            liquidity_account_id=second_liquidity,
        )
        wizard = self._wizard(payment)
        self.assertEqual(wizard.liquidity_account_id, second_liquidity)
        self.assertEqual(wizard.counterpart_account_id, self.account_b)

        second = self._reclassify(payment, liquidity_account_id=third_liquidity)

        self.assertEqual(
            sorted(second.line_ids.mapped(lambda l: (l.account_id.id, l.balance))),
            sorted([(second_liquidity.id, -100.0), (third_liquidity.id, 100.0)]),
        )
        self.assertEqual(self._net(liquidity), 0.0)
        self.assertEqual(self._net(second_liquidity), 0.0)
        self.assertEqual(self._net(third_liquidity), 100.0)
        self.assertEqual(self._net(self.account_b), -100.0)

    def test_a_reclassified_payment_in_an_open_period_is_reclassified_again(self):
        payment = self._payment()
        self._reclassify(payment, counterpart_account_id=self.account_b)
        self.env.company.account_config_id.fiscalyear_lock_date = False
        wizard = self._wizard(payment)
        self.assertFalse(wizard.is_locked)
        self.assertTrue(wizard.is_reclassified)

        second = self._reclassify(payment, counterpart_account_id=self.account_c)

        self.assertEqual(len(second), 1)
        self.assertEqual(payment.counterpart_account_id, self.account_a)
        self.assertEqual(self._net(self.account_b), 0.0)
        self.assertEqual(self._net(self.account_c), -100.0)
