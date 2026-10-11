from odoo import Command, api, fields, models
from odoo.libs.debug_log import DebugLog
from odoo.tools import is_html_empty

_debug = DebugLog(__name__)


class WizardDocumentDocumentSetupAiSort(models.TransientModel):
    """Wizard responsible to create the Automation Rule and the server action to auto sort files."""

    _name = "wizard.document.document.setup.ai.sort"
    _description = "Ai Documents Sort"

    @api.model
    def default_get(self, fields):
        values = super().default_get(fields)

        tool_actions = self.env["ir.actions.server"]
        if "folder_id" in values and "ai_tool_ids" in fields:
            existing_ir_action = self.env["ir.actions.server"].search(
                [("ai_autosort_folder_id", "=", values["folder_id"])],
                limit=1,
            )
            if existing_ir_action:
                _debug.logic(
                    "sort_wizard", by="existing_rule", folder=values["folder_id"]
                )
                values["ai_sort_prompt"] = (
                    self.env["document.document"]
                    .browse(values["folder_id"])
                    .ai_sort_prompt
                )
                values["ai_tool_ids"] = [
                    Command.set(existing_ir_action.ai_tool_ids.ids)
                ]
                return values

            folder = self.env["document.document"].browse(values["folder_id"])
            tool_actions = self._get_folder_actions(folder)

        if "ai_tool_ids" in fields:
            move_in_folder = self.env.ref(
                "ai_document.ir_actions_server_move_in_folder",
                raise_if_not_found=False,
            )
            if move_in_folder:
                tool_actions |= move_in_folder
            values["ai_tool_ids"] = [Command.set(tool_actions.ids)]

        finance_folder = self.env.ref(
            "document.document_finance_folder", raise_if_not_found=False
        )
        if "ai_sort_prompt" not in fields or not finance_folder:
            return values

        values["ai_sort_prompt"] = self.env._(
            "If the document is an invoice, send it to %s",
            self.env["document.document"]._ai_folder_insert(finance_folder.id),
        )

        return values

    folder_id = fields.Many2one(
        comodel_name="document.document",
        required=True,
        domain=[("type", "=", "folder"), ("shortcut_document_id", "=", False)],
    )
    ai_sort_prompt = fields.Html(string="AI Folder Sort Prompt")

    ai_tool_ids = fields.Many2many(
        comodel_name="ir.actions.server",
        string="Additional Tools",
        domain="[('id', 'in', allowed_tools_ids)]",
    )

    allowed_tools_ids = fields.Many2many(
        comodel_name="ir.actions.server",
        compute="_compute_allowed_tools_ids",
    )

    model = fields.Char(compute="_compute_ui_fields")
    relation = fields.Char(compute="_compute_ui_fields")
    is_ai_sort_prompt_set = fields.Boolean(
        string="Is Prompt Set",
        compute="_compute_is_prompt_set",
    )

    def _compute_ui_fields(self) -> None:
        self.model = "document.document"
        self.relation = "document.document"

    @api.depends("ai_sort_prompt")
    def _compute_is_prompt_set(self) -> None:
        for record in self:
            record.is_ai_sort_prompt_set = not is_html_empty(
                record.folder_id.ai_sort_prompt
            )

    @api.depends("folder_id")
    def _compute_allowed_tools_ids(self) -> None:
        documents_tools = self.env["ir.actions.server"].search(
            [
                ("model_id.model", "=", "document.document"),
                ("usage", "in", ["documents_embedded", "ir_actions_server"]),
            ]
        )
        documents_tools = documents_tools.filtered(lambda d: d.ai_tool_is_candidate)
        self.allowed_tools_ids = documents_tools

    def action_setup_folder(self) -> None:
        _debug.lifecycle(
            "autosort_configured", folder=self.folder_id, tools=self.ai_tool_ids
        )
        self.folder_id.ai_sort_prompt = self.ai_sort_prompt
        self.folder_id._ai_setup_sort_actions(self.ai_tool_ids.ids)

    def action_delete(self):
        _debug.lifecycle("autosort_removed", folder=self.folder_id)
        self.folder_id.ai_sort_prompt = False
        self.folder_id._ai_setup_sort_actions(self.ai_tool_ids.ids)

    def _get_folder_actions(self, folder):
        embedded_server_actions = (
            self.env["document.document"]
            ._get_folder_embedded_actions(folder.ids)
            .get(folder.id)
        )
        if not embedded_server_actions:
            _debug.logic("sort_tools_empty", reason="no_embedded_action", folder=folder)
            return self.env["ir.actions.server"]

        tool_actions = embedded_server_actions.action_id.filtered(
            lambda a: a.type == "ir.actions.server"
        )
        tool_actions = self.env["ir.actions.server"].browse(tool_actions.ids)
        return tool_actions.filtered("ai_tool_is_candidate").filtered("use_in_ai")
