from odoo import api, fields, models


class TelegramBot(models.Model):
    _inherit = "telegram.bot"

    has_solicitar_command = fields.Boolean(
        compute="_compute_has_solicitar_command",
        store=True,
        help="Technical field: whether the /solicitar command is enabled for "
        "this bot. Gates the Smart Approval configuration page so it only shows "
        "on bots that actually run the intake flow.",
    )
    smart_approval_ai_enabled = fields.Boolean(
        string="Enable AI for /solicitar wizard",
        default=False,
        help="When enabled, the /solicitar wizard handled by this bot calls the "
        "configured AI vendor to classify the request into an approval.category "
        "and extract fields (amount, partner, quantity) from natural language "
        "and voice. Disable to fall back to a manual category picker (no "
        "external API call).",
    )
    smart_approval_ai_provider_id = fields.Many2one(
        comodel_name="integration.ml.provider",
        string="Approval AI Provider",
        default=lambda self: self.env.ref(
            "integration_machine_learning.ai_provider_groq", raise_if_not_found=False
        ),
        domain="[('service_ids.operation', '=', 'chat')]",
        ondelete="restrict",
        help="Which vendor answers the classification call. The API key comes "
        "from the company's connection to that vendor's service, so swapping "
        "vendor is a configuration change. Not every vendor can transcribe voice "
        "notes: the form warns when the selected one cannot.",
    )
    smart_approval_ai_model_id = fields.Many2one(
        comodel_name="integration.ml.model",
        string="Approval AI Model",
        compute="_compute_smart_approval_ai_model_id",
        store=True,
        readonly=False,
        domain="[('provider_id', '=', smart_approval_ai_provider_id), "
        "('kind', '=', 'chat')]",
        ondelete="set null",
        help="Optional model override. Leave empty to use the vendor default. "
        "Set it when a vendor retires the shipped default, which happens fast "
        "on some of them.",
    )

    @api.depends("command_ids")
    def _compute_has_solicitar_command(self) -> None:
        for bot in self:
            bot.has_solicitar_command = "/solicitar" in bot.command_ids.mapped("name")

    @api.depends("smart_approval_ai_provider_id")
    def _compute_smart_approval_ai_model_id(self) -> None:
        for bot in self:
            model = bot.smart_approval_ai_model_id
            if model and model.provider_id != bot.smart_approval_ai_provider_id:
                bot.smart_approval_ai_model_id = False
