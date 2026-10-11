from odoo.db import schema


def migrate(cr, version):
    if not version or schema.column_exists(
        cr, "document_document", "thumbnail_source_checksum"
    ):
        return
    schema.create_column(
        cr, "document_document", "thumbnail_source_checksum", "varchar"
    )
