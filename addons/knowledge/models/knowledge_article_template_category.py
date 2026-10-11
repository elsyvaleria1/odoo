from odoo import fields, models


class KnowledgeArticleTemplateCategory(models.Model):

    _name = "knowledge.article.template.category"
    _description = "Article Template Category"
    _order = "sequence ASC, id ASC"

    name = fields.Char(
        string="Title",
        translate=True,
        required=True,
    )
    sequence = fields.Integer(
        string="Category Sequence",
        default=0,
        required=True,
        help="It determines the display order of the category",
    )
