from odoo.tests import new_test_user, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.document.tests.test_document_common import TEXT
from odoo.addons.document_account.tests.common import (
    PDF,
    DocumentsAccountHelpersCommon,
)


@tagged("post_install", "-at_install")
class TestBankStatementDocument(
    AccountTestInvoicingCommon, DocumentsAccountHelpersCommon
):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids += cls.quick_ref("document.group_documents_manager")
        # shared by every company, as the area folders are
        cls.bank_folder = cls.env["document.document"].create(
            {"name": "Banks", "type": "folder", "company_id": False}
        )
        cls.bank_journal = cls.company_data["default_journal_bank"]
        cls.setup_sync_journal_folder(cls.bank_journal, cls.bank_folder)

    def _create_statement(self, journal):
        return (
            self.env["account.bank.statement"]
            .with_company(journal.company_id)
            .create(
                {
                    "name": "statement",
                    "line_ids": [
                        (
                            0,
                            0,
                            {
                                "date": "2026-09-30",
                                "payment_ref": "line",
                                "journal_id": journal.id,
                                "amount": 100.0,
                            },
                        ),
                    ],
                }
            )
        )

    def _attach(self, statement, name, datas, mimetype):
        return statement.env["ir.attachment"].create(
            {
                "name": name,
                "datas": datas,
                "mimetype": mimetype,
                "res_model": statement._name,
                "res_id": statement.id,
            }
        )

    def _documents_of(self, attachment):
        return self.env["document.document"].search(
            [("attachment_id", "in", attachment.ids)]
        )

    def test_pdf_is_filed_in_journal_folder_under_statement_company(self):
        statement = self._create_statement(self.bank_journal)

        attachment = self._attach(statement, "statement.pdf", PDF, "application/pdf")

        document = self._documents_of(attachment)
        self.assertEqual(len(document), 1)
        self.assertEqual(attachment.name, f"statement {self.bank_journal.name}.pdf")
        self.assertEqual(document.name, attachment.name)
        self.assertEqual(document.folder_id, self.bank_folder)
        self.assertEqual(document.company_id, statement.company_id)
        self.assertEqual(document.owner_id, self.env.user)
        self.assertEqual(
            (document.res_model, document.res_id), (statement._name, statement.id)
        )

    def test_import_file_stays_on_statement(self):
        statement = self._create_statement(self.bank_journal)

        attachment = self._attach(statement, "statement.txt", TEXT, "text/plain")

        self.assertFalse(self._documents_of(attachment))
        self.assertEqual(attachment.name, "statement.txt")

    def test_journal_without_folder_files_nothing(self):
        journal = self.bank_journal.copy()
        self.env["document.account.folder.setting"].search(
            [("journal_id", "=", journal.id)]
        ).unlink()
        statement = self._create_statement(journal)

        attachment = self._attach(statement, "statement.pdf", PDF, "application/pdf")

        self.assertFalse(self._documents_of(attachment))

    def test_other_company_statement_keeps_its_company(self):
        company_data_2 = self.setup_other_company()
        journal_2 = company_data_2["default_journal_bank"]
        self.setup_sync_journal_folder(
            journal_2, self.bank_folder, company=company_data_2["company"]
        )
        self.env.user.company_ids += company_data_2["company"]
        statement = self._create_statement(journal_2)

        attachment = self._attach(statement, "statement.pdf", PDF, "application/pdf")

        self.assertEqual(
            self._documents_of(attachment).company_id, company_data_2["company"]
        )

    def test_report_printed_by_odoo_stays_on_statement(self):
        statement = self._create_statement(self.bank_journal)

        statement.action_generate_attachment()

        printed = statement.attachment_ids.filtered(
            lambda attachment: attachment.mimetype == "application/pdf"
        )
        self.assertTrue(printed)
        self.assertFalse(self._documents_of(printed))

    def test_accountant_without_documents_rights_files_the_pdf(self):
        accountant = new_test_user(
            self.env,
            login="statement_accountant",
            groups="account.group_account_user",
        )
        statement = self._create_statement(self.bank_journal).with_user(accountant)

        attachment = self._attach(statement, "statement.pdf", PDF, "application/pdf")

        self.assertEqual(self._documents_of(attachment).folder_id, self.bank_folder)

    def test_folder_with_a_company_keeps_it(self):
        folder = self.env["document.document"].create(
            {"name": "Bank of the company", "type": "folder"}
        )
        folder.company_id = self.env.company
        journal = self.bank_journal.copy()
        self.setup_sync_journal_folder(journal, folder)
        statement = self._create_statement(journal)

        attachment = self._attach(statement, "statement.pdf", PDF, "application/pdf")

        self.assertEqual(self._documents_of(attachment).company_id, folder.company_id)
