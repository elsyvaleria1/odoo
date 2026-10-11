import logging

from odoo import api, fields, models
from odoo.db.errors import PG_RETRY_EXCEPTIONS
from odoo.exceptions import ValidationError
from odoo.tools.authority_keys import declare_authority_keys
from odoo.tools.date_utils import time_unit_selection

from odoo.addons.base.models.mixin_catalog import name_uniq_index

declare_authority_keys("date_range", "bypass_company_validation")

_logger = logging.getLogger(__name__)

UNIT_SELECTION = time_unit_selection("day", "week", "month", "year")


class DateRangeType(models.Model):

    _name = "date.range.type"
    _description = "Date Range Type"
    _order = "name,id"

    name = fields.Char(
        translate=True,
        required=True,
    )
    allow_overlap = fields.Boolean(
        default=False,
        help="If set, date ranges of this type are allowed to overlap each "
        "other. Leave unset to require them to be disjoint.",
    )
    active = fields.Boolean(
        default=True,
        help="The active field allows you to hide the date range type without removing it.",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company.id,
        index=True,
    )
    date_range_ids = fields.One2many(
        comodel_name="date.range",
        inverse_name="type_id",
        string="Ranges",
    )
    date_ranges_exist = fields.Boolean(compute="_compute_date_ranges_exist")

    name_expr = fields.Text(
        string="Range name expression",
        help="Evaluated expression. E.g. "
        "\"'FY%s' % date_start.strftime('%Y%m%d')\"\nYou can "
        "use the Date types 'date_end' and 'date_start', as well as "
        "the 'index' variable.",
    )
    range_name_preview = fields.Char(compute="_compute_range_name_preview")
    name_prefix = fields.Char(
        string="Range name prefix",
        compute="_compute_name_prefix",
        store=True,
        readonly=False,
    )
    duration_count = fields.Integer(string="Duration")
    duration_unit = fields.Selection(selection=UNIT_SELECTION)
    autogeneration_date_start = fields.Date(
        string="Autogeneration Start Date",
        help="Only applies when there are no date ranges of this type yet",
    )
    autogeneration_count = fields.Integer()
    autogeneration_unit = fields.Selection(selection=UNIT_SELECTION)

    _name_src_uniq = name_uniq_index(
        "company_id",
        nulls_distinct=True,
        message="A date range type must be unique per Company",
    )

    @api.constrains(
        "autogeneration_date_start",
        "autogeneration_count",
        "duration_count",
        "duration_unit",
    )
    def _check_autogeneration_settings(self) -> None:
        for record in self:
            if not record.autogeneration_count:
                continue
            if not record.autogeneration_date_start:
                raise ValidationError(
                    self.env._(
                        "Autogeneration start date is required when autogeneration count is set for type '%s'"
                    )
                    % record.name
                )
            if record.autogeneration_count < 1:
                raise ValidationError(
                    self.env._("Autogeneration count must be positive for type '%s'")
                    % record.name
                )
            if not record.duration_count or record.duration_count < 1:
                raise ValidationError(
                    self.env._(
                        "Duration count must be positive when autogeneration is enabled for type '%s'"
                    )
                    % record.name
                )
            if not record.duration_unit:
                raise ValidationError(
                    self.env._(
                        "Unit of time must be set when autogeneration is enabled for type '%s'"
                    )
                    % record.name
                )

    @api.constrains("company_id")
    def _check_company_id(self) -> None:
        if self.env.context.get("bypass_company_validation", False):
            return
        for rec in self.sudo():
            if not rec.company_id:
                continue
            foreign = rec.date_range_ids.filtered_domain(
                [("company_id", "!=", False), ("company_id", "!=", rec.company_id.id)]
            )
            if foreign:
                raise ValidationError(
                    self.env._(
                        "You cannot change the company, as this Date Range Type is assigned to Date Range '%s'."
                    )
                    % foreign[:1].display_name
                )

    @api.depends(
        "name_expr",
        "name_prefix",
        "duration_count",
        "duration_unit",
        "autogeneration_date_start",
        "autogeneration_count",
        "autogeneration_unit",
    )
    def _compute_range_name_preview(self) -> None:
        generator = self.env["wizard.date.range.create"]
        for dr_type in self:
            has_horizon = bool(
                dr_type.autogeneration_date_start
                and dr_type.autogeneration_count
                and dr_type.autogeneration_unit
            )
            if not (dr_type.name_expr or dr_type.name_prefix) or not has_horizon:
                dr_type.range_name_preview = False
                continue
            dr_type.range_name_preview = generator.new(
                {"type_id": dr_type.id, "count": 1}
            ).range_name_preview

    @api.depends("date_range_ids")
    def _compute_date_ranges_exist(self) -> None:
        for dr_type in self:
            dr_type.date_ranges_exist = bool(dr_type.date_range_ids)

    @api.depends("name_expr")
    def _compute_name_prefix(self) -> None:
        for range_type in self:
            if range_type.name_expr and range_type.name_prefix:
                range_type.name_prefix = False

    def write(self, vals):
        res = super().write(vals)
        if vals.get("active") is False:
            ranges = (
                self.env["date.range"]
                .with_context(active_test=False)
                .search([("type_id", "in", self.ids), ("active", "=", True)])
            )
            ranges.write({"active": False})
        return res

    @api.model
    def autogenerate_ranges(self) -> None:
        types = self.search(
            [
                ("autogeneration_count", ">", 0),
                ("autogeneration_unit", "!=", False),
                ("duration_count", ">", 0),
                ("duration_unit", "!=", False),
            ]
        )
        for dr_type in types:
            try:
                with self.env.cr.savepoint():
                    wizard = self.env["wizard.date.range.create"].new(
                        {"type_id": dr_type.id}
                    )
                    if not wizard.date_end:
                        continue
                    wizard.action_apply(batch=True)
            except PG_RETRY_EXCEPTIONS:
                raise
            except Exception as error:
                _logger.warning(
                    "Error autogenerating ranges for date range type %s: %s",
                    dr_type.name,
                    error,
                    exc_info=True,
                )
