from odoo import api, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class DocumentsTag(models.Model):
    _inherit = "document.tag"

    @api.model
    def _create_missing_documents_project_tags(self) -> None:
        tags_list = [
            {
                "xml_id": "document.documents_tag_draft",
                "noupdate": True,
                "values": {"name": "Draft", "sequence": 2},
            },
            {
                "xml_id": "document.documents_tag_to_validate",
                "noupdate": True,
                "values": {"name": "To validate", "sequence": 6},
            },
            {
                "xml_id": "document.documents_tag_validated",
                "noupdate": True,
                "values": {"name": "Validated", "sequence": 8},
            },
            {
                "xml_id": "document.documents_tag_deprecated",
                "noupdate": True,
                "values": {"name": "Deprecated", "sequence": 4},
            },
        ]
        _debug.lifecycle("project_tags_seeded", count=len(tags_list))
        self._load_records(tags_list)
