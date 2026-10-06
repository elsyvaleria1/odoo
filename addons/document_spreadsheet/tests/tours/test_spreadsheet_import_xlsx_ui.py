import base64

from odoo.tests import tagged
from odoo.tests.common import HttpCase
from odoo.tools import file_open


@tagged("post_install", "-at_install")
class TestSpreadsheetImportXLSXUi(HttpCase):
    def test_01_spreadsheet_clone_and_archive_xlsx(self):
        with file_open("document_spreadsheet/tests/data/test.xlsx", "rb") as f:
            spreadsheet_data = base64.encodebytes(f.read())

        folder = self.env["document.document"].create(
            {
                "name": "Test folder",
                "type": "folder",
                "owner_id": False,
                "access_internal": "view",
                "access_via_link": "none",
            }
        )
        self.env["document.document"].create(
            {
                "datas": spreadsheet_data,
                "name": "test.xlsx",
                "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "folder_id": folder.id,
            }
        )

        self.start_tour("/odoo", "spreadsheet_clone_xlsx", login="admin")
