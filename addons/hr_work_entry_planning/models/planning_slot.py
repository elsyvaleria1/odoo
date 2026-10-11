from collections import defaultdict

from odoo import api, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


def batch(iterable, batch_size):
    l = len(iterable)
    for n in range(0, l, batch_size):
        yield iterable[n : min(n + batch_size, l)]


class PlanningSlot(models.Model):
    _inherit = "planning.slot"

    def _create_work_entries(self) -> None:
        self_with_employee = self.filtered(lambda s: s.employee_id)
        if not self_with_employee:
            _debug.logic(
                "planning_work_entries_skipped", reason="no_employee", slots=self
            )
            return
        with _debug.perf(
            "planning_slot.create_work_entries", slots=self_with_employee
        ) as span:
            self.flush_model(["start_datetime", "end_datetime", "employee_id"])
            self.env["hr.version"].flush_model(
                [
                    "employee_id",
                    "work_entry_source",
                    "contract_date_start",
                    "contract_date_end",
                    "date_generated_from",
                    "date_generated_to",
                ]
            )
            self.env["hr.work.entry"].flush_model(["employee_id", "date"])
            self.env.cr.execute(
                """
                SELECT slot.id as id,
                       ARRAY_AGG(DISTINCT version.id) as version_ids,
                       ARRAY_AGG(DISTINCT hwe.id) as work_entry_ids,
                       slot.start_datetime as start,
                       slot.end_datetime as stop
                  FROM planning_slot slot
                  JOIN hr_employee employee
                    ON slot.employee_id = employee.id AND
                       employee.active
            -- Keeping only the last version.
            -- We consider that work entries that covers two versions should not be handled as super rare.
            INNER JOIN (SELECT DISTINCT ON (employee_id) *
                                      FROM hr_version v
                                  ORDER BY employee_id, date_version DESC) version
                    ON version.employee_id = employee.id AND
                       version.work_entry_source = 'planning' AND
                       version.date_generated_from < slot.end_datetime AND
                       version.date_generated_to > slot.start_datetime AND
                       version.contract_date_start <= slot.end_datetime AND
                       (version.contract_date_end IS NULL OR
                        version.contract_date_end >= slot.start_datetime)
             LEFT JOIN hr_work_entry hwe
                    ON hwe.employee_id = slot.employee_id AND
                       hwe.date <= slot.end_datetime::date AND
                       hwe.date >= slot.start_datetime::date
                 WHERE slot.id = ANY(%s)
              GROUP BY slot.id
            """,
                [list(self_with_employee.ids)],
            )
            query_result = self.env.cr.dictfetchall()
            span.set(matched_slots=len(query_result))
            periods_to_generate = defaultdict(list)
            work_entries_to_archive = []
            for row in query_result:
                periods_to_generate[row["start"], row["stop"]].extend(
                    row["version_ids"]
                )
                if any(row["work_entry_ids"]):
                    work_entries_to_archive.extend(row["work_entry_ids"])
            span.set(
                periods=len(periods_to_generate),
                archived=len(work_entries_to_archive),
            )
            self.env["hr.work.entry"].sudo().browse(work_entries_to_archive).write(
                {"active": False}
            )
            work_entries_vals_list = []
            for period, version_ids in periods_to_generate.items():
                if not version_ids:
                    _debug.logic(
                        "planning_work_entries_period_skipped",
                        reason="no_version",
                        period_start=period[0],
                        period_end=period[1],
                    )
                    continue
                contracts = self.env["hr.version"].sudo().browse(version_ids)
                work_entries_vals_list.extend(
                    contracts._prepare_work_entries_values(period[0], period[1])
                )
            span.set(before_postprocess=len(work_entries_vals_list))
            work_entries_vals_list = self.env[
                "hr.version"
            ]._generate_work_entries_postprocess(work_entries_vals_list)
            span.set(created=len(work_entries_vals_list))
            self.env["hr.work.entry"].sudo().create(work_entries_vals_list)

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        _debug.lifecycle("planning_slots_created", slots=res)
        scheduled = self._get_scheduled_states()
        res.filtered(lambda s: s.state in scheduled)._create_work_entries()
        return res

    def write(self, vals):
        if (
            vals.get("resource_id")
            or vals.get("start_datetime")
            or vals.get("end_datetime")
            or vals.get("allocated_hours")
        ):
            validated_work_entries = (
                self.env["hr.work.entry"]
                .sudo()
                .search(
                    [("planning_slot_id", "in", self.ids), ("state", "=", "validated")]
                )
            )
            if validated_work_entries:
                _debug.logic(
                    "planning_slot_write_refused",
                    reason="validated_work_entries",
                    slots=self,
                    work_entries=validated_work_entries,
                )
                raise UserError(
                    self.env._(
                        "This shift record is linked to a validated working entry. You can't modify it."
                    )
                )
        state = vals.get("state")
        concerned_slots = (
            self.filtered(lambda s: s.state != state)
            if state
            else self.env["planning.slot"]
        )
        _debug.pipeline(
            "planning_slot_write",
            slots=self,
            state=state,
            regenerating=concerned_slots,
        )
        res = super().write(vals)
        concerned_slots._create_work_entries()
        return res

    @api.ondelete(at_uninstall=False)
    def _unlink_except_validated_work_entries(self) -> None:
        validated_work_entries = (
            self.env["hr.work.entry"]
            .sudo()
            .search([("planning_slot_id", "in", self.ids), ("state", "=", "validated")])
        )
        if validated_work_entries:
            _debug.logic(
                "planning_slot_unlink_refused",
                reason="validated_work_entries",
                slots=self,
                work_entries=validated_work_entries,
            )
            raise UserError(
                self.env._(
                    "This shift record is linked to a validated working entry. You can't delete it."
                )
            )

    def unlink(self):
        if _debug.lifecycle.enabled:
            _debug.lifecycle(
                "planning_slots_unlinked",
                slots=self,
                work_entries=self.env["hr.work.entry"]
                .sudo()
                .search_count([("planning_slot_id", "in", self.ids)]),
            )
        self.env["hr.work.entry"].sudo().search(
            [("planning_slot_id", "in", self.ids)]
        ).write({"active": False})
        return super().unlink()

    def _get_planning_duration(self, date_start, date_stop):
        self.check_singleton()
        if self.start_datetime == date_start and self.end_datetime == date_stop:
            _debug.logic(
                "planning_duration_exact",
                slot=self,
                allocated_hours=self.allocated_hours,
            )
            return self.allocated_hours
        new_slot = self.env["planning.slot"].new(
            {
                **self.read(
                    ["employee_id", "company_id", "allocated_percentage", "resource_id"]
                )[0],
                "start_datetime": date_start,
                "end_datetime": date_stop,
            }
        )
        _debug.logic(
            "planning_duration_recomputed",
            slot=self,
            date_start=date_start,
            date_stop=date_stop,
            allocated_hours=new_slot.allocated_hours,
        )
        return new_slot.allocated_hours
