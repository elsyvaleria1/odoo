from odoo import api, fields, models
from odoo.libs.json import loads as json_loads


class IrActionsServer(models.Model):
    _inherit = "ir.actions.server"

    conversation_enabled = fields.Boolean(
        string="Offer in conversations",
        help="Let the conversation analyst propose this tool as an action",
    )
    conversation_key = fields.Char(
        string="Conversation tool key",
        help="Stable identifier the analyst uses to name this tool, e.g. create_task",
    )
    conversation_examples = fields.Text(
        string="Typical phrases",
        help="What people say when they mean this action; guides the analyst",
    )

    _conversation_key_unique = models.Constraint(
        "UNIQUE(conversation_key)", "Conversation tool keys must be unique."
    )

    @api.model
    def _conversation_catalog(self):
        tools = self.sudo().search(
            [
                ("use_in_ai", "=", True),
                ("conversation_enabled", "=", True),
                ("conversation_key", "!=", False),
                ("model_id.model", "=", "conversation.conversation"),
            ],
            order="conversation_key",
        )
        catalog = []
        for tool in tools:
            try:
                schema = json_loads(tool.ai_tool_schema) if tool.ai_tool_schema else {}
            except ValueError:
                schema = {}
            catalog.append(
                {
                    "key": tool.conversation_key,
                    "record": tool,
                    "description": tool.ai_tool_description or tool.name,
                    "schema": schema,
                    "examples": tool.conversation_examples or "",
                }
            )
        return catalog
