from odoo.tests import new_test_user, tagged

from .common import SpreadsheetTestCommon
from odoo.addons.base.tests.common import converted_reach


@tagged("post_install", "-at_install")
class TestCellThreadDocumentsManager(SpreadsheetTestCommon):
    def test_a_documents_manager_deletes_a_documents_thread(self):
        manager = new_test_user(
            self.env, login="thread_manager", groups="document.group_documents_manager"
        )
        thread = self.env["spreadsheet.cell.thread"].create(
            {"document_id": self.create_spreadsheet().id}
        )
        self.assertEqual(
            converted_reach(self.env, "spreadsheet.cell.thread", manager, "unlink")
            & thread,
            thread,
        )
        thread.with_user(manager).unlink()
        self.assertFalse(thread.exists())
