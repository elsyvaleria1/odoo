from odoo import fields, models


class TelegramInsightLog(models.Model):
    _name = "telegram.insight.log"
    _description = "Telegram Question"
    _order = "create_date desc, id desc"

    bot_id = fields.Many2one(
        comodel_name="telegram.bot",
        index=True,
        required=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        related="bot_id.company_id",
        help="The company the bot speaks for: where the question belongs.",
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Asked By",
        index=True,
        required=True,
        ondelete="cascade",
    )
    question = fields.Text(required=True)
    query = fields.Char(
        help="The report the question was routed to; empty when none answers it.",
    )
    interpretation = fields.Json(
        help="The report and parameters the model extracted from the question.",
    )
    answered = fields.Boolean(
        index=True,
        help="Whether the bot answered: a report, the AI, a document or the help. "
        "The unanswered questions are the ones the catalogue should learn next.",
    )
    answer = fields.Text()
