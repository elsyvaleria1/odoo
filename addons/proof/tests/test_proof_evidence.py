from unittest.mock import patch

from odoo.exceptions import ConcurrencyError, UserError
from odoo.tests import tagged
from odoo.tools import SQL

from .common import ProofCase


@tagged("at_install", "-post_install")
class TestProofEvidence(ProofCase):
    def test_each_proof_chains_after_the_last(self):
        first = self._prove()

        second = self._prove(user=self.other_user)

        self.assertEqual(second.sequence, first.sequence + 1)
        self.assertEqual(second.prev_hash, first.hash)
        self.assertEqual(len(second.hash), 64)
        self.assertIsNone(self.env["proof.evidence"]._get_chain_error())

    def test_evidence_cannot_be_changed_or_deleted(self):
        evidence = self._prove().sudo()

        with self.assertRaisesRegex(UserError, "cannot be changed"):
            evidence.write({"ip": "10.0.0.1"})
        with self.assertRaisesRegex(UserError, "cannot be deleted"):
            evidence.unlink()

    def test_chain_check_reports_a_changed_row(self):
        evidence = self._prove()
        self._prove()
        self.env.cr.execute(
            SQL(
                "UPDATE proof_evidence SET facts = %s WHERE id = %s",
                '{"amount": "1.00", "currency": "MXN"}',
                evidence.id,
            )
        )
        self.env["proof.evidence"].invalidate_model()

        error = self.env["proof.evidence"]._get_chain_error()

        self.assertEqual(
            error, f"Proof {evidence.sequence} was changed after it was recorded."
        )

    def test_chain_check_reports_a_missing_row(self):
        evidence = self._prove()
        position = evidence.sequence
        self._prove()
        self.env.cr.execute(
            SQL("DELETE FROM proof_evidence WHERE id = %s", evidence.id)
        )
        self.env["proof.evidence"].invalidate_model()

        error = self.env["proof.evidence"]._get_chain_error()

        self.assertEqual(error, f"Proof {position} is missing from the chain.")

    def test_chain_check_reports_a_relinked_row(self):
        self._prove()
        evidence = self._prove()
        self.env.cr.execute(
            SQL(
                "UPDATE proof_evidence SET prev_hash = %s WHERE id = %s",
                "0" * 64,
                evidence.id,
            )
        )
        self.env["proof.evidence"].invalidate_model()

        error = self.env["proof.evidence"]._get_chain_error()

        self.assertEqual(
            error, f"Proof {evidence.sequence} is not linked to the proof before it."
        )

    def test_check_chain_action_notifies_the_verdict(self):
        self._prove()
        evidence = self.env["proof.evidence"]

        intact = evidence.action_check_chain()
        self.env.cr.execute("UPDATE proof_evidence SET ip = '10.9.9.9'")
        evidence.invalidate_model()
        broken = evidence.action_check_chain()

        self.assertEqual(intact["params"]["type"], "success")
        self.assertEqual(broken["params"]["type"], "danger")
        self.assertTrue(broken["params"]["sticky"])

    def test_a_concurrent_proof_on_the_same_position_is_retried(self):
        self._prove()
        stale_head = self.env["proof.evidence"]

        with (
            patch.object(
                type(self.env["proof.evidence"]),
                "_get_chain_head",
                lambda self: stale_head,
            ),
            self.assertRaises(ConcurrencyError),
        ):
            self._prove()

    def test_users_read_only_their_own_evidence(self):
        own = self._prove()
        other = self._prove(user=self.other_user)

        visible = self.env["proof.evidence"].with_user(self.user).search([])

        self.assertIn(own, visible)
        self.assertNotIn(other, visible)
