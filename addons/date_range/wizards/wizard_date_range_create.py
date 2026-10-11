import datetime
import logging

import psycopg
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.date_utils import get_timedelta
from odoo.tools.safe_eval import safe_eval

from ..models.date_range_type import UNIT_SELECTION

_logger = logging.getLogger(__name__)


class WizardDateRangeCreate(models.TransientModel):

    _name = "wizard.date.range.create"
    _description = "Date Range Generator"

    name_expr = fields.Text(
        string="Range name expression",
        compute="_compute_name_expr",
        store=True,
        readonly=False,
        help="Evaluated expression. E.g. "
        "\"'FY%s' % date_start.strftime('%Y%m%d')\"\nYou can "
        "use the Date types 'date_end' and 'date_start', as well as "
        "the 'index' variable.",
    )
    name_prefix = fields.Char(
        string="Range name prefix",
        compute="_compute_name_prefix",
        store=True,
        readonly=False,
    )
    range_name_preview = fields.Char(compute="_compute_range_name_preview")
    date_start = fields.Date(
        string="Start date",
        compute="_compute_date_start",
        store=True,
        readonly=False,
    )
    date_end = fields.Date(
        string="End date",
        compute="_compute_date_end",
        store=True,
        readonly=False,
    )
    type_id = fields.Many2one(
        comodel_name="date.range.type",
        domain="['|', ('company_id', '=', company_id), ('company_id', '=', False)]",
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        compute="_compute_company_id",
        store=True,
        readonly=False,
    )
    duration_unit = fields.Selection(
        selection=UNIT_SELECTION,
        compute="_compute_duration_unit",
        store=True,
        readonly=False,
    )
    duration_count = fields.Integer(
        string="Duration",
        compute="_compute_duration_count",
        store=True,
        readonly=False,
    )
    count = fields.Integer(string="Number of ranges to generate")

    @api.constrains("company_id", "type_id")
    def _check_company_id_type_id(self) -> None:
        for rec in self.sudo():
            if (
                rec.company_id
                and rec.type_id.company_id
                and rec.company_id != rec.type_id.company_id
            ):
                raise ValidationError(
                    self.env._(
                        "The Company in the Date Range Generator and in Date Range Type must be the same."
                    )
                )

    @api.onchange("company_id")
    def _onchange_company_id(self):
        for wiz in self:
            if (
                wiz.company_id
                and wiz.type_id.company_id
                and wiz.type_id.company_id != wiz.company_id
            ):
                wiz.type_id = False

    @api.onchange("date_end")
    def onchange_date_end(self) -> None:
        for wiz in self:
            if wiz.date_end and wiz.count:
                wiz.count = 0

    @api.onchange("count")
    def onchange_count(self) -> None:
        for wiz in self:
            if wiz.count and wiz.date_end:
                wiz.date_end = False

    @api.onchange("name_expr")
    def onchange_name_expr(self) -> None:
        for wiz in self:
            if wiz.name_expr and wiz.name_prefix:
                wiz.name_prefix = False

    @api.depends("type_id")
    def _compute_company_id(self):
        for wiz in self:
            wiz.company_id = wiz.type_id.company_id or self.env.company

    @api.depends("type_id")
    def _compute_name_expr(self) -> None:
        for wiz in self:
            wiz.name_expr = wiz.type_id.name_expr or wiz.name_expr or False

    @api.depends("type_id")
    def _compute_name_prefix(self) -> None:
        for wiz in self:
            wiz.name_prefix = wiz.type_id.name_prefix or wiz.name_prefix or False

    @api.depends("type_id")
    def _compute_duration_count(self) -> None:
        for wiz in self:
            wiz.duration_count = wiz.type_id.duration_count or wiz.duration_count or 0

    @api.depends("type_id")
    def _compute_duration_unit(self) -> None:
        for wiz in self:
            wiz.duration_unit = wiz.type_id.duration_unit or wiz.duration_unit or False

    @api.depends("type_id")
    def _compute_date_start(self) -> None:
        types = self.type_id
        last_end = {}
        if types:
            last_end = {
                dr_type.id: date_end
                for dr_type, date_end in self.env["date.range"]._read_group(
                    [("type_id", "in", types.ids)],
                    groupby=["type_id"],
                    aggregates=["date_end:max"],
                )
            }
        for wiz in self:
            if not wiz.type_id:
                wiz.date_start = wiz.date_start or False
                continue
            last = last_end.get(wiz.type_id.id)
            if last:
                wiz.date_start = last + relativedelta(days=1)
            elif wiz.type_id.autogeneration_date_start:
                wiz.date_start = wiz.type_id.autogeneration_date_start
            else:
                wiz.date_start = fields.Date.context_today(wiz).replace(day=1, month=1)

    @api.depends("date_start", "type_id")
    def _compute_date_end(self) -> None:
        for wiz in self:
            date_end = False
            dr_type = wiz.type_id
            if (
                dr_type
                and wiz.date_start
                and dr_type.autogeneration_unit
                and dr_type.autogeneration_count
            ):
                horizon = fields.Date.context_today(wiz) + get_timedelta(
                    dr_type.autogeneration_count, dr_type.autogeneration_unit
                )
                if horizon > wiz.date_start:
                    date_end = horizon
            wiz.date_end = date_end or wiz.date_end or False

    def _check_settings_complete(self, batch=False) -> bool:
        self.check_singleton()
        missing = [
            label
            for value, label in (
                (self.type_id, self.env._("date range type")),
                (self.date_start, self.env._("start date")),
                (self.duration_count, self.env._("duration")),
                (self.duration_unit, self.env._("unit of time")),
            )
            if not value
        ]
        if not missing and self.duration_count < 0:
            missing.append(self.env._("a positive duration"))
        if not missing and not self.date_end and not self.count:
            missing.append(self.env._("end date or number of ranges to generate"))
        if not missing and not self.name_expr and not self.name_prefix:
            missing.append(self.env._("name prefix or name expression"))
        if not missing:
            return True
        if batch:
            return False
        raise ValidationError(
            self.env._("Please set the %s before generating date ranges.")
            % ", ".join(missing)
        )

    @api.depends(
        "name_expr",
        "name_prefix",
        "date_start",
        "date_end",
        "count",
        "duration_count",
        "duration_unit",
    )
    def _compute_range_name_preview(self) -> None:
        for wiz in self:
            preview = False
            if (wiz.name_expr or wiz.name_prefix) and wiz._check_settings_complete(
                batch=True
            ):
                try:
                    names = wiz.generate_names(wiz._generate_intervals())
                    preview = names[0] if names else False
                except ValidationError as error:
                    preview = str(error)
                except UserError:
                    preview = False
                except Exception:
                    _logger.exception("Unexpected error building the name preview")
            wiz.range_name_preview = preview

    def _generate_intervals(self):
        self.check_singleton()
        vals = []
        index = 0
        while True:
            boundary = self.date_start + get_timedelta(
                self.duration_count * index, self.duration_unit
            )
            if (self.date_end and boundary > self.date_end) or (
                not self.date_end and index >= self.count
            ):
                break
            vals.append(datetime.datetime.combine(boundary, datetime.time()))
            index += 1
        if not vals:
            raise UserError(self.env._("No ranges to generate with these settings"))
        last_boundary = datetime.datetime.combine(
            self.date_start
            + get_timedelta(self.duration_count * index, self.duration_unit),
            datetime.time(),
        )
        if self.date_end:
            capped_end = self.date_end + relativedelta(days=1)
            if last_boundary.date() > capped_end:
                last_boundary = datetime.datetime.combine(capped_end, datetime.time())
        vals.append(last_boundary)
        return vals

    def generate_names(self, vals):
        self.check_singleton()
        return self._generate_names(vals, self.name_expr, self.name_prefix)

    @api.model
    def _generate_names(self, vals, name_expr, name_prefix):
        if not name_expr and not name_prefix:
            raise ValidationError(
                self.env._(
                    "Please set a prefix or an expression to generate the range names."
                )
            )
        names = []
        count_digits = len(str(len(vals) - 1))
        for idx, dt_start in enumerate(vals[:-1]):
            date_start = dt_start.date()
            date_end = vals[idx + 1].date() - relativedelta(days=1)
            index = f"{idx + 1:0{count_digits}d}"
            if name_expr:
                try:
                    names.append(
                        safe_eval(
                            name_expr,
                            {
                                "date_end": date_end,
                                "date_start": date_start,
                                "index": index,
                            },
                        )
                    )
                except Exception as error:
                    raise ValidationError(
                        self.env._("Invalid name expression: %s") % error
                    ) from error
            else:
                names.append(name_prefix + index)
        return names

    def _generate_date_ranges(self, batch=False) -> list:
        self.check_singleton()
        if not self._check_settings_complete(batch=batch):
            return []
        vals = self._generate_intervals()
        names = self.generate_names(vals)
        return [
            {
                "name": names[idx],
                "date_start": dt_start.date(),
                "date_end": vals[idx + 1].date() - relativedelta(days=1),
                "type_id": self.type_id.id,
                "company_id": self.company_id.id,
            }
            for idx, dt_start in enumerate(vals[:-1])
        ]

    def action_apply(self, batch=False):
        self.check_singleton()
        DateRange = self.env["date.range"]
        try:
            date_ranges = self._generate_date_ranges(batch=batch)
        except (UserError, ValidationError) as error:
            if not batch:
                raise UserError(str(error)) from error
            _logger.warning(
                "Cannot generate date ranges for type %s: %s",
                self.type_id.display_name or "?",
                error,
            )
            return None

        if batch:
            created = DateRange.browse()
            for vals in date_ranges:
                try:
                    with self.env.cr.savepoint():
                        created |= DateRange.create(vals)
                except (UserError, psycopg.Error) as error:
                    _logger.warning(
                        "Skipping date range %s: %s", vals.get("name", "?"), error
                    )
            _logger.info(
                "Autogenerated %d date ranges for type %s",
                len(created),
                self.type_id.display_name,
            )
            return None

        if date_ranges:
            try:
                DateRange.create(date_ranges)
            except (UserError, ValidationError) as error:
                raise UserError(
                    self.env._(
                        "Failed to generate date ranges:\n\n"
                        "Error: %(error)s\n"
                        "Type: %(type)s\n"
                        "Date Start: %(start)s\n"
                        "Date End: %(end)s"
                    )
                    % {
                        "error": error,
                        "type": self.type_id.display_name or "Not set",
                        "start": self.date_start or "Not set",
                        "end": self.date_end or "Not set",
                    }
                ) from error
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "date_range.date_range_action"
        )
        action["domain"] = [("type_id", "=", self.type_id.id)]
        return action
