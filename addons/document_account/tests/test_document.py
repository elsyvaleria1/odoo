import base64
import unittest
from unittest.mock import patch

from odoo import Command
from odoo.exceptions import UserError
from odoo.libs import pdf_raster
from odoo.tests.common import tagged

from odoo.addons.account.tests.test_account_move_send import TestAccountMoveSendCommon
from odoo.addons.base.tests.test_pdf_raster import make_pdf
from odoo.addons.document.models.document_document import DocumentsDocument
from odoo.addons.document_account.tests.common import (
    PDF,
    TEXT,
    DocumentsAccountTestCommon,
)


@tagged("post_install", "-at_install", "test_document_bridge")
class TestCaseDocumentsBridgeAccount(DocumentsAccountTestCommon):
    def test_action_view_documents_account_move(self):
        account_move_test_1, account_move_test_2 = self.env["account.move"].create(
            [
                {
                    "name": "Journal Entry 1",
                    "move_type": "entry",
                },
                {
                    "name": "Journal Entry 2",
                    "move_type": "entry",
                },
            ]
        )
        self.setup_sync_journal_folder(account_move_test_1.journal_id, self.folder_a)
        self.assertFalse(
            account_move_test_1.has_documents,
            "Should be False because no attachment is attached to this record",
        )
        self.assertFalse(
            account_move_test_2.has_documents,
            "Should be False because no attachment is attached to this record",
        )
        attachments = self.env["ir.attachment"].create(
            [
                {
                    "name": "fileText_test.txt",
                    "res_model": "account.move",
                    "res_id": account_move_test_1.id,
                },
                {
                    "name": "fileText_test2.txt",
                    "res_model": "account.move",
                    "res_id": account_move_test_1.id,
                },
            ]
        )
        self.assertTrue(
            account_move_test_1.has_documents,
            "Should be True because attachment is attached to this record",
        )
        self.assertFalse(
            account_move_test_2.has_documents,
            "Should be False because no attachment is attached to this record",
        )

        action = account_move_test_1.action_view_documents_account_move()
        self.assertEqual(
            action["context"]["searchpanel_default_user_folder_id"],
            str(self.folder_a.id),
            "The 'folder A' should be the default.",
        )

        folder_test = self.env["document.document"].create(
            {"name": "folder_test", "type": "folder"}
        )
        document = self.env["document.document"].search(
            [("attachment_id", "=", attachments[0].id)]
        )
        document.folder_id = folder_test.id

        action = account_move_test_1.action_view_documents_account_move()
        self.assertFalse(
            action["context"]["searchpanel_default_user_folder_id"],
            "The 'All' folder should be the default.",
        )

    def test_bridge_folder_workflow(self):
        self.assertFalse(self.document_txt.res_model, "failed at default res model")
        account_moves_count_pre = self.env["account.move"].sudo().search_count([])
        multi_return = (
            self.document_txt | self.document_gif
        ).account_create_account_move("in_invoice")
        account_moves_count_post = self.env["account.move"].sudo().search_count([])
        self.assertEqual(account_moves_count_post - account_moves_count_pre, 2)
        self.assertEqual(
            multi_return.get("type"),
            "ir.actions.act_window",
            "failed at invoice workflow return value type",
        )
        self.assertEqual(
            multi_return.get("res_model"),
            "account.move",
            "failed at invoice workflow return value res model",
        )

        self.assertEqual(
            self.document_txt.res_model,
            "account.move",
            "failed at workflow_bridge_dms_account new res_model",
        )
        vendor_bill_txt = self.env["account.move"].search(
            [("id", "=", self.document_txt.res_id)]
        )
        self.assertTrue(
            vendor_bill_txt.exists(),
            "failed at workflow_bridge_dms_account vendor_bill",
        )
        self.assertEqual(
            self.document_txt.res_id,
            vendor_bill_txt.id,
            "failed at workflow_bridge_dms_account res_id",
        )
        self.assertEqual(
            vendor_bill_txt.move_type,
            "in_invoice",
            "failed at workflow_bridge_dms_account vendor_bill type",
        )
        vendor_bill_gif = self.env["account.move"].search(
            [("id", "=", self.document_gif.res_id)]
        )
        self.assertEqual(
            self.document_gif.res_id,
            vendor_bill_gif.id,
            "failed at workflow_bridge_dms_account res_id",
        )
        account_moves_count_pre = self.env["account.move"].sudo().search_count([])
        single_return = self.document_txt.account_create_account_move("in_invoice")
        account_moves_count_post = self.env["account.move"].sudo().search_count([])
        self.assertEqual(account_moves_count_post - account_moves_count_pre, 0)
        self.assertEqual(
            single_return.get("res_model"),
            "account.move",
            "failed at invoice res_model action from workflow create model",
        )
        invoice = self.env[single_return["res_model"]].browse(
            single_return.get("res_id")
        )
        attachments = self.env["ir.attachment"].search(
            [("res_model", "=", "account.move"), ("res_id", "=", invoice.id)]
        )
        self.assertEqual(
            len(attachments), 1, "there should only be one ir attachment matching"
        )

    def _assert_main_attachment_and_document(
        self, invoice, document, first_attachment, main_attachment, previous_ids
    ):
        self.assertRecordValues(
            invoice, [{"message_main_attachment_id": main_attachment.id}]
        )
        self.env["document.document"].flush_model()
        if invoice.move_type == "entry":
            expected = {
                "attachment_id": first_attachment.id,
                "previous_attachment_ids": [],
            }
        else:
            expected = {
                "attachment_id": main_attachment.id,
                "previous_attachment_ids": previous_ids,
            }
        self.assertRecordValues(document, [expected])

    def test_bridge_account_account_settings_on_write(self):
        folder_test = self.env["document.document"].create(
            {"name": "folder_test", "type": "folder"}
        )

        for invoice_type in [
            "in_invoice",
            "out_invoice",
            "in_refund",
            "out_refund",
            "entry",
        ]:
            invoice_test = (
                self.env["account.move"]
                .with_context(default_move_type=invoice_type)
                .create(
                    {
                        "name": "invoice_test",
                        "move_type": invoice_type,
                    }
                )
            )
            setting = self.setup_sync_journal_folder(
                invoice_test.journal_id, folder_test
            )

            attachments = self.env["ir.attachment"]
            for i in range(3):
                attachment = self.env["ir.attachment"].create(
                    {
                        "datas": TEXT,
                        "name": f"fileText_test{i}.txt",
                        "mimetype": "text/plain",
                        "res_model": "account.move",
                        "res_id": invoice_test.id,
                    }
                )
                attachment.register_as_main_attachment(force=False)
                attachments |= attachment

            document = self.env["document.document"].search(
                [("attachment_id", "=", attachments[0].id)]
            )
            self.assertEqual(
                document.folder_id, folder_test, "the text test document have a folder"
            )

            self._assert_main_attachment_and_document(
                invoice_test, document, attachments[0], attachments[0], []
            )

            invoice_test.write({"message_main_attachment_id": attachments[1].id})
            self._assert_main_attachment_and_document(
                invoice_test,
                document,
                attachments[0],
                attachments[1],
                attachments[0].ids,
            )

            attachments[2].register_as_main_attachment(force=True)
            self._assert_main_attachment_and_document(
                invoice_test,
                document,
                attachments[0],
                attachments[2],
                (attachments[0] + attachments[1]).ids,
            )

            attachments = self.env["ir.attachment"].search(
                [("res_model", "=", "account.move"), ("res_id", "=", invoice_test.id)]
            )
            self.assertEqual(
                len(attachments),
                3,
                "there should be 3 attachments linked to the invoice",
            )

            setting.unlink()

    def test_bridge_account_account_settings_on_write_with_versioning(self):
        folder_test = self.env["document.document"].create(
            {"name": "folder_test", "type": "folder"}
        )

        invoice_test = (
            self.env["account.move"]
            .with_context(default_move_type="in_invoice")
            .create(
                {
                    "name": "invoice_test",
                    "move_type": "in_invoice",
                }
            )
        )

        self.setup_sync_journal_folder(invoice_test.journal_id, folder_test)

        attachments = self.env["ir.attachment"]
        for i in range(1, 3):
            attachment = self.env["ir.attachment"].create(
                {
                    "datas": TEXT,
                    "name": f"attachment-{i}.txt",
                    "mimetype": "text/plain",
                    "res_model": "account.move",
                    "res_id": invoice_test.id,
                }
            )
            attachment.register_as_main_attachment(force=False)
            attachments |= attachment

        first_attachment, second_attachment = attachments[0], attachments[1]

        document = self.env["document.document"].search(
            [("res_model", "=", "account.move"), ("res_id", "=", invoice_test.id)]
        )
        self.assertEqual(
            len(document), 1, "there should be 1 document linked to the invoice"
        )
        self.assertEqual(
            document.folder_id, folder_test, "the text test document have a folder"
        )

        def check_main_attachment_and_document(
            main_attachment, doc_attachment, previous_attachment_ids
        ):
            self.assertRecordValues(
                invoice_test,
                [{"message_main_attachment_id": main_attachment.id}],
            )
            self.assertRecordValues(
                document,
                [
                    {
                        "attachment_id": doc_attachment.id,
                        "previous_attachment_ids": previous_attachment_ids,
                    }
                ],
            )

        check_main_attachment_and_document(first_attachment, first_attachment, [])

        document.write(
            {
                "datas": TEXT,
                "name": "attachment-3.txt",
                "mimetype": "text/plain",
            }
        )
        third_attachment = document.attachment_id
        first_attachment = document.previous_attachment_ids[0]
        check_main_attachment_and_document(
            third_attachment, third_attachment, first_attachment.ids
        )

        second_attachment.register_as_main_attachment(force=True)
        check_main_attachment_and_document(
            second_attachment,
            second_attachment,
            (first_attachment + third_attachment).ids,
        )

        document.write({"attachment_id": document.previous_attachment_ids[0].id})
        check_main_attachment_and_document(
            second_attachment,
            first_attachment,
            (third_attachment + second_attachment).ids,
        )

        third_attachment.register_as_main_attachment(force=True)
        check_main_attachment_and_document(
            third_attachment,
            third_attachment,
            (second_attachment + first_attachment).ids,
        )

        document = self.env["document.document"].search(
            [("res_model", "=", "account.move"), ("res_id", "=", invoice_test.id)]
        )
        self.assertEqual(
            len(document), 1, "there should be 1 document linked to the invoice"
        )

    def test_journal_entry(self):
        folder_test = self.env["document.document"].create(
            {"name": "Bills", "type": "folder"}
        )

        invoice_test = (
            self.env["account.move"]
            .with_context(default_move_type="entry")
            .create(
                {
                    "name": "Journal Entry",
                    "move_type": "entry",
                }
            )
        )
        setting = self.setup_sync_journal_folder(invoice_test.journal_id, folder_test)
        attachments = self.env["ir.attachment"].create(
            [
                {
                    "datas": TEXT,
                    "name": "fileText_test.txt",
                    "mimetype": "text/plain",
                    "res_model": "account.move",
                    "res_id": invoice_test.id,
                },
                {
                    "datas": TEXT,
                    "name": "fileText_test2.txt",
                    "mimetype": "text/plain",
                    "res_model": "account.move",
                    "res_id": invoice_test.id,
                },
            ]
        )
        documents = self.env["document.document"].search(
            [("attachment_id", "in", attachments.ids)]
        )
        self.assertEqual(len(documents), 2)
        setting.unlink()

    def test_bridge_account_sync_partner(self):
        partner_1, partner_2 = self.env["res.partner"].create(
            [{"name": "partner_1"}, {"name": "partner_2"}]
        )
        self.document_txt.partner_id = partner_1
        (self.document_txt | self.document_gif).account_create_account_move(
            "in_invoice"
        )
        move = self.env["account.move"].browse(self.document_txt.res_id)
        self.assertEqual(move.partner_id, partner_1)
        move.partner_id = partner_2
        self.assertEqual(self.document_txt.partner_id, partner_2)

    def test_embedded_pdf(self):
        document = self.env["document.document"].create(
            {
                "name": "test",
                "folder_id": self.folder_a.id,
                "datas": base64.b64encode(b'<?xml version="1.0" ?>\n<test> </test>'),
            }
        )
        self.assertEqual(document.mimetype, "application/xml")
        self.assertFalse(document._extract_pdf_from_xml())
        self.assertFalse(document.thumbnail_status)
        self.assertFalse(document.has_embedded_pdf)

        document = self.env["document.document"].create(
            {
                "name": "test",
                "folder_id": self.folder_a.id,
                "datas": base64.b64encode(
                    b'<?xml version="1.0" ?>\n<test> <Attachment>JVBERi0gRmFrZSBQREYgY29udGVudA==</Attachment> </test>'
                ),
            }
        )
        self.assertEqual(document.mimetype, "application/xml")
        self.assertEqual(document._extract_pdf_from_xml(), b"%PDF- Fake PDF content")
        self.assertTrue(document.has_embedded_pdf)
        self.assertEqual(document._get_thumbnail_kind(), "pdf")
        self.assertEqual(document._get_thumbnail_source(), b"%PDF- Fake PDF content")
        self.assertEqual(document.thumbnail_source_checksum, document.checksum)

    @unittest.skipUnless(pdf_raster.available(), "PyMuPDF is not installed")
    def test_an_embedded_pdf_is_rendered_as_the_thumbnail(self):
        embedded = base64.b64encode(make_pdf())
        document = self.env["document.document"].create(
            {
                "name": "invoice.xml",
                "folder_id": self.folder_a.id,
                "datas": base64.b64encode(
                    b'<?xml version="1.0" ?>\n<Invoice><Attachment>'
                    + embedded
                    + b"</Attachment></Invoice>"
                ),
            }
        )
        self.env.cr.flush()
        self.assertEqual(document.thumbnail_status, "pending")

        document._job_render_thumbnails()

        self.assertEqual(document.thumbnail_status, "present")
        self.assertTrue(base64.b64decode(document.thumbnail).startswith(b"\x89PNG"))

    def test_move_document_unlink(self):
        document1, document2 = self.document_txt, self.document_gif
        (document1 | document2).account_create_account_move("in_invoice")
        self.assertEqual(document1.res_model, "account.move")
        self.assertEqual(document2.res_model, "account.move")
        move1 = self.env["account.move"].browse(document1.res_id).exists()
        move2 = self.env["account.move"].browse(document2.res_id).exists()
        self.assertTrue(move1)
        self.assertTrue(move2)
        attachment1 = self.env["ir.attachment"].search(
            [
                ("res_model", "=", move1._name),
                ("res_id", "=", move1.id),
            ]
        )
        attachment2 = self.env["ir.attachment"].search(
            [
                ("res_model", "=", move2._name),
                ("res_id", "=", move2.id),
            ]
        )
        attachment3 = self.env["ir.attachment"].create(
            {
                "name": "Attachment 3",
                "res_model": move2._name,
                "res_id": move2.id,
            }
        )
        self.assertEqual(len(attachment1), 1)
        self.assertEqual(len(attachment2), 1)

        self.env.flush_all()
        (move1 | move2).unlink()

        self.assertTrue(attachment1.exists())
        self.assertTrue(document1.exists())
        self.assertFalse(document1.active)

        self.assertTrue(attachment2.exists())
        self.assertTrue(document2.exists())
        self.assertFalse(document2.active)

        self.assertFalse(
            attachment3.exists(),
            "That attachment is not linked to a record and so it should be removed",
        )

        document2.unlink()
        self.assertFalse(attachment2.exists())

    def test_workflow_create_misc_entry(self):
        misc_entry_action = (
            self.document_txt | self.document_gif
        ).account_create_account_move("entry")
        move = self.env["account.move"].browse(self.document_txt.res_id)
        self.assertEqual(misc_entry_action.get("res_model"), "account.move")
        self.assertEqual(move.move_type, "entry")

    def test_workflow_create_bank_statement_raise_content_parsing(self):
        for document in self.document_txt, self.document_gif:
            with self.subTest(document=document.name):
                with self.assertRaises(UserError) as err:
                    document.account_create_account_bank_statement()
                self.assertEqual(
                    err.exception.args[0],
                    f"All or part of the following file(s) could not be imported:\n"
                    f"- {document.name}: Could not make sense of the given file.\n"
                    f"Did you install the module to support this type of file?",
                )

    def test_workflow_create_bank_statement_raise_no_journal(self):
        new_company = self.env["res.company"].create(
            {"name": "new_company_without_journals"}
        )
        doc_in_new_company = self.document_txt.copy({"company_id": new_company.id})

        for sudo in False, True:
            with self.subTest(sudo=sudo):
                with self.assertRaises(UserError) as err:
                    doc_in_new_company.with_company(new_company).sudo(
                        sudo
                    ).account_create_account_bank_statement()
                self.assertEqual(
                    err.exception.args[0],
                    "No journal could be found in company new_company_without_journals for any of those types: bank",
                )

    def test_workflow_create_vendor_bill(self):
        vendor_bill_entry_action = self.document_txt.account_create_account_move(
            "in_invoice"
        )
        move = self.env["account.move"].browse(self.document_txt.res_id)
        self.assertEqual(vendor_bill_entry_action.get("res_model"), "account.move")
        self.assertEqual(move.move_type, "in_invoice")

    def test_workflow_create_vendor_receipt(self):
        vendor_receipt_action = self.document_txt.account_create_account_move(
            "in_receipt"
        )
        move = self.env["account.move"].browse(self.document_txt.res_id)
        self.assertEqual(vendor_receipt_action.get("res_model"), "account.move")
        self.assertEqual(move.move_type, "in_receipt")

    def test_documents_xml_attachment(self):
        folder_test = self.env["document.document"].create(
            {"name": "Bills", "type": "folder"}
        )

        invoice = self.init_invoice("out_invoice", amounts=[1000], post=True)
        setting = self.setup_sync_journal_folder(invoice.journal_id, folder_test)
        att_ids = []
        for fmt in ("xml", "txt"):
            attachment = self.env["ir.attachment"].create(
                {
                    "raw": "<text/>",
                    "name": f"attachment-{fmt}.txt",
                    "mimetype": f"application/{fmt}",
                    "res_model": "account.move",
                    "res_id": invoice.id,
                }
            )
            att_ids.append(attachment.id)
        documents = self.env["document.document"].search(
            [("attachment_id", "in", att_ids)]
        )
        self.assertEqual(len(documents), 1, "TXT should not create a document")
        attachment_pdf = self.env["ir.attachment"].create(
            {
                "datas": PDF,
                "name": "file.pdf",
                "mimetype": "application/pdf",
                "res_model": invoice._name,
                "res_id": invoice.id,
            }
        )
        documents = self.env["document.document"].search(
            [("attachment_id", "=", attachment_pdf.id)]
        )
        self.assertFalse(documents, "pdf should not be attached if not main attachment")
        attachment_pdf.register_as_main_attachment(force=False)
        documents = self.env["document.document"].search(
            [("attachment_id", "=", attachment_pdf.id)]
        )
        self.assertEqual(
            len(documents),
            1,
            "Pdf registered as main attachment did not create a single document",
        )
        setting.unlink()

    def test_embeddable_server_action_domain(self):
        IrActionServer = self.env["ir.actions.server"]

        def get_server_actions_for_company(company):
            return IrActionServer.with_company(company).search(
                self.env["document.document"]
                .with_company(company)
                ._get_domain_embeddable_server_action()
            )

        company_1 = self.env.company
        company_2 = self.setup_other_company()["company"]
        companies = company_1 | company_2
        pre_existing = {
            company: get_server_actions_for_company(company) for company in companies
        }
        action_base_vals = {
            "model_id": self.env["ir.model"]._get_id("document.document")
        }
        action_create_base_vals = {
            **action_base_vals,
            "state": "documents_account_record_create",
            "documents_account_create_model": "account.move.in_invoice",
        }
        journal_id_per_company = {
            company: self.env["account.move"]
            .with_company(company)
            ._get_suitable_journal_ids("in_invoice")
            .ids[0]
            for company in companies
        }
        for company in companies:
            other_company = companies - company
            action_single_company_vals = {
                **action_create_base_vals,
                "name": f"single {company.name}",
                "documents_account_journal_id": journal_id_per_company[company],
            }
            IrActionServer.with_company(company).create(
                [
                    action_single_company_vals,
                    {
                        **action_base_vals,
                        "name": f"multi {company.name}",
                        "state": "multi",
                        "child_ids": [Command.create(action_single_company_vals)],
                    },
                    {
                        **action_base_vals,
                        "name": "multi invalid",
                        "state": "multi",
                        "child_ids": [
                            IrActionServer.with_company(company)
                            .create(action_single_company_vals)
                            .id,
                            IrActionServer.with_company(other_company)
                            .create(
                                {
                                    **action_single_company_vals,
                                    "documents_account_journal_id": journal_id_per_company[
                                        other_company
                                    ],
                                }
                            )
                            .id,
                        ],
                    },
                ]
            )
        action_single_vals = {
            **action_create_base_vals,
            "name": "single",
        }
        IrActionServer.create(
            [
                action_single_vals,
                {
                    **action_base_vals,
                    "name": "multi",
                    "state": "multi",
                    "child_ids": [Command.create(action_single_vals)],
                },
            ]
        )

        self.assertEqual(
            set(
                (
                    get_server_actions_for_company(company_1) - pre_existing[company_1]
                ).mapped("name")
            ),
            {"multi", f"multi {company_1.name}", "single", f"single {company_1.name}"},
        )
        self.assertEqual(
            set(
                (
                    get_server_actions_for_company(company_2) - pre_existing[company_2]
                ).mapped("name")
            ),
            {"multi", f"multi {company_2.name}", "single", f"single {company_2.name}"},
        )


@tagged("post_install_l10n", "post_install", "-at_install")
class TestAccountMoveSendDocument(
    DocumentsAccountTestCommon, TestAccountMoveSendCommon
):
    def test_send_and_print_document_creation(self):
        folder_test = self.env["document.document"].create(
            {"name": "Bills", "type": "folder"}
        )
        move = self.init_invoice("out_invoice", amounts=[1000], post=True)
        setting = self.setup_sync_journal_folder(move.journal_id, folder_test)

        wizard = self.create_send_and_print(move)
        wizard.action_send_and_print()
        attachments = move.attachment_ids | move.invoice_pdf_report_id
        documents = self.env["document.document"].search(
            [("attachment_id", "in", attachments.ids)]
        )
        self.assertEqual(
            len(documents),
            len(attachments),
            "Each move attachment should create a corresponding document",
        )
        with patch.object(DocumentsDocument, "_get_is_multipage", return_value=False):
            setting.unlink()
