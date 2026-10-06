from datetime import timedelta

from freezegun import freeze_time

from odoo.exceptions import UserError
from odoo.tools import mute_logger

from odoo.addons.document_sign.tests.test_document import TestCaseDocumentsBridgeSign


class TestSignedDocument(TestCaseDocumentsBridgeSign):
    def setUp(cls):  # noqa: N805  preexisting: instance setUp named `cls`; renaming is out of the comment-sweep scope
        super().setUp()
        partner = cls.env["res.partner"]
        user = cls.env["res.users"].create(
            {
                "name": "test_sign_owner_",
                "login": "test_sign_owner@ex.com",
                "email": "test_sign_owner@ex.com",
            }
        )
        sign_request = cls.create_sign_request_1_role(user.partner_id, partner)
        sign_document = cls.document_3
        sign_request.completed_document_attachment_ids = [(4, cls.attachment.id)]

        cls.trash_doc, cls.signed_document_pdf, cls.sign_doc = cls.env[
            "document.document"
        ].create(
            [
                {
                    "name": "trash_doc",
                    "attachment_id": cls.attachment.copy().id,
                    "folder_id": cls.folder_a_a.id,
                    "active": False,
                    "res_model": False,
                },
                {
                    "name": "signed document",
                    "folder_id": cls.folder_a_a.id,
                    "res_model": sign_request._name,
                    "res_id": sign_request.id,
                    "active": False,
                    "attachment_id": cls.attachment.id,
                },
                {
                    "name": "sign document",
                    "attachment_id": sign_document.attachment_id.id,
                    "folder_id": cls.folder_a_a.id,
                    "res_model": sign_document._name,
                    "res_id": sign_document.id,
                    "active": False,
                },
            ]
        )

    def test_gc_clear_bin(self):
        """Ensure that old, auto-deletable (in the trash) documents linked to sign requests and sign documents are not
        deleted by the garbage collector.
        """

        self.assertFalse(self.sign_doc.active)
        self.assertFalse(self.signed_document_pdf.active)
        self.assertFalse(self.trash_doc.active)
        # The purge reads the deletion date stamped when a document entered the
        # trash, not `write_date`, so that a later write to a trashed document
        # cannot postpone a deletion its own chatter message already promised.
        # Freezing to the day after every promise here is what makes all three
        # eligible; which of them the GC then spares is the thing under test.
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
        """A sign or signed document cannot be deleted while a sign document or
        sign request still holds its attachment. The refusal is a UserError with
        the reason: sign.document.attachment_id is ondelete="restrict", so
        without the guard the database refuses it as a psycopg RestrictViolation
        that reaches the client as a 500.
        """
        self.assertFalse(self.sign_doc.active)
        self.assertFalse(self.signed_document_pdf.active)

        with self.assertRaises(UserError):
            self.sign_doc.unlink()
        with self.assertRaises(UserError):
            self.signed_document_pdf.unlink()
