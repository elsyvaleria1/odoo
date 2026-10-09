from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import freeze_time, tagged

from .common import ProofCase


@tagged("at_install", "-post_install")
class TestProofChallenge(ProofCase):
    def test_redeemed_challenge_records_evidence(self):
        params = self._issue()
        challenge = self._get_challenge(params)

        evidence = self._redeem(params)

        self.assertEqual(challenge.state, "redeemed")
        self.assertEqual(evidence.env.uid, self.user.id)
        self.assertEqual(evidence.user_id, self.user)
        self.assertEqual(
            (evidence.res_model, evidence.res_id, evidence.purpose),
            ("res.partner", self.subject.id, "test.handover"),
        )
        self.assertEqual(evidence.facts, self.facts)
        self.assertEqual(evidence.summary, self.summary)
        self.assertEqual(evidence.digest, challenge.digest)
        self.assertEqual(evidence.nonce, challenge.token_hash)
        self.assertNotEqual(challenge.token_hash, params["token"])
        self.assertEqual(evidence.method_id, self.password_method)
        self.assertEqual(evidence.strength, "shared_secret")
        self.assertFalse(evidence.payload)

    def test_issue_returns_the_client_params_once(self):
        params = self._issue()

        challenge = self._get_challenge(params)

        self.assertEqual(len(challenge), 1)
        self.assertEqual(len(params["token"]), 43)
        self.assertEqual(params["summary"], self.summary)
        self.assertEqual(
            params["methods"],
            [{"code": "password", "name": "Password", "options": {}}],
        )

    def test_challenge_is_answered_once(self):
        params = self._issue()
        self._redeem(params)

        with self.assertRaisesRegex(UserError, "expired or was already used"):
            self._redeem(params)

    def test_unknown_token_is_refused(self):
        with self.assertRaisesRegex(UserError, "expired or was already used"):
            self.env["proof.challenge"].with_user(self.user)._redeem(
                "not-a-token",
                "password",
                {"password": "irrelevant"},
                self.subject,
                "test.handover",
                self.facts,
            )

    def test_expired_challenge_is_refused(self):
        params = self._issue()

        with (
            freeze_time(fields.Datetime.now() + timedelta(minutes=6)),
            self.assertRaisesRegex(UserError, "expired or was already used"),
        ):
            self._redeem(params)

    def test_challenge_of_another_user_is_refused(self):
        params = self._issue()

        with self.assertRaisesRegex(UserError, "issued to someone else"):
            self._redeem(params, user=self.other_user)

    def test_challenge_for_another_act_is_refused(self):
        other_subject = self.env["res.partner"].create({"name": "Other subject"})
        cases = [
            {"purpose": "test.other"},
            {"record": other_subject},
        ]
        for case in cases:
            with (
                self.subTest(**{k: str(v) for k, v in case.items()}),
                self.assertRaisesRegex(UserError, "issued for another act"),
            ):
                self._redeem(self._issue(), **case)

    def test_moved_figures_refuse_the_proof(self):
        params = self._issue()

        with self.assertRaisesRegex(UserError, "changed since you were asked"):
            self._redeem(params, facts={"amount": "1400.00", "currency": "MXN"})
        self.assertEqual(self._get_challenge(params).state, "issued")

    def test_method_not_offered_is_refused(self):
        params = self._issue()

        with self.assertRaisesRegex(UserError, "not offered"):
            self._redeem(params, method_code="passkey")

    def test_wrong_password_is_refused(self):
        params = self._issue()

        with self.assertRaisesRegex(UserError, "Incorrect password"):
            self._redeem(params, password="wrong-password")
        self.assertEqual(self._get_challenge(params).state, "issued")

    def test_issue_without_an_enrolled_method_is_refused(self):
        with self.assertRaisesRegex(UserError, "no way set up"):
            self.env["proof.challenge"].with_user(self.user)._issue(
                self.subject,
                "test.handover",
                self.facts,
                self.env["proof.method"],
            )

    def test_a_contact_with_no_method_for_contacts_is_not_asked(self):
        contact = self.env["res.partner"].create({"name": "Outside custodian"})

        with self.assertRaisesRegex(UserError, "Outside custodian has no way set up"):
            self.env["proof.challenge"].with_user(self.user)._issue(
                self.subject,
                "test.handover",
                self.facts,
                self.password_method,
                partner=contact,
            )

    def test_users_cannot_reach_challenges_directly(self):
        challenge = self._get_challenge(self._issue())
        challenges = self.env["proof.challenge"].with_user(self.user)

        with self.assertRaises(AccessError):
            challenges.browse(challenge.id).read(["token_hash"])
        with self.assertRaises(AccessError):
            challenges.create(
                {
                    "token_hash": "forged",
                    "user_id": self.user.id,
                    "purpose": "test.handover",
                    "res_model": "res.partner",
                    "res_id": self.subject.id,
                    "digest": "0" * 64,
                    "date_expire": fields.Datetime.now(),
                }
            )

    def test_stale_challenges_are_collected(self):
        stale = self._get_challenge(self._issue())
        fresh = self._get_challenge(self._issue())

        with freeze_time(fields.Datetime.now() + timedelta(days=2)):
            fresh.date_expire = fields.Datetime.now()
            self.env["proof.challenge"]._gc_challenges()

        self.assertFalse(stale.exists())
        self.assertTrue(fresh.exists())

    def _issue_confirmation(self):
        return (
            self.env["proof.challenge"]
            .with_user(self.user)
            ._issue_confirmation(
                self.subject,
                "test.confirmation",
                self.facts,
                self.env["res.partner"].create({"name": "Customer"}),
                summary=self.summary,
            )
        )

    def test_a_confirmation_no_channel_reaches_is_issued_with_nothing_sent(self):
        challenge = self._issue_confirmation().sudo()

        self.assertEqual(
            (challenge.kind, challenge.state, challenge.user_id),
            ("confirm", "issued", self.user),
        )
        self.assertFalse(challenge.method_ids)
        self.assertFalse(challenge.delivery_ids)
        self.assertEqual(
            challenge.date_expire.date(),
            (fields.Datetime.now() + timedelta(days=3)).date(),
        )

    def test_a_confirmation_is_never_answered_in_the_dialog(self):
        challenge = self._issue_confirmation().sudo()
        with patch.object(
            type(self.env["proof.challenge"]),
            "_get_token_hash",
            return_value=challenge.token_hash,
        ):
            with self.assertRaisesRegex(UserError, "expired or was already used"):
                self._redeem({"token": "any"}, purpose="test.confirmation")

    def test_confirmations_outlive_the_collection_of_stale_challenges(self):
        confirmation = self._issue_confirmation().sudo()

        with freeze_time(fields.Datetime.now() + timedelta(days=5)):
            self.env["proof.challenge"]._gc_challenges()

        self.assertTrue(confirmation.exists())

    def test_withdrawn_confirmation_is_spent(self):
        challenge = self._issue_confirmation().sudo()

        challenge._withdraw()

        self.assertEqual(challenge.state, "withdrawn")
