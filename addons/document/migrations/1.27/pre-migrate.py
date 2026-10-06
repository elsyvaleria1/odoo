from odoo.db import schema


def migrate(cr, version):
    if not version or schema.column_exists(
        cr, "document_document", "thumbnail_source_checksum"
    ):
        return
    # created empty, so loading the module computes nothing: the post-migrate
    # computes it once the stored thumbnails are in the store, and only the
    # contents left without one are rendered
    schema.create_column(
        cr, "document_document", "thumbnail_source_checksum", "varchar"
    )
