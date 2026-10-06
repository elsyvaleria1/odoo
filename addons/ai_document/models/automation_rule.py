import logging

from odoo import fields, models
from odoo.libs.debug_log import DebugLog

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)


class AutomationRule(models.Model):
    _inherit = "automation.rule"

    ai_autosort_folder_id = fields.Many2one(
        comodel_name="document.document",
        string="Sorted Folder",
        domain=[("type", "=", "folder"), ("shortcut_document_id", "=", False)],
    )

    _unique_ai_autosort_folder_id = models.Constraint(
        "UNIQUE(ai_autosort_folder_id)",
        "Only one automation rule can be used to sort with AI a given folder",
    )

    def _process(self, records, domain_post=None):
        if (
            self.env.context.get("ai_documents_skip_autosort")
            and records
            and records._name == "document.document"
            and self.ai_autosort_folder_id
        ):
            _debug.logic("autosort_skipped", reason="context_flag", rule=self)
            return None
        return super()._process(records, domain_post)
