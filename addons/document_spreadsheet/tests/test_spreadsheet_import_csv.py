from odoo.libs.json import loads as json_loads
from odoo.tests.common import HttpCase
from odoo.tools import file_open

from .common import SpreadsheetTestCommon


class SpreadsheetImportCSV(HttpCase, SpreadsheetTestCommon):
    def test_import_csv(self):
        folder = self.env["document.document"].create(
            {"name": "New folder", "type": "folder"}
        )
        with file_open("document_spreadsheet/tests/data/test.csv", "rb") as f:
            document_csv = self.env["document.document"].create(
                {
                    "raw": f.read(),
                    "name": "test.csv",
                    "mimetype": "text/csv",
                    "folder_id": folder.id,
                }
            )
            spreadsheet_id = document_csv.import_to_spreadsheet()
            spreadsheet = self.env["document.document"].browse(spreadsheet_id).exists()
            self.assertTrue(spreadsheet)
            self.assertEqual(spreadsheet.name, "test")
            expected_data = {
                "sheets": [
                    {
                        "cells": {
                            "A1": "1",
                            "B1": "Pamella",
                            "C1": "Piercy",
                            "D1": "ppiercy0@slashdot.org",
                            "A2": "2",
                            "B2": "Crissie",
                            "C2": "Narrie",
                            "D2": "cnarrie1@godaddy.com",
                            "A3": "3",
                            "B3": "Ruby",
                            "C3": "Smallcombe",
                            "D3": "rsmallcombe2@google.it",
                        },
                        "comments": {},
                    }
                ]
            }
            self.assertEqual(json_loads(spreadsheet.raw), expected_data)
