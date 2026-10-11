from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestKpiProvider(TransactionCase):
    def test_kpi_summary(self):
        folder_inbox = self.env.ref("document.document_inbox_folder")
        other_folder = self.env.ref("document.document_finance_folder")

        self.env["document.document"].search(
            [
                ("folder_id", "=", folder_inbox.id),
            ]
        ).folder_id = other_folder
        self.assertCountEqual(
            self.env["kpi.provider"].get_documents_kpi_summary(),
            [{"id": "document.inbox", "name": "Inbox", "type": "integer", "value": 0}],
        )

        all_documents = self.env["document.document"].create(
            [
                {
                    "name": "Test Document",
                    "folder_id": folder_inbox.id,
                }
            ]
            * 2
        )
        self.assertCountEqual(
            self.env["kpi.provider"].get_documents_kpi_summary(),
            [{"id": "document.inbox", "name": "Inbox", "type": "integer", "value": 2}],
        )

        all_documents[0].folder_id = other_folder
        self.assertCountEqual(
            self.env["kpi.provider"].get_documents_kpi_summary(),
            [{"id": "document.inbox", "name": "Inbox", "type": "integer", "value": 1}],
        )

        folder_inbox.action_archive()
        self.assertCountEqual(self.env["kpi.provider"].get_documents_kpi_summary(), [])

        folder_inbox.action_unarchive()
        all_documents.folder_id = other_folder
        folder_inbox.unlink()
        self.assertCountEqual(self.env["kpi.provider"].get_documents_kpi_summary(), [])
