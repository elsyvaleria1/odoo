from odoo import fields, models


class LossReason(models.Model):
    _name = "loss.reason"
    _description = "Why a deal did not go ahead"
    _order = "sequence, id"

    name = fields.Char(
        string="Reason",
        translate=True,
        required=True,
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        comodel_name="res.company",
        index="btree_not_null",
        help="Leave empty to share the reason between companies.",
    )
    scope = fields.Selection(
        selection=[
            ("sale", "Sales"),
            ("purchase", "Purchases"),
            ("task", "Tasks"),
        ],
        help="Leave empty to offer the reason everywhere a document can be lost.",
    )

    def _domain_for_scope(self, scope) -> list:
        return [("scope", "in", [False, scope])]
