from odoo import fields, models


class GamificationChallengeLine(models.Model):

    _name = "gamification.challenge.line"
    _description = "Gamification generic goal for challenge"
    _order = "sequence, id"

    challenge_id = fields.Many2one(
        comodel_name="gamification.challenge",
        index=True,
        required=True,
        ondelete="cascade",
    )
    definition_id = fields.Many2one(
        comodel_name="gamification.goal.definition",
        string="Goal Definition",
        required=True,
        ondelete="cascade",
    )

    sequence = fields.Integer(default=1)
    target_goal = fields.Float(
        string="Target Value to Reach",
        required=True,
    )

    name = fields.Char(
        related="definition_id.name",
        string="Name",
        readonly=True,
    )
    condition = fields.Selection(
        related="definition_id.condition",
        string="Condition",
        readonly=True,
    )
    definition_suffix = fields.Char(
        related="definition_id.suffix",
        string="Unit",
        readonly=True,
    )
    definition_monetary = fields.Boolean(
        related="definition_id.monetary",
        string="Monetary",
        readonly=True,
    )
    definition_full_suffix = fields.Char(
        related="definition_id.full_suffix",
        string="Suffix",
        readonly=True,
    )
