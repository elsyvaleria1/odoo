from odoo.tests import tagged

from .sign_request_common import SignRequestCommon


@tagged("post_install", "-at_install")
class TestSignTokenRotation(SignRequestCommon):
    def assert_renewed(self, item, before):
        SignRequestItem = self.env["sign.request.item"]
        item.invalidate_recordset(["access_token"])
        self.assertFalse(SignRequestItem._from_signer_token(before))
        self.assertTrue(item.sudo().access_token)
        self.assertNotEqual(item.sudo().access_token, before)
        self.assertEqual(
            SignRequestItem._from_signer_token(item.sudo().access_token), item
        )

    def test_a_reassigned_signer_gets_a_fresh_link(self):
        sign_request = self.create_sign_request_no_item(
            signer=self.partner_1, cc_partners=self.partner_4
        )
        item = sign_request.request_item_ids
        item.role_id.change_authorized = True
        before = item.sudo().access_token
        self.assertTrue(item.is_mail_sent)

        item.write({"partner_id": self.partner_5.id})

        self.assert_renewed(item, before)
        self.assertFalse(item.is_mail_sent)

    def test_a_canceled_request_revokes_every_signer_link(self):
        sign_request = self.create_sign_request_2_roles(
            signer_1=self.partner_1, signer_2=self.partner_2, cc_partners=self.partner_4
        )
        items = sign_request.request_item_ids
        before = [item.sudo().access_token for item in items]
        request_before = sign_request.access_token

        sign_request.cancel()

        for token in before:
            self.assertFalse(self.env["sign.request.item"]._from_signer_token(token))
        SignRequest = self.env["sign.request"]
        self.assertFalse(
            SignRequest._from_request_token(request_before, sign_request.id)
        )
        self.assertTrue(sign_request.access_token)
        self.assertNotEqual(sign_request.access_token, request_before)
        self.assertEqual(
            SignRequest._from_request_token(sign_request.access_token, sign_request.id),
            sign_request,
        )

    def test_a_changed_signer_email_renews_the_link(self):
        sign_request = self.create_sign_request_no_item(
            signer=self.partner_1, cc_partners=self.partner_4
        )
        item = sign_request.request_item_ids
        before = item.sudo().access_token

        self.partner_1.write({"email": "laurie.poiret.rotated@example.com"})

        self.assert_renewed(item, before)
