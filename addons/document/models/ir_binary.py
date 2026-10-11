from os.path import splitext
from typing import Any

from odoo import models
from odoo.exceptions import AccessError
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL

_debug = DebugLog(__name__)

ATTACHMENT_CONTENT_FIELDS = ("raw", "datas", "db_datas")


class IrBinary(models.AbstractModel):
    _inherit = "ir.binary"

    def _record_to_stream(self, record: models.Model, field_name: str) -> Any:
        if record._name == "document.document" and field_name in ("raw", "datas"):
            _debug.logic("stream_from_attachment", document=record, field=field_name)
            self._check_document_content_served(record.attachment_id)
            return super()._record_to_stream(record.attachment_id.sudo(), field_name)
        if record._name == "ir.attachment" and field_name in ATTACHMENT_CONTENT_FIELDS:
            self._check_document_content_served(record)
        return super()._record_to_stream(record, field_name)

    def _check_document_content_served(self, attachment: models.Model) -> None:
        if attachment.env.su or not attachment:
            return
        Documents = attachment.env["document.document"].with_context(active_test=False)
        if not self._is_blocked_document_content(
            attachment
        ) or not Documents.has_access("read"):
            return
        documents = Documents.search(
            [
                "|",
                ("attachment_id", "=", attachment.id),
                ("previous_attachment_ids", "in", attachment.ids),
            ]
        )
        refused = documents.filtered(
            lambda document: (
                not (
                    document._is_inline_content_allowed()
                    if document.attachment_id == attachment
                    else document._is_download_allowed()
                )
            )
        )
        if documents:
            _debug.logic(
                "stream_gate",
                attachment=attachment,
                documents=documents,
                current=documents.filtered(lambda d: d.attachment_id == attachment),
                refused=refused,
            )
        if refused:
            _debug.logic(
                "stream_refused",
                attachment=attachment,
                documents=refused,
                reason="download_blocked",
            )
            raise AccessError(self.env._("Downloading this document is not allowed."))

    def _is_blocked_document_content(self, attachment: models.Model) -> bool:
        Documents = self.env["document.document"]
        versions = Documents._fields["previous_attachment_ids"]
        Documents.flush_model(
            ["attachment_id", "previous_attachment_ids", "is_download_blocked"]
        )
        self.env.cr.execute(
            SQL(
                """SELECT 1 FROM document_document
                    WHERE attachment_id = %(id)s AND is_download_blocked
                    UNION ALL
                   SELECT 1 FROM %(versions)s AS version
                     JOIN document_document AS document
                       ON document.id = version.%(document)s
                    WHERE version.%(column)s = %(id)s
                      AND document.is_download_blocked
                    LIMIT 1""",
                id=attachment.id,
                versions=SQL.identifier(versions.relation),
                document=SQL.identifier(versions.column1),
                column=SQL.identifier(versions.column2),
            )
        )
        found = bool(self.env.cr.rowcount)
        _debug.perf.count("blocked_content_probe", attachment=attachment, found=found)
        return found

    def _get_stream_from_record(
        self,
        record: models.Model,
        field_name: str = "raw",
        filename: str | None = None,
        filename_field: str = "name",
        mimetype: str | None = None,
        default_mimetype: str = "application/octet-stream",
    ) -> Any:
        if (
            record._name == "document.document"
            and filename is None
            and record.file_extension
        ):
            name, extension = splitext(record.name)
            if extension == f".{record.file_extension}":
                filename = record.name
            else:
                filename = f"{name}.{record.file_extension}"
        if (
            record._name in ("document.document", "ir.attachment")
            and record.mimetype == "application/documents-email"
        ):
            _debug.logic("stream_mimetype_rewritten", record=record, to="text/plain")
            mimetype = "text/plain"
        return super()._get_stream_from_record(
            record, field_name, filename, filename_field, mimetype, default_mimetype
        )
