from datetime import UTC, datetime, timedelta
from typing import Self

from odoo import Command, api, fields, models
from odoo.exceptions import ValidationError
from odoo.libs.datetime import timezone
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


def _get_postponed_values(vals, postponed) -> dict:
    return {field: vals[field] for field in postponed if field in vals}


class ProjectTaskRecurrence(models.Model):
    _name = "project.task.recurrence"
    _description = "Task Recurrence"
    _inherit = ["mixin.recurrence.rule"]

    task_ids = fields.One2many(
        comodel_name="project.task",
        inverse_name="recurrence_id",
        copy=False,
    )

    company_id = fields.Many2one(
        comodel_name="res.company",
        compute="_compute_company_id",
        store=True,
        index=True,
    )
    repeat_until = fields.Date(string="End Date")
    date_recurrence_origin = fields.Datetime(copy=False)
    recurrence_anchor_field = fields.Char(copy=False)

    @api.depends("task_ids.company_id")
    def _compute_company_id(self) -> None:
        for recurrence in self:
            companies = recurrence.task_ids.company_id
            recurrence.company_id = (
                companies.root_id if len(companies) > 1 else companies
            )

    @api.constrains("repeat_type", "repeat_until")
    def _check_repeat_until_date(self) -> None:
        today = fields.Date.today()
        if self.filtered(lambda t: t.repeat_type == "until" and not t.repeat_until):
            raise ValidationError(
                self.env._("The end date is required for 'Until' recurrence.")
            )
        if self.filtered(
            lambda t: (
                t.repeat_type == "until" and t.repeat_until and t.repeat_until < today
            )
        ):
            raise ValidationError(self.env._("The end date should be in the future"))

    def write(self, vals) -> bool:
        if "date_recurrence_origin" not in vals and vals.keys() & {
            "repeat_interval",
            "repeat_unit",
        }:
            vals = {
                **vals,
                "date_recurrence_origin": False,
                "recurrence_anchor_field": False,
            }
        return super().write(vals)

    @api.model
    def _get_recurring_fields_to_copy(self) -> list[str]:
        return [
            "recurrence_id",
        ]

    @api.model
    def _get_recurring_fields_to_postpone(self) -> list[str]:
        return [
            "date_end",
            "date_start",
        ]

    def _get_occurrence_anchor(self, task) -> tuple[str, datetime] | tuple[None, None]:
        return next(
            (
                (field, task[field])
                for field in self._get_recurring_fields_to_postpone()
                if task[field]
            ),
            (None, None),
        )

    def _get_next_occurrence_shift(self, task) -> timedelta | None:
        self.check_singleton()
        field, anchor = self._get_occurrence_anchor(task)
        if not anchor:
            return None
        origin = (
            self.date_recurrence_origin
            if self.date_recurrence_origin and self.recurrence_anchor_field == field
            else anchor
        )
        return (
            self._get_next_recurrence_after(origin, anchor, self._get_tz(task)) - anchor
        )

    def _get_tz(self, task):
        return timezone((task.company_id or self.env.company).partner_id.tz or "UTC")

    def _end(self, deleted_tasks=None) -> None:
        tasks = self.with_context(active_test=False).task_ids - (
            deleted_tasks or self.env["project.task"]
        )
        _debug.lifecycle("recurrence_ended", recurrences=self, tasks=tasks)
        self.unlink()
        tasks.write({"recurring_task": False})

    def _get_last_task_id_per_recurrence_id(self) -> dict[int, int]:
        return (
            {}
            if not self
            else {
                recurrence.id: max_task_id
                for recurrence, max_task_id in self.env["project.task"]
                .sudo()
                .with_context(active_test=False)
                ._read_group(
                    [("recurrence_id", "in", self.ids)],
                    ["recurrence_id"],
                    ["id:max"],
                )
            }
        )

    @_debug.perf.timed
    @api.model
    def _create_next_occurrences(self, occurrences_from: Self) -> Self:
        tasks_copy = self.env["project.task"]
        requested = occurrences_from

        def is_occurrence_allowed(task) -> bool:
            rec = task.recurrence_id.sudo()
            if rec.repeat_type != "until":
                return True
            next_start = (
                task.date_end + rec._get_next_occurrence_shift(task)
                if task.date_end
                else fields.Datetime.now()
            )
            next_date = next_start.replace(tzinfo=UTC).astimezone(rec._get_tz(task))
            return bool(rec.repeat_until) and next_date.date() <= rec.repeat_until

        occurrences_from = occurrences_from.filtered(is_occurrence_allowed)
        _debug.logic(
            "next_occurrences_allowed", allowed=occurrences_from, requested=requested
        )

        if occurrences_from:
            recurrence_by_task = {
                task: task.recurrence_id.sudo() for task in occurrences_from
            }
            tasks_copy = (
                self.env["project.task"]
                .sudo()
                .create(self._prepare_next_occurrence_vals_list(recurrence_by_task))
                .sudo(False)
            )
            for task, recurrence in recurrence_by_task.items():
                field, anchor = recurrence._get_occurrence_anchor(task)
                if anchor and (
                    not recurrence.date_recurrence_origin
                    or recurrence.recurrence_anchor_field != field
                ):
                    recurrence.write(
                        {
                            "date_recurrence_origin": anchor,
                            "recurrence_anchor_field": field,
                        }
                    )
            _debug.lifecycle(
                "next_occurrences_created", tasks=occurrences_from, copies=tasks_copy
            )
            if _debug.pipeline.enabled:
                _debug.pipeline(
                    "dependencies_copy_requested",
                    recurrences=sorted({rec.id for rec in recurrence_by_task.values()}),
                )
            occurrences_from._update_copied_dependencies(tasks_copy)
        return tasks_copy

    @api.model
    def _prepare_next_occurrence_vals_list(
        self, recurrence_by_task: dict, shift_by_task: dict | None = None
    ) -> list[dict]:
        shift_by_task = shift_by_task or {}
        tasks = self.env["project.task"].concat(*recurrence_by_task.keys())
        list_create_values = []
        list_copy_data = (
            tasks.with_context(copy_project=True, active_test=False)
            .sudo()
            .copy_data(default={"recurrence_id": False})
        )
        list_fields_to_copy = tasks.sudo()._read_format(
            self._get_recurring_fields_to_copy()
        )
        list_fields_to_postpone = tasks.sudo()._read_format(
            self._get_recurring_fields_to_postpone()
        )

        for task, copy_data, fields_to_copy, fields_to_postpone in zip(
            tasks,
            list_copy_data,
            list_fields_to_copy,
            list_fields_to_postpone,
            strict=True,
        ):
            recurrence = recurrence_by_task[task]
            shift = (
                shift_by_task[task]
                if task in shift_by_task
                else recurrence._get_next_occurrence_shift(task)
            )
            if shift is None:
                shift = recurrence._get_recurrence_delta()
            fields_to_copy.pop("id", None)
            fields_to_postpone.pop("id", None)
            create_values = {
                "priority": "0",
                "step_id": (
                    task.sudo().project_id.workflow_step_ids[0].id
                    if task.sudo().project_id.workflow_step_ids
                    else task.step_id.id
                ),
                "child_ids": [
                    Command.create(vals)
                    for vals in self._prepare_next_occurrence_vals_list(
                        dict.fromkeys(task.child_ids.sorted("id"), recurrence),
                        dict.fromkeys(task.child_ids.sorted("id"), shift),
                    )
                ],
            }
            create_values.update(
                {
                    field: value[0] if isinstance(value, tuple) else value
                    for field, value in fields_to_copy.items()
                }
            )
            create_values.update(
                {
                    field: value and value + shift
                    for field, value in fields_to_postpone.items()
                }
            )
            if _debug.logic.enabled:
                _debug.logic(
                    "next_occurrence_prepared",
                    task=task,
                    step=create_values["step_id"],
                    postponed=_get_postponed_values(create_values, fields_to_postpone),
                    children=len(create_values["child_ids"]),
                )
            copy_data.update(create_values)
            list_create_values.append(copy_data)

        return list_create_values
