from collections import Counter

from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class DocumentsDocument(models.Model):
    _inherit = "document.document"

    document_count = fields.Integer(compute="_compute_document_count")

    @api.depends_context("uid")
    @api.depends("type", "children_ids", "shortcut_document_id")
    def _compute_document_count(self) -> None:
        folders = (self | self.shortcut_document_id).filtered(
            lambda d: d.type == "folder" and not d.shortcut_document_id
        )

        children_counts = Counter(
            dict(
                self._read_group(
                    [("folder_id", "in", folders.ids)],
                    groupby=["folder_id"],
                    aggregates=["__count"],
                )
            )
        )

        _debug.perf.count("folder_child_counts", folders=folders, documents=self)
        for doc in self:
            doc.document_count = children_counts[doc.shortcut_document_id or doc]
