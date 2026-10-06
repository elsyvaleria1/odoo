from odoo.tests import tagged

from ..common import SpreadsheetTestTourCommon


@tagged("post_install", "-at_install")
class TestSpreadsheetCreateTemplate(SpreadsheetTestTourCommon):
    def test_01_spreadsheet_create_template(self):
        self.env.ref("base.user_admin").write(
            {
                "email": "mitchell.admin@example.com",
            }
        )
        self.start_tour(
            "/odoo", "documents_spreadsheet_create_template_tour", login="admin"
        )
