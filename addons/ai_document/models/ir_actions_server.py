import json
import logging

import psycopg.errors

from odoo import fields, models
from odoo.libs.debug_log import DebugLog

from odoo.addons.ai_fields.tools import parse_ai_prompt_values

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)


class IrActionsServer(models.Model):
    _inherit = "ir.actions.server"

    ai_autosort_folder_id = fields.Many2one(
        comodel_name="document.document",
        string="Sorted Folder",
        domain=[("type", "=", "folder"), ("shortcut_document_id", "=", False)],
    )

    def _ai_action_run(self, record) -> tuple:
        self.check_singleton()
        if not self.ai_autosort_folder_id or record._name != "document.document":
            _debug.logic("ai_run_delegated", reason="not_autosort", action=self)
            return super()._ai_action_run(record)

        record = record.with_context(
            ai_executed_action=self, ai_documents_skip_autosort=True
        )

        ret, tool_calls_history = [], []
        try:
            with (
                _debug.perf("ai_action_run", cr=self.env.cr, action=self),
                self.env.cr.savepoint(),
            ):
                ret, tool_calls_history = super()._ai_action_run(record)
        except psycopg.errors.SerializationFailure, psycopg.errors.DeadlockDetected:
            raise
        except Exception as e:
            # We don't want to raise, to not break the flow like documents upload
            # (e.g., if the OpenAI key is not set)
            error = e
            _debug.logic("ai_run_failed", action=self, error=type(e).__name__)
            _logger.exception("AI error: %s", error)
        else:
            error = next((t["error"] for t in tool_calls_history if t["error"]), None)

        if error:
            _debug.pipeline("ai_run_outcome", by="error", action=self)
            if isinstance(record, self.pool["mixin.mail.thread"]):
                record._message_log(
                    body=self.env._("AI: An error occurred: %s", error),
                    author_id=self._ai_partner().id,
                )

            if self.env.user.active:
                self.env.user._bus_send(
                    "ai_document.auto_sort_notification",
                    {
                        "message": str(error),
                        "type": "warning",
                        "document_name": record.name,
                        "document_access_url": record.access_url,
                    },
                )

        elif self.env.user.active:
            # Send the last tool result or name as toast notification
            # Or the main AI action if no tool was executed
            tool_history = " ".join(
                t["result"] for t in tool_calls_history if t["result"]
            )
            message = tool_history or self._ai_get_action_description(record)
            _debug.pipeline(
                "ai_run_outcome", by="success", tools=len(tool_calls_history)
            )

            self.env.user._bus_send(
                "ai_document.auto_sort_notification",
                {
                    "message": message,
                    "type": "success",
                    "document_name": record.name,
                    "document_access_url": record.access_url,
                },
            )
        return ret, tool_calls_history

    def _ai_prepare_prompt_values(self, record) -> tuple:
        action_prompt, context_fields = super()._ai_prepare_prompt_values(record)

        if (
            self.ai_autosort_folder_id
            and record._name == "document.document"
            and self.ai_autosort_folder_id == record.folder_id
        ):
            # Evaluate the folder prompt on the document and not on the folder
            folder_prompt, folder_context_fields, target_folders = (
                parse_ai_prompt_values(
                    self.env,
                    # sudo: ai_sort_prompt has group system
                    record.folder_id.sudo().ai_sort_prompt,
                    "document.document",
                )
            )
            _debug.logic(
                "ai_prompt_from_folder",
                folder=record.folder_id,
                targets=len(target_folders),
            )
            context_fields |= folder_context_fields
            action_prompt += f"\n{folder_prompt}"
            action_prompt += "\n" + self.env._(
                "You can move the document in one of those folders:"
            )
            action_prompt += "\n" + json.dumps(
                target_folders, ensure_ascii=False, indent=2
            )

        return action_prompt, context_fields
