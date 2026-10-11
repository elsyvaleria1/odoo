import logging
from datetime import timedelta
from typing import Self

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain
from odoo.tools import format_date

_logger = logging.getLogger(__name__)


class DateRange(models.Model):
    """Named period of time, optionally nested inside a parent period."""

    _name = "date.range"
    _description = "Date Range"
    _check_company_auto = True
    _order = "type_id, date_start"

    name = fields.Char(
        translate=True,
        required=True,
    )
    date_start = fields.Date(
        string="Start date",
        index=True,
        required=True,
    )
    date_end = fields.Date(
        string="End date",
        index=True,
        required=True,
    )
    type_id = fields.Many2one(
        comodel_name="date.range.type",
        index=True,
        required=True,
        ondelete="restrict",
        check_company=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company.id,
        index=True,
    )
    active = fields.Boolean(
        default=True,
        help="Uncheck to hide the date range without removing it. Archiving a "
        "date range type archives its ranges too; restoring the type does not "
        "restore them, so a range archived by hand stays archived.",
    )
    allow_overlap = fields.Boolean(
        related="type_id.allow_overlap",
        store=True,
        help="Technical mirror of the type's setting; do not set by hand.",
    )
    duration_days = fields.Integer(
        string="Duration (days)",
        compute="_compute_duration_days",
        store=True,
        help="Number of days in this date range (inclusive)",
    )
    business_days = fields.Integer(
        compute="_compute_day_counts",
        store=True,
        help="Number of business days (Mon-Fri) in this date range",
    )
    weekend_days = fields.Integer(
        compute="_compute_day_counts",
        store=True,
        help="Number of weekend days (Sat-Sun) in this date range",
    )
    parent_id = fields.Many2one(
        comodel_name="date.range",
        string="Parent Range",
        index=True,
        ondelete="cascade",
        check_company=True,
        help="Nest this range inside another one of the same type. Overlap is "
        "checked between siblings only, so a sub-range may span its parent.",
    )
    child_ids = fields.One2many(
        comodel_name="date.range",
        inverse_name="parent_id",
        string="Sub-ranges",
    )
    is_sub_range = fields.Boolean(
        string="Is Sub-range",
        compute="_compute_is_sub_range",
        store=True,
    )

    _date_range_no_overlap = models.Constraint(
        "EXCLUDE USING gist ("
        "COALESCE(company_id, 0) WITH =, type_id WITH =,"
        " COALESCE(parent_id, 0) WITH =,"
        " daterange(date_start, date_end, '[]') WITH &&)"
        " WHERE (COALESCE(active, TRUE) AND NOT COALESCE(allow_overlap, FALSE)"
        " AND date_start <= date_end)"
        " DEFERRABLE INITIALLY DEFERRED",
        "Date ranges of the same type, company and parent must not overlap.",
    )

    def _auto_init(self) -> None:
        try:
            with self.env.cr.savepoint(flush=False):
                self.env.cr.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
        except Exception:
            _logger.warning(
                "Could not create the btree_gist extension; the date_range "
                "overlap exclusion constraint will not be installed and "
                "overlaps will only be caught by the Python check.",
                exc_info=True,
            )
        super()._auto_init()

    @api.constrains("parent_id")
    def _check_parent_recursion(self) -> None:
        if self._has_cycle():
            raise ValidationError(
                self.env._("You cannot nest a date range inside itself.")
            )

    @api.constrains(
        "type_id",
        "date_start",
        "date_end",
        "company_id",
        "parent_id",
        "active",
        "allow_overlap",
    )
    def _check_dates(self) -> None:
        for this in self:
            if this.date_start > this.date_end:
                raise ValidationError(
                    self.env._(
                        "%(name)s is not a valid range (%(date_start)s > %(date_end)s)"
                    )
                    % {
                        "name": this.name,
                        "date_start": this.date_start,
                        "date_end": this.date_end,
                    }
                )
            parent = this.parent_id
            if not parent:
                continue
            if this.date_start < parent.date_start:
                raise ValidationError(
                    self.env._(
                        "Sub-range '%(name)s' start date (%(start)s) "
                        "cannot be before parent range start date (%(parent_start)s)"
                    )
                    % {
                        "name": this.name,
                        "start": this.date_start,
                        "parent_start": parent.date_start,
                    }
                )
            if this.date_end > parent.date_end:
                raise ValidationError(
                    self.env._(
                        "Sub-range '%(name)s' end date (%(end)s) "
                        "cannot be after parent range end date (%(parent_end)s)"
                    )
                    % {
                        "name": this.name,
                        "end": this.date_end,
                        "parent_end": parent.date_end,
                    }
                )

    @api.constrains(
        "type_id",
        "date_start",
        "date_end",
        "company_id",
        "parent_id",
        "active",
        "allow_overlap",
    )
    def _check_no_overlap(self) -> None:
        candidates = self.filtered(
            lambda r: (
                not r.allow_overlap
                and r.active
                and r.date_start
                and r.date_end
                and r.date_start <= r.date_end
            )
        )
        if not candidates:
            return
        self.env.cr.execute(
            """
            SELECT v.id, dt.id
            FROM unnest(
                     %s::int[], %s::date[], %s::date[],
                     %s::int[], %s::int[], %s::int[]
                 ) AS v(id, date_start, date_end, type_id, company_id, parent_id)
            JOIN date_range dt
              ON dt.id <> v.id
             AND dt.type_id = v.type_id
             AND dt.company_id IS NOT DISTINCT FROM v.company_id
             AND dt.parent_id IS NOT DISTINCT FROM v.parent_id
             AND COALESCE(dt.active, TRUE)
             AND daterange(dt.date_start, dt.date_end, '[]')
                 && daterange(v.date_start, v.date_end, '[]')
            LIMIT 1
            """,
            (
                candidates.ids,
                [r.date_start for r in candidates],
                [r.date_end for r in candidates],
                [r.type_id.id for r in candidates],
                [r.company_id.id or None for r in candidates],
                [r.parent_id.id or None for r in candidates],
            ),
        )
        row = self.env.cr.fetchone()
        if row:
            this, other = self.browse(row[0]), self.browse(row[1])
            raise ValidationError(
                self.env._("%(thisname)s overlaps %(dtname)s")
                % {"thisname": this.name, "dtname": other.name}
            )

    @api.constrains("name", "type_id", "company_id")
    def _check_unique_name(self) -> None:
        if not self:
            return
        candidates = self.with_context(active_test=False).search(
            Domain.OR(
                Domain("name", "=", this.name)
                & Domain("type_id", "=", this.type_id.id)
                & Domain("company_id", "=", this.company_id.id)
                for this in self
            )
        )
        seen = {}
        for candidate in candidates:
            seen.setdefault(
                (candidate.name, candidate.type_id.id, candidate.company_id.id), []
            ).append(candidate.id)
        for this in self:
            key = (this.name, this.type_id.id, this.company_id.id)
            if any(other != this.id for other in seen.get(key, ())):
                raise ValidationError(
                    self.env._(
                        "A date range named '%(name)s' already exists for this "
                        "type and company."
                    )
                    % {"name": this.name}
                )

    @api.depends("date_start", "date_end")
    def _compute_duration_days(self) -> None:
        for record in self:
            if record.date_start and record.date_end:
                record.duration_days = (record.date_end - record.date_start).days + 1
            else:
                record.duration_days = 0

    @api.depends("date_start", "date_end")
    def _compute_day_counts(self) -> None:
        for record in self:
            if not (record.date_start and record.date_end):
                record.business_days = 0
                record.weekend_days = 0
                continue
            total = (record.date_end - record.date_start).days + 1
            whole_weeks, remainder = divmod(total, 7)
            first_weekday = record.date_start.weekday()
            business = whole_weeks * 5 + sum(
                1 for offset in range(remainder) if (first_weekday + offset) % 7 < 5
            )
            record.business_days = business
            record.weekend_days = total - business

    @api.depends("parent_id")
    def _compute_is_sub_range(self) -> None:
        for record in self:
            record.is_sub_range = bool(record.parent_id)

    def get_domain_for_field(self, field_name) -> list:
        self.check_singleton()
        return [
            (field_name, ">=", self.date_start),
            (field_name, "<=", self.date_end),
        ]

    @api.model
    def get_current_range(self, date=None, type_id=None, company_id=None) -> Self:
        date = date or fields.Date.context_today(self)
        domain = [("date_start", "<=", date), ("date_end", ">=", date)]
        domain += self._scope_domain(type_id, company_id)
        return self.search(domain, order="date_start, id", limit=1)

    def get_next_range(self) -> Self:
        self.check_singleton()
        return self.search(
            [
                ("type_id", "=", self.type_id.id),
                ("company_id", "=", self.company_id.id),
                ("parent_id", "=", self.parent_id.id),
                ("date_start", ">", self.date_end),
            ],
            order="date_start, id",
            limit=1,
        )

    def get_previous_range(self) -> Self:
        self.check_singleton()
        return self.search(
            [
                ("type_id", "=", self.type_id.id),
                ("company_id", "=", self.company_id.id),
                ("parent_id", "=", self.parent_id.id),
                ("date_end", "<", self.date_start),
            ],
            order="date_end desc, id desc",
            limit=1,
        )

    @api.model
    def _scope_domain(self, type_id=None, company_id=None):
        domain = []
        if type_id:
            domain.append(("type_id", "=", int(type_id)))
        if company_id is None:
            company_id = self.env.company.id
        if company_id:
            domain.append(("company_id", "in", [int(company_id), False]))
        return domain

    def split_by(self, unit="month"):
        self.check_singleton()
        if unit not in ("week", "month"):
            raise ValueError(f"Unknown split unit {unit!r}")
        vals = []
        current = self.date_start
        while current <= self.date_end:
            if unit == "week":
                end = current + timedelta(days=6 - current.weekday())
                label = self.env._("Week %s") % current.strftime("%G-W%V")
            else:
                end = (current.replace(day=1) + timedelta(days=32)).replace(
                    day=1
                ) - timedelta(days=1)
                label = format_date(self.env, current, date_format="MMMM y")
            end = min(end, self.date_end)
            vals.append(
                {
                    "name": f"{self.name} - {label}",
                    "date_start": current,
                    "date_end": end,
                    "type_id": self.type_id.id,
                    "parent_id": self.id,
                    "company_id": self.company_id.id,
                }
            )
            current = end + timedelta(days=1)
        return vals
