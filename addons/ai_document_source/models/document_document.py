from odoo import api, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class DocumentsDocument(models.Model):
    _inherit = "document.document"

    @api.model
    def create_ai_agent_sources_from_documents(self, document_ids, agent_id):
        """Create AI agent sources from the given documents."""
        documents = self.browse(document_ids)
        # Create copies of the attachments
        attachment_ids = []
        document_source_mapping = {}
        for document in documents:
            attachment = document.attachment_id.with_context(no_document=True).copy(
                {
                    "res_model": False,
                    "res_id": False,
                }
            )
            attachment_ids.append(attachment.id)
            document_source_mapping[attachment.id] = document.id
        _debug.pipeline(
            "ai_sources_from_documents",
            documents=documents,
            attachments=len(attachment_ids),
            agent=agent_id,
        )
        sources = self.env["ai.agent.source"].create_from_attachments(
            attachment_ids, agent_id
        )
        for source in sources:
            source.write(
                {
                    "type": "document",
                    "document_id": document_source_mapping[source.attachment_id.id],
                }
            )
        return sources

    @api.ondelete(at_uninstall=False)
    def _unlink_sources(self) -> None:
        """Delete sources when a document is deleted."""
        source_linked_to_document = self.env["ai.agent.source"].search(
            [("document_id", "in", self.ids)]
        )
        if source_linked_to_document:
            _debug.lifecycle(
                "ai_sources_unlinked",
                documents=self,
                sources=source_linked_to_document,
            )
            source_linked_to_document.unlink()
