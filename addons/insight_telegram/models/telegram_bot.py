from odoo import api, fields, models


class TelegramBot(models.Model):
    _inherit = "telegram.bot"

    insight_ai_enabled = fields.Boolean(
        string="Answer Odoo Questions",
        help="When enabled, this bot answers questions about Odoo data asked "
        "by members of the 'Ask Odoo through Telegram' group, from a catalogue "
        "of read-only reports. It can never write.",
    )
    insight_ai_provider_id = fields.Many2one(
        comodel_name="integration.ml.provider",
        string="Questions AI Provider",
        default=lambda self: self.env.ref(
            "integration_machine_learning.ai_provider_google",
            raise_if_not_found=False,
        ),
        domain="[('service_ids.operation', '=', 'chat')]",
        ondelete="restrict",
        help="The vendor that reads each question and picks the report that "
        "answers it. One short call per question: a fast, inexpensive model is "
        "enough, since the figures come from the reports, never from it.",
    )
    insight_ai_model_id = fields.Many2one(
        comodel_name="integration.ml.model",
        string="Questions AI Model",
        compute="_compute_insight_ai_model_id",
        store=True,
        readonly=False,
        domain="[('provider_id', '=', insight_ai_provider_id), ('kind', '=', 'chat')]",
        ondelete="set null",
        help="Leave empty to use the vendor default.",
    )
    insight_reader_user_id = fields.Many2one(
        comodel_name="res.users",
        string="Questions Reader",
        default=lambda self: self.env.ref(
            "insight_telegram.user_reader", raise_if_not_found=False
        ),
        ondelete="restrict",
        help="The user the questions are read as, on a read-only transaction "
        "that sees every company: its language and timezone shape the answer, "
        "never what it may read.",
    )

    @api.depends("insight_ai_provider_id")
    def _compute_insight_ai_model_id(self) -> None:
        for bot in self:
            model = bot.insight_ai_model_id
            if model and model.provider_id != bot.insight_ai_provider_id:
                bot.insight_ai_model_id = False
