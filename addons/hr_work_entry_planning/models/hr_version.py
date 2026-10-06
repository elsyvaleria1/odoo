from collections import defaultdict
from datetime import UTC, timedelta

from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog
from odoo.libs.intervals import Intervals

from odoo.addons.resource.models.utils import last_day_of

_debug = DebugLog(__name__)


class HrVersion(models.Model):
    _inherit = "hr.version"

    work_entry_source = fields.Selection(
        selection_add=[("planning", "Planning")],
        ondelete={"planning": "set default"},
    )

    def _get_more_vals_attendance_interval(self, interval):
        result = super()._get_more_vals_attendance_interval(interval)
        if interval[2]._name == "planning.slot":
            # Due to how Intervals work we might lose the right start and end time for our work entry
            # i.e. [(1, 5, slot_1), (3, 10, slot_2)] will result in (1, 10, {slot_1, slot_2})
            # `_prepare_version_work_entries_values` already takes care of unsplitting our invervals into two for that case
            # But the date needs to be correct after the fact, which we do here.
            # We still take the interval's date in case it was pushed by start_dt/end_dt.
            slot = interval[2]
            # Avoid timezone conversions
            subresult = [("planning_slot_id", slot.id)]
            if interval[0] < slot.start_datetime.replace(tzinfo=UTC):
                subresult.append(("date_start", slot.start_datetime))
            if interval[1] > slot.end_datetime.replace(tzinfo=UTC):
                subresult.append(("date_stop", slot.end_datetime))
            _debug.logic(
                "planning_interval_realigned",
                slot=slot,
                interval_start=interval[0],
                interval_stop=interval[1],
                adjustments=len(subresult) - 1,
            )
            result.extend(subresult)
        return result

    def _get_attendance_intervals(self, start_dt, end_dt):
        planning_based_contracts = self.filtered(
            lambda c: c.work_entry_source == "planning"
        )
        search_domain = [
            ("employee_id", "in", planning_based_contracts.employee_id.ids),
            ("state", "in", self.env["planning.slot"]._get_scheduled_states()),
            ("start_datetime", "<", end_dt.replace(tzinfo=None)),
            ("end_datetime", ">", start_dt.replace(tzinfo=None)),
        ]
        resource_ids = planning_based_contracts.employee_id.resource_id.ids
        planning_slots = (
            self.env["planning.slot"].sudo().search(search_domain)
            if planning_based_contracts
            else self.env["planning.slot"]
        )
        intervals = defaultdict(list)
        for planning_slot in planning_slots:
            intervals[planning_slot.resource_id.id].append(
                (
                    max(start_dt, planning_slot.start_datetime.replace(tzinfo=UTC)),
                    min(end_dt, planning_slot.end_datetime.replace(tzinfo=UTC)),
                    planning_slot,
                )
            )
        _debug.perf.count(
            "planning_attendance_intervals",
            versions=self,
            planning_versions=planning_based_contracts,
            resources=len(resource_ids),
            slots=planning_slots,
        )
        mapped_intervals = {
            r: Intervals(intervals[r], keep_distinct=True) for r in resource_ids
        }
        mapped_intervals.update(super()._get_attendance_intervals(start_dt, end_dt))
        return mapped_intervals

    @api.model
    def _generate_work_entries_postprocess(self, vals_list):
        new_vals_list = []
        slot_backed = 0  # debuglog
        for vals in vals_list:
            if (
                not vals.get("planning_slot_id")
                or not vals.get("date_start")
                or not vals.get("date_stop")
            ):
                new_vals_list.append(vals)
                continue
            dt_start = vals.pop("date_start")
            dt_stop = vals.pop("date_stop")
            date_start = dt_start.date()
            date_stop = last_day_of(dt_start, dt_stop)
            slot = self.env["planning.slot"].browse(vals["planning_slot_id"])
            number_of_days = (date_stop - date_start).days + 1
            allocated_hours = slot._get_planning_duration(dt_start, dt_stop)
            slot_backed += 1  # debuglog
            if _debug.logic.enabled and number_of_days > 1:
                _debug.logic(
                    "planning_work_entry_spans_days",
                    slot=slot,
                    days=number_of_days,
                    allocated_hours=allocated_hours,
                )
            for i in range(number_of_days):
                new_vals = vals.copy()
                new_vals["date"] = date_start + timedelta(days=i)
                new_vals["duration"] = allocated_hours / number_of_days
                new_vals_list.append(new_vals)
        _debug.pipeline(
            "planning_work_entries_postprocess",
            incoming=len(vals_list),
            outgoing=len(new_vals_list),
            slot_backed=slot_backed,
        )
        return super()._generate_work_entries_postprocess(new_vals_list)
