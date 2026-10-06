from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .credit_aging import AGING_SELECTION


class CreditProvisionMatrix(models.Model):
    _name = "credit.provision.matrix"
    _inherit = ["mixin.catalog"]
    _description = "Expected Credit Loss Matrix"
    _check_company_auto = True

    company_id = fields.Many2one(
        comodel_name="res.company",
        help="Empty makes the matrix available to every company.",
    )
    line_ids = fields.One2many(
        comodel_name="credit.provision.matrix.line",
        inverse_name="matrix_id",
    )

    @api.model
    def _for_company(self, company):
        config = self.env["credit.config"].sudo()._for(company)
        if config.provision_matrix_id:
            return config.provision_matrix_id
        return self.search(
            [("company_id", "in", [False, company.id])],
            order="company_id desc, id",
            limit=1,
        )

    def _rate_for(self, grade, bucket):
        self.check_singleton()
        specific = self.line_ids.filtered(
            lambda l: l.bucket == bucket and l.grade_id == grade
        )
        if specific:
            return specific[:1].rate
        generic = self.line_ids.filtered(
            lambda l: l.bucket == bucket and not l.grade_id
        )
        if generic:
            return generic[:1].rate
        return grade.expected_loss_rate if grade else 0.0


class CreditProvisionMatrixLine(models.Model):
    _name = "credit.provision.matrix.line"
    _description = "Expected Credit Loss Matrix Line"
    _order = "matrix_id, grade_id, bucket, id"

    _unique_cell = models.UniqueIndex(
        "(matrix_id, grade_id, bucket) NULLS NOT DISTINCT",
        "One rate per matrix, grade and aging bucket.",
    )

    matrix_id = fields.Many2one(
        comodel_name="credit.provision.matrix",
        required=True,
        ondelete="cascade",
    )
    grade_id = fields.Many2one(
        comodel_name="credit.grade",
        help="Empty applies to every grade the matrix names no specific rate for.",
    )
    bucket = fields.Selection(
        selection=AGING_SELECTION,
        required=True,
    )
    rate = fields.Float(
        digits=(5, 2),
        required=True,
        help="Expected loss as a percent of the open amount in this bucket.",
    )

    @api.constrains("rate")
    def _check_rate(self) -> None:
        if any(not 0 <= line.rate <= 100 for line in self):
            raise ValidationError(self.env._("A loss rate lies between 0 and 100."))
