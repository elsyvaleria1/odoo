from collections import defaultdict
from datetime import UTC, datetime, time, timedelta
from itertools import groupby

from odoo import api, fields, models
from odoo.libs.datetime import timezone
from odoo.libs.debug_log import DebugLog
from odoo.tools import format_date, format_time
from odoo.tools.date_utils import localized

from odoo.addons.base.models.resource_utils import last_day_of

_debug = DebugLog(__name__)


class HrLeave(models.Model):
    _inherit = "hr.leave"

    @api.model
    def _get_leave_interval(self, date_from, date_to, employee_ids):
        calendar_leaves = self.env["resource.schedule.exception"].search(
            [
                ("time_type_id.is_work", "=", False),
                "|",
                ("company_id", "in", employee_ids.mapped("company_id").ids),
                ("company_id", "=", False),
                "|",
                ("resource_id", "in", employee_ids.mapped("resource_id").ids),
                ("resource_id", "=", False),
                "|",
                (
                    "calendar_id",
                    "in",
                    employee_ids.mapped("resource_calendar_id").ids,
                ),
                ("calendar_id", "=", False),
                ("date_from", "<", date_to),
                ("date_to", ">", date_from),
            ],
            order="date_from",
        )

        _debug.perf.count(
            "leave_intervals",
            employees=employee_ids,
            calendar_leaves=calendar_leaves,
            date_from=str(date_from),
            date_to=str(date_to),
        )
        leaves = defaultdict(list)
        for leave in calendar_leaves:
            for employee in employee_ids:
                if (
                    (not leave.company_id or leave.company_id == employee.company_id)
                    and (
                        not leave.resource_id
                        or leave.resource_id == employee.resource_id
                    )
                    and (
                        not leave.calendar_id
                        or leave.calendar_id == employee.resource_calendar_id
                    )
                ):
                    leaves[employee.id].append(leave)

        leaves_query = self.env["hr.leave"].search(
            [
                ("employee_id", "in", employee_ids.ids),
                ("state", "in", ["confirm", "validate1"]),
                ("date_from", "<=", date_to),
                ("date_to", ">=", date_from),
            ],
            order="date_from",
        )
        for leave in leaves_query:
            leaves[leave.employee_id.id].append(leave)
        return leaves

    def _get_leave_warning_parameters(self, leaves, employee, date_from, date_to):
        loc_cache = {}

        def localize(date):
            if date not in loc_cache:
                loc_cache[date] = (
                    date.replace(tzinfo=UTC)
                    .astimezone(timezone(self.env.user.tz or "UTC"))
                    .replace(tzinfo=None)
                )
            return loc_cache[date]

        periods = self._group_leaves(leaves, employee, date_from, date_to)
        periods_by_states = [
            list(b) for a, b in groupby(periods, key=lambda x: x["is_validated"])
        ]
        res = {}
        for periods in periods_by_states:
            leaves_for_employee = {"name": employee.name, "leaves": []}
            for period in periods:
                dfrom = period["from"]
                dto = period["to"]
                number_of_days = period["number_of_days"]
                if number_of_days == 1:
                    leaves_for_employee["leaves"].append(
                        {
                            "start_date": format_date(self.env, localize(dfrom).date()),
                        }
                    )
                elif number_of_days < 1:
                    leaves_for_employee["leaves"].append(
                        {
                            "start_date": format_date(self.env, localize(dfrom).date()),
                            "start_time": format_time(
                                self.env, localize(dfrom).time(), time_format="short"
                            ),
                            "end_time": format_time(
                                self.env, localize(dto).time(), time_format="short"
                            ),
                        }
                    )
                else:
                    leaves_for_employee["leaves"].append(
                        {
                            "start_date": format_date(self.env, localize(dfrom).date()),
                            "end_date": format_date(self.env, localize(dto).date()),
                        }
                    )
            res["validated" if periods[0].get("is_validated") else "requested"] = (
                leaves_for_employee
            )
        return res

    def format_date_range_to_string(self, date_dict) -> str:
        if len(date_dict) == 3:
            return self.env._(
                "on %(start_date)s from %(start_time)s to %(end_time)s", **date_dict
            )
        elif len(date_dict) == 2:
            return self.env._("from %(start_date)s to %(end_date)s", **date_dict)
        else:
            return self.env._("on %(start_date)s", **date_dict)

    def _get_leave_warning(self, leaves, employee, date_from, date_to):
        leaves_parameters = self._get_leave_warning_parameters(
            leaves, employee, date_from, date_to
        )
        warning = ""
        for leave_type, leaves_for_employee in leaves_parameters.items():
            if not leaves_for_employee:
                continue
            if leave_type == "validated":
                warning += self.env._(
                    "%(name)s is on time off %(leaves)s. \n",
                    name=leaves_for_employee["name"],
                    leaves=", ".join(
                        map(
                            self.format_date_range_to_string,
                            leaves_for_employee["leaves"],
                        )
                    ),
                )
            else:
                warning += self.env._(
                    "%(name)s requested time off %(leaves)s. \n",
                    name=leaves_for_employee["name"],
                    leaves=", ".join(
                        map(
                            self.format_date_range_to_string,
                            leaves_for_employee["leaves"],
                        )
                    ),
                )
        return warning

    def _group_leaves(self, leaves, employee, date_from, date_to):
        work_times = {
            wk[0]: wk[1]
            for wk in employee._get_work_time_per_day(date_from, date_to)[employee.id]
        }

        def has_working_hours(start_dt, end_dt, covered_ranges=()) -> bool:
            diff_days = (end_dt - start_dt).days
            all_dates = [
                start_dt.date() + timedelta(days=delta)
                for delta in range(diff_days + 1)
            ]
            return any(
                d in work_times
                and not any(r_from <= d <= r_to for r_from, r_to in covered_ranges)
                for d in all_dates
            )

        periods = []
        for leave in leaves:
            if leave.date_from > date_to or leave.date_to < date_from:
                continue

            number_of_days = 0
            is_validated = True
            if isinstance(leave, self.pool["hr.leave"]):
                number_of_days = leave.number_of_days
                is_validated = False
            else:
                dt_delta = leave.date_to - leave.date_from
                if leave.holiday_id and not (
                    leave.holiday_id.sudo().request_unit_half
                    or leave.holiday_id.sudo().request_unit_hours
                ):
                    number_of_days = (
                        last_day_of(leave.date_from, leave.date_to)
                        - leave.date_from.date()
                    ).days + 1
                else:
                    number_of_days = dt_delta.days + ((dt_delta.seconds / 3600) / 24)
            if (
                not periods
                or has_working_hours(
                    periods[-1]["from"],
                    leave.date_to,
                    covered_ranges=(
                        (
                            periods[-1]["from"].date(),
                            last_day_of(periods[-1]["from"], periods[-1]["to"]),
                        ),
                        (
                            leave.date_from.date(),
                            last_day_of(leave.date_from, leave.date_to),
                        ),
                    ),
                )
                or periods[-1]["is_validated"] != is_validated
            ):
                periods.append(
                    {
                        "is_validated": is_validated,
                        "from": leave.date_from,
                        "to": leave.date_to,
                        "number_of_days": number_of_days,
                    }
                )
            else:
                periods[-1]["is_validated"] = is_validated
                periods[-1]["to"] = max(periods[-1]["to"], leave.date_to)
                periods[-1]["number_of_days"] += number_of_days
        return periods

    @api.model
    def _gantt_unavailability(self, field_name, res_ids, start, stop, scale):
        if field_name != "employee_id":
            return super()._gantt_unavailability(
                field_name, res_ids, start, stop, scale
            )

        start_date = fields.Datetime.to_string(start)
        stop_date = fields.Datetime.to_string(stop)
        employees = self.env["hr.employee"].browse(res_ids)
        leaves_mapping = defaultdict(list)
        employee_contracts = (
            self.env["hr.version"]
            .sudo()
            .search(
                [
                    ("employee_id", "in", employees.ids),
                    ("contract_date_start", "!=", False),
                    ("contract_date_start", "<=", stop_date),
                    "|",
                    ("contract_date_end", "=", False),
                    ("contract_date_end", ">=", start_date),
                ]
            )
        )

        employee_with_contracts = employee_contracts.employee_id
        employees_without_contracts = employees - employee_with_contracts

        leaves_mapping.update(
            employees_without_contracts.resource_id._get_unavailable_intervals(
                start, stop
            )
        )

        for contract in employee_contracts:
            if (
                contract.date_end
                and datetime.combine(contract.date_end + timedelta(days=1), time.min)
                <= start
            ):
                continue
            tmp_date_from = max(start, datetime.combine(contract.date_start, time.min))
            tmp_date_to = (
                min(
                    stop,
                    datetime.combine(contract.date_end + timedelta(days=1), time.min),
                )
                if contract.date_end
                else stop
            )
            resources_unavailable_intervals = (
                contract.resource_calendar_id._unavailable_intervals_batch(
                    localized(tmp_date_from),
                    localized(tmp_date_to),
                    contract.employee_id.resource_id,
                )
            )
            for key, value in resources_unavailable_intervals.items():
                leaves_mapping[key] += value

        cell_dt = (
            timedelta(hours=1) if scale in ["day", "week"] else timedelta(hours=12)
        )

        result = {}
        for employee in employees:
            notable_intervals = filter(
                lambda interval: interval[1] - interval[0] >= cell_dt,
                leaves_mapping.get(employee.resource_id.id, []),
            )
            result[employee.id] = [
                {"start": interval[0], "stop": interval[1]}
                for interval in notable_intervals
            ]

        return result
