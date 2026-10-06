from odoo.tests import tagged

from ..common import SpreadsheetTestTourCommon


@tagged("post_install", "-at_install")
class TestSpreadsheetOpenPivot(SpreadsheetTestTourCommon):
    def test_01_spreadsheet_open_pivot_as_admin(self):
        self.start_tour("/odoo", "spreadsheet_open_pivot_sheet", login="admin")

    def test_01_spreadsheet_open_pivot_as_user(self):
        self.start_tour(
            "/odoo", "spreadsheet_open_pivot_sheet", login="spreadsheetDude"
        )
