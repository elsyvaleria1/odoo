from odoo import fields, models


class KnowledgeArticleStage(models.Model):
    _name = "knowledge.article.stage"
    _description = "Knowledge Stage"
    _order = "parent_id, sequence, id"

    name = fields.Char(
        translate=True,
        required=True,
    )
    sequence = fields.Integer(default=1)
    fold = fields.Boolean(string="Folded in kanban view")
    parent_id = fields.Many2one(
        comodel_name="knowledge.article",
        string="Owner Article",
        required=True,
        ondelete="cascade",
        help="Stages are shared among a common parent and its children articles.",
    )
