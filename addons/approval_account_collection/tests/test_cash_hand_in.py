from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import new_test_user, tagged

from odoo.addons.account_collection.tests.common import CollectionCommon


@tagged("post_install", "-at_install")
class TestCashHandIn(CollectionCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.category = cls.env.ref(
            "approval_account_collection.approval_category_cash_hand_in"
        )
        # a software passkey is phase 2's business; the password proves the flow
        cls.category.sudo().proof_method_ids = cls.env.ref(
            "proof.proof_method_password"
        )
        cls.invoice = cls._post_invoice(1500.0)

    def _remit(self, journal, collector=None):
        collector = collector or self.collector
        self._collect(self.invoice, 1500.0, collector=collector)
        remittance = (
            self.env["account.collection.remittance"]
            .with_user(collector)
            .create({"destination_journal_id": journal.id})
        )
        remittance.action_load_custody()
        remittance.action_submit()
        return remittance.with_env(self.env)

    def _decide(self, remittance, user, decision="approve"):
        request = remittance.approval_request_id.with_user(user)
        params = request.action_issue_decision_proof(decision)
        proof = {
            "token": params["token"],
            "method": "password",
            "payload": {"password": user.login},
        }
        if decision == "approve":
            request.action_approve_with_proof(proof)
        else:
            request.with_context(skip_wizard=True, approval_proof=proof).action_refuse()

    def test_validating_a_cash_hand_in_asks_both_parties(self):
        remittance = self._remit(self.till_journal)

        remittance.with_user(self.treasurer).action_validate()

        self.assertEqual(remittance.state, "submitted")
        self.assertEqual(remittance.receiver_id, self.treasurer)
        self.assertEqual(remittance.approval_state, "pending")
        request = remittance.approval_request_id.sudo()
        self.assertEqual(request.approver_ids.user_id, self.collector | self.treasurer)
        self.assertEqual(request.amount, 1500.0)

    def test_both_proofs_validate_it_in_the_receivers_name(self):
        remittance = self._remit(self.till_journal)
        remittance.with_user(self.treasurer).action_validate()

        self._decide(remittance, self.collector)
        self.assertEqual(remittance.state, "submitted")
        self._decide(remittance, self.treasurer)

        self.assertEqual(remittance.state, "done")
        self.assertEqual(remittance.validated_by_id, self.treasurer)
        logs = remittance.approval_request_id.sudo().decision_log_ids.filtered(
            lambda log: log.verdict == "approved"
        )
        self.assertEqual(logs.evidence_id.user_id, self.collector | self.treasurer)
        self.assertEqual(
            set(logs.evidence_id.mapped(lambda e: e.facts["amount"])), {repr(1500.0)}
        )

    def test_a_refusal_keeps_the_cash_out_of_the_till(self):
        remittance = self._remit(self.till_journal)
        remittance.with_user(self.treasurer).action_validate()

        self._decide(remittance, self.collector, "refuse")

        self.assertEqual(remittance.approval_state, "refused")
        self.assertEqual(remittance.state, "submitted")
        with self.assertRaisesRegex(UserError, "was refused or cancelled"):
            remittance.with_user(self.treasurer).action_validate()

    def test_the_figures_cannot_move_while_both_parties_decide(self):
        remittance = self._remit(self.till_journal)
        remittance.with_user(self.treasurer).action_validate()

        with self.assertRaises(UserError):
            remittance.with_user(self.treasurer).amount_handed_in = 1400.0

    def test_a_collector_does_not_receive_their_own_cash(self):
        cashier = new_test_user(
            self.env,
            login="collector_and_treasurer",
            groups="base.group_user,account.group_account_invoice,"
            "account_collection.group_collection_collector",
            company_id=self.company_data["company"].id,
            company_ids=[Command.set(self.company_data["company"].ids)],
        )
        remittance = self._remit(self.till_journal, collector=cashier)

        with self.assertRaisesRegex(UserError, "your own cash"):
            remittance.with_user(cashier).action_validate()

    def test_a_bank_deposit_is_not_asked(self):
        remittance = self._remit(self.bank_journal)

        self.assertFalse(remittance._get_approval_trigger())
        self.assertFalse(remittance.approval_required)
