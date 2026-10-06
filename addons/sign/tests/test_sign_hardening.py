import base64
import re
from unittest.mock import patch

from PIL import Image

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tools import file_open, mute_logger

from .sign_controller_common import TestSignControllerCommon
from .sign_request_common import SignRequestCommon
from odoo.addons.sign.models.sign_document import SignDocument, _fix_image_transparency


@tagged("post_install", "-at_install")
class TestSignHardening(SignRequestCommon):
    def _sign_role(self, request, role):
        item = request.request_item_ids.filtered(lambda i: i.role_id == role).sudo()
        values = self.create_sign_values(request.template_id.sign_item_ids, role.id)
        item._sign(values)
        return item

    # C1 -- the 'Waiting for me' filter must return what needs my signature
    def test_need_my_signature_search(self):
        mine = self.create_sign_request_1_role(self.partner_1, self.env["res.partner"])
        other = self.create_sign_request_1_role(self.partner_2, self.env["res.partner"])
        env = self.env(user=self.user_1)
        found = env["sign.request"].search(
            [("need_my_signature", "=", True), ("id", "in", (mine | other).ids)]
        )
        self.assertIn(mine, found)
        self.assertNotIn(other, found)

    # C3 -- a past validity expires only pending requests, never a signed one
    def test_validity_never_expires_signed(self):
        signed = self.create_sign_request_1_role(
            self.partner_1, self.env["res.partner"]
        )
        signed.request_item_ids.sudo()._sign(self.single_signer_sign_values)
        self.assertEqual(signed.state, "signed")
        signed.write({"validity": fields.Date.subtract(fields.Date.today(), days=1)})
        self.assertEqual(signed.state, "signed")

        pending = self.create_sign_request_1_role(
            self.partner_2, self.env["res.partner"]
        )
        pending.write({"validity": fields.Date.subtract(fields.Date.today(), days=1)})
        self.assertEqual(pending.state, "expired")

    # C5 -- a completed signer's integrity survives another signer's refusal
    def test_integrity_survives_refusal(self):
        request = self.create_sign_request_2_roles(
            self.partner_1, self.partner_2, self.env["res.partner"]
        )
        self._sign_role(request, self.role_signer_1)
        self.assertTrue(request.integrity)
        other = request.request_item_ids.filtered(
            lambda i: i.role_id == self.role_signer_2
        )
        other.sudo()._refuse("sent", "no thanks")
        self.assertTrue(
            request.integrity,
            "a completed signer's integrity must survive another signer's refusal",
        )

    # C4 -- one tampered request must not mark a whole read batch as broken
    def test_integrity_not_contaminated_in_batch(self):
        clean = self.create_sign_request_1_role(self.partner_1, self.env["res.partner"])
        clean.request_item_ids.sudo()._sign(self.single_signer_sign_values)
        tampered = self.create_sign_request_1_role(
            self.partner_2, self.env["res.partner"]
        )
        tampered.request_item_ids.sudo()._sign(self.single_signer_sign_values)
        sign_log = tampered.sign_log_ids.filtered(lambda log: log.action == "sign")
        self.env.cr.execute(
            "UPDATE sign_log SET log_hash = 'tampered' WHERE id = %s", [sign_log.id]
        )
        self.env.invalidate_all()
        both = self.env["sign.request"].browse((clean | tampered).ids)
        both.mapped("integrity")
        self.assertTrue(clean.integrity)
        self.assertFalse(tampered.integrity)

    # C6 -- generating completed documents on a multi-record set no longer crashes
    def test_create_completed_documents_multi(self):
        reqs = self.env["sign.request"]
        for partner in (self.partner_1, self.partner_2):
            r = self.create_sign_request_1_role(partner, self.env["res.partner"])
            r.request_item_ids.sudo()._sign(
                self.create_sign_values(
                    r.template_id.sign_item_ids, self.role_signer_1.id
                )
            )
            reqs |= r
        reqs.completed_document_ids.sudo().unlink()
        reqs.sudo().completed_document_attachment_ids = [Command.clear()]
        reqs.sudo()._create_completed_documents()
        for r in reqs:
            self.assertEqual(len(r.completed_document_ids), 1)

    # S6 -- a follower cannot flip states by a direct write
    def test_follower_cannot_write_state(self):
        request = self.create_sign_request_1_role(self.partner_2, self.partner_1)
        self.assertIn(self.partner_1, request.message_partner_ids)
        with self.assertRaises(UserError):
            request.with_user(self.user_1).write({"state": "signed"})
        with self.assertRaises(UserError):
            request.request_item_ids.with_user(self.user_1).write(
                {"state": "completed"}
            )

    # S4 -- a non-owner sign user cannot delete a completed document; a manager can
    def test_completed_document_unlink_restricted(self):
        request = self.create_sign_request_1_role(
            self.partner_1, self.env["res.partner"]
        )
        request.request_item_ids.sudo()._sign(self.single_signer_sign_values)
        doc = request.completed_document_ids
        stranger = self.env["res.users"].create(
            {
                "name": "Stranger",
                "login": "hard_stranger",
                "email": "hs@example.com",
                "group_ids": [Command.set([self.env.ref("sign.group_sign_user").id])],
            }
        )
        with self.assertRaises(AccessError):
            doc.with_user(stranger).unlink()
        self.assertTrue(doc.exists())
        manager = self.env["res.users"].create(
            {
                "name": "Mgr",
                "login": "hard_mgr",
                "email": "hm@example.com",
                "group_ids": [
                    Command.set([self.env.ref("sign.group_sign_manager").id])
                ],
            }
        )
        doc.with_user(manager).unlink()
        self.assertFalse(doc.exists())

    # S5 -- a sign user cannot cascade-delete items off a locked template
    def test_radio_set_unlink_blocked_on_locked_template(self):
        radio_type = self.env.ref("sign.sign_item_type_radio")
        radio_set = self.env["sign.item.radio.set"].create({})
        item = self.env["sign.item"].create(
            {
                "document_id": self.document_2.id,
                "type_id": radio_type.id,
                "responsible_id": self.role_signer_1.id,
                "radio_set_id": radio_set.id,
                "page": 1,
                "posX": 0.5,
                "posY": 0.5,
                "width": 0.02,
                "height": 0.02,
                "required": False,
            }
        )
        self.create_sign_request_1_role(self.partner_1, self.env["res.partner"])
        self.assertTrue(self.template_1_role.has_sign_requests)
        stranger = self.env["res.users"].create(
            {
                "name": "Str2",
                "login": "hard_str2",
                "email": "hs2@example.com",
                "group_ids": [Command.set([self.env.ref("sign.group_sign_user").id])],
            }
        )
        with self.assertRaises(AccessError):
            radio_set.with_user(stranger).unlink()
        self.assertTrue(item.exists())

    # S3 -- the log keeps no signer's access token: it is a credential
    def test_log_keeps_no_access_token(self):
        self.assertNotIn("token", self.env["sign.log"]._fields)

    # P3 -- the template counts stay correct while scoped to the templates read
    def test_template_counts_scoped(self):
        signed = self.create_sign_request_1_role(
            self.partner_1, self.env["res.partner"]
        )
        signed.request_item_ids.sudo()._sign(self.single_signer_sign_values)
        self.create_sign_request_1_role(self.partner_2, self.env["res.partner"])
        template = self.template_1_role
        template.invalidate_recordset(["signed_count", "in_progress_count"])
        self.assertEqual(template.signed_count, 1)
        self.assertEqual(template.in_progress_count, 1)

    # S8 -- the SMS one-time code is 6 digits, and only its keyed hash is kept
    def test_sms_code_format(self):
        request = self.create_sign_request_1_role_sms_auth(
            self.partner_1, self.env["res.partner"]
        )
        item = request.request_item_ids.sudo()
        item.sms_number = "+32499000000"
        with patch.object(type(self.env["sms.sms"]), "send", lambda self: None):
            self.assertTrue(item._send_sms_code())
        sms = self.env["sms.sms"].search([("number", "=", "+32499000000")])
        code = re.search(r"\d{6}", sms.body).group()
        self.assertNotIn(code, item.sms_code_hash)
        self.assertEqual(item.sms_code_hash, item._hash_sms_code(code, "+32499000000"))

    # P1 -- the vectorised transparency fix must match the pixel-by-pixel version
    def test_fix_image_transparency_matches_naive(self):
        img = Image.new("RGBA", (8, 6))
        img.putdata(
            [
                (0, 0, 0, 0),
                (0, 0, 0, 255),
                (255, 255, 255, 0),
                (1, 0, 0, 0),
            ]
            * 12
        )
        naive = img.copy()
        pixels = naive.load()
        for x in range(naive.size[0]):
            for y in range(naive.size[1]):
                if pixels[x, y] == (0, 0, 0, 0):
                    pixels[x, y] = (255, 255, 255, 0)
        fixed = img.copy()
        _fix_image_transparency(fixed)
        self.assertEqual(list(fixed.getdata()), list(naive.getdata()))

    # C10 -- a bad selection value is rejected at submission, not at final render
    def test_selection_value_validated(self):
        option = self.env["sign.item.option"].create({"value": "Yes"})
        template = self.env["sign.template"].create({"name": "sel"})
        document = self.env["sign.document"].create(
            {"attachment_id": self.attachment.copy().id, "template_id": template.id}
        )
        item = self.env["sign.item"].create(
            {
                "document_id": document.id,
                "type_id": self.env.ref("sign.sign_item_type_selection").id,
                "responsible_id": self.role_1.id,
                "option_ids": [Command.set(option.ids)],
                "page": 1,
                "posX": 0.1,
                "posY": 0.1,
                "width": 0.1,
                "height": 0.02,
            }
        )
        request = self.env["sign.request"].create(
            {
                "template_id": template.id,
                "reference": "sel",
                "request_item_ids": [
                    Command.create(
                        {"partner_id": self.partner_1.id, "role_id": self.role_1.id}
                    )
                ],
            }
        )
        sri = request.request_item_ids.sudo()
        with self.assertRaises(UserError):
            sri._update_signature_values({str(item.id): "not-an-option"})
        sri._update_signature_values({str(item.id): str(option.id)})
        self.assertEqual(sri.sign_item_value_ids.value, str(option.id))

    # C16 -- an unrenderable (e.g. encrypted) PDF is refused, not crashed on None
    def test_completed_document_none_render_guarded(self):
        request = self.create_sign_request_1_role(
            self.partner_1, self.env["res.partner"]
        )
        request.request_item_ids.sudo()._sign(self.single_signer_sign_values)
        request.completed_document_ids.sudo().unlink()
        completed = (
            self.env["sign.completed.document"]
            .sudo()
            .create(
                {
                    "sign_request_id": request.id,
                    "document_id": request.template_id.document_ids[:1].id,
                }
            )
        )
        with (
            patch.object(SignDocument, "render_document_with_items", return_value=None),
            self.assertRaises(UserError),
        ):
            completed._update_completed_document()

    # C7 -- quick-sign works whatever the signature field is named
    def _quick_sign_template(self, signer, field_name):
        env = self.env(user=signer)
        data = env["sign.template"].create_from_attachment_data(
            [{"name": "qs.pdf", "datas": self.pdf_data_64}]
        )
        template = env["sign.template"].browse(data["id"])
        env["sign.item"].create(
            {
                "document_id": template.document_ids.id,
                "type_id": self.env.ref("sign.sign_item_type_signature").id,
                "responsible_id": self.role_1.id,
                "name": field_name,
                "page": 1,
                "posX": 0.1,
                "posY": 0.1,
                "width": 0.2,
                "height": 0.05,
            }
        )
        wiz = (
            env["wizard.sign.request.send"]
            .with_context(
                default_template_id=template.id,
                active_model="sign.template",
                active_ids=template.ids,
            )
            .create({"template_id": template.id, "signer_id": signer.partner_id.id})
        )
        return template, wiz

    def test_itsme_identification_is_neither_offered_nor_installable(self):
        self.assertNotIn("module_sign_itsme", self.env["res.config.settings"]._fields)
        self.assertEqual(
            self.env["ir.module.module"]._get("sign_itsme").state,
            "uninstallable",
            "the itsme proxy's answer carries no proof this database can verify",
        )

    def test_quick_sign_field_name_independent(self):
        signer = self.env["res.users"].create(
            {
                "name": "QS",
                "login": "hard_qs",
                "email": "qs@example.com",
                "group_ids": [Command.set([self.env.ref("sign.group_sign_user").id])],
            }
        )
        with file_open("sign/static/demo/signature.png", "rb") as f:
            signer.sign_signature = base64.b64encode(f.read())
        for field_name in ("Signature", "Firma", None):
            template, wiz = self._quick_sign_template(signer, field_name)
            self.assertTrue(wiz.display_download_button)
            with mute_logger("odoo.http"):
                wiz.quick_sign()
            req = (
                self.env["sign.request"]
                .sudo()
                .search([("template_id", "=", template.id)])
            )
            self.assertEqual(req.state, "signed", "failed for name=%r" % field_name)


@tagged("post_install", "-at_install")
class TestSignHardeningController(TestSignControllerCommon):
    def _rpc(self, url, params):
        return self._json_url_open(url, params).json().get("result")

    # S1 -- the item token, not the request token, gates get_sign_request_items,
    # and only the caller's own pending items come back
    def test_sign_request_items_scoping(self):
        victim = self.env["res.partner"].create(
            {"name": "Victim", "email": "victim@example.com"}
        )
        victim_req = self.create_sign_request_1_role(victim, self.env["res.partner"])
        victim_item = victim_req.request_item_ids
        caller_req = self.create_sign_request_1_role(
            self.partner_1, self.env["res.partner"]
        )
        caller_item = caller_req.request_item_ids
        self.authenticate(None, None)

        # request token must NOT unlock the route any more
        leaked = self._rpc(
            "/sign/sign_request_items",
            {
                "request_id": caller_req.id,
                "token": caller_req.access_token,
                "sign_item_id": victim_item.id,
            },
        )
        self.assertEqual(leaked, [])

        # the caller's own item token returns only the caller's items
        got = self._rpc(
            "/sign/sign_request_items",
            {
                "request_id": caller_req.id,
                "token": caller_item.sudo().access_token,
                "sign_item_id": caller_item.id,
            },
        )
        tokens = {row["token"] for row in got}
        self.assertNotIn(victim_item.sudo().access_token, tokens)

    # S2 -- a request token cannot download a document from another template
    def test_origin_download_ownership(self):
        req = self.create_sign_request_1_role(self.partner_1, self.env["res.partner"])
        own_doc = req.template_id.document_ids[:1]
        foreign_doc = self.template_3_roles.document_ids[:1]
        self.authenticate(None, None)
        own = self.url_open(
            f"/sign/download/{req.id}/{req.access_token}/origin/{own_doc.id}"
        )
        self.assertEqual(own.status_code, 200)
        foreign = self.url_open(
            f"/sign/download/{req.id}/{req.access_token}/origin/{foreign_doc.id}"
        )
        self.assertEqual(foreign.status_code, 404)
