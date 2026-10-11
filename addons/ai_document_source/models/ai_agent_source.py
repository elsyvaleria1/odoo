from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class AIAgentSource(models.Model):
    _name = "ai.agent.source"
    _inherit = ["ai.agent.source"]

    document_id = fields.Many2one(
        comodel_name="document.document",
        string="Source Document",
        index=True,
    )
    type = fields.Selection(
        selection_add=[("document", "Document")],
        ondelete={"document": lambda recs: recs.write({"type": "binary"})},
    )

    @api.depends_context("uid")
    @api.depends("document_id")
    def _compute_user_has_access(self) -> None:
        document_sources = self.filtered(lambda s: s.type == "document")
        for source in document_sources:
            source.user_has_access = source.document_id.user_permission != "none"
        super(AIAgentSource, self - document_sources)._compute_user_has_access()

    def _update_name(self):
        if not self:
            return None

        source = self[0]

        if source.type != "document":
            return super()._update_name()

        current_name = source.document_id.name
        if source.name != current_name:
            self.name = current_name
        return None

        return None

    def action_access_source(self) -> dict:
        self.check_singleton()
        if self.document_id:
            return {
                "type": "ir.actions.act_window",
                "name": self.env._("Source Document"),
                "view_mode": "kanban",
                "res_model": "document.document",
                "domain": [("id", "=", self.document_id.id)],
                "view_id": self.env.ref("document.document_view_kanban").id,
            }

        return super().action_access_source()

    def action_reprocess_index(self):
        self.check_singleton()
        if self.type != "document":
            return super().action_reprocess_index()

        sources_to_reprocess = self.env["ai.agent.source"].search(
            [("attachment_id.checksum", "=", self.attachment_id.checksum)]
        )

        sources_to_reprocess._update_name()

        if self.attachment_id.checksum == self.document_id.attachment_id.checksum:
            _debug.logic("source_reindex_skipped", reason="unchanged", source=self)
            return None

        self._recreate_attachments_for_sources(sources_to_reprocess)

        indexed_sources, sources_to_update_status, trigger_embeddings_cron = (
            self._get_sources_indexing_state(
                sources_to_reprocess, self.document_id.attachment_id.checksum
            )
        )

        self._update_sources_status(indexed_sources, sources_to_update_status)

        if trigger_embeddings_cron:
            self.env["ir.cron"]._trigger_ref("ai.ir_cron_generate_embedding")
        return None

        return None

    def _recreate_attachments_for_sources(self, sources) -> None:
        if not sources:
            return

        old_checksum = sources[0].attachment_id.checksum
        _debug.pipeline("source_attachments_recreated", sources=sources)
        self.env["ai.embedding"].search([("checksum", "=", old_checksum)]).unlink()

        for source in sources:
            base_attachment = source.document_id.attachment_id.with_context(
                no_document=True
            )
            source.attachment_id = base_attachment.copy(
                {
                    "res_model": "ai.agent.source",
                    "res_id": source.id,
                }
            )
