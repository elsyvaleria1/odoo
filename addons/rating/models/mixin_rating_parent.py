from collections import defaultdict
from datetime import timedelta

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.tools import DOMAIN_PREDICATES

from odoo.addons.rating.models import rating_data


class MixinRatingParent(models.AbstractModel):
    _name = "mixin.rating.parent"
    _description = "Rating Parent Mixin"
    _rating_satisfaction_days = False

    rating_child_ids = fields.One2many(
        comodel_name="rating.rating",
        inverse_name="parent_res_id",
        string="Child Ratings",
        domain=lambda self: [
            ("parent_res_model", "=", self._get_reference_model_name())
        ],
        bypass_search_access=True,
        classification="base.internal",
    )
    rating_child_percentage_satisfaction = fields.Integer(
        string="Rating Satisfaction",
        compute="_compute_rating_child_stats",
        compute_sudo=True,
        store=False,
        help="Percentage of happy ratings",
    )
    rating_child_count = fields.Integer(
        string="# Ratings",
        compute="_compute_rating_child_stats",
        compute_sudo=True,
    )
    rating_child_avg = fields.Float(
        string="Average Rating",
        compute="_compute_rating_child_stats",
        search="_search_rating_child_avg",
        compute_sudo=True,
        classification="base.internal",
    )
    rating_child_avg_percentage = fields.Float(
        string="Average Rating (%)",
        compute="_compute_rating_child_avg_percentage",
        compute_sudo=True,
        classification="base.internal",
    )

    def write(self, vals):
        result = super().write(vals)
        if not self._display_name_field_names().isdisjoint(vals):
            ratings = (
                self.env["rating.rating"]
                .sudo()
                .search(
                    [
                        ("parent_res_model", "=", self._name),
                        ("parent_res_id", "in", self.ids),
                    ]
                )
            )
            if ratings:
                self.env.add_to_compute(
                    self.env["rating.rating"]._fields["parent_res_name"], ratings
                )
        return result

    @api.depends("rating_child_ids.rating", "rating_child_ids.consumed")
    def _compute_rating_child_stats(self) -> None:
        domain = [
            ("parent_res_model", "=", self._name),
            ("parent_res_id", "in", self.ids),
            ("rating", ">=", rating_data.RATING_LIMIT_MIN),
            ("consumed", "=", True),
        ]
        if self._rating_satisfaction_days:
            domain += [
                (
                    "write_date",
                    ">=",
                    fields.Datetime.to_string(
                        fields.Datetime.now()
                        - timedelta(days=self._rating_satisfaction_days)
                    ),
                )
            ]
        data = self.env["rating.rating"]._read_group(
            domain, ["parent_res_id", "rating"], ["__count"]
        )

        default_grades = {"great": 0, "okay": 0, "bad": 0}
        grades_per_parent = {
            parent_id: dict(default_grades) for parent_id in self.ids
        }
        rating_scores_per_parent = defaultdict(
            int
        )
        for parent_id, rating, count in data:
            grade = rating_data._rating_to_grade(rating)
            grades_per_parent[parent_id][grade] += count
            rating_scores_per_parent[parent_id] += rating * count

        for record in self:
            repartition = grades_per_parent.get(record.id, default_grades)
            rating_count = sum(repartition.values())
            record.rating_child_count = rating_count
            record.rating_child_percentage_satisfaction = (
                repartition["great"] * 100 / rating_count if rating_count else -1
            )
            record.rating_child_avg = (
                rating_scores_per_parent[record.id] / rating_count
                if rating_count
                else 0
            )

    @api.depends("rating_child_avg")
    def _compute_rating_child_avg_percentage(self) -> None:
        for record in self:
            record.rating_child_avg_percentage = record.rating_child_avg / 5

    def _search_rating_child_avg(self, operator, value):
        if operator not in DOMAIN_PREDICATES:
            return NotImplemented
        domain = Domain(
            [
                ("parent_res_model", "=", self._name),
                ("consumed", "=", True),
                ("rating", ">=", rating_data.RATING_LIMIT_MIN),
            ]
        )
        if self._rating_satisfaction_days:
            min_date = fields.Datetime.now() - timedelta(
                days=self._rating_satisfaction_days
            )
            domain &= Domain("write_date", ">=", fields.Datetime.to_string(min_date))
        rating_read_group = (
            self.env["rating.rating"]
            .sudo()
            ._read_group(domain, ["parent_res_id"], ["rating:avg"])
        )
        parent_res_ids = [
            parent_res_id
            for parent_res_id, rating_avg in rating_read_group
            if rating_data._rating_avg_satisfies(operator, rating_avg, value)
        ]
        return [("id", "in", parent_res_ids)]
