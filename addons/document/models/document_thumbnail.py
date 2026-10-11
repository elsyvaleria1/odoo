from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class DocumentThumbnail(models.Model):
    _name = "document.thumbnail"
    _description = "Document Thumbnail"

    checksum = fields.Char(
        index=True,
        readonly=True,
    )
    document_id = fields.Many2one(
        comodel_name="document.document",
        index="btree_not_null",
        readonly=True,
        ondelete="cascade",
    )
    image = fields.Binary(
        attachment=True,
        readonly=True,
    )
    state = fields.Selection(
        selection=[
            ("present", "Present"),
            ("error", "Error"),
        ],
        readonly=True,
        required=True,
    )

    _content_unique = models.UniqueIndex("(checksum) WHERE document_id IS NULL")
    _document_unique = models.UniqueIndex("(document_id) WHERE document_id IS NOT NULL")
    _keyed = models.Constraint(
        "CHECK(document_id IS NOT NULL OR checksum IS NOT NULL)",
        "A rendered thumbnail names the content it was rendered from.",
    )

    @api.autovacuum
    def _gc_unreferenced(self) -> None:
        self.env.cr.execute(
            """
            SELECT thumbnail.id
              FROM document_thumbnail AS thumbnail
             WHERE thumbnail.document_id IS NULL
               AND NOT EXISTS (
                   SELECT 1
                     FROM document_document AS document
                    WHERE document.thumbnail_source_checksum = thumbnail.checksum
               )
            """
        )
        orphans = self.browse(row[0] for row in self.env.cr.fetchall())
        orphans.unlink()
        if orphans:
            _debug.lifecycle("thumbnails_collected", thumbnails=len(orphans))
