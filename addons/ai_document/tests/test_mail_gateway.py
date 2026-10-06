from unittest.mock import patch

from odoo.addons.ai.utils.llm_api_service import LLMApiService
from odoo.addons.ai_document.tests.test_common import TestAiDocumentsCommon
from odoo.addons.mail.tests.common import MailCommon
from odoo.addons.test_mail.data.test_mail_data import MAIL_EML_ATTACHMENT


class TestMailGateway(TestAiDocumentsCommon, MailCommon):
    def test_ai_documents_send_mail(self):
        self.folder.alias_name = "inbox-test"

        documents = (
            self.env["document.document"]
            .with_context(active_test=False)
            .search([("folder_id", "=", self.folder.id)])
        )
        self.assertFalse(documents)

        with (
            self.mock_mail_gateway(),
            patch.object(LLMApiService, "_request_llm") as _mocked_request_llm,
        ):
            self.format_and_process(
                MAIL_EML_ATTACHMENT,
                "test@example.com",
                f"inbox-test@{self.alias_domain}",
                subject="Test document creation on incoming mail",
                target_model="document.document",
                references="<f3b9f8f8-28fa-2543-cab2-7aa68f679ebb@odoo.com>",
                msg_id="<cb7eaf62-58dc-2017-148c-305d0c78892f@odoo.com>",
            )

        self.assertFalse(_mocked_request_llm.called)
        # The gateway files the mail itself as an ARCHIVED document and its
        # attachments as active ones, so counting them needs active_test=False --
        # the same context `document`'s own mail-gateway tests use.
        documents = (
            self.env["document.document"]
            .with_context(active_test=False)
            .search([("folder_id", "=", self.folder.id)])
        )
        self.assertEqual(len(documents), 2)
        self.assertTrue(all(documents.mapped("ai_to_sort")))
