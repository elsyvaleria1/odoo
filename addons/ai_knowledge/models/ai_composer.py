from odoo import fields, models


class AIComposer(models.Model):
    _name = "ai.composer"
    _inherit = ["ai.composer"]

    interface_key = fields.Selection(
        selection_add=[("html_field_knowledge", "Write a new Knowledge article")],
        ondelete={"html_field_knowledge": "cascade"},
    )
