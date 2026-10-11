from datetime import timedelta

from freezegun import freeze_time

from odoo.exceptions import UserError
from odoo.tools import mute_logger

from odoo.addons.document_sign.tests.test_document import TestCaseDocumentsBridgeSign


class TestSignedDocument(TestCaseDocumentsBridgeSign):
    def setUp(self):
        super().setUp()
        partner = self.env["res.partner"]
        user = self.env["res.users"].create(
            {
                "name": "test_sign_owner_",
                "login": "test_sign_owner@ex.com",
                "email": "test_sign_owner@ex.com",
            }
        )
        sign_request = self.create_sign_request_1_role(user.partner_id, partner)
        sign_document = self.document_3
        sign_request.completed_document_attachment_ids = [(4, self.attachment.id)]

        self.trash_doc, self.signed_document_pdf, self.sign_doc = self.env[
            "document.document"
        ].create(
            [
                {
                    "name": "trash_doc",
                    "attachment_id": self.attachment.copy().id,
                    "folder_id": self.folder_a_a.id,
                    "active": False,
                    "res_model": False,
                },
                {
                    "name": "signed document",
                    "folder_id": self.folder_a_a.id,
                    "res_model": sign_request._name,
                    "res_id": sign_request.id,
                    "active": False,
                    "attachment_id": self.attachment.id,
                },
                {
                    "name": "sign document",
                    "attachment_id": sign_document.attachment_id.id,
                    "folder_id": self.folder_a_a.id,
                    "res_model": sign_document._name,
                    "res_id": sign_document.id,
                    "active": False,
                },
            ]
        )

    def test_gc_clear_bin(self):

        self.assertFalse(self.sign_doc.active)
        self.assertFalse(self.signed_document_pdf.active)
        self.assertFalse(self.trash_doc.active)
        documents = self.sign_doc | self.signed_document_pdf | self.trash_doc
        documents_deletion_date = max(documents.mapped("deletion_date")) + timedelta(
            days=1
        )
        with freeze_time(documents_deletion_date):
            self.env["document.document"]._gc_clear_bin()

        self.assertTrue(
            self.sign_doc.exists(),
            "sign document should not be deleted after gc_clear_bin",
        )
        self.assertTrue(
            self.signed_document_pdf.exists(),
            "signed document should not be deleted after gc_clear_bin",
        )
        self.assertFalse(
            self.trash_doc.exists(),
            "trash document should be deleted after gc_clear_bin",
        )

    @mute_logger("odoo.models.unlink")
    def test_signed_document_unlink(self):
        self.assertFalse(self.sign_doc.active)
        self.assertFalse(self.signed_document_pdf.active)

        with self.assertRaises(UserError):
            self.sign_doc.unlink()
        with self.assertRaises(UserError):
            self.signed_document_pdf.unlink()
