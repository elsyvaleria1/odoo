from odoo.db import schema as sql
from odoo.libs.sql import SQL
from odoo.tests.common import TransactionCase

FIVE_GB = 5_000_000_000


class TestDocumentFileSize(TransactionCase):
    def test_a_document_keeps_the_size_of_a_file_past_int4(self):
        columns = sql.get_table_columns(self.env.cr, "document_document")
        self.assertEqual(columns["file_size"]["udt_name"], "int8")
        document = self.env["document.document"].create(
            {"name": "archive.zip", "raw": b"PK\x05\x06" + b"\0" * 18}
        )
        attachment = document.attachment_id
        self.env.flush_all()
        self.env.cr.execute(
            SQL(
                "UPDATE ir_attachment SET file_size = %s WHERE id = %s",
                FIVE_GB,
                attachment.id,
            )
        )
        attachment.invalidate_recordset(["file_size"])
        attachment.modified(["file_size"])
        self.env.flush_all()
        document.invalidate_recordset(["file_size"])
        self.assertEqual(document.file_size, FIVE_GB)
