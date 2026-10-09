import re

from odoo.tests import tagged
from odoo.tools import SQL

from odoo.addons.mail.tests.common import MockEmail
from odoo.addons.sign.tests.sign_request_common import SignRequestCommon
from odoo.addons.sign_proof.controllers.main import SignProof


@tagged("post_install", "-at_install")
class TestSignerProof(MockEmail, SignRequestCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.signer = cls.env["res.partner"].create(
            {"name": "Ferreteria Lupita", "email": "lupita@example.com"}
        )
        cls.role_signer_1.auth_method = "proof"

    def setUp(self):
        super().setUp()
        self.sign_request = self.create_sign_request_1_role(
            self.signer, self.env["res.partner"]
        )
        self.item = self.sign_request.request_item_ids.sudo()
        self.controller = SignProof()

    def _issue(self):
        with self.mock_mail_gateway():
            params = self.item._issue_signer_proof()
            code = re.search(r">\s*(\d{6})\s*<", self._new_mails.body_html).group(1)
        return params, code

    def _answer(self, params, code):
        return self.controller._acquire_auth_method_result(
            self.item,
            proof={
                "token": params["token"],
                "method": params["methods"][0]["code"],
                "code": code,
            },
        )

    def test_the_code_goes_to_the_signer_and_proves_it_is_them(self):
        params, code = self._issue()
        self.assertEqual(params["signer"], "Ferreteria Lupita")
        self.assertEqual([m["code"] for m in params["methods"]], ["email_code"])

        result = self._answer(params, code)

        self.assertEqual(result, {"success": True})
        evidence = self.item.proof_evidence_id.sudo()
        self.assertEqual(evidence.partner_id, self.signer)
        self.assertEqual(evidence.user_id, self.sign_request.create_uid)
        self.assertEqual(evidence.facts["item"], self.item.id)
        self.assertIn("proved it is them", self.sign_request.message_ids[0].body)

    def test_a_wrong_or_missing_code_does_not_sign(self):
        params, code = self._issue()

        wrong = self._answer(params, f"{(int(code) + 1) % 10**6:06d}")
        missing = self.controller._acquire_auth_method_result(self.item)

        self.assertEqual(wrong["proof"], True)
        self.assertIn("not the one we sent", wrong["message"])
        self.assertEqual(missing, {"success": False, "proof": True})
        self.assertFalse(self.item.proof_evidence_id)

    def test_the_signature_entry_covers_the_evidence(self):
        params, code = self._issue()
        self._answer(params, code)

        self.item.sign(self.single_signer_sign_values)

        log = self.sign_request.sudo().sign_log_ids.filtered(
            lambda log: log.action == "sign"
        )
        self.assertEqual(log.hash_version, 3)
        self.assertEqual(log.signer_evidence, self.item.proof_evidence_id.sudo().hash)
        logs = self.sign_request.sudo().sign_log_ids
        self.assertIsNone(logs._get_integrity_error())
        self.env.cr.execute(
            SQL("UPDATE sign_log SET signer_evidence = 'forged' WHERE id = %s", log.id)
        )
        logs.invalidate_model()
        self.assertIn("no longer matches its hash", logs._get_integrity_error())

    def test_another_method_is_left_to_sign(self):
        self.role_signer_1.auth_method = "sms"

        result = self.controller._acquire_auth_method_result(self.item)

        self.assertFalse(result["success"])
        self.assertNotIn("proof", result)
