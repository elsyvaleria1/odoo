from odoo.libs.json import loads as json_loads
from odoo.tests import tagged

from odoo.addons.mail.tests.common import MockEmail
from odoo.addons.sign.tests.sign_controller_common import TestSignControllerCommon


@tagged("post_install", "-at_install")
class TestSignerProofRoute(MockEmail, TestSignControllerCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.signer = cls.env["res.partner"].create(
            {"name": "Ferreteria Lupita", "email": "lupita@example.com"}
        )
        cls.role_signer_1.auth_method = "proof"

    def _ask(self, item):
        response = self._json_url_open(
            f"/sign/proof/{item.sign_request_id.id}/{item.access_token}",
            {},
        )
        return json_loads(response.content)["result"]

    def _item(self, signer=None):
        sign_request = self.create_sign_request_1_role(
            signer if signer is not None else self.signer, self.env["res.partner"]
        )
        return sign_request.request_item_ids

    def test_a_signer_is_sent_only_so_many_codes(self):
        item = self._item()

        with self.mock_mail_gateway():
            answers = [self._ask(item) for _call in range(4)]

        self.assertTrue(all("token" in answer for answer in answers[:3]))
        self.assertIn("Several codes were just sent", answers[3]["error"])

    def test_a_request_no_internal_user_sent_still_asks_a_code(self):
        item = self._item()
        item.sign_request_id.sudo().create_uid = self.env.ref("base.public_user")

        with self.mock_mail_gateway():
            answer = self._ask(item)

        self.assertEqual(answer["sent_to"], "l*****@example.com")
