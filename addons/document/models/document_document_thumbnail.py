import base64
import hashlib
import logging
import typing

from PIL import features
from psycopg import errors

from odoo import api, fields, models
from odoo.api import SUPERUSER_ID
from odoo.exceptions import UserError
from odoo.libs import pdf_raster
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL
from odoo.tools.image import image_process

if typing.TYPE_CHECKING:
    from .document_thumbnail import DocumentThumbnail

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)

THUMBNAIL_SIZE = (200, 140)
JOB_CHANNEL = "document_thumbnail"
PRECOMMIT_KEY = "document.thumbnails_awaited"
INLINE_IMAGES = 20
MAX_PDF_BYTES = 64 * 1024 * 1024
SWEEP_BATCH = 500
SERVER_KINDS = ("image", "pdf")


class DocumentsDocument(models.Model):
    _inherit = "document.document"

    thumbnail_source_checksum = fields.Char(
        export_string_translation=False,
        compute="_compute_thumbnail_source_checksum",
        store=True,
        index="btree_not_null",
    )
    thumbnail = fields.Binary(
        compute="_compute_thumbnail",
        inverse="_inverse_thumbnail",
    )
    thumbnail_status = fields.Selection(
        selection=[
            ("present", "Present"),
            ("error", "Error"),
            ("pending", "Pending"),
            ("client_generated", "Client Generated"),
        ],
        compute="_compute_thumbnail_status",
    )
    thumbnail_unique = fields.Char(
        export_string_translation=False,
        compute="_compute_thumbnail_status",
    )

    def _get_thumbnail_kind(self) -> str | bool:
        self.check_singleton()
        if self.type != "binary" or not self.attachment_id:
            return False
        mimetype = self.mimetype or ""
        is_pdf = mimetype.startswith("application/pdf")
        if not is_pdf and not mimetype.startswith("image/"):
            return False
        if is_pdf:
            return "pdf" if self.attachment_id.file_size <= MAX_PDF_BYTES else "browser"
        if mimetype.startswith("image/webp") and not features.check("webp"):
            return "browser"
        return "image"

    def _get_thumbnail_content_key(self) -> str | bool:
        self.check_singleton()
        attachment = self.attachment_id
        if attachment.checksum:
            return attachment.checksum
        if attachment.type == "cloud_storage" and attachment.url:
            return "url:" + hashlib.sha256(attachment.url.encode()).hexdigest()
        return False

    def _get_thumbnail_source(self) -> bytes:
        self.check_singleton()
        return self.attachment_id._get_content() or b""

    @api.depends(
        "type",
        "checksum",
        "mimetype",
        "attachment_id.type",
        "attachment_id.url",
        "attachment_id.file_size",
        "shortcut_document_id",
    )
    def _compute_thumbnail_source_checksum(self) -> None:
        for document in self:
            rendered = (
                not document.shortcut_document_id
                and document._get_thumbnail_kind() in SERVER_KINDS
            )
            document.thumbnail_source_checksum = (
                document._get_thumbnail_content_key() if rendered else False
            )
        awaited = {
            document.id
            for document in self
            if document.thumbnail_source_checksum and isinstance(document.id, int)
        }
        if not awaited:
            return
        pending = self.env.cr.precommit.data.setdefault_set(PRECOMMIT_KEY)
        if not pending:
            self.env.cr.precommit.add(
                self.env["document.document"]._render_awaited_thumbnails
            )
        pending.update(awaited)

    @api.depends(
        "thumbnail_source_checksum",
        "checksum",
        "attachment_id.url",
        "shortcut_document_id.thumbnail_source_checksum",
        "shortcut_document_id.checksum",
    )
    def _compute_thumbnail(self) -> None:
        rows = self._get_thumbnail_rows()
        for document in self:
            row = rows.get(document._origin.id)
            document.thumbnail = row.image if row else False

    def _inverse_thumbnail(self) -> None:
        for document in self:
            document._store_own_thumbnail(document.thumbnail or False, "present")

    @api.depends(
        "type",
        "mimetype",
        "thumbnail_source_checksum",
        "checksum",
        "attachment_id.type",
        "attachment_id.file_size",
        "attachment_id.url",
        "shortcut_document_id.thumbnail_source_checksum",
        "shortcut_document_id.checksum",
    )
    def _compute_thumbnail_status(self) -> None:
        rows = self._get_thumbnail_rows()
        for document in self:
            source = document.shortcut_document_id or document
            row = rows.get(document._origin.id)
            version = (
                f"{row.id}:{row.write_date}"
                if row
                else source._get_thumbnail_content_key()
            )
            document.thumbnail_unique = (
                hashlib.sha256(version.encode()).hexdigest()[:16] if version else False
            )
            if row:
                document.thumbnail_status = row.state
                continue
            kind = source._get_thumbnail_kind()
            if kind == "pdf" and not pdf_raster.available():
                kind = "browser"
            document.thumbnail_status = {
                "image": "pending",
                "pdf": "pending",
                "browser": "client_generated",
            }.get(kind, False)

    def _thumbnail_store(self) -> DocumentThumbnail:
        return self.env["document.thumbnail"].with_privilege(
            "document.privilege_thumbnails",
            reason="a thumbnail is reached through the document it shows",
        )

    def _get_thumbnail_rows(self) -> dict[int, DocumentThumbnail]:
        sources = {
            document._origin.id: (document.shortcut_document_id or document)._origin
            for document in self
            if document._origin.id
        }
        if not sources:
            return {}
        store = self._thumbnail_store()
        own = {
            row.document_id.id: row
            for row in store.search(
                [("document_id", "in", list({s.id for s in sources.values()}))]
            )
        }
        checksums = {s.thumbnail_source_checksum for s in sources.values()} - {False}
        shared = {
            row.checksum: row
            for row in store.search(
                [("document_id", "=", False), ("checksum", "in", list(checksums))]
            )
        }
        rows = {}
        for document_id, source in sources.items():
            row = own.get(source.id)
            if row and row.checksum != source._get_thumbnail_content_key():
                row = row if source._get_thumbnail_kind() == "authored" else None
            if row := row or shared.get(source.thumbnail_source_checksum):
                rows[document_id] = row
        return rows

    def _store_own_thumbnail(
        self, image: bytes | typing.Literal[False], state: str
    ) -> None:
        self.check_singleton()
        store = self._thumbnail_store()
        row = store.search([("document_id", "=", self.id)])
        if not image and state == "present":
            row.unlink()
            self.invalidate_model(["thumbnail", "thumbnail_status", "thumbnail_unique"])
            return
        vals = {
            "checksum": self._get_thumbnail_content_key(),
            "image": image,
            "state": state,
        }
        if row:
            row.write(vals)
        else:
            store.create({**vals, "document_id": self.id})
        self.invalidate_model(["thumbnail", "thumbnail_status", "thumbnail_unique"])

    @api.model
    def _render_awaited_thumbnails(self) -> None:
        ids = self.env.cr.precommit.data.pop(PRECOMMIT_KEY, set())
        system = self.with_user(SUPERUSER_ID)
        system.browse(sorted(ids)).exists()._schedule_thumbnails(inline=INLINE_IMAGES)

    def _schedule_thumbnails(self, inline: int = 0) -> None:
        rows = self._get_thumbnail_rows()
        by_checksum = {}
        for document in self:
            if document.id not in rows and document.thumbnail_source_checksum:
                by_checksum.setdefault(document.thumbnail_source_checksum, document)
        rendered = queued = 0
        for checksum, document in by_checksum.items():
            kind = document._get_thumbnail_kind()
            local = document.attachment_id.type != "cloud_storage"
            if kind == "image" and local and rendered < inline:
                document._render_thumbnail()
                rendered += 1
                continue
            if kind == "pdf" and not pdf_raster.available():
                continue
            document.delayed(
                channel=JOB_CHANNEL,
                identity_key=f"document.thumbnail:{checksum}",
                name=f"Render the thumbnail of {document.display_name}",
            )._job_render_thumbnails()
            queued += 1
        if rendered or queued:
            _debug.lifecycle("thumbnails_scheduled", rendered=rendered, queued=queued)

    @api.job(channel=JOB_CHANNEL, max_retries=2)
    def _job_render_thumbnails(self) -> None:
        for document in self.exists():
            if (
                document.thumbnail_source_checksum
                and document.id not in document._get_thumbnail_rows()
            ):
                document._render_thumbnail()

    def _render_thumbnail(self) -> None:
        self.check_singleton()
        checksum = self.thumbnail_source_checksum
        kind = self._get_thumbnail_kind()
        with _debug.perf("thumbnail_render", cr=self.env.cr, kind=kind) as span:
            try:
                content = self._get_thumbnail_source()
            except UserError, OSError:
                _logger.warning(
                    "Documents: the content of %r is unreachable",
                    self.name,
                    exc_info=True,
                )
                span.set(outcome="unreachable")
                return
            if kind == "pdf":
                width, height = THUMBNAIL_SIZE
                rendering = pdf_raster.render_first_page(content, 2 * width, 2 * height)
                span.set(outcome=rendering.outcome)
                if rendering.outcome in (
                    pdf_raster.Outcome.UNAVAILABLE,
                    pdf_raster.Outcome.TIMED_OUT,
                ):
                    return
                if rendering.pages is not None:
                    self._note_page_count(checksum, rendering.pages)
                image = _fit(rendering.png, crop="top")
            else:
                image = _fit(content, crop="center")
                span.set(outcome="rendered" if image else "failed")
        self._store_rendered_thumbnail(checksum, image)

    def _note_page_count(self, checksum: str, pages: int) -> None:
        self.env.cr.execute(
            SQL(
                """
                UPDATE document_document AS document
                   SET is_multipage = %s
                  FROM ir_attachment AS attachment
                 WHERE attachment.id = document.attachment_id
                   AND attachment.type = 'cloud_storage'
                   AND attachment.mimetype LIKE 'application/pdf%%'
                   AND document.thumbnail_source_checksum = %s
                   AND document.is_multipage IS DISTINCT FROM %s
                """,
                pages > 1,
                checksum,
                pages > 1,
            )
        )
        if noted := self.env.cr.rowcount:
            self.invalidate_model(["is_multipage"])
            _debug.logic(
                "page_count_noted", checksum=checksum, pages=pages, documents=noted
            )

    def _store_rendered_thumbnail(self, checksum: str, image: bytes | None) -> None:
        vals = {
            "checksum": checksum,
            "image": base64.b64encode(image) if image else False,
            "state": "present" if image else "error",
        }
        try:
            with self.env.cr.savepoint():
                self._thumbnail_store().create(vals)
        except errors.UniqueViolation:
            _debug.logic("thumbnail_render_raced", checksum=checksum)
        self.invalidate_model(["thumbnail", "thumbnail_status", "thumbnail_unique"])

    @api.model
    def _rekey_thumbnail_sources(self) -> None:
        documents = self.with_context(active_test=False).search(
            [("type", "=", "binary"), ("shortcut_document_id", "=", False)]
        )
        keyed = {
            document.id: document._get_thumbnail_content_key()
            for document in documents
            if document._get_thumbnail_kind() in SERVER_KINDS
        }
        self.env.cr.execute(
            SQL(
                """
                UPDATE document_document AS document
                   SET thumbnail_source_checksum = keyed.checksum
                  FROM unnest(%s::int[], %s::varchar[]) AS keyed(id, checksum)
                 WHERE document.id = keyed.id
                   AND document.thumbnail_source_checksum IS DISTINCT FROM keyed.checksum
                """,
                list(keyed),
                list(keyed.values()),
            )
        )
        written = self.env.cr.rowcount
        unkeyed = self._thumbnail_store().search(
            [("document_id", "in", documents.ids), ("checksum", "=", False)]
        )
        for row in unkeyed:
            row.checksum = row.document_id._get_thumbnail_content_key()
        documents.invalidate_model(["thumbnail_source_checksum"])
        documents.browse(keyed)._schedule_thumbnails()
        _debug.lifecycle(
            "thumbnail_sources_rekeyed",
            keyed=len(keyed),
            written=written,
        )

    @api.model
    def _cron_render_awaited_thumbnails(self) -> None:
        self.env.cr.execute(
            SQL(
                """
                SELECT DISTINCT ON (document.thumbnail_source_checksum) document.id
                  FROM document_document AS document
                 WHERE document.thumbnail_source_checksum IS NOT NULL
                   AND NOT EXISTS (
                       SELECT 1
                         FROM document_thumbnail AS thumbnail
                        WHERE thumbnail.document_id IS NULL
                          AND thumbnail.checksum = document.thumbnail_source_checksum
                   )
                   AND NOT EXISTS (
                       SELECT 1
                         FROM document_thumbnail AS thumbnail
                        WHERE thumbnail.document_id = document.id
                          AND thumbnail.checksum = document.thumbnail_source_checksum
                   )
                 ORDER BY document.thumbnail_source_checksum, document.id DESC
                 LIMIT %s
                """,
                SWEEP_BATCH,
            )
        )
        awaited = self.browse(row[0] for row in self.env.cr.fetchall())
        awaited._schedule_thumbnails()
        if awaited:
            _debug.lifecycle("thumbnails_swept", documents=len(awaited))


def _fit(content: bytes, crop: str) -> bytes | None:
    if not content:
        return None
    try:
        return (
            image_process(
                content, size=THUMBNAIL_SIZE, crop=crop, verify_resolution=True
            )
            or None
        )
    except Exception:
        _logger.warning("Documents: could not build a thumbnail", exc_info=True)
        return None
