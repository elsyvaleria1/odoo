from odoo import api, fields, models
from odoo.exceptions import UserError

INTERFACE_KEYS = [
    ("html_field_record", "Write in an HTML field"),
    ("mail_composer", "Write an email"),
    ("html_field_text_select", "Rewrite content"),
    ("chatter_ai_button", "Get help on a record"),
    ("html_prompt_shortcut", "Convert a prompt in an email"),
    ("systray_ai_button", "Ask AI for help"),
]


class AIComposer(models.Model):
    _name = "ai.composer"
    _description = "AI model configurations (system prompts) for text drafting."

    def _get_default_agent(self):
        return self.env["ir.model.data"]._xmlid_to_res_id("ai.ai_default_agent")

    name = fields.Char(
        string="Rule Name",
        required=True,
        help="The identifier for the interface component to agent rule",
    )
    interface_key = fields.Selection(
        selection=INTERFACE_KEYS,
        string="Action",
        required=True,
    )
    focused_models = fields.Many2many(
        comodel_name="ir.model",
        string="Models",
    )
    ai_agent = fields.Many2one(
        comodel_name="ai.agent",
        string="Agent",
        default=lambda self: self._get_default_agent(),
    )
    default_prompt = fields.Text(string="Instructions")
    is_system_default = fields.Boolean(
        string="Is the rule a system default or user created",
        default=False,
        copy=False,
        readonly=True,
    )
    available_prompts = fields.One2many(
        comodel_name="ai.prompt.button",
        inverse_name="composer_id",
        string="Available User Prompts",
    )

    @api.ondelete(at_uninstall=False)
    def _unlink_except_default_rules(self) -> None:
        if any(rule.is_system_default for rule in self):
            raise UserError(self.env._("System default prompts cannot be removed."))

    def copy_data(self, default=None):
        default = dict(default or {})
        vals_list = super().copy_data(default=default)
        if "name" not in default:
            for composer, vals in zip(self, vals_list, strict=True):
                vals["name"] = self.env._("%s (copy)", composer.name)
        return vals_list
