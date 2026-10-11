from collections import defaultdict

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.libs.numbers import float_round
from odoo.tools import DOMAIN_PREDICATES

from odoo.addons.rating.models import rating_data


class MixinRating(models.AbstractModel):

    _name = "mixin.rating"
    _description = "Rating Mixin"
    _inherit = ["mixin.mail.thread"]

    rating_last_value = fields.Float(
        compute="_compute_rating_last_value",
        compute_sudo=True,
        store=True,
        aggregator="avg",
        classification="base.internal",
    )
    rating_last_feedback = fields.Text(
        related="rating_ids.feedback",
        string="Rating Last Feedback",
        classification="base.internal",
    )
    rating_last_image = fields.Binary(
        related="rating_ids.rating_image",
        string="Rating Last Image",
        classification="base.internal",
    )
    rating_count = fields.Integer(
        string="Rating count",
        compute="_compute_rating_stats",
        compute_sudo=True,
    )
    rating_avg = fields.Float(
        string="Average Rating",
        compute="_compute_rating_stats",
        search="_search_rating_avg",
        compute_sudo=True,
        classification="base.internal",
    )
    rating_avg_text = fields.Selection(
        selection=rating_data.RATING_TEXT,
        compute="_compute_rating_avg_text",
        compute_sudo=True,
        classification="base.internal",
    )
    rating_percentage_satisfaction = fields.Float(
        string="Rating Satisfaction",
        compute="_compute_rating_percentage_satisfaction",
        compute_sudo=True,
    )
    rating_last_text = fields.Selection(
        related="rating_ids.rating_text",
        string="Rating Text",
        classification="base.internal",
    )

    @api.depends("rating_ids", "rating_ids.rating", "rating_ids.consumed")
    def _compute_rating_last_value(self) -> None:
        self.flush_model(["rating_ids"])
        self.env["rating.rating"].flush_model(
            ["res_model", "res_id", "consumed", "rating"]
        )
        if not self.ids:
            self.rating_last_value = 0
            return
        self.env.cr.execute(
            """
            SELECT
                array_agg(rating ORDER BY write_date DESC, id DESC) AS "ratings",
                res_id as res_id
            FROM "rating_rating"
            WHERE
                res_model = %s
            AND res_id = ANY(%s)
            AND consumed = true
            GROUP BY res_id""",
            [self._get_reference_model_name(), list(self.ids)],
        )
        read_group_raw = self.env.cr.dictfetchall()
        rating_by_res_id = {e["res_id"]: e["ratings"][0] for e in read_group_raw}
        for record in self:
            record.rating_last_value = rating_by_res_id.get(record.id, 0)

    @api.depends("rating_ids.res_id", "rating_ids.rating")
    def _compute_rating_stats(self) -> None:
        domain = self._get_domain_rating() & Domain(
            "rating", ">=", rating_data.RATING_LIMIT_MIN
        )
        read_group_res = self.env["rating.rating"]._read_group(
            domain, ["res_id"], aggregates=["__count", "rating:avg"]
        )
        mapping = {
            res_id: {"rating_count": count, "rating_avg": rating_avg}
            for res_id, count, rating_avg in read_group_res
        }
        for record in self:
            record.rating_count = mapping.get(record.id, {}).get("rating_count", 0)
            record.rating_avg = mapping.get(record.id, {}).get("rating_avg", 0)

    def _search_rating_avg(self, operator, value):
        if operator not in DOMAIN_PREDICATES:
            return NotImplemented
        rating_read_group = (
            self.env["rating.rating"]
            .sudo()
            ._read_group(
                [
                    ("res_model", "=", self._get_reference_model_name()),
                    ("consumed", "=", True),
                    ("rating", ">=", rating_data.RATING_LIMIT_MIN),
                ],
                ["res_id"],
                ["rating:avg"],
            )
        )
        res_ids = [
            res_id
            for res_id, rating_avg in rating_read_group
            if rating_data._rating_avg_satisfies(operator, rating_avg, value)
        ]
        return [("id", "in", res_ids)]

    @api.depends("rating_avg")
    def _compute_rating_avg_text(self) -> None:
        for record in self:
            record.rating_avg_text = rating_data._rating_avg_to_text(record.rating_avg)

    @api.depends("rating_ids.res_id", "rating_ids.rating")
    def _compute_rating_percentage_satisfaction(self) -> None:
        domain = self._get_domain_rating() & Domain(
            "rating", ">=", rating_data.RATING_LIMIT_MIN
        )
        read_group_res = self.env["rating.rating"]._read_group(
            domain, ["res_id", "rating"], aggregates=["__count"]
        )
        default_grades = {"great": 0, "okay": 0, "bad": 0}
        grades_per_record = {record_id: default_grades.copy() for record_id in self.ids}

        for record_id, rating, count in read_group_res:
            grade = rating_data._rating_to_grade(rating)
            grades_per_record[record_id][grade] += count

        for record in self:
            grade_repartition = grades_per_record.get(record.id, default_grades)
            grade_count = sum(grade_repartition.values())
            record.rating_percentage_satisfaction = (
                grade_repartition["great"] * 100 / grade_count if grade_count else -1
            )

    def write(self, vals):
        result = super().write(vals)
        records = self.sudo()
        if not self._display_name_field_names().isdisjoint(vals):
            self.env.add_to_compute(
                self.env["rating.rating"]._fields["res_name"], records.rating_ids
            )
        parent_field = self._rating_get_parent_field_name()
        if parent_field and parent_field in vals:
            for record in records:
                record.rating_ids.write({"parent_res_id": record[parent_field].id})
        return result

    def _rating_get_parent_field_name(self):
        return

    def _get_domain_rating(self, record_ids=None):
        return Domain(
            [
                ("res_model", "=", self._get_reference_model_name()),
                ("res_id", "in", self.ids if record_ids is None else record_ids),
                ("consumed", "=", True),
            ]
        )

    def _rating_get_repartition(self, add_stats=False, domain=None, record_ids=None):
        base_domain = self._get_domain_rating(record_ids=record_ids) & Domain(
            "rating", ">=", 1
        )
        if domain:
            base_domain &= Domain(domain)
        rg_data = self.env["rating.rating"]._read_group(
            base_domain, ["rating"], ["__count"]
        )
        values = dict.fromkeys(range(1, 6), 0)
        for rating, count in rg_data:
            rating_val_round = float_round(rating, precision_digits=1)
            values[rating_val_round] = values.get(rating_val_round, 0) + count
        if add_stats:
            rating_number = sum(values.values())
            return {
                "repartition": values,
                "avg": sum(float(key * values[key]) for key in values) / rating_number
                if rating_number > 0
                else 0,
                "total": sum(count for __, count in rg_data),
            }
        return values

    def rating_get_grades(self, domain=None, record_ids=None):
        data = self._rating_get_repartition(domain=domain, record_ids=record_ids)
        res = dict.fromkeys(["great", "okay", "bad"], 0)
        for key in data:
            grade = rating_data._rating_to_grade(key)
            res[grade] += data[key]
        return res

    def rating_get_stats(self, domain=None):
        data = self._rating_get_repartition(domain=domain, add_stats=True)
        result = {
            "avg": data["avg"],
            "total": data["total"],
            "percent": dict.fromkeys(range(1, 6), 0),
        }
        for rate in data["repartition"]:
            result["percent"][rate] = (
                (data["repartition"][rate] * 100) / data["total"]
                if data["total"] > 0
                else 0
            )
        return result

    def _rating_get_stats_per_record(self, domain=None):
        base_domain = self._get_domain_rating() & Domain("rating", ">=", 1)
        if domain:
            base_domain &= Domain(domain)
        rg_data = self.env["rating.rating"]._read_group(
            base_domain,
            groupby=["res_id", "rating"],
            aggregates=["__count"],
        )
        stats_per_record = defaultdict(
            lambda: {
                "total": 0,
                "weighted_sum": 0.0,
                "counts": defaultdict(int),
                "percent": {},
            }
        )
        for res_id, rating, count in rg_data:
            stats = stats_per_record[res_id]
            stats["total"] += count
            stats["weighted_sum"] += rating * count
            stats["counts"][int(rating)] += count
        for stats in stats_per_record.values():
            total = stats["total"]
            if total > 0:
                stats["avg"] = stats["weighted_sum"] / total
                stats["percent"] = {
                    rate: (stats["counts"].get(rate, 0) * 100) / total
                    for rate in range(1, 6)
                }
            else:
                stats["avg"] = 0
                stats["percent"] = dict.fromkeys(range(1, 6), 0.0)
            del stats["weighted_sum"]
            del stats["counts"]
        return stats_per_record

    @api.model
    def _allow_publish_rating_stats(self) -> bool:
        return False
