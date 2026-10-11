import base64

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger

TEXT = base64.b64encode(bytes("workflow bridge project", "utf-8"))


class TestCaseDocumentsBridgeExpense(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.folder_internal = cls.env.ref("document.document_internal_folder")
        cls.folder_internal.action_update_access_rights(access_internal="edit")

        cls.documents_user = cls.env["res.users"].create(
            {
                "name": "aaadocuments test basic user",
                "login": "aadtbu",
                "email": "aadtbu@yourcompany.com",
                "group_ids": [
                    Command.set([cls.env.ref("document.group_documents_user").id])
                ],
            }
        )

    def _create_txt_attachment_for_documents_user(self):
        return (
            self.env["document.document"]
            .with_user(self.documents_user)
            .create(
                {
                    "datas": "JVBERi0gRmFrZSBQREYgY29udGVudA==",
                    "name": "file.pdf",
                    "mimetype": "application/pdf",
                    "folder_id": self.folder_internal.id,
                }
            )
        )

    @mute_logger("odoo.addons.document.models.document_document", "pypdf._reader")
    def test_create_document_to_expense(self):
        self.documents_user.action_create_employee()
        document_txt = self._create_txt_attachment_for_documents_user()

        self.assertFalse(
            document_txt.res_model, "The default res model of a document is False."
        )
        self.assertEqual(
            document_txt.attachment_id.res_model,
            "document.document",
            "The default res model of an attachment is document.document.",
        )
        document_txt.with_user(
            self.documents_user
        ).document_hr_expense_create_hr_expense()
        self.assertEqual(
            document_txt.res_model, "hr.expense", "The document model is updated."
        )
        self.assertEqual(
            document_txt.attachment_id.res_model,
            "hr.expense",
            "The attachment model is updated.",
        )
        expense = self.env["hr.expense"].search([("id", "=", document_txt.res_id)])
        self.assertTrue(expense.exists(), "expense sholud be created.")
        self.assertEqual(
            document_txt.res_id, expense.id, "Expense should be linked to document"
        )

    @mute_logger("odoo.addons.document.models.document_document", "pypdf._reader")
    def test_create_document_to_expense_without_employee(self):
        attachment_txt = self._create_txt_attachment_for_documents_user()
        with self.assertRaisesRegex(
            UserError, "You must be linked to an employee to create an expense."
        ):
            attachment_txt.with_user(
                self.documents_user
            ).document_hr_expense_create_hr_expense()

        expense = self.env["hr.expense"].search([("id", "=", attachment_txt.res_id)])
        self.assertFalse(expense.exists())
