from odoo import SUPERUSER_ID, api
from odoo.db import schema

from odoo.addons.document.models.document_document_thumbnail import SERVER_KINDS


def migrate(cr, version):
    if not version or not schema.column_exists(
        cr, "document_document", "thumbnail_status"
    ):
        return
    # a thumbnail stored on its document becomes that document's own, for the
    # content it holds: rendered there, by a browser, or authored (a
    # spreadsheet's, whose status was never set). An error is not kept, the
    # server renders it again; a shortcut's was a copy of its target's
    cr.execute(
        """
        INSERT INTO document_thumbnail
               (document_id, checksum, state, create_uid, create_date, write_uid, write_date)
        SELECT document.id, attachment.checksum, 'present',
               %(root)s, now() AT TIME ZONE 'UTC', %(root)s, now() AT TIME ZONE 'UTC'
          FROM document_document AS document
          JOIN ir_attachment AS attachment ON attachment.id = document.attachment_id
         WHERE document.shortcut_document_id IS NULL
           AND EXISTS (
               SELECT 1
                 FROM ir_attachment AS image
                WHERE image.res_model = 'document.document'
                  AND image.res_field = 'thumbnail'
                  AND image.res_id = document.id
           )
        """,
        {"root": SUPERUSER_ID},
    )
    cr.execute(
        """
        UPDATE ir_attachment AS image
           SET res_model = 'document.thumbnail',
               res_field = 'image',
               res_id = thumbnail.id
          FROM document_thumbnail AS thumbnail
         WHERE image.res_model = 'document.document'
           AND image.res_field = 'thumbnail'
           AND image.res_id = thumbnail.document_id
        """
    )
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["ir.attachment"].search(
        [("res_model", "=", "document.document"), ("res_field", "=", "thumbnail")]
    ).unlink()
    schema.drop_columns(cr, "document_document", ["thumbnail_status"])
    # the key is written past the ORM: a recompute would stamp every file
    # with today's write_date, and nothing about them changed
    documents = (
        env["document.document"]
        .with_context(active_test=False)
        .search([("type", "=", "binary"), ("shortcut_document_id", "=", False)])
    )
    keyed = {
        document.id: document.checksum
        for document in documents
        if document._get_thumbnail_kind() in SERVER_KINDS
    }
    cr.execute(
        """
        UPDATE document_document AS document
           SET thumbnail_source_checksum = keyed.checksum
          FROM unnest(%s::int[], %s::varchar[]) AS keyed(id, checksum)
         WHERE document.id = keyed.id
        """,
        [list(keyed), list(keyed.values())],
    )
    documents.invalidate_model(["thumbnail_source_checksum"])
    # an upgrade renders nothing itself: what no stored thumbnail covers queues
    documents.browse(keyed)._schedule_thumbnails()
