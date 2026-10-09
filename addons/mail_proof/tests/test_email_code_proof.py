import re

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, new_test_user, tagged

from odoo.addons.mail.tests.common import MockEmail


@tagged("post_install", "-at_install")
class TestEmailCodeProof(MockEmail, TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.archivist = new_test_user(
            cls.env, login="mail_proof_archivist", email="archivist@agromarin.mx"
        )
        cls.custodian = cls.env["res.partner"].create(
            {"name": "Notary Lopez", "email": "notary@notaria.mx"}
        )
        cls.subject = cls.env["res.partner"].create({"name": "Deed 42"})
        cls.method = cls.env.ref("mail_proof.proof_method_email_code")
        cls.facts = {"document": "Deed 42", "custodian": cls.custodian.id}

    def _issue(self, partner=None):
        with self.mock_mail_gateway():
            params = (
                self.env["proof.challenge"]
                .with_user(self.archivist)
                ._issue(
                    self.subject,
                    "test.loan",
                    self.facts,
                    self.method,
                    summary=[["Document", "Deed 42"]],
                    partner=partner if partner is not None else self.custodian,
                )
            )
            mail = self._new_mails
        return params, mail

    def _code(self, mail):
        return re.search(r">\s*(\d{6})\s*<", mail.body_html).group(1)

    def _redeem(self, params, code):
        return (
            self.env["proof.challenge"]
            .with_user(self.archivist)
            ._redeem(
                params["token"],
                "email_code",
                {"code": code},
                self.subject,
                "test.loan",
                self.facts,
            )
        )

    def test_the_code_goes_to_the_contact_and_proves_it_is_them(self):
        params, mail = self._issue()

        self.assertEqual(params["signer"], "Notary Lopez")
        (option,) = params["methods"]
        self.assertEqual(
            option["options"], {"sent_to": "n*****@notaria.mx", "digits": 6}
        )
        self.assertEqual(mail.email_to, self.custodian.email_formatted)
        self.assertIn("Deed 42", mail.body_html)
        evidence = self._redeem(params, self._code(mail)).sudo()

        self.assertEqual(evidence.user_id, self.archivist)
        self.assertEqual(evidence.partner_id, self.custodian)
        self.assertEqual(evidence.strength, "possession")
        self.assertEqual(evidence.payload["sent_to"], "n*****@notaria.mx")
        self.assertIsNone(self.env["proof.evidence"]._get_chain_error())

    def _challenge(self, params):
        challenges = self.env["proof.challenge"].sudo()
        return challenges.search(
            [("token_hash", "=", challenges._get_token_hash(params["token"]))]
        )

    def test_only_the_hash_of_the_code_is_kept(self):
        params, mail = self._issue()
        challenge = self._challenge(params)

        self.assertEqual(len(challenge.code_hash), 64)
        self.assertNotIn(self._code(mail), challenge.code_hash)

    def test_a_wrong_code_is_refused(self):
        params, mail = self._issue()

        with self.assertRaisesRegex(UserError, "not the one we sent"):
            self._redeem(params, f"{(int(self._code(mail)) + 1) % 10**6:06d}")

    def test_five_wrong_codes_spend_the_challenge(self):
        params, mail = self._issue()
        challenge = self._challenge(params)
        # counted in a transaction of its own, which assertRaises' savepoint
        # would roll back here: the count is driven directly
        for _attempt in range(5):
            self.method._count_wrong_code(challenge)

        with self.assertRaisesRegex(UserError, "Too many wrong codes"):
            self._redeem(params, self._code(mail))

    def test_a_contact_without_email_cannot_be_asked(self):
        self.custodian.email = False

        with self.assertRaisesRegex(UserError, "Notary Lopez has no way set up"):
            self._issue()

    def test_a_user_can_prove_with_a_code_to_their_own_email(self):
        params, mail = self._issue(partner=self.env["res.partner"])

        self.assertIsNone(params["signer"])
        self.assertEqual(mail.email_to, self.archivist.email_formatted)
        evidence = self._redeem(params, self._code(mail)).sudo()
        self.assertFalse(evidence.partner_id)
        self.assertEqual(evidence.user_id, self.archivist)
