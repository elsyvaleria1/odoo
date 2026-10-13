from odoo import Command
from odoo.tests.common import RecordCapturer, tagged, users
from odoo.tools import mute_logger

from odoo.addons.document_account.tests.common import DocumentsAccountHelpersCommon
from odoo.addons.mail.tests.common import MailCommon
from odoo.addons.mail.tests.mail_data import MAIL_EML_ATTACHMENT

VENDOR_BILL_MAIL = """Subject: {subject}
From: {email_from}
To: {to}
References: {references}
Message-ID: {msg_id}
Date: Wed, 14 Mar 2018 14:26:58 +0100
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="BILL"

--BILL
Content-Type: text/plain; charset=utf-8

Please find our bill attached.

--BILL
Content-Type: application/pdf; name="bill_42.pdf"
Content-Transfer-Encoding: base64
Content-Disposition: attachment; filename="bill_42.pdf"

JVBERi0xLjMKJZOMi54gUmVwb3J0TGFiIEdlbmVyYXRlZCBQREYgZG9jdW1lbnQgKG9wZW5zb3Vy
Y2UpCjEgMCBvYmoKPDwKL0YxIDIgMCBSCj4+CmVuZG9iagoyIDAgb2JqCjw8Ci9CYXNlRm9udCAv
SGVsdmV0aWNhIC9FbmNvZGluZyAvV2luQW5zaUVuY29kaW5nIC9OYW1lIC9GMSAvU3VidHlwZSAv
VHlwZTEgL1R5cGUgL0ZvbnQKPj4KZW5kb2JqCjMgMCBvYmoKPDwKL0NvbnRlbnRzIDcgMCBSIC9N
ZWRpYUJveCBbIDAgMCA1OTUuMjc1NiA4NDEuODg5OCBdIC9QYXJlbnQgNiAwIFIgL1Jlc291cmNl
cyA8PAovRm9udCAxIDAgUiAvUHJvY1NldCBbIC9QREYgL1RleHQgL0ltYWdlQiAvSW1hZ2VDIC9J
bWFnZUkgXQo+PiAvUm90YXRlIDAgL1RyYW5zIDw8Cgo+PiAKICAvVHlwZSAvUGFnZQo+PgplbmRv
YmoKNCAwIG9iago8PAovUGFnZU1vZGUgL1VzZU5vbmUgL1BhZ2VzIDYgMCBSIC9UeXBlIC9DYXRh
bG9nCj4+CmVuZG9iago1IDAgb2JqCjw8Ci9BdXRob3IgKGFub255bW91cykgL0NyZWF0aW9uRGF0
ZSAoRDoyMDI2MTAwMTE4NTEyMi0wNicwMCcpIC9DcmVhdG9yIChhbm9ueW1vdXMpIC9LZXl3b3Jk
cyAoKSAvTW9kRGF0ZSAoRDoyMDI2MTAwMTE4NTEyMi0wNicwMCcpIC9Qcm9kdWNlciAoUmVwb3J0
TGFiIFBERiBMaWJyYXJ5IC0gXChvcGVuc291cmNlXCkpIAogIC9TdWJqZWN0ICh1bnNwZWNpZmll
ZCkgL1RpdGxlICh1bnRpdGxlZCkgL1RyYXBwZWQgL0ZhbHNlCj4+CmVuZG9iago2IDAgb2JqCjw8
Ci9Db3VudCAxIC9LaWRzIFsgMyAwIFIgXSAvVHlwZSAvUGFnZXMKPj4KZW5kb2JqCjcgMCBvYmoK
PDwKL0ZpbHRlciBbIC9BU0NJSTg1RGVjb2RlIC9GbGF0ZURlY29kZSBdIC9MZW5ndGggOTkKPj4K
c3RyZWFtCkdhcEBDMGFgRmInWktkOywsNzNfSiMyLjJkKWtoODVTMDFScmk5JEVPPEkibzZfQkRI
ZnBPYWxMbj8pVCQvXGxLWycibkQpOVppQFY5O3BoVXRGXWQ1LmktISFQWyhyKnJ+PmVuZHN0cmVh
bQplbmRvYmoKeHJlZgowIDgKMDAwMDAwMDAwMCA2NTUzNSBmIAowMDAwMDAwMDYxIDAwMDAwIG4g
CjAwMDAwMDAwOTIgMDAwMDAgbiAKMDAwMDAwMDE5OSAwMDAwMCBuIAowMDAwMDAwNDAyIDAwMDAw
IG4gCjAwMDAwMDA0NzAgMDAwMDAgbiAKMDAwMDAwMDczMSAwMDAwMCBuIAowMDAwMDAwNzkwIDAw
MDAwIG4gCnRyYWlsZXIKPDwKL0lEIApbPGMzZmM1NTFiYWNkNDU0Nzc3YWJmYzJhYzdiOWIyYTI2
PjxjM2ZjNTUxYmFjZDQ1NDc3N2FiZmMyYWM3YjliMmEyNj5dCiUgUmVwb3J0TGFiIGdlbmVyYXRl
ZCBQREYgZG9jdW1lbnQgLS0gZGlnZXN0IChvcGVuc291cmNlKQoKL0luZm8gNSAwIFIKL1Jvb3Qg
NCAwIFIKL1NpemUgOAo+PgpzdGFydHhyZWYKOTc4CiUlRU9GCg==
--BILL--
"""


@tagged("post_install", "-at_install", "documents_account_multicompany_mail")
class TestMultiCompanyDocumentsAccountMail(MailCommon, DocumentsAccountHelpersCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.simple_accountman = (
            cls.env["res.users"]
            .with_company(cls.company_2.id)
            .create(
                {
                    "name": "simple accountman",
                    "login": "simple_accountman",
                    "password": "simple_accountman",
                    "group_ids": [
                        Command.link(cls.env.ref("account.group_account_manager").id),
                        Command.link(cls.env.ref("account.group_account_user").id),
                    ],
                }
            )
        )

        cls.env["ir.config_parameter"].sudo().set_param(
            "mail.catchall.domain", "alias.company2.com"
        )

        cls.mail_alias_domain_c2 = cls.env["mail.alias.domain"].create(
            {
                "name": "alias.company2.com",
                "company_ids": [(4, cls.company_2.id)],
            }
        )

        cls.journal_company2 = (
            cls.env["account.journal"]
            .with_company(cls.company_2)
            .create(
                {
                    "name": "Vendor Bills (Company 2)",
                    "type": "purchase",
                    "code": "BILLC2",
                }
            )
        )

        cls.folder_finance_company2 = cls.env["document.document"].create(
            {
                "name": "Finance Company 2",
                "type": "folder",
                "company_id": cls.company_2.id,
            }
        )

        cls.company_2.account_folder_id = cls.folder_finance_company2.id

        cls.setup_sync_journal_folder(
            cls.journal_company2, cls.folder_finance_company2, cls.company_2
        )

    def _mail_journal_company2(self, template, msg_id):
        with (
            self.mock_mail_gateway(),
            RecordCapturer(self.env["account.move"], []) as move_capture,
            RecordCapturer(self.env["document.document"], []) as doc_capture,
        ):
            self.format_and_process(
                template,
                "external.sender@example.com",
                self.journal_company2.alias_email,
                subject="Draft Bill",
                target_model="account.move",
                msg_id=msg_id,
                target_field="display_name",
            )
        return move_capture.records, doc_capture.records

    @users("simple_accountman")
    @mute_logger("odoo.addons.mail.models.mixin_mail_thread")
    def test_incoming_mail_to_journal_alias_attachment_company(self):
        new_move, new_document = self._mail_journal_company2(
            VENDOR_BILL_MAIL, "<account-company-2-mail-test@odoo.com>"
        )

        self.assertEqual(
            len(new_move),
            1,
            "Should have created exactly one new account move from the email.",
        )
        self.assertEqual(
            new_move.company_id,
            self.company_2,
            "The new account move should belong to Company 2.",
        )
        self.assertEqual(
            len(new_document),
            1,
            "Should have created exactly one new document from the email attachment.",
        )
        self.assertEqual(
            new_document.company_id,
            self.company_2,
            "The new document should be linked to Company 2.",
        )
        self.assertEqual(
            new_document.folder_id,
            self.folder_finance_company2,
            "The new document should be in Company 2's finance folder.",
        )
        self.assertEqual(
            new_document.attachment_id, new_move.message_main_attachment_id
        )

    @users("simple_accountman")
    @mute_logger("odoo.addons.mail.models.mixin_mail_thread")
    def test_a_forwarded_email_alone_is_no_bill_to_file(self):
        new_move, new_document = self._mail_journal_company2(
            MAIL_EML_ATTACHMENT, "<account-company-2-forward-test@odoo.com>"
        )

        self.assertEqual(len(new_move), 1)
        self.assertFalse(new_move.message_main_attachment_id)
        self.assertFalse(new_document)
