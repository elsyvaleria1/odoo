from lxml import etree

from odoo import api, fields, models
from odoo.fields import Domain

from odoo.addons.base.models.ir_ui_view_base import attach_ir

_NEGATIVE_OPERATORS = frozenset(
    (
        "!=",
        "<>",
        "not in",
        "not like",
        "not ilike",
        "not =like",
        "not =ilike",
        "not any",
        "not any!",
    )
)


class MixinDateRangeSearch(models.AbstractModel):

    _name = "mixin.date.range.search"
    _description = "Mixin class to add a Many2one style period search field"
    _date_range_search_field = "date"

    date_range_search_id = fields.Many2one(
        comodel_name="date.range",
        string="Filter by period (technical field)",
        compute="_compute_date_range_search_id",
        search="_search_date_range_search_id",
    )

    def _compute_date_range_search_id(self) -> None:
        for record in self:
            record.date_range_search_id = False

    @api.model
    def _is_negative_operator(self, operator) -> bool:
        return operator in _NEGATIVE_OPERATORS

    @api.model
    def _search_date_range_search_id(self, operator, value):
        if (
            not isinstance(value, (str, bytes))
            and hasattr(value, "__iter__")
            and not isinstance(value, bool)
        ):
            value_list = list(value)
            if len(value_list) == 1 and isinstance(value_list[0], bool):
                value = value_list[0]

        if not value:
            if self._is_negative_operator(operator):
                return Domain.TRUE
            return Domain.FALSE
        if value is True:
            if self._is_negative_operator(operator):
                return Domain.FALSE
            return Domain.TRUE
        ranges = self.env["date.range"]
        if isinstance(value, str):
            ranges = self.env["date.range"].search([("name", operator, value)])
        else:
            if isinstance(value, int) and not isinstance(value, bool):
                value = [value]
            sub_op = "not in" if self._is_negative_operator(operator) else "in"
            ranges = self.env["date.range"].search([("id", sub_op, value)])
        if not ranges:
            return Domain.FALSE
        field = self._date_range_search_field
        return Domain.OR(
            Domain(field, ">=", date_range.date_start)
            & Domain(field, "<=", date_range.date_end)
            for date_range in ranges
        )

    @api.model
    def get_view(self, view_id=None, view_type="form", **options):
        result = super().get_view(view_id=view_id, view_type=view_type, **options)
        if view_type != "search":
            return result
        root = etree.fromstring(result["arch"])
        if root.xpath("//field[@name='date_range_search_id']"):
            return result
        separator = etree.Element("separator")
        field = etree.Element(
            "field",
            attrib={
                "name": "date_range_search_id",
                "string": self.env._("Period"),
            },
        )
        groups = root.xpath("/search/group")
        if groups:
            groups[0].addprevious(separator)
            groups[0].addprevious(field)
        else:
            search = root.xpath("/search")
            search[0].append(separator)
            search[0].append(field)
        result["arch"] = etree.tostring(root, encoding="unicode")
        return attach_ir(result)

    @api.model
    def get_views(self, views, options=None):
        result = super().get_views(views, options=options)
        if "date_range_search_id" in result["models"][self._name]["fields"]:
            result["models"][self._name]["fields"]["date_range_search_id"]["string"] = (
                self.env._("Period")
            )
        return result
