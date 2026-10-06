from odoo import Command
from odoo.tests.common import HttpCase, new_test_user

from .test_common import TestQualityCommon
from odoo.addons.spreadsheet_edition.tests.spreadsheet_test_case import (
    SpreadsheetTestCase,
)


class TestQualitySpreadsheet(TestQualityCommon, SpreadsheetTestCase, HttpCase):
    def test_create_spreadsheet_template(self):
        spreadsheet = self.env["quality.spreadsheet.template"].create(
            {
                "check_cell": "A1",
                "name": "my spreadsheet quality check template",
            }
        )
        point = self.env["quality.point"].create(
            {
                "name": "QP1",
                "test_type_id": self.env.ref(
                    "quality_control.test_type_spreadsheet"
                ).id,
                "spreadsheet_template_id": spreadsheet.id,
                "picking_type_ids": [Command.link(self.picking_type_id)],
            }
        )
        self.assertEqual(point.spreadsheet_check_cell, "A1")
        user = new_test_user(
            self.env, login="raoul", groups="quality.group_quality_user"
        )
        self.authenticate(user.login, user.password)
        response = self.url_open(
            "/spreadsheet/data/quality.spreadsheet.template/%s" % spreadsheet.id
        )
        data = response.json()
        self.assertEqual(data["quality_check_cell"], "A1")

        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": self.picking_type_id,
                "partner_id": self.partner_id,
                "location_id": self.location_id,
                "location_dest_id": self.location_dest_id,
            }
        )
        self.env["stock.move"].create(
            {
                "product_id": self.product.id,
                "product_uom_qty": 1,
                "product_uom_id": self.product.uom_id.id,
                "picking_id": picking.id,
                "location_id": self.location_id,
                "location_dest_id": self.location_dest_id,
            }
        )
        picking.action_confirm()
        self.assertEqual(len(picking.check_ids), 1)
        check = picking.check_ids

        self.assertFalse(check.spreadsheet_id, "the spreadsheet is lazily created")
        action = check.action_view_spreadsheet()
        spreadsheet = check.spreadsheet_id
        self.assertEqual(action["params"]["check_id"], check.id)
        self.assertEqual(action["params"]["spreadsheet_id"], spreadsheet.id)

        response = self.url_open(
            "/spreadsheet/data/quality.check.spreadsheet/%s" % spreadsheet.id
        )
        data = response.json()
        self.assertEqual(data["quality_check_cell"], "A1")

        check.unlink()
        self.assertFalse(spreadsheet.exists())
