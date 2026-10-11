from unittest.mock import patch

from odoo.tests.common import TransactionCase


class TestAISources(TransactionCase):
    def _create_attachment(self, name, mimetype, content):
        def _get_index_content(self, data, _type, checksum=None):
            return data

        with patch.object(
            self.registry["ir.attachment"], "_get_index_content", _get_index_content
        ):
            return self.env["ir.attachment"].create(
                {
                    "name": name,
                    "mimetype": mimetype,
                    "raw": content,
                }
            )

    def test_multi_sheet_csv_with_headers(self):
        index_content = (
            b"Name,Age\nAlice,30\nBob,25\n\nProduct,Price\nPen,1.2\nNotebook,2.5"
        )

        attachment = self._create_attachment(
            "people_and_products.csv", "text/csv", index_content
        )
        content = attachment._get_attachment_content()
        self.assertIsInstance(content, str)
        self.assertTrue(content)
        self.assertIn("{'Name': 'Alice', 'Age': '30'}", content)
        self.assertIn("{'Name': 'Bob', 'Age': '25'}", content)
        self.assertIn("{'Product': 'Pen', 'Price': '1.2'}", content)
        self.assertIn("{'Product': 'Notebook', 'Price': '2.5'}", content)

    def test_ragged_rows_extra_and_missing_columns(self):
        sheet = b"3,10\n1,2,3,4\n5\n6,7"

        attachment = self._create_attachment("ragged.csv", "text/csv", sheet)
        content = attachment._get_attachment_content()
        self.assertIsInstance(content, str)
        self.assertTrue(content)
        self.assertIn("'Column_0': '1'", content)
        self.assertIn("'Column_1': '2'", content)
        self.assertIn("'_extra_fields': ['3', '4']", content)
        self.assertIn("{'Column_0': '5', 'Column_1': None}", content)
        self.assertIn("{'Column_0': '6', 'Column_1': '7'}", content)
