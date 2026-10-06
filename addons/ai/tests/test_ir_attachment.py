from unittest.mock import patch

from odoo.tests.common import TransactionCase


class TestAISources(TransactionCase):
    # Processing of tabular attachments whose index_content comes from `attachment_indexation`
    def _create_attachment(self, name, mimetype, content):
        # Mirror ir.attachment._get_index_content(bin_data, file_type, checksum=None). The
        # `checksum` keyword is passed by _store_content on every
        # create, so a two-parameter stand-in raises TypeError before the test
        # reaches its assertions.
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
        # Two sheets separated by blank line, both with headers
        index_content = (
            b"Name,Age\nAlice,30\nBob,25\n\nProduct,Price\nPen,1.2\nNotebook,2.5"
        )

        attachment = self._create_attachment(
            "people_and_products.csv", "text/csv", index_content
        )
        content = attachment._get_attachment_content()
        self.assertIsInstance(content, str)
        self.assertTrue(content)
        # Validate first sheet rows are parsed with explicit headers
        self.assertIn("{'Name': 'Alice', 'Age': '30'}", content)
        self.assertIn("{'Name': 'Bob', 'Age': '25'}", content)
        # Validate second sheet rows are parsed with explicit headers
        self.assertIn("{'Product': 'Pen', 'Price': '1.2'}", content)
        self.assertIn("{'Product': 'Notebook', 'Price': '2.5'}", content)

    def test_ragged_rows_extra_and_missing_columns(self):
        # All-numeric CSV: no header is detected, so columns get generated names
        # Row 2 has extra fields (captured under _extra_fields), row 3 has a missing value
        sheet = b"3,10\n1,2,3,4\n5\n6,7"

        attachment = self._create_attachment("ragged.csv", "text/csv", sheet)
        content = attachment._get_attachment_content()
        self.assertIsInstance(content, str)
        self.assertTrue(content)
        # Extra fields captured under _extra_fields
        self.assertIn("'Column_0': '1'", content)
        self.assertIn("'Column_1': '2'", content)
        self.assertIn("'_extra_fields': ['3', '4']", content)
        # Missing column becomes None
        self.assertIn("{'Column_0': '5', 'Column_1': None}", content)
        # Normal row
        self.assertIn("{'Column_0': '6', 'Column_1': '7'}", content)
