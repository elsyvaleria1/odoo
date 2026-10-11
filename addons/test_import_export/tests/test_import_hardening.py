import datetime
import unittest
from unittest.mock import MagicMock, patch

from odoo.tests.common import BaseCase, TransactionCase, can_import

from odoo.addons.base_import.models.base_import import ImportValidationError


class ImportHardeningCase(TransactionCase):

    def _make_import(self, res_model="import.char", **vals):
        vals.setdefault("res_model", res_model)
        return self.env["base_import.import"].create(vals)

    def test_execute_import_empty_file_raises_clean_error(self):
        imp = self._make_import(file=b"", file_name="empty.csv", file_type="text/csv")
        result = imp.execute_import(
            ["value"], ["Value"], {"has_headers": False, "quoting": '"'}
        )
        self.assertTrue(result.get("messages"))
        self.assertIn("no content", result["messages"][0]["message"])

    def test_execute_import_blank_rows_raises_clean_error(self):
        imp = self._make_import(
            file=b"\n\n\n", file_name="blank.csv", file_type="text/csv"
        )
        result = imp.execute_import(
            ["value"], ["Value"], {"has_headers": False, "quoting": '"'}
        )
        self.assertTrue(result.get("messages"))
        self.assertIn("no content", result["messages"][0]["message"])

    def test_read_csv_undetectable_encoding_raises_clean_error(self):
        imp = self._make_import(file=b"a,b,c", file_name="x.csv", file_type="text/csv")
        with (
            patch(
                "odoo.addons.base_import.models.base_import.guess_encoding",
                return_value=None,
            ),
            self.assertRaises(ImportValidationError),
        ):
            imp._read_csv({"quoting": '"'})

    def test_import_file_by_url_oversized_reports_specific_error(self):
        imp = self._make_import()
        fake_response = MagicMock(headers={"Content-Length": str(10**9)})
        fake_session = MagicMock()
        fake_session.get.return_value = fake_response

        with self.assertRaises(ImportValidationError) as cm:
            imp._import_file_by_url(
                "http://example.com/big.png", fake_session, "image_field", 0
            )

        self.assertIn("exceeds configured maximum", cm.exception.message)
        self.assertEqual(cm.exception.field_path, ["image_field"])

    def test_binary_field_date_value_does_not_crash(self):
        imp = self._make_import(res_model="res.partner")
        data = [[datetime.date(2024, 1, 1)]]
        with self.assertRaises(ImportValidationError):
            imp._parse_import_data(data, ["image_1920"], {})


@unittest.skipUnless(can_import("odf"), "odfpy not installed")
class TestODSReaderHardening(BaseCase):

    def _build_doc_with_repeat(self, repeat_value):
        from odf.opendocument import OpenDocumentSpreadsheet
        from odf.table import Table, TableCell, TableRow
        from odf.text import P

        doc = OpenDocumentSpreadsheet()
        table = Table(name="Sheet1")
        row = TableRow()
        repeated_cell = TableCell()
        repeated_cell.setAttribute("numbercolumnsrepeated", str(repeat_value))
        repeated_cell.addElement(P(text="x"))
        row.addElement(repeated_cell)
        row.addElement(TableCell())
        table.addElement(row)
        doc.spreadsheet.addElement(table)
        return doc

    def test_repeat_count_is_capped(self):
        from odoo.addons.base_import.models.odf_ods_reader import (
            MAX_CELL_REPEAT,
            ODSReader,
        )

        doc = self._build_doc_with_repeat(10**8)
        reader = ODSReader(content=doc)
        row = reader.get_sheet("Sheet1")[0]
        self.assertEqual(len(row), MAX_CELL_REPEAT + 1)
