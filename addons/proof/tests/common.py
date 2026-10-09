from odoo.tests import TransactionCase, new_test_user

PASSWORD = "proof-pass-1234"


class ProofCase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(cls.env, login="proof_giver", password=PASSWORD)
        cls.other_user = new_test_user(
            cls.env, login="proof_receiver", password=PASSWORD
        )
        cls.subject = cls.env["res.partner"].create({"name": "Handover subject"})
        cls.password_method = cls.env.ref("proof.proof_method_password")
        cls.facts = {"amount": "1500.00", "currency": "MXN"}
        cls.summary = [["Amount", "$ 1,500.00"]]

    def _issue(self, user=None, facts=None, purpose="test.handover"):
        return (
            self.env["proof.challenge"]
            .with_user(user or self.user)
            ._issue(
                self.subject,
                purpose,
                facts or self.facts,
                self.password_method,
                summary=self.summary,
            )
        )

    def _get_challenge(self, params):
        challenges = self.env["proof.challenge"].sudo()
        return challenges.search(
            [("token_hash", "=", challenges._get_token_hash(params["token"]))]
        )

    def _redeem(
        self,
        params,
        user=None,
        password=PASSWORD,
        facts=None,
        purpose="test.handover",
        record=None,
        method_code="password",
    ):
        return (
            self.env["proof.challenge"]
            .with_user(user or self.user)
            ._redeem(
                params["token"],
                method_code,
                {"password": password},
                record or self.subject,
                purpose,
                facts or self.facts,
            )
        )

    def _prove(self, user=None):
        return self._redeem(self._issue(user=user), user=user)
