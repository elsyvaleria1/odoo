import base64
from unittest.mock import patch

from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.pdf_signing import prepare_signing_pki, sign_incrementally
from odoo.tools.misc import file_open

from odoo.addons.sign.tests.test_sign_controllers import TestSignControllerCommon

CONTROLLER = "odoo.addons.sign_emsigner.controllers.main"


@tagged("post_install", "-at_install")
class SignEmsignerCommon(TestSignControllerCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        emsigner_auth_role = cls.env["sign.item.role"].create(
            {"name": "Emsigner Role", "auth_method": "emsigner"}
        )

        cls.template_emsigner = cls.env["sign.template"].create(
            {
                "name": "template_emsigner_test",
            }
        )

        cls.document_emsigner = cls.env["sign.document"].create(
            {
                "attachment_id": cls.attachment.id,
                "template_id": cls.template_emsigner.id,
            }
        )

        cls.env["sign.item"].create(
            [
                {
                    "type_id": cls.env.ref("sign.sign_item_type_signature").id,
                    "required": True,
                    "responsible_id": emsigner_auth_role.id,
                    "page": 1,
                    "posX": 0.273,
                    "posY": 0.158,
                    "document_id": cls.document_emsigner.id,
                    "width": 0.150,
                    "height": 0.015,
                }
            ]
        )

        cls.sign_request_emsigner = cls.env["sign.request"].create(
            {
                "template_id": cls.template_emsigner.id,
                "reference": cls.template_emsigner.display_name,
                "request_item_ids": [
                    Command.create(
                        {
                            "partner_id": cls.partner_1.id,
                            "role_id": emsigner_auth_role.id,
                        }
                    )
                ],
            }
        )

    def create_signature_value(self, sign_item_ids, role_id):
        with file_open("sign/static/demo/signature.png", "rb") as f:
            self.signature_fake = base64.b64encode(f.read())
        return {
            str(sign_id): self.signature_fake.decode("utf-8")
            for sign_id in sign_item_ids.filtered(
                lambda r: not r.responsible_id or r.responsible_id.id == role_id
            ).mapped("id")
        }

    def test_sign_emsigner_with_sign_is_successful(self):
        sign_request_item = self.sign_request_emsigner.request_item_ids[0]
        self.assertEqual(sign_request_item.state, "sent")
        vals = self.create_signature_value(
            self.sign_request_emsigner.template_id.sign_item_ids,
            sign_request_item.role_id.id,
        )
        sign_request_item._sign(vals, validation_required=True)
        self.assertEqual(sign_request_item.state, "sent")
        sign_request_item.write(
            {
                "emsigner_transaction_number": "test1234",
                "emsigner_reference_number": "test3232",
                "emsigner_status": "success",
            }
        )
        sign_request_item._post_fill_request_item()
        self.assertEqual(sign_request_item.state, "completed")
        self.assertEqual(self.sign_request_emsigner.state, "signed")

    def test_sign_emsigner_without_emsigner_status_raises_error(self):
        sign_request_item = self.sign_request_emsigner.request_item_ids[0]
        self.assertEqual(sign_request_item.state, "sent")
        vals = self.create_signature_value(
            self.sign_request_emsigner.template_id.sign_item_ids,
            sign_request_item.role_id.id,
        )
        sign_request_item._sign(vals, validation_required=True)
        self.assertEqual(sign_request_item.state, "sent")
        with self.assertRaises(ValidationError):
            sign_request_item._post_fill_request_item()
        self.assertEqual(sign_request_item.state, "sent")
        self.assertEqual(self.sign_request_emsigner.state, "sent")


@tagged("post_install", "-at_install")
class TestEmsignerResultIsVerified(SignEmsignerCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pki = prepare_signing_pki("Genuine Signer")
        cls.other_request = cls.sign_request_emsigner.copy()

    def _send(self, sign_request):
        item = sign_request.request_item_ids[0]
        sent = {}

        def proxy(url, params, *, env):
            sent["pdf"] = base64.b64decode(params["signature_data"]["File"])
            return {"success": True, "authorization_url": "https://esign.test/"}

        with (
            patch(
                "odoo.addons.iap.models.iap_account.IapAccount.get_credits",
                lambda self, service: 10,
            ),
            patch("odoo.tools.iap.jsonrpc", proxy),
        ):
            response = self._json_url_open(
                f"/sign/sign/{sign_request.id}/{item.access_token}",
                data={
                    "signature": self.create_signature_value(
                        sign_request.template_id.sign_item_ids, item.role_id.id
                    )
                },
            ).json()["result"]
        self.assertTrue(response.get("success"))
        return item, sent["pdf"]

    def _complete(self, item, signed_pdf, state=None):
        with patch(f"{CONTROLLER}._emsigner_trust_roots", lambda: (self.pki.root,)):
            return self._json_url_open(
                "/emsigner_sign/emsigner_successful",
                data={
                    "emsigner_state": state
                    or f"{item.sign_request_id.id}.{item.access_token}",
                    "reference_number": "REF",
                    "transaction_number": "TXN",
                    "return_status": "Success",
                    "error_message": "",
                    "decrypted_data": base64.b64encode(signed_pdf).decode(),
                },
            ).json()["result"]

    def assertStillWaiting(self, item):
        self.assertEqual(item.state, "sent")
        self.assertFalse(item.emsigner_status)
        self.assertFalse(item.emsigner_signer_name)
        self.assertFalse(item.sign_request_id.completed_document_ids)

    def test_a_certified_signature_of_the_sent_document_completes_the_signer(self):
        item, sent = self._send(self.sign_request_emsigner)
        signed = sign_incrementally(sent, self.pki)

        self.assertTrue(self._complete(item, signed).get("success"))
        self.assertEqual(item.state, "completed")
        self.assertEqual(item.emsigner_signer_name, "Genuine Signer")
        self.assertEqual(
            item.sign_request_id.completed_document_ids.file,
            base64.b64encode(signed),
        )

    def test_a_document_nobody_certified_is_refused(self):
        item, sent = self._send(self.sign_request_emsigner)
        forged = sign_incrementally(sent, prepare_signing_pki("Genuine Signer"))

        self.assertFalse(self._complete(item, forged).get("success"))
        self.assertStillWaiting(item)

    def test_the_unsigned_document_is_refused(self):
        item, sent = self._send(self.sign_request_emsigner)

        self.assertFalse(self._complete(item, sent).get("success"))
        self.assertStillWaiting(item)

    def test_a_certified_signature_of_another_document_is_refused(self):
        item, _sent = self._send(self.sign_request_emsigner)
        with file_open("base/tests/minimal.pdf", "rb") as other:
            replaced = sign_incrementally(other.read(), self.pki)

        self.assertFalse(self._complete(item, replaced).get("success"))
        self.assertStillWaiting(item)

    def test_one_request_s_signed_result_does_not_complete_another(self):
        item, sent = self._send(self.sign_request_emsigner)
        other_item, _other_sent = self._send(self.other_request)
        signed = sign_incrementally(sent, self.pki)

        self.assertFalse(self._complete(other_item, signed).get("success"))
        self.assertStillWaiting(other_item)
        self.assertTrue(self._complete(item, signed).get("success"))

    def test_a_revoked_signer_link_completes_nothing(self):
        item, sent = self._send(self.sign_request_emsigner)
        signed = sign_incrementally(sent, self.pki)
        state = f"{item.sign_request_id.id}.{item.access_token}"
        item.sudo()._renew_signer_links("the signer's link was leaked")

        self.assertFalse(self._complete(item, signed, state=state).get("success"))
        self.assertStillWaiting(item)

    def test_a_signer_link_of_another_request_completes_nothing(self):
        item, sent = self._send(self.sign_request_emsigner)
        signed = sign_incrementally(sent, self.pki)
        state = f"{self.other_request.id}.{item.access_token}"

        self.assertFalse(self._complete(item, signed, state=state).get("success"))
        self.assertStillWaiting(item)

    def test_a_malformed_state_is_refused(self):
        item, sent = self._send(self.sign_request_emsigner)
        signed = sign_incrementally(sent, self.pki)

        for state in ("no-separator", "x.token", ".token"):
            with self.subTest(state=state):
                self.assertFalse(
                    self._complete(item, signed, state=state).get("success")
                )
        self.assertStillWaiting(item)
