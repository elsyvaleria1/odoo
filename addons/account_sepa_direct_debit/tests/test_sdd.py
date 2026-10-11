import datetime

from odoo import Command, fields
from odoo.exceptions import AccessError, RedirectWarning, UserError, ValidationError
from odoo.tests import freeze_time, tagged
from odoo.tests.common import new_test_user

from odoo.addons.account_sepa_direct_debit.tests.common import SDDTestCommon


@tagged("post_install", "-at_install")
class SDDTest(SDDTestCommon):
    def test_sdd(self):
        payments_agrolait = self.invoice_agrolait.reconciled_payment_ids
        self.assertEqual(
            self.invoice_agrolait.payment_state,
            self.env["account.move"]._get_invoice_in_payment_state(),
            "This invoice should have payments and in payment state thanks to the mandate",
        )
        self.assertEqual(payments_agrolait.sdd_mandate_id, self.mandate_agrolait)
        self.assertEqual(
            self.mandate_agrolait.payment_ids,
            payments_agrolait,
            "The mandate should be linked to the payment",
        )
        payments_china_export = self.invoice_china_export.reconciled_payment_ids
        self.assertEqual(
            self.invoice_china_export.payment_state,
            self.env["account.move"]._get_invoice_in_payment_state(),
            "This invoice should have have payments and in payment state thanks to the mandate",
        )
        self.assertEqual(
            payments_china_export.sdd_mandate_id, self.mandate_china_export
        )
        self.assertEqual(
            self.mandate_china_export.payment_ids,
            payments_china_export,
            "The mandate should be linked to the payment",
        )
        payments_no_bic = self.invoice_no_bic.reconciled_payment_ids
        self.assertEqual(
            self.invoice_no_bic.payment_state,
            self.env["account.move"]._get_invoice_in_payment_state(),
            "This invoice should have payments and in payment state thanks to the mandate",
        )
        self.assertEqual(payments_no_bic.sdd_mandate_id, self.mandate_no_bic)
        self.assertEqual(
            self.mandate_no_bic.payment_ids,
            payments_no_bic,
            "The mandate should be linked to the payment",
        )
        payments = (
            self.invoice_agrolait + self.invoice_china_export + self.invoice_no_bic
        ).reconciled_payment_ids
        self.reconcile_payments(payments)
        self.env.invalidate_all()
        self.assertEqual(
            self.mandate_agrolait.paid_invoice_ids,
            self.invoice_agrolait,
            "The mandate should be linked to the paid invoice",
        )
        self.assertEqual(
            self.mandate_china_export.paid_invoice_ids,
            self.invoice_china_export,
            "The mandate should be linked to the paid invoice",
        )
        self.assertEqual(
            self.mandate_no_bic.paid_invoice_ids,
            self.invoice_no_bic,
            "The mandate should be linked to the paid invoice",
        )

        self.assertEqual(
            self.mandate_agrolait.state,
            "active",
            "A recurrent mandate should stay confirmed after accepting a payment",
        )
        self.assertEqual(
            self.mandate_china_export.state,
            "closed",
            "A one-off mandate should be closed after accepting a payment",
        )
        self.assertEqual(
            self.mandate_no_bic.state,
            "closed",
            "A one-off mandate should be closed after accepting a payment",
        )

        payment_agrolait = self.invoice_agrolait.reconciled_payment_ids
        payment_agrolait.action_draft()
        payment_agrolait.move_id.line_ids.remove_move_reconcile()
        self.assertEqual(self.invoice_agrolait.payment_state, "not_paid")

    def test_xml_pain_008_001_08_generation(self):
        self.sdd_company_bank_journal.debit_sepa_pain_version = "pain.008.001.08"

        for invoice in (self.invoice_agrolait, self.invoice_no_bic):
            payment = invoice.reconciled_payment_ids
            payment.generate_xml(self.sdd_company, fields.Date.today(), True)

        payment = self.invoice_china_export.reconciled_payment_ids

        self.partner_china_export.write(
            {"city": False, "country_id": self.country_china}
        )
        with self.assertRaises(UserError):
            payment.generate_xml(self.sdd_company, fields.Date.today(), True)

        self.partner_china_export.write(
            {"city": "China Town", "country_id": self.country_china}
        )
        payment.generate_xml(self.sdd_company, fields.Date.today(), True)

    @freeze_time("2019-01-01")
    def test_expiry(self):
        self.mandate_agrolait.action_revoke_mandate()
        self.assertEqual(self.mandate_agrolait.state, "revoked")

        mandate = self.create_mandate(
            self.partner_agrolait,
            self.partner_bank_agrolait,
            False,
            self.sdd_company,
            "CORE",
        )
        mandate.start_date = "2020-01-01"
        mandate.end_date = "2025-01-30"
        self.assertEqual(mandate.state, "draft")
        mandate.action_validate_mandate()
        mandate.cron_update_mandates_states()
        self.assertEqual(
            mandate.state, "active"
        )

        with freeze_time(
            "2022-12-02"
        ):
            mandates_per_validity = mandate._update_and_partition_state_by_validity()
            self.assertTrue(
                mandates_per_validity["expiring"], "The mandate is expiring soon"
            )

            new_invoice = self.create_invoice(self.partner_agrolait)
            payment = self.pay_with_mandate(
                new_invoice
            )
            payment.action_validate()
            mandates_per_validity = mandate._update_and_partition_state_by_validity()
            self.assertTrue(
                mandates_per_validity["valid"],
                "The mandate should not be expiring soon anymore, as we have reset the period",
            )
            new_expiry_date = next(
                iter(mandate._get_expiry_date_per_mandate().values())
            ).isoformat()
            self.assertEqual(
                new_expiry_date,
                "2025-01-30",
                "The new expiry date is the end date, as the last collection + 36 month is after that date",
            )

        with freeze_time("2025-01-01"):
            mandates_per_validity = mandate._update_and_partition_state_by_validity()
            self.assertTrue(
                mandates_per_validity["expiring"], "The mandate is expiring soon"
            )

        with freeze_time("2025-01-31"):
            mandates_per_validity = mandate._update_and_partition_state_by_validity()
            self.assertTrue(mandates_per_validity["invalid"], "The mandate is expired")
            self.assertEqual(mandate.state, "closed")

    def test_required_data(self):
        stateless_partner = self.env["res.partner"].create(
            {
                "name": "stateless partner",
            }
        )
        stateless_iban_account = self.env["res.partner.bank.account"].create(
            {
                "acc_number": "NL61INGB6008851617",
                "partner_id": stateless_partner.id,
            }
        )
        stateless_mandate = self.env["sdd.mandate"].create(
            {
                "partner_id": stateless_partner.id,
                "bank_account_id": stateless_iban_account.id,
            }
        )

        bankless_partner = self.env["res.partner"].create(
            {
                "name": "no bank partner",
                "country_id": self.env.ref("base.nl").id,
            }
        )
        not_iban_bank_account = self.env["res.partner.bank.account"].create(
            {
                "acc_number": "01",
                "partner_id": bankless_partner.id,
            }
        )
        bankless_mandate = self.env["sdd.mandate"].create(
            {
                "partner_id": bankless_partner.id,
            }
        )

        with self.assertRaises(
            RedirectWarning,
            msg="The country of the partner should be set to go forward",
        ):
            stateless_mandate.action_send_and_print()
        stateless_mandate.partner_id.country_id = self.env.ref("base.nl")
        stateless_mandate.action_send_and_print()
        bankless_mandate.action_send_and_print()

        stateless_mandate.action_validate_mandate()
        with self.assertRaises(
            UserError, msg="No partner bank should raise an error when going forward"
        ):
            bankless_mandate.action_validate_mandate()

        bankless_mandate.bank_account_id = not_iban_bank_account
        with self.assertRaises(
            UserError, msg="The bank account isn't an iban bank account"
        ):
            bankless_mandate.action_validate_mandate()

        bankless_mandate.bank_account_id = self.env["res.partner.bank.account"].create(
            {
                "acc_number": "NL43INGB9822994664",
                "partner_id": bankless_partner.id,
            }
        )
        bankless_mandate.action_validate_mandate()

    @freeze_time("2024-01-01")
    def test_collection_date(self):
        partner = self.env["res.partner"].create(
            {
                "name": "partner",
                "country_id": self.env.ref("base.nl").id,
            }
        )
        iban_account = self.env["res.partner.bank.account"].create(
            {
                "acc_number": "NL61INGB6008851617",
                "partner_id": partner.id,
            }
        )

        with self.assertRaises(
            UserError, msg="Cannot have a pre-notification period under 2 days"
        ):
            self.env["sdd.mandate"].create(
                {
                    "partner_id": partner.id,
                    "bank_account_id": iban_account.id,
                    "pre_notification_period": 1,
                }
            )
        mandate = self.env["sdd.mandate"].create(
            {
                "partner_id": partner.id,
                "bank_account_id": iban_account.id,
                "pre_notification_period": 2,
            }
        )

        mandate.pre_notification_period = (
            14
        )
        mandate.action_validate_mandate()

        invoice = self.create_invoice(partner)
        payment = self.pay_with_mandate(invoice)
        unchanged_data = {
            "payment_ids": [Command.set(payment.ids)],
            "journal_id": payment.journal_id.id,
        }
        with self.assertRaises(
            ValidationError,
            msg="Collection date should not be in the 2 day period required for the bank to process",
        ):
            self.env["account.batch.payment"].create(
                {
                    **unchanged_data,
                    "sdd_required_collection_date": fields.Date.context_today(mandate)
                    + datetime.timedelta(days=1),
                }
            )

        batch_payment = self.env["account.batch.payment"].create(
            {
                **unchanged_data,
                "sdd_required_collection_date": fields.Date.context_today(mandate)
                + datetime.timedelta(days=2),
            }
        )

        self.assertEqual(
            batch_payment.sdd_first_time_payment_ids,
            payment,
            "The first-time payments should be set correctly.",
        )
        self.assertEqual(
            batch_payment.sdd_min_required_collection_date,
            fields.Date.context_today(mandate) + datetime.timedelta(days=5),
            "The minimum required collection date should be set at 5 days after today.",
        )

        batch_payment.confirm_batch()


        self.reconcile_payments(payment)
        self.assertTrue(payment.is_bank_matched)

        new_invoice = self.create_invoice(partner)
        new_payment = self.pay_with_mandate(new_invoice)
        unchanged_data["payment_ids"] = [Command.set(new_payment.ids)]
        with self.assertRaises(
            ValidationError,
            msg="Collection date should not be in the 2 day period required for the bank to process if all the mandates are already used at least once",
        ):
            self.env["account.batch.payment"].create(
                {
                    **unchanged_data,
                    "sdd_required_collection_date": fields.Date.context_today(mandate)
                    + datetime.timedelta(days=1),
                }
            )

        new_batch_payment = self.env["account.batch.payment"].create(
            {
                **unchanged_data,
                "sdd_required_collection_date": fields.Date.context_today(mandate)
                + datetime.timedelta(days=2),
            }
        )

        self.assertFalse(
            batch_payment.sdd_first_time_payment_ids,
            "The first-time payments should be empty.",
        )
        self.assertFalse(
            batch_payment.sdd_min_required_collection_date,
            "The minimum required collection date should not be set.",
        )

        new_batch_payment.confirm_batch()

    def test_batch_register_payment_all_valids(self):
        mandate_china_export = self.create_mandate(
            self.partner_china_export,
            self.partner_bank_china_export,
            False,
            self.sdd_company,
        )
        mandate_china_export.action_validate_mandate()

        invoices = self.create_invoice(self.partner_agrolait) + self.create_invoice(
            self.partner_china_export
        )
        journal = self.sdd_company_bank_journal
        wizard = (
            self.env["wizard.account.move.line.pay"]
            .with_context(
                {
                    "active_ids": invoices.line_ids.ids,
                    "active_model": "account.move.line",
                }
            )
            .create(
                {
                    "journal_id": journal.id,
                    "payment_channel_id": journal.inbound_payment_channel_ids.filtered(
                        lambda l: l.code == "sdd"
                    ).id,
                }
            )
        )
        wizard.action_create_payments()

        self.assertRecordValues(
            invoices.reconciled_payment_ids.sorted("partner_id"),
            [
                {"partner_id": self.partner_agrolait.id},
                {"partner_id": self.partner_china_export.id},
            ],
        )

    def test_batch_register_payment_mixed_valids_invalids(self):
        invoices = self.create_invoice(self.partner_agrolait) + self.create_invoice(
            self.partner_china_export
        )
        journal = self.sdd_company_bank_journal
        wizard = (
            self.env["wizard.account.move.line.pay"]
            .with_context(
                {
                    "active_ids": invoices.line_ids.ids,
                    "active_model": "account.move.line",
                }
            )
            .create(
                {
                    "journal_id": journal.id,
                    "payment_channel_id": journal.inbound_payment_channel_ids.filtered(
                        lambda l: l.code == "sdd"
                    ).id,
                }
            )
        )
        wizard.action_create_payments()
        payments = invoices.reconciled_payment_ids
        self.assertEqual(len(payments), 1, "Only one payment should be created.")
        self.assertEqual(
            payments.partner_id,
            self.partner_agrolait,
            "The payment should be for the 'Agrolait' partner since it have a valid mandate.",
        )

    def test_batch_register_payment_all_invalids(self):
        self.mandate_agrolait.action_revoke_mandate()
        invoices = self.create_invoice(self.partner_agrolait) + self.create_invoice(
            self.partner_china_export
        )
        journal = self.sdd_company_bank_journal
        wizard = (
            self.env["wizard.account.move.line.pay"]
            .with_context(
                {
                    "active_ids": invoices.line_ids.ids,
                    "active_model": "account.move.line",
                }
            )
            .create(
                {
                    "journal_id": journal.id,
                    "payment_channel_id": journal.inbound_payment_channel_ids.filtered(
                        lambda l: l.code == "sdd"
                    ).id,
                }
            )
        )
        with self.assertRaises(
            UserError,
            msg="As there is no payment that can be generated, we raise an error when trying to do so",
        ):
            wizard.action_create_payments()

    def test_batch_payment_group(self):
        mandate_china_export = self.create_mandate(
            self.partner_china_export,
            self.partner_bank_china_export,
            False,
            self.sdd_company,
        )
        mandate_china_export.action_validate_mandate()

        invoices = (
            self.create_invoice(self.partner_agrolait)
            + self.create_invoice(self.partner_agrolait)
            + self.create_invoice(self.partner_china_export)
        )
        journal = self.sdd_company_bank_journal
        wizard = (
            self.env["wizard.account.move.line.pay"]
            .with_context(
                {
                    "active_ids": invoices.line_ids.ids,
                    "active_model": "account.move.line",
                }
            )
            .create(
                {
                    "journal_id": journal.id,
                    "payment_channel_id": journal.inbound_payment_channel_ids.filtered(
                        lambda l: l.code == "sdd"
                    ).id,
                    "group_payment": True,
                }
            )
        )
        res = wizard.action_create_payments()
        payments = self.env["account.payment"].search(res.get("domain", []))
        self.assertEqual(len(payments), 2, "There should be two payments")

    def test_register_payment_other_journal(self):
        bank_journal_copy = self.sdd_company_bank_journal.copy()
        bank_journal_copy.bank_acc_number = "CH9300762011623852958"
        invoices = self.create_invoice(self.partner_agrolait)
        wizard = (
            self.env["wizard.account.move.line.pay"]
            .with_context(
                {
                    "active_ids": invoices.line_ids.ids,
                    "active_model": "account.move.line",
                }
            )
            .create(
                {
                    "journal_id": bank_journal_copy.id,
                    "payment_channel_id": bank_journal_copy.inbound_payment_channel_ids.filtered(
                        lambda l: l.code == "sdd"
                    ).id,
                }
            )
        )
        res = wizard.action_create_payments()
        payments = self.env["account.payment"].search(res.get("domain", []))
        self.assertTrue(payments, "A payment should have been generated")

    def test_user_without_bank_account_validation_role_cannot_validate_mandates(self):
        invoicing_banks_user = new_test_user(
            self.env, "invoicing_banks_user", groups="account.group_account_basic"
        )

        with self.assertRaisesRegex(AccessError, "validate SDD"):
            self.mandate_agrolait.with_user(
                invoicing_banks_user
            ).action_validate_mandate()
