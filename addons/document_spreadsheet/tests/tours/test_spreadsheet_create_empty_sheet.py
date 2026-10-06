from odoo.tests import tagged

from ..common import SpreadsheetTestTourCommon

SPREADSHEET_LOG = "document_spreadsheet.*,spreadsheet_edition.*"


@tagged("post_install", "-at_install")
class TestSpreadsheetCreateEmpty(SpreadsheetTestTourCommon):
    def test_01_spreadsheet_create_empty(self):
        self.start_tour(
            f"/odoo?log={SPREADSHEET_LOG}",
            "spreadsheet_create_empty_sheet",
            login="admin",
        )

    def test_02_spreadsheet_create_list_view(self):
        self.start_tour(
            f"/odoo?log={SPREADSHEET_LOG}",
            "spreadsheet_create_list_view",
            login="admin",
        )
