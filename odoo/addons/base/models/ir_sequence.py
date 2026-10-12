import logging
import re
from collections.abc import Collection
from datetime import datetime, timedelta
from typing import Any, Literal, Self

from odoo import Command, api, fields, models
from odoo.api import ValuesType
from odoo.db import get_or_create_row
from odoo.exceptions import UserError, ValidationError
from odoo.libs.debug_log import DebugLog

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)


def _create_sequence(
    env: Any, seq_name: str, number_increment: int, number_next: int
) -> None:
    env.backend.sequences.create(
        env, seq_name, increment=number_increment, start=number_next
    )


def _drop_sequences(env: Any, seq_names: list[str]) -> None:
    env.backend.sequences.drop(env, seq_names)


def _alter_sequence(
    env: Any,
    seq_name: str,
    number_increment: int | None = None,
    number_next: int | None = None,
) -> None:
    env.backend.sequences.alter(
        env, seq_name, increment=number_increment, restart=number_next
    )


def _select_nextvals(env: Any, seq_name: str, count: int) -> list[int]:
    return env.backend.sequences.next_values(env, seq_name, count)


def _update_nogap(self: Any, number_increment: int) -> int:
    self.flush_recordset(["number_next"])
    with _debug.perf(
        "nogap_fetch_and_add", cr=self.env.cr, record=self.id, step=number_increment
    ):
        number_next = self.env.backend.columns.fetch_and_add(
            self, "number_next", self.id, number_increment
        )
    self.invalidate_recordset(["number_next"])
    return number_next


def _update_nogap_batch(self: Any, number_increment: int, count: int) -> list[int]:
    first = _update_nogap(self, number_increment * count)
    return [first + index * number_increment for index in range(count)]


def _predict_nextvals(env: Any, seq_names: Collection[str]) -> dict[str, int]:
    predicted = env.backend.sequences.peek(env, seq_names)
    _debug.perf.count(
        "nextvals_predicted", asked=len(seq_names), answered=len(predicted)
    )
    return predicted


def _draw_numbers(counter: Any, sequence: Any, count: int) -> list[int]:
    if sequence.implementation == "standard":
        numbers = _select_nextvals(counter.env, counter._get_pg_sequence_name(), count)
    else:
        numbers = _update_nogap_batch(counter, sequence.number_increment, count)
    counter.invalidate_recordset(["number_next_actual"])
    return numbers


def _assign_number_next_actual(counters: Any, standard: Any) -> None:
    predicted = _predict_nextvals(
        counters.env, [counter._get_pg_sequence_name() for counter in standard]
    )
    for counter in counters:
        origin = counter._origin
        counter.number_next_actual = (
            predicted.get(origin._get_pg_sequence_name(), counter.number_next)
            if origin
            else counter.number_next
        )


def _write_number_next_actual(counters: Any) -> None:
    for counter in counters:
        val = counter.number_next_actual
        _debug.lifecycle(
            "number_next_set", model=counter._name, record=counter.id, value=val
        )
        counter.write({"number_next": val if val is not None else 1})


def _carry_over_pg_counters(counters: Any) -> None:
    if not counters:
        return
    predicted = _predict_nextvals(
        counters.env, [counter._get_pg_sequence_name() for counter in counters]
    )
    _debug.lifecycle(
        "pg_counters_carried_over", model=counters._name, records=counters.ids
    )
    counters.flush_recordset(["number_next"])
    counters.env.backend.columns.write(
        counters,
        "number_next",
        [
            (
                counter.id,
                predicted.get(counter._get_pg_sequence_name(), counter.number_next),
            )
            for counter in counters
        ],
    )
    counters.invalidate_recordset(["number_next", "number_next_actual"])


def _range_ids_given_a_counter(vals: dict[str, Any]) -> set[int]:
    return {
        command[1]
        for command in vals.get("date_range_ids") or ()
        if isinstance(command, (list, tuple))
        and command[0] == Command.UPDATE
        and {"number_next", "number_next_actual"} & command[2].keys()
    }


_INTERPOLATION_FORMATS = {
    "year": "%Y",
    "month": "%m",
    "day": "%d",
    "y": "%y",
    "doy": "%j",
    "woy": "%W",
    "weekday": "%w",
    "h24": "%H",
    "h12": "%I",
    "min": "%M",
    "sec": "%S",
    "isoyear": "%G",
    "isoy": "%g",
    "isoweek": "%V",
}

_INTERPOLATION_WIDTHS = {
    "year": 4,
    "month": 2,
    "day": 2,
    "y": 2,
    "doy": 3,
    "woy": 2,
    "weekday": 1,
    "h24": 2,
    "h12": 2,
    "min": 2,
    "sec": 2,
    "isoyear": 4,
    "isoy": 2,
    "isoweek": 2,
}

_INTERPOLATION_REGEXES = {
    prefix + name: rf"\d{{{width}}}"
    for name, width in _INTERPOLATION_WIDTHS.items()
    for prefix in ("", "range_", "current_")
}

_PLACEHOLDER_RE = re.compile(r"%\((\w+)\)s")


class _InterpolationDict(dict):
    def __init__(
        self, effective_date: datetime, range_date: datetime, now: datetime
    ) -> None:
        super().__init__()
        self._dates = {"": effective_date, "range_": range_date, "current_": now}

    def __missing__(self, key: str) -> str:
        date, fmt_key = self._dates[""], key
        for date_prefix in ("range_", "current_"):
            if key.startswith(date_prefix):
                date = self._dates[date_prefix]
                fmt_key = key.removeprefix(date_prefix)
                break
        try:
            fmt = _INTERPOLATION_FORMATS[fmt_key]
        except KeyError:
            raise KeyError(key) from None
        value = date.strftime(fmt)
        self[key] = value
        return value


class IrSequence(models.Model):
    _name = "ir.sequence"
    _description = "Sequence"
    _order = "name, id"
    _allow_sudo_commands = False

    def _get_pg_sequence_name(self) -> str:
        return "ir_sequence_%03d" % self.id

    @api.depends("implementation", "number_next")
    def _compute_number_next_actual(self) -> None:
        _assign_number_next_actual(
            self, self._origin.filtered(lambda seq: seq.implementation == "standard")
        )

    def _inverse_number_next_actual(self) -> None:
        _write_number_next_actual(self)

    name = fields.Char(required=True)
    code = fields.Char(string="Sequence Code")
    implementation = fields.Selection(
        selection=[("standard", "Standard"), ("no_gap", "No gap")],
        default="standard",
        required=True,
        help="While assigning a sequence number to a record, the 'no gap' sequence implementation ensures that each previous sequence number has been assigned already. "
        "While this sequence implementation will not skip any sequence number upon assignment, there can still be gaps in the sequence if records are deleted. "
        "The 'no gap' implementation is slower than the standard one.",
    )
    active = fields.Boolean(default=True)
    prefix = fields.Char(
        trim=False,
        help="Prefix value of the record for the sequence",
    )
    suffix = fields.Char(
        trim=False,
        help="Suffix value of the record for the sequence",
    )
    number_next = fields.Integer(
        string="Next Number",
        default=1,
        required=True,
        help="Next number of this sequence",
    )
    number_next_actual = fields.Integer(
        string="Actual Next Number",
        compute="_compute_number_next_actual",
        inverse="_inverse_number_next_actual",
        help="Next number that will be used. This number can be incremented "
        "frequently so the displayed value might already be obsolete",
    )
    number_increment = fields.Integer(
        string="Step",
        default=1,
        required=True,
        help="The next number of the sequence will be incremented by this number",
    )
    padding = fields.Integer(
        string="Sequence Size",
        default=0,
        required=True,
        help="Odoo will automatically adds some '0' on the left of the 'Next Number' to get the required padding size.",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda s: s.env.company,
    )
    use_date_range = fields.Boolean(string="Use subsequences per date_range")
    date_range_ids = fields.One2many(
        comodel_name="ir.sequence.date_range",
        inverse_name="sequence_id",
        string="Subsequences",
    )

    _positive_increment = models.Constraint(
        "CHECK (number_increment > 0)",
        "The sequence step must be strictly positive.",
    )
    _non_negative_padding = models.Constraint(
        "CHECK (padding >= 0)",
        "The sequence size cannot be negative.",
    )

    @api.model_create_multi
    def create(self, vals_list: list[ValuesType]) -> Self:
        seqs = super().create(vals_list)
        _debug.lifecycle(
            "create",
            count=len(seqs),
            codes=seqs.mapped("code"),
            standard=sum(1 for seq in seqs if seq.implementation == "standard"),
        )
        for seq in seqs:
            if seq.implementation == "standard":
                _create_sequence(
                    self.env,
                    seq._get_pg_sequence_name(),
                    seq.number_increment,
                    seq.number_next if seq.number_next is not None else 1,
                )
        return seqs

    def unlink(self) -> bool:
        _debug.lifecycle(
            "unlink", count=len(self), date_ranges=len(self.date_range_ids)
        )
        _drop_sequences(
            self.env,
            [
                *(x._get_pg_sequence_name() for x in self),
                *(r._get_pg_sequence_name() for r in self.date_range_ids),
            ],
        )
        return super().unlink()

    def write(self, vals: dict[str, Any]) -> bool:
        previous = {seq.id: (seq.implementation, seq.number_increment) for seq in self}
        given_range_ids = _range_ids_given_a_counter(vals)
        res = super().write(vals)
        self.flush_model(vals.keys())
        for seq in self:
            previous_implementation, previous_increment = previous[seq.id]
            was_standard = previous_implementation == "standard"
            is_standard = seq.implementation == "standard"
            if _debug.lifecycle.enabled and was_standard != is_standard:
                _debug.lifecycle(
                    "implementation_switched",
                    sequence=seq.id,
                    old=previous_implementation,
                    new=seq.implementation,
                )
            if was_standard and is_standard:
                if "number_next" in vals:
                    _debug.lifecycle(
                        "pg_sequence_restarted", sequence=seq.id, at=seq.number_next
                    )
                    _alter_sequence(
                        self.env,
                        seq._get_pg_sequence_name(),
                        number_next=seq.number_next,
                    )
                if previous_increment != seq.number_increment:
                    _debug.lifecycle(
                        "pg_sequence_step_changed",
                        sequence=seq.id,
                        old=previous_increment,
                        new=seq.number_increment,
                        ranges=len(seq.date_range_ids),
                    )
                    _alter_sequence(
                        self.env,
                        seq._get_pg_sequence_name(),
                        number_increment=seq.number_increment,
                    )
                    seq.date_range_ids._alter_sequence(
                        number_increment=seq.number_increment
                    )
            elif was_standard:
                _debug.logic(
                    "pg_sequences_dropped",
                    sequence=seq.id,
                    carry_counter="number_next" not in vals
                    and "number_next_actual" not in vals,
                )
                if "number_next" not in vals and "number_next_actual" not in vals:
                    _carry_over_pg_counters(seq)
                _carry_over_pg_counters(
                    seq.date_range_ids.filtered(
                        lambda rng: rng.id not in given_range_ids
                    )
                )
                _drop_sequences(
                    self.env,
                    [
                        seq._get_pg_sequence_name(),
                        *(s._get_pg_sequence_name() for s in seq.date_range_ids),
                    ],
                )
            elif is_standard:
                _debug.logic(
                    "pg_sequences_created",
                    sequence=seq.id,
                    ranges=len(seq.date_range_ids),
                )
                _create_sequence(
                    self.env,
                    seq._get_pg_sequence_name(),
                    seq.number_increment,
                    seq.number_next,
                )
                for sub_seq in seq.date_range_ids:
                    _create_sequence(
                        self.env,
                        sub_seq._get_pg_sequence_name(),
                        seq.number_increment,
                        sub_seq.number_next,
                    )
        return res

    def _get_prefix_suffix(
        self, date: Any = None, date_range: Any = None
    ) -> tuple[str, str]:
        def _interpolate(s, d):
            return (s % d) if s else ""

        self.check_singleton()
        if not self.prefix and not self.suffix:
            return "", ""
        _debug.logic(
            "prefix_suffix_interpolated",
            sequence=self.id,
            date_given=bool(date or self.env.context.get("ir_sequence_date")),
            range_given=bool(
                date_range or self.env.context.get("ir_sequence_date_range")
            ),
        )
        now = range_date = effective_date = datetime.now(self.env.tz)
        if date or self.env.context.get("ir_sequence_date"):
            effective_date = fields.Datetime.from_string(
                date or self.env.context.get("ir_sequence_date")
            )
        if date_range or self.env.context.get("ir_sequence_date_range"):
            range_date = fields.Datetime.from_string(
                date_range or self.env.context.get("ir_sequence_date_range")
            )
        d = _InterpolationDict(effective_date, range_date, now)
        try:
            interpolated_prefix = _interpolate(self.prefix, d)
            interpolated_suffix = _interpolate(self.suffix, d)
        except (ValueError, TypeError, KeyError) as exc:
            _debug.logic(
                "prefix_suffix_rejected", sequence=self.id, error=type(exc).__name__
            )
            raise UserError(
                self.env._("Invalid prefix or suffix for sequence '%s'", self.name)
            ) from None
        return interpolated_prefix, interpolated_suffix

    def get_next_char(self, number_next: int) -> str:
        return self._format_numbers([number_next])[0]

    def _format_numbers(self, numbers: list[int]) -> list[str]:
        prefix, suffix = self._get_prefix_suffix()
        padding = max(0, self.padding)
        return [f"{prefix}{number:0{padding}d}{suffix}" for number in numbers]

    @api.model
    def _get_interpolation_mapping(self, date=None, range_date=None) -> dict[str, str]:
        now = datetime.now(self.env.tz)
        return _InterpolationDict(date or now, range_date or now, now)

    @api.model
    def _get_pattern_placeholders(self) -> dict[str, str]:
        return dict(_INTERPOLATION_REGEXES)

    @api.model
    def _pattern_to_regex(
        self, pattern: str, placeholders: dict[str, str] | None = None
    ) -> str:
        if placeholders is None:
            placeholders = self._get_pattern_placeholders()
        parts = ["^"]
        seen = set()
        position = 0
        for match in _PLACEHOLDER_RE.finditer(pattern):
            parts.append(re.escape(pattern[position : match.start()]))
            name = match.group(1)
            if name not in placeholders:
                _debug.logic("pattern_placeholder_unknown", name=name)
                raise ValueError(
                    f"Unknown placeholder %({name})s: expected one of "
                    f"{', '.join(sorted(placeholders))}"
                )
            if name in seen:
                parts.append(f"(?P={name})")
            else:
                seen.add(name)
                parts.append(f"(?P<{name}>{placeholders[name]})")
            position = match.end()
        parts.append(re.escape(pattern[position:]))
        parts.append("$")
        _debug.perf.count("pattern_to_regex", placeholders=len(seen))
        return "".join(parts)

    def _get_date_range_bounds(self, date: Any) -> tuple[Any, Any]:
        year = fields.Date.from_string(date).year
        return fields.Date.to_date(f"{year}-01-01"), fields.Date.to_date(
            f"{year}-12-31"
        )

    def _get_domain_covering_date_range(self, date: Any) -> list[tuple]:
        return [
            ("sequence_id", "=", self.id),
            ("date_from", "<=", date),
            ("date_to", ">=", date),
        ]

    def _get_covering_date_range(self, date: Any) -> Any:
        return self.env["ir.sequence.date_range"].search(
            self._get_domain_covering_date_range(date),
            order="date_from desc, id",
            limit=1,
        )

    def _get_date_range_number_next(self, date_from: Any, date_to: Any) -> int:
        return 1

    def _get_new_date_range_bounds(
        self, date: Any, ranges: Any = None
    ) -> tuple[Any, Any]:
        date = fields.Date.to_date(date)
        date_from, date_to = self._get_date_range_bounds(date)
        if ranges is None:
            ranges = self.env["ir.sequence.date_range"].search(
                [
                    ("sequence_id", "=", self.id),
                    ("date_from", "<=", date_to),
                    ("date_to", ">=", date_from),
                ]
            )
        next_start = min(
            (r.date_from for r in ranges if date <= r.date_from <= date_to),
            default=None,
        )
        previous_end = max(
            (r.date_to for r in ranges if date_from <= r.date_to <= date),
            default=None,
        )
        if next_start is not None:
            _debug.logic("date_range_bound_clipped", sequence=self.id, side="to")
            date_to = next_start + timedelta(days=-1)
        if previous_end is not None:
            _debug.logic("date_range_bound_clipped", sequence=self.id, side="from")
            date_from = previous_end + timedelta(days=1)
        if date_from > date_to:
            _debug.logic("date_range_refused", sequence=self.id, reason="no_room")
            raise UserError(
                self.env._(
                    "Cannot create a sequence date range for %(date)s on "
                    "sequence '%(seq)s': the neighbouring ranges leave no room "
                    "between %(date_from)s and %(date_to)s.",
                    date=date,
                    seq=self.display_name,
                    date_from=date_from,
                    date_to=date_to,
                )
            )
        return date_from, date_to

    def _create_date_range_seq(self, date: Any) -> Any:
        date = fields.Date.to_date(date)
        date_from, date_to = self._get_new_date_range_bounds(date)
        DateRange = self.env["ir.sequence.date_range"]
        vals = {
            "date_from": date_from,
            "date_to": date_to,
            "sequence_id": self.id,
            "number_next": self._get_date_range_number_next(date_from, date_to),
        }

        def find_covering() -> Any:
            DateRange.invalidate_model()
            return self._get_covering_date_range(date)

        date_range, created = get_or_create_row(
            self.env.cr,
            lambda: DateRange.sudo().create(vals),
            find_covering,
            conflict=f"ir.sequence {self.id} date range {date_from}..{date_to}",
            flush=False,
        )
        _debug.lifecycle(
            "date_range",
            sequence=self.id,
            date_from=date_from,
            date_to=date_to,
            created=created,
        )
        return date_range

    def _get_sequence_date(self, sequence_date: Any = None) -> Any:
        return (
            sequence_date
            or self.env.context.get("ir_sequence_date")
            or datetime.now(self.env.tz).replace(tzinfo=None)
        )

    def _get_current_sequence(self, sequence_date: Any = None) -> Any:
        self.check_singleton()
        if not self.use_date_range:
            return self
        dt = self._get_sequence_date(sequence_date)
        covering = self._get_covering_date_range(dt)
        _debug.logic(
            "date_range_resolved", sequence=self.id, date=str(dt), found=bool(covering)
        )
        return covering or self._create_date_range_seq(dt)

    def _with_sequence_dates(self, sequence_date: Any, range_date: Any = None) -> Self:
        context = {}
        if sequence_date is not None:
            context["ir_sequence_date"] = (
                sequence_date.replace(tzinfo=None)
                if isinstance(sequence_date, datetime)
                else sequence_date
            )
        if range_date is not None:
            context["ir_sequence_date_range"] = range_date
        return self.with_context(**context)

    def _next(self, sequence_date: Any = None) -> str:
        return self._next_batch(1, sequence_date=sequence_date)[0]

    def _next_batch(self, count: int, sequence_date: Any = None) -> list[str]:
        self.check_singleton()
        _debug.pipeline(
            "next_requested",
            sequence=self.id,
            count=count,
            date_range=self.use_date_range,
            dated=sequence_date is not None,
        )
        if count <= 0:
            return []
        if self.use_date_range:
            sequence_date = self._get_sequence_date(sequence_date)
            counter = self._get_current_sequence(sequence_date)
            range_date = counter.date_from
        else:
            counter, range_date = self, None
        numbers = _draw_numbers(counter, self, count)
        _debug.logic(
            "next",
            sequence=self.id,
            range=counter.id if range_date else None,
            implementation=self.implementation,
            count=count,
            first=numbers[0],
        )
        return self._with_sequence_dates(sequence_date, range_date)._format_numbers(
            numbers
        )

    def next_by_id(self, sequence_date: Any = None) -> str:
        self.browse().check_access("read")
        return self._next(sequence_date=sequence_date)

    def preview_next(self, sequence_date: Any = None) -> str:
        self.browse().check_access("read")
        self.check_singleton()
        if not self.use_date_range:
            return self._with_sequence_dates(sequence_date).get_next_char(
                self.number_next_actual
            )
        dt = self._get_sequence_date(sequence_date)
        date_range = self._get_covering_date_range(dt)
        _debug.logic(
            "preview_date_range",
            sequence=self.id,
            found=bool(date_range),
            range=date_range.id if date_range else None,
        )
        if date_range:
            number_next = date_range.number_next_actual
            range_date = date_range.date_from
        else:
            range_date, range_end = self._get_new_date_range_bounds(dt)
            number_next = self._get_date_range_number_next(range_date, range_end)
        return self._with_sequence_dates(dt, range_date).get_next_char(number_next)

    @api.model
    def _get_by_code(self, sequence_code: str) -> Self:
        self.browse().check_access("read")
        company_id = self.env.company.id
        sequence = self.search(
            [
                ("code", "=", sequence_code),
                ("company_id", "in", [company_id, False]),
            ],
            order="company_id, id",
            limit=1,
        )
        if not sequence:
            _logger.debug(
                "No ir.sequence has been found for code '%s'. Please make sure a sequence is set for current company.",
                sequence_code,
            )
        _debug.logic(
            "code_resolved",
            code=sequence_code,
            company=company_id,
            sequence=sequence.id,
        )
        return sequence

    @api.model
    def next_by_code(self, sequence_code: str, sequence_date: Any = None) -> str | bool:
        sequence = self._get_by_code(sequence_code)
        if not sequence:
            return False
        return sequence._next(sequence_date=sequence_date)

    @api.model
    def next_by_code_batch(
        self, sequence_code: str, count: int, sequence_date: Any = None
    ) -> list[str] | Literal[False]:
        if count <= 0:
            self.browse().check_access("read")
            return []
        sequence = self._get_by_code(sequence_code)
        if not sequence:
            return False
        return sequence._next_batch(count, sequence_date=sequence_date)


class IrSequenceDate_Range(models.Model):
    _name = "ir.sequence.date_range"
    _description = "Sequence Date Range"
    _rec_name = "sequence_id"
    _allow_sudo_commands = False

    _unique_range_per_sequence = models.Constraint(
        "UNIQUE(sequence_id, date_from, date_to)",
        "You cannot create two date ranges for the same sequence with the same date range.",
    )

    def _get_pg_sequence_name(self) -> str:
        return "ir_sequence_%03d_%03d" % (self.sequence_id.id, self.id)

    @api.depends("number_next", "sequence_id.implementation")
    def _compute_number_next_actual(self) -> None:
        _assign_number_next_actual(
            self,
            self._origin.filtered(
                lambda rng: rng.sequence_id.implementation == "standard"
            ),
        )

    def _inverse_number_next_actual(self) -> None:
        _write_number_next_actual(self)

    date_from = fields.Date(
        string="From",
        required=True,
    )
    date_to = fields.Date(
        string="To",
        required=True,
    )
    sequence_id = fields.Many2one(
        comodel_name="ir.sequence",
        string="Main Sequence",
        required=True,
        ondelete="cascade",
    )
    number_next = fields.Integer(
        string="Next Number",
        default=1,
        required=True,
        help="Next number of this sequence",
    )
    number_next_actual = fields.Integer(
        string="Actual Next Number",
        compute="_compute_number_next_actual",
        inverse="_inverse_number_next_actual",
        help="Next number that will be used. This number can be incremented "
        "frequently so the displayed value might already be obsolete",
    )

    @api.constrains("sequence_id", "date_from", "date_to")
    def _check_ranges_do_not_overlap(self) -> None:
        ranges_by_sequence = self.search(
            [("sequence_id", "in", self.sequence_id.ids)]
        ).grouped("sequence_id")
        _debug.perf.count(
            "ranges_overlap_checked",
            ranges=len(self),
            sequences=len(ranges_by_sequence),
        )
        for rng in self:
            if rng.date_from > rng.date_to:
                _debug.logic("date_range_rejected", range=rng.id, reason="inverted")
                raise ValidationError(
                    self.env._(
                        "The date range %(date_from)s - %(date_to)s of sequence "
                        "'%(seq)s' ends before it starts.",
                        date_from=rng.date_from,
                        date_to=rng.date_to,
                        seq=rng.sequence_id.display_name,
                    )
                )
            overlapping = next(
                (
                    other
                    for other in ranges_by_sequence.get(rng.sequence_id, self.browse())
                    if other.id != rng.id
                    and other.date_from <= rng.date_to
                    and other.date_to >= rng.date_from
                ),
                None,
            )
            if overlapping:
                _debug.logic(
                    "date_range_rejected",
                    range=rng.id,
                    reason="overlap",
                    other=overlapping.id,
                )
                raise ValidationError(
                    self.env._(
                        "The date range %(date_from)s - %(date_to)s of sequence "
                        "'%(seq)s' overlaps %(other_from)s - %(other_to)s.",
                        date_from=rng.date_from,
                        date_to=rng.date_to,
                        seq=rng.sequence_id.display_name,
                        other_from=overlapping.date_from,
                        other_to=overlapping.date_to,
                    )
                )

    def _alter_sequence(
        self,
        number_increment: int | None = None,
        number_next: int | None = None,
    ) -> None:
        _debug.lifecycle(
            "ranges_altered",
            ranges=len(self),
            step=number_increment,
            restart=number_next,
        )
        for seq in self:
            _alter_sequence(
                self.env,
                seq._get_pg_sequence_name(),
                number_increment=number_increment,
                number_next=number_next,
            )

    @api.model_create_multi
    def create(self, vals_list: list[ValuesType]) -> Self:
        seqs = super().create(vals_list)
        _debug.lifecycle(
            "range_create",
            count=len(seqs),
            sequences=sorted({vals.get("sequence_id") or 0 for vals in vals_list}),
        )
        for seq in seqs:
            main_seq = seq.sequence_id
            if main_seq.implementation == "standard":
                val = seq.number_next
                _create_sequence(
                    self.env,
                    seq._get_pg_sequence_name(),
                    main_seq.number_increment or 1,
                    val if val is not None else 1,
                )
        return seqs

    def unlink(self) -> bool:
        _debug.lifecycle("range_unlink", ranges=self.ids)
        _drop_sequences(self.env, [x._get_pg_sequence_name() for x in self])
        return super().unlink()

    def write(self, vals: dict[str, Any]) -> bool:
        _debug.lifecycle("range_write", ranges=self.ids, fields=list(vals))
        if "number_next" in vals:
            seq_to_alter = self.filtered(
                lambda seq: seq.sequence_id.implementation == "standard"
            )
            _debug.logic(
                "range_number_next_written",
                ranges=len(self),
                standard=len(seq_to_alter),
            )
            seq_to_alter._alter_sequence(number_next=vals["number_next"])
        res = super().write(vals)
        self.flush_model(vals.keys())
        return res
