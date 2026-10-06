import re

from odoo import api, fields, models
from odoo.exceptions import ValidationError

GRADE_KINDS = [
    ("entry", "Cash Only"),
    ("performing", "Performing"),
    ("watch", "Watch"),
    ("default", "Default"),
]


class CreditGrade(models.Model):
    _name = "credit.grade"
    _inherit = ["mixin.score.scale"]
    _description = "Credit Grade"

    _score_host_model = "credit.profile"

    _code_uniq = models.UniqueIndex("(code)")

    code = fields.Char(
        compute="_compute_code",
        precompute=True,
        store=True,
        readonly=False,
        required=True,
    )
    description = fields.Text(translate=True)
    sequence = fields.Integer(
        default=10,
        help="Severity: a lower sequence is a better grade.",
    )
    kind = fields.Selection(
        selection=GRADE_KINDS,
        default="performing",
        required=True,
    )
    color = fields.Integer()
    min_value = fields.Float(
        string="Minimum Score",
        help="Lowest scorecard score that proposes this grade, inclusive.",
    )
    max_value = fields.Float(
        string="Maximum Score",
        help="Scorecard score from which the next grade starts, exclusive. 0 on "
        "the best grade leaves it open-ended, so a perfect score still "
        "proposes it. A grade with no range at all, like the entry grade, is "
        "never proposed by the scorecard.",
    )
    expected_loss_rate = fields.Float(
        digits=(5, 2),
        help="Expected credit loss, percent of exposure, for provisioning "
        "(NIF C-16 / IFRS 9).",
    )
    limit_pct_annual_purchases = fields.Float(
        digits=(5, 2),
        help="Suggested credit limit as a percent of the last twelve months of "
        "purchases.",
    )
    max_payment_term_days = fields.Integer(
        help="Longest payment term the grade allows. 0 means cash only.",
    )
    review_interval_months = fields.Integer(
        default=12,
        help="Months between periodic reviews of a profile in this grade.",
    )
    regulatory_code = fields.Char(
        help="Equivalent grade in the regulator's scale (CNBV: A-1 to E).",
    )
    rule_ids = fields.One2many(
        comodel_name="credit.grade.rule",
        inverse_name="grade_id",
    )
    profile_count = fields.Integer(compute="_compute_profile_count")

    @api.depends("name")
    def _compute_code(self) -> None:
        for grade in self:
            if grade.code:
                continue
            base = re.sub(r"[^a-z0-9]+", "_", (grade.name or "grade").lower()).strip(
                "_"
            )
            code = base or "grade"
            taken = set(self.search([("code", "=like", f"{code}%")]).mapped("code"))
            candidate, n = code, 2
            while candidate in taken:
                candidate, n = f"{code}_{n}", n + 1
            grade.code = candidate

    @api.depends()
    def _compute_profile_count(self) -> None:
        counts = dict(
            self.env["credit.profile"]._read_group(
                [("grade_id", "in", self.ids)], ["grade_id"], ["__count"]
            )
        )
        for grade in self:
            grade.profile_count = counts.get(grade, 0)

    def _is_band(self) -> bool:
        self.check_singleton()
        return self.kind != "entry" and bool(self.min_value or self.max_value)

    @api.constrains("min_value", "max_value")
    def _check_score_range(self) -> None:
        for grade in self:
            if grade.min_value > 100 or grade.max_value > 100:
                raise ValidationError(
                    self.env._("A grade's score range must lie within 0 and 100.")
                )

    def action_view_profiles(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Profiles in %s", self.name),
            "res_model": "credit.profile",
            "view_mode": "list,form",
            "domain": [("grade_id", "=", self.id)],
            "context": {"default_grade_id": self.id},
        }
