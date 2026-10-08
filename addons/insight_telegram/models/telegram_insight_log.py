from odoo import fields, models


class TelegramInsightLog(models.Model):
    """One question asked to a Telegram questions bot, and what it answered."""

    _name = "telegram.insight.log"
    _description = "Telegram Question"
    _order = "create_date desc, id desc"

    bot_id = fields.Many2one(
        comodel_name="telegram.bot", required=True, index=True, ondelete="cascade"
    )
    company_id = fields.Many2one(
        related="bot_id.company_id",
        store=True,
        index=True,
        help="The company the bot speaks for: where the question belongs.",
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Asked By",
        required=True,
        index=True,
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
        help="Whether a report answered. The unanswered questions are the ones "
        "the catalogue should learn next.",
    )
    answer = fields.Text()
