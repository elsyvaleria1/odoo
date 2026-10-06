from odoo import api, fields, models
from odoo.exceptions import ValidationError


class CreditGradeRule(models.Model):
    _name = "credit.grade.rule"
    _description = "Documents a Credit Grade Requires"

    _unique_rule_per_grade = models.UniqueIndex(
        "(grade_id, document_type_id, is_guarantor) NULLS NOT DISTINCT",
        "Only one rule per (grade, document type, guarantor) combination.",
    )

    name = fields.Char(required=True)
    document_type_id = fields.Many2one(
        comodel_name="document.type",
        required=True,
    )
    is_guarantor = fields.Boolean(
        help="Indicates if this rule is for guarantor documents"
    )
    min_quantity = fields.Integer(
        default=0,
        help="Minimum number of required documents (0 means not required)",
    )
    max_quantity = fields.Integer(
        default=0,
        help="Maximum number of allowed documents (0 means unlimited)",
    )
    grade_id = fields.Many2one(
        comodel_name="credit.grade",
        ondelete="cascade",
    )

    def _sync_profiles(self) -> None:
        profiles = (
            self.env["credit.profile"]
            .sudo()
            .search([("grade_id", "in", self.grade_id.ids)])
        )
        profiles.modified(["grade_id"])
        profiles._sync_partner_credit_limit()

    @api.model_create_multi
    def create(self, vals_list):
        rules = super().create(vals_list)
        rules._sync_profiles()
        return rules

    def write(self, vals):
        result = super().write(vals)
        self._sync_profiles()
        return result

    def unlink(self):
        grades = self.grade_id
        result = super().unlink()
        profiles = (
            self.env["credit.profile"].sudo().search([("grade_id", "in", grades.ids)])
        )
        profiles.modified(["grade_id"])
        profiles._sync_partner_credit_limit()
        return result

    @api.constrains("min_quantity", "max_quantity")
    def _check_quantity_constraints(self) -> None:
        for rule in self:
            if rule.max_quantity > 0 and rule.min_quantity > rule.max_quantity:
                raise ValidationError(
                    self.env._(
                        "Minimum quantity cannot be greater than maximum quantity"
                    )
                )
