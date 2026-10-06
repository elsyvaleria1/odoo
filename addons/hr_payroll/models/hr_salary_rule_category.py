from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class HrSalaryRuleCategory(models.Model):
    _name = "hr.salary.rule.category"
    _description = "Salary Rule Category"

    name = fields.Char(
        translate=True,
        required=True,
    )
    code = fields.Char(required=True)
    parent_id = fields.Many2one(
        comodel_name="hr.salary.rule.category",
        index=True,
        domain="['|', ('country_id', '=', False), ('country_id', '=', country_id)]",
        help="Linking a salary category to its parent is used only for the reporting purpose.",
    )
    children_ids = fields.One2many(
        comodel_name="hr.salary.rule.category",
        inverse_name="parent_id",
    )
    note = fields.Html(string="Description")
    country_id = fields.Many2one(
        comodel_name="res.country",
        default=lambda self: self.env.company.country_id,
        domain=lambda self: [("id", "in", self.env.companies.country_id.ids)],
    )

    @api.constrains("parent_id")
    def _check_parent_id(self) -> None:
        if self._has_cycle():
            raise ValidationError(
                self.env._(
                    "Error! You cannot create recursive hierarchy of Salary Rule Category."
                )
            )

    @api.constrains("country_id")
    def _check_rule_category_country(self) -> None:
        for category in self:
            if category.country_id and self.env["hr.salary.rule"].sudo().search_count(
                [
                    ("category_id", "=", category.id),
                    ("country_id", "!=", category.country_id.id),
                ],
                limit=1,
            ):
                raise UserError(
                    self.env._(
                        "You cannot change the country of category %s as it is used in existing Salary Rules",
                        category.name,
                    )
                )

    @api.ondelete(at_uninstall=False)
    def _unlink_if_not_used_in_salary_rule(self) -> None:
        if self.env["hr.salary.rule"].search_count(
            [("category_id", "in", self.ids)], limit=1
        ):
            raise UserError(
                self.env._(
                    "You cannot delete a category currently used in a salary rule."
                )
            )

    def _get_salary_rule_category_sum(self, localdict, amount):
        self.check_singleton()
        if self.parent_id:
            localdict = self.parent_id._get_salary_rule_category_sum(localdict, amount)
        localdict["categories"][self.code] += amount
        return localdict

    def copy_data(self, default=None):
        vals_list = super().copy_data(default)
        for category, vals in zip(self, vals_list, strict=True):
            vals["name"] = self.env._("%s (copy)", category.name)
        return vals_list

    def copy_translations(self, new, excluded=()) -> None:
        super().copy_translations(new, excluded=(*excluded, "name"))
        self._copy_translations_of_renamed_field(
            new, "name", lambda record, term: record.env._("%s (copy)", term)
        )
