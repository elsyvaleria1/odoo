from collections import defaultdict
from datetime import UTC, datetime, timedelta

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog
from odoo.libs.intervals import Intervals
from odoo.tools import SQL
from odoo.tools.date_utils import get_intervals_hours, get_timedelta

from odoo.addons.base.models.resource_utils import filter_domain_leaf
from odoo.addons.project.models.project_task import (
    FINISH_ANCHORED_TYPES,
    START_CONSTRAINED_TYPES,
)

_debug = DebugLog(__name__)

FS_LINK = ("fs", timedelta(0))


def _link_anchor_field(dependency_type, start_date_field_name, stop_date_field_name):
    if dependency_type in FINISH_ANCHORED_TYPES:
        return stop_date_field_name
    return start_date_field_name


def _link_constrained_field(
    dependency_type, start_date_field_name, stop_date_field_name
):
    if dependency_type in START_CONSTRAINED_TYPES:
        return start_date_field_name
    return stop_date_field_name


def _is_link_violated(
    links, predecessor, successor, start_date_field_name, stop_date_field_name
) -> bool:
    dependency_type, lag = links.get((predecessor.id, successor.id), FS_LINK)
    anchor = _link_anchor_field(
        dependency_type, start_date_field_name, stop_date_field_name
    )
    constrained = _link_constrained_field(
        dependency_type, start_date_field_name, stop_date_field_name
    )
    return successor[constrained] < predecessor[anchor] + lag


class ProjectTask(models.Model):
    _name = "project.task"
    _inherit = "project.task"

    display_warning_dependency_in_gantt = fields.Boolean(
        export_string_translation=False,
        compute="_compute_display_warning_dependency_in_gantt",
    )

    gantt_dependency_types = fields.Json(
        export_string_translation=False,
        compute="_compute_gantt_dependency_types",
    )

    user_ids = fields.Many2many(group_expand="_group_expand_user_ids")
    partner_id = fields.Many2one(group_expand="_group_expand_partner_ids")
    project_id = fields.Many2one(group_expand="_group_expand_project_ids")

    @api.depends("is_closed")
    def _compute_display_warning_dependency_in_gantt(self) -> None:
        for task in self:
            task.display_warning_dependency_in_gantt = not task.is_closed

    @api.depends(
        "predecessor_ids", "dependency_ids.dependency_type", "dependency_ids.lag_hours"
    )
    def _compute_gantt_dependency_types(self) -> None:
        links_per_successor = defaultdict(dict)
        links = self._web_gantt_get_dependency_links()
        for (predecessor_id, successor_id), (dependency_type, lag) in links.items():
            links_per_successor[successor_id][str(predecessor_id)] = {
                "type": dependency_type,
                "lag": lag / timedelta(hours=1),
            }
        for task in self:
            task.gantt_dependency_types = links_per_successor.get(task._origin.id, {})

    def _get_additional_users(self, domain):
        return self.env["res.users"]

    def _group_expand_user_ids(self, users, domain):
        additional_users = self._get_additional_users(domain)
        if additional_users:
            return additional_users
        start_date = self.env.context.get("gantt_start_date")
        scale = self.env.context.get("gantt_scale")
        if not (start_date and scale):
            return additional_users
        domain = filter_domain_leaf(
            domain,
            lambda field: field not in ["date_start", "date_end", "state"],
        )
        search_on_comodel = self._search_on_comodel(domain, "user_ids", "res.users")
        if search_on_comodel:
            return search_on_comodel
        start_date = fields.Datetime.from_string(start_date)
        delta = get_timedelta(1, scale)
        domain_expand = (
            Domain(
                self._group_expand_user_ids_domain(
                    [
                        ("date_start", ">=", start_date - delta),
                        ("date_end", "<", start_date + delta),
                    ]
                )
            )
            & domain
        )
        return (
            self.search(domain_expand).user_ids.filtered(lambda user: user.active)
            | self.env.user
        )

    def _group_expand_user_ids_domain(self, domain_expand):
        project_id = self.env.context.get("default_project_id")
        if project_id:
            domain_expand = Domain.OR(
                [
                    [
                        ("project_id", "=", project_id),
                        ("is_closed", "=", False),
                        ("date_start", "=", False),
                        ("date_end", "=", False),
                    ],
                    domain_expand,
                ]
            )
        else:
            domain_expand = Domain.AND(
                [
                    [
                        ("project_id", "!=", False),
                    ],
                    domain_expand,
                ]
            )
        return domain_expand

    @api.model
    def _group_expand_project_ids(self, projects, domain):
        start_date = self.env.context.get("gantt_start_date")
        scale = self.env.context.get("gantt_scale")
        default_project_id = self.env.context.get("default_project_id")
        is_my_task = self.env.context.get("my_tasks")
        if not (start_date and scale) or default_project_id:
            return projects
        domain = self._expand_domain_dates(domain)
        filtered_domain = list(
            filter_domain_leaf(domain, lambda field: field == "project_id")
        )
        search_on_comodel = self._search_on_comodel(
            domain, "project_id", "project.project"
        )
        if search_on_comodel and (
            default_project_id or is_my_task or len(filtered_domain) > 1
        ):
            return search_on_comodel
        return self.search(domain).project_id

    @api.model
    def _group_expand_partner_ids(self, partners, domain):
        start_date = self.env.context.get("gantt_start_date")
        scale = self.env.context.get("gantt_scale")
        if not (start_date and scale):
            return partners
        domain = self._expand_domain_dates(domain)
        search_on_comodel = self._search_on_comodel(domain, "partner_id", "res.partner")
        if search_on_comodel:
            return search_on_comodel
        return self.search(domain).partner_id

    def _expand_domain_dates(self, domain):
        filters = []
        for dom in domain:
            if len(dom) == 3 and dom[0] == "date_end" and dom[1] == ">=":
                min_date = (
                    dom[2]
                    if isinstance(dom[2], datetime)
                    else datetime.strptime(dom[2], "%Y-%m-%d %H:%M:%S")
                )
                min_date -= get_timedelta(1, self.env.context.get("gantt_scale"))
                filters.append((dom[0], dom[1], min_date))
            else:
                filters.append(dom)
        return filters

    def schedule_tasks(self, vals):
        required_written_fields = {"date_start", "date_end"}
        if not self.env.context.get("last_date_view") or any(
            key not in vals for key in required_written_fields
        ):
            self.write(vals)
            return {}

        max_date_start = datetime.strptime(
            self.env.context.get("last_date_view"), "%Y-%m-%d %H:%M:%S"
        )
        return self.sorted(
            lambda t: (
                not t.date_end,
                t.date_end,
                t._get_hours_to_plan() <= 0,
                -int(t.priority),
            )
        )._schedule_tasks(vals, max_date_start)

    def action_rollback_auto_scheduling(self, old_vals_per_task_id) -> None:
        for task in self:
            if str(task.id) in old_vals_per_task_id:
                task.write(old_vals_per_task_id[str(task.id)])

    def _get_tasks_durations(self, users, start_date_field_name, stop_date_field_name):
        if not self:
            return {}

        scheduled = self.filtered(
            lambda task: task[start_date_field_name] and task[stop_date_field_name]
        )
        valid_intervals_per_user = {}
        if scheduled:
            valid_intervals_per_user, _dummy, _dummy = (
                self._scheduling_get_valid_intervals(
                    min(scheduled.mapped(start_date_field_name)),
                    max(scheduled.mapped(stop_date_field_name)),
                    users,
                    [],
                    False,
                )
            )

        duration_per_task = defaultdict(int)
        for task in self:
            reservations = task.reservation_ids.filtered("active")
            if reservations:
                if task.allocated_hours > 0:
                    duration_per_task[task.id] = (
                        task.allocated_hours / len(reservations) * 3600
                    )
                    continue
            elif task.planned_hours_manual and task.planned_hours > 0:
                duration_per_task[task.id] = task.planned_hours * 3600
                continue

            if task not in scheduled:
                continue

            task_start, task_end = (
                task[start_date_field_name].astimezone(UTC),
                task[stop_date_field_name].astimezone(UTC),
            )
            user_id = (task.user_ids.id,) if len(task.user_ids) == 1 else False
            work_intervals = valid_intervals_per_user.get(user_id, Intervals())
            for start, end, _dummy in work_intervals:
                start, end = start.astimezone(UTC), end.astimezone(UTC)
                if task_start < end and task_end > start:
                    duration_per_task[task.id] += (
                        min(task_end, end) - max(task_start, start)
                    ).total_seconds()

            if task.id not in duration_per_task:
                duration_per_task[task.id] = (
                    task.scheduled_hours * 3600
                    if task.scheduled_hours > 0
                    else (task.date_end - task.date_start).total_seconds()
                )

        return duration_per_task

    def _get_new_dates(
        self,
        valid_intervals_per_user,
        users_ids,
        search_forward,
        first_possible_start_date_per_candidate,
        last_possible_end_date_per_candidate,
        candidate_duration,
        move_in_conflicts_users=None,
    ) -> tuple:
        if move_in_conflicts_users is None:
            move_in_conflicts_users = set()

        intervals = valid_intervals_per_user[users_ids]._items
        intervals_durations = 0
        step = 1 if search_forward else -1
        index = 0 if search_forward else len(intervals) - 1
        used_intervals = []
        compute_start_date, compute_end_date = False, False
        while (
            users_ids not in move_in_conflicts_users
            and (
                (search_forward and index < len(intervals))
                or (not search_forward and index >= 0)
            )
            and candidate_duration > intervals_durations
        ):
            start, end, _dummy = intervals[index]
            index += step

            if search_forward:
                first_date = first_possible_start_date_per_candidate.get(self.id)
                if first_date and end <= first_date:
                    continue

                if not compute_start_date:
                    if first_date:
                        start = max(start, first_date)
                    compute_start_date = start

                compute_end_date = end
            else:
                last_date = last_possible_end_date_per_candidate.get(self.id)
                if last_date and start >= last_date:
                    continue

                if not compute_end_date:
                    if last_date:
                        end = min(end, last_date)
                    compute_end_date = end

                compute_start_date = start

            duration = (end - start).total_seconds()
            if intervals_durations + duration > candidate_duration:
                remaining = intervals_durations + duration - candidate_duration
                duration -= remaining
                if search_forward:
                    end += timedelta(seconds=-remaining)
                    compute_end_date = end
                else:
                    start += timedelta(seconds=remaining)
                    compute_start_date = start

            intervals_durations += duration
            used_intervals.append((start, end, self))

        return (
            used_intervals,
            intervals_durations,
            compute_start_date,
            compute_end_date,
        )

    def _web_gantt_get_dependency_links(self) -> dict:
        ids = self._origin.ids
        if not ids:
            return {}
        self.env["project.task.dependency"].flush_model(
            ["task_id", "depends_on_id", "dependency_type", "lag_hours"]
        )
        self.env.cr.execute(
            SQL(
                """
                SELECT depends_on_id, task_id, dependency_type, lag_hours
                  FROM project_task_dependency
                 WHERE task_id = ANY(%s)
                    OR depends_on_id = ANY(%s)
                """,
                ids,
                ids,
            )
        )
        return {
            (predecessor_id, successor_id): (dependency_type, timedelta(hours=lag))
            for predecessor_id, successor_id, dependency_type, lag in (
                self.env.cr.fetchall()
            )
        }

    def _web_gantt_is_candidate_in_conflict(
        self,
        start_date_field_name,
        stop_date_field_name,
        dependency_field_name,
        dependency_inverted_field_name,
    ) -> bool:
        links = self._web_gantt_get_dependency_links()
        return any(
            predecessor[start_date_field_name]
            and predecessor[stop_date_field_name]
            and _is_link_violated(
                links, predecessor, self, start_date_field_name, stop_date_field_name
            )
            for predecessor in self[dependency_field_name]
        ) or any(
            successor[start_date_field_name]
            and successor[stop_date_field_name]
            and _is_link_violated(
                links, self, successor, start_date_field_name, stop_date_field_name
            )
            for successor in self[dependency_inverted_field_name]
        )

    def _web_gantt_get_possible_dates_per_candidate(
        self,
        links,
        dependency_field_name,
        dependency_inverted_field_name,
        search_forward,
        start_date_field_name,
        stop_date_field_name,
        movable=None,
    ) -> dict:
        movable = self if movable is None else movable
        dates_per_field = {start_date_field_name: {}, stop_date_field_name: {}}
        for candidate in self:
            neighbours = (
                candidate[dependency_field_name]
                if search_forward
                else candidate[dependency_inverted_field_name]
            ).filtered(
                lambda pill: pill[start_date_field_name] and pill[stop_date_field_name]
            ) - movable
            for neighbour in neighbours:
                if search_forward:
                    dependency_type, lag = links.get(
                        (neighbour.id, candidate.id), FS_LINK
                    )
                    field = _link_constrained_field(
                        dependency_type, start_date_field_name, stop_date_field_name
                    )
                    date = (
                        neighbour[
                            _link_anchor_field(
                                dependency_type,
                                start_date_field_name,
                                stop_date_field_name,
                            )
                        ]
                        + lag
                    )
                    dates = dates_per_field[field]
                    dates[candidate.id] = max(dates.get(candidate.id, date), date)
                else:
                    dependency_type, lag = links.get(
                        (candidate.id, neighbour.id), FS_LINK
                    )
                    field = _link_anchor_field(
                        dependency_type, start_date_field_name, stop_date_field_name
                    )
                    date = (
                        neighbour[
                            _link_constrained_field(
                                dependency_type,
                                start_date_field_name,
                                stop_date_field_name,
                            )
                        ]
                        - lag
                    )
                    dates = dates_per_field[field]
                    dates[candidate.id] = min(dates.get(candidate.id, date), date)
        return {
            field: {
                candidate_id: date.astimezone(UTC)
                for candidate_id, date in dates.items()
            }
            for field, dates in dates_per_field.items()
        }

    def _web_gantt_get_typed_window_edge(
        self, links, search_forward, start_date_field_name, stop_date_field_name, edge
    ):
        records = {record.id: record for record in self}
        for (predecessor_id, successor_id), (dependency_type, lag) in links.items():
            if dependency_type == "fs" and lag >= timedelta(0):
                continue
            if predecessor_id not in records or successor_id not in records:
                continue
            pair = (records[predecessor_id], records[successor_id])
            lead = min(lag, timedelta(0))
            if search_forward:
                edge = min(
                    edge, *(record[start_date_field_name] + lead for record in pair)
                )
            else:
                edge = max(
                    edge, *(record[stop_date_field_name] - lead for record in pair)
                )
        return edge

    def _web_gantt_update_next_candidates_dates(
        self,
        cascade,
        dependency_field_name,
        dependency_inverted_field_name,
        search_forward,
        consume_buffer,
        start_date_field_name,
        stop_date_field_name,
        old_planned_date_begin,
        old_date_deadline,
        compute_start_date,
        compute_end_date,
    ) -> bool:
        links = cascade["links"]
        valid_intervals_per_user = cascade["valid_intervals_per_user"]
        valid_intervals_per_user_for_buffer_computes = cascade[
            "valid_intervals_per_user_for_buffer_computes"
        ]
        old_dates = {
            start_date_field_name: old_planned_date_begin,
            stop_date_field_name: old_date_deadline,
        }
        new_dates = {
            start_date_field_name: compute_start_date.astimezone(UTC),
            stop_date_field_name: compute_end_date.astimezone(UTC),
        }
        next_candidates = self[
            dependency_inverted_field_name if search_forward else dependency_field_name
        ]
        for task in next_candidates:
            if not task._web_gantt_reschedule_is_record_candidate(
                start_date_field_name, stop_date_field_name
            ):
                continue

            if search_forward:
                dependency_type, lag = links.get((self.id, task.id), FS_LINK)
                anchor = _link_anchor_field(
                    dependency_type, start_date_field_name, stop_date_field_name
                )
                constrained = _link_constrained_field(
                    dependency_type, start_date_field_name, stop_date_field_name
                )
                bounds = cascade[
                    "first_possible_start_date_per_candidate"
                    if constrained == start_date_field_name
                    else "first_possible_end_date_per_candidate"
                ]
                bound = new_dates[anchor] + lag
                bounds[task.id] = max(bounds.get(task.id, bound), bound)
                gap_start, gap_end = old_dates[anchor] + lag, task[constrained]
            else:
                dependency_type, lag = links.get((task.id, self.id), FS_LINK)
                anchor = _link_anchor_field(
                    dependency_type, start_date_field_name, stop_date_field_name
                )
                constrained = _link_constrained_field(
                    dependency_type, start_date_field_name, stop_date_field_name
                )
                bounds = cascade[
                    "last_possible_end_date_per_candidate"
                    if anchor == stop_date_field_name
                    else "last_possible_start_date_per_candidate"
                ]
                bound = new_dates[constrained] - lag
                bounds[task.id] = min(bounds.get(task.id, bound), bound)
                gap_start, gap_end = task[anchor] + lag, old_dates[constrained]
            _debug.logic(
                "link_bound",
                task=task,
                moved=self,
                dependency_type=dependency_type,
                lag=lag,
                field=constrained if search_forward else anchor,
                bound=bounds[task.id],
            )

            if consume_buffer or gap_end <= gap_start:
                continue
            calendar_owner = (
                tuple(self.user_ids.ids)
                if self.user_ids and self.user_ids == task.user_ids
                else False
            )
            seconds_between_tasks = (
                get_intervals_hours(
                    Intervals(
                        [
                            (
                                gap_start.astimezone(UTC),
                                gap_end.astimezone(UTC),
                                self.env["resource.calendar.attendance"],
                            )
                        ]
                    )
                    & valid_intervals_per_user_for_buffer_computes.get(
                        calendar_owner, Intervals()
                    )
                )
                * 3600
            )
            if seconds_between_tasks <= 0:
                continue
            if search_forward:
                _dummy, buffer_duration, _dummy, buffer_date = task._get_new_dates(
                    valid_intervals_per_user,
                    calendar_owner,
                    search_forward,
                    bounds,
                    {},
                    seconds_between_tasks,
                )
            else:
                _dummy, buffer_duration, buffer_date, _dummy = task._get_new_dates(
                    valid_intervals_per_user,
                    calendar_owner,
                    search_forward,
                    {},
                    bounds,
                    seconds_between_tasks,
                )
            if not buffer_date or buffer_duration < seconds_between_tasks:
                _debug.logic(
                    "buffer_not_kept",
                    task=task,
                    buffer_seconds=seconds_between_tasks,
                    found_seconds=buffer_duration,
                )
                return False
            bounds[task.id] = (
                max(bounds[task.id], buffer_date)
                if search_forward
                else min(bounds[task.id], buffer_date)
            )
            _debug.logic(
                "buffer_kept",
                task=task,
                buffer_seconds=seconds_between_tasks,
                bound=bounds[task.id],
            )

        return True

    def _web_gantt_get_valid_intervals_for_buffer(
        self,
        candidates_ids,
        start_date_field_name,
        stop_date_field_name,
        users,
        consume_buffer,
    ):
        if consume_buffer:
            return {}

        all_candidates = self.browse(candidates_ids)

        starts = all_candidates.filtered(start_date_field_name).mapped(
            start_date_field_name
        )
        stops = all_candidates.filtered(stop_date_field_name).mapped(
            stop_date_field_name
        )
        if not (starts and stops):
            return {}

        buffer_start_date = min(starts).astimezone(UTC)
        buffer_end_date = max(stops).astimezone(UTC)
        return all_candidates._scheduling_get_valid_intervals(
            buffer_start_date, buffer_end_date, users
        )[0]

    def _web_gantt_start_cascade(
        self,
        candidates,
        vals,
        old_vals_per_pill_id,
        search_forward,
        consume_buffer,
        start_date_field_name,
        stop_date_field_name,
        dependency_field_name,
        dependency_inverted_field_name,
    ):
        self.check_singleton()
        if "user_ids" in vals:
            new_user = vals["user_ids"]
            old_user_ids = self.user_ids.ids
            if not new_user:
                vals["user_ids"] = False
            else:
                user_to_assign = self.env["res.users"].browse(new_user)
                if user_to_assign.id not in old_user_ids:
                    vals["user_ids"] = user_to_assign.ids
            old_vals_per_pill_id[self.id]["user_ids"] = old_user_ids or False

        users = candidates.user_ids.sudo()
        valid_intervals_per_user_for_buffer_computes = (
            self._web_gantt_get_valid_intervals_for_buffer(
                [self.id, *candidates.ids],
                start_date_field_name,
                stop_date_field_name,
                users,
                consume_buffer,
            )
        )
        self.write(vals)
        links = (self | candidates)._web_gantt_get_dependency_links()

        if search_forward:
            start_date = self[stop_date_field_name]
            end_date = start_date + timedelta(weeks=53)
            start_date = max(
                fields.Datetime.now(),
                (self | candidates)._web_gantt_get_typed_window_edge(
                    links,
                    search_forward,
                    start_date_field_name,
                    stop_date_field_name,
                    start_date,
                ),
            )
        else:
            end_date = self[start_date_field_name]
            start_date = max(datetime.now(), end_date - timedelta(weeks=53))
            if end_date <= start_date:
                return {"error": "past_error"}
            end_date = (self | candidates)._web_gantt_get_typed_window_edge(
                links,
                search_forward,
                start_date_field_name,
                stop_date_field_name,
                end_date,
            )
        _debug.logic(
            "cascade_window",
            moved=self,
            forward=search_forward,
            start=start_date,
            end=end_date,
            links=len(links),
        )

        valid_intervals_per_user, _dummy, _dummy = (
            candidates._scheduling_get_valid_intervals(
                start_date, end_date, users, candidates.ids
            )
        )
        possible_dates = candidates._web_gantt_get_possible_dates_per_candidate(
            links,
            dependency_field_name,
            dependency_inverted_field_name,
            search_forward,
            start_date_field_name,
            stop_date_field_name,
        )
        cascade = {
            "links": links,
            "dependency_fields": (
                dependency_field_name,
                dependency_inverted_field_name,
            ),
            "moved_ids": {self.id},
            "window": (start_date, end_date),
            "users": users,
            "candidates": candidates,
            "first_possible_start_date_per_candidate": (
                possible_dates[start_date_field_name] if search_forward else {}
            ),
            "first_possible_end_date_per_candidate": (
                possible_dates[stop_date_field_name] if search_forward else {}
            ),
            "last_possible_end_date_per_candidate": (
                {} if search_forward else possible_dates[stop_date_field_name]
            ),
            "last_possible_start_date_per_candidate": (
                {} if search_forward else possible_dates[start_date_field_name]
            ),
            "valid_intervals_per_user": valid_intervals_per_user,
            "initial_valid_intervals_per_user": dict(valid_intervals_per_user.items()),
            "valid_intervals_per_user_for_buffer_computes": valid_intervals_per_user_for_buffer_computes,
            "move_in_conflicts_users": set(),
            "candidates_durations": candidates._get_tasks_durations(
                users, start_date_field_name, stop_date_field_name
            ),
            "used_intervals": {},
            "passed_initial_deadline": False,
            "moved_with_conflicts": False,
        }
        if not self._web_gantt_update_next_candidates_dates(
            cascade,
            dependency_field_name,
            dependency_inverted_field_name,
            search_forward,
            consume_buffer,
            start_date_field_name,
            stop_date_field_name,
            old_vals_per_pill_id[self.id][start_date_field_name],
            old_vals_per_pill_id[self.id][stop_date_field_name],
            self[start_date_field_name],
            self[stop_date_field_name],
        ):
            return {"error": "no_intervals_error"}
        return cascade

    def _web_gantt_place_candidate(
        self,
        cascade,
        search_forward,
        users_ids,
        candidate_duration,
        start_date_field_name,
        stop_date_field_name,
    ) -> tuple:
        valid_intervals_per_user = cascade["valid_intervals_per_user"]
        move_in_conflicts_users = cascade["move_in_conflicts_users"]
        if search_forward:
            pushed_by = "first_possible_end_date_per_candidate"
            held_by = "first_possible_start_date_per_candidate"
        else:
            pushed_by = "last_possible_start_date_per_candidate"
            held_by = "last_possible_end_date_per_candidate"
        pushed_bound = cascade[pushed_by].get(self.id)
        if pushed_bound is None:
            return self._get_new_dates(
                valid_intervals_per_user,
                users_ids,
                search_forward,
                cascade["first_possible_start_date_per_candidate"],
                cascade["last_possible_end_date_per_candidate"],
                candidate_duration,
                move_in_conflicts_users,
            )

        own_date = self[
            start_date_field_name if search_forward else stop_date_field_name
        ].astimezone(UTC)
        held_bound = cascade[held_by].get(self.id)
        if search_forward:
            held_bound = max(held_bound or own_date, own_date)
            laid = self._get_new_dates(
                valid_intervals_per_user,
                users_ids,
                False,
                {},
                {self.id: pushed_bound},
                candidate_duration,
                move_in_conflicts_users,
            )
            used_intervals, placed, laid_start, laid_end = laid
            fits = bool(
                placed == candidate_duration and laid_start and laid_start >= held_bound
            )
        else:
            held_bound = min(held_bound or own_date, own_date)
            laid = self._get_new_dates(
                valid_intervals_per_user,
                users_ids,
                True,
                {self.id: pushed_bound},
                {},
                candidate_duration,
                move_in_conflicts_users,
            )
            used_intervals, placed, laid_start, laid_end = laid
            fits = bool(
                placed == candidate_duration and laid_end and laid_end <= held_bound
            )
        if not fits:
            _debug.logic(
                "candidate_held_by_bound",
                task=self,
                forward=search_forward,
                pushed_by=pushed_bound,
                held_by=held_bound,
            )
            return self._get_new_dates(
                valid_intervals_per_user,
                users_ids,
                search_forward,
                {self.id: held_bound},
                {self.id: held_bound},
                candidate_duration,
                move_in_conflicts_users,
            )

        gap = (laid_end, pushed_bound) if search_forward else (pushed_bound, laid_start)
        if gap[0] < gap[1] and self._web_gantt_has_working_time(
            cascade, users_ids, *gap
        ):
            _debug.logic(
                "candidate_past_booked_time",
                task=self,
                forward=search_forward,
                pushed_by=pushed_bound,
                gap=gap,
            )
            return self._get_new_dates(
                valid_intervals_per_user,
                users_ids,
                search_forward,
                {self.id: pushed_bound},
                {self.id: pushed_bound},
                candidate_duration,
                move_in_conflicts_users,
            )
        _debug.logic(
            "candidate_laid_on_bound",
            task=self,
            forward=search_forward,
            pushed_by=pushed_bound,
            start=laid_start,
            end=laid_end,
        )
        if search_forward:
            return used_intervals, placed, laid_start, pushed_bound
        return used_intervals, placed, pushed_bound, laid_end

    def _web_gantt_has_working_time(self, cascade, users_ids, start, end) -> bool:
        if "calendar_intervals_per_user" not in cascade:
            cascade["calendar_intervals_per_user"] = cascade[
                "candidates"
            ]._scheduling_get_valid_intervals(
                *cascade["window"], cascade["users"], [], False
            )[0]
        gap = Intervals([(start, end, self.env["resource.calendar.attendance"])])
        return bool(
            gap & cascade["calendar_intervals_per_user"].get(users_ids, Intervals())
        )

    def _web_gantt_add_bounds_of_tasks_left_in_place(
        self, cascade, search_forward, start_date_field_name, stop_date_field_name
    ) -> None:
        dependency_field_name, dependency_inverted_field_name = cascade[
            "dependency_fields"
        ]
        neighbours = self[
            dependency_field_name if search_forward else dependency_inverted_field_name
        ]
        left_in_place = (neighbours & cascade["candidates"]).filtered(
            lambda task: task.id not in cascade["moved_ids"]
        )
        if not left_in_place:
            return
        possible_dates = self._web_gantt_get_possible_dates_per_candidate(
            cascade["links"],
            dependency_field_name,
            dependency_inverted_field_name,
            search_forward,
            start_date_field_name,
            stop_date_field_name,
            movable=self | (neighbours - left_in_place),
        )
        if search_forward:
            bounds_per_field = {
                start_date_field_name: "first_possible_start_date_per_candidate",
                stop_date_field_name: "first_possible_end_date_per_candidate",
            }
            tighter = max
        else:
            bounds_per_field = {
                start_date_field_name: "last_possible_start_date_per_candidate",
                stop_date_field_name: "last_possible_end_date_per_candidate",
            }
            tighter = min
        for field, key in bounds_per_field.items():
            date = possible_dates[field].get(self.id)
            if date is None:
                continue
            bounds = cascade[key]
            bounds[self.id] = tighter(bounds.get(self.id, date), date)
            _debug.logic(
                "bound_from_task_left_in_place",
                task=self,
                left_in_place=left_in_place,
                field=field,
                bound=bounds[self.id],
            )

    def _web_gantt_cascade_dates(
        self, cascade, search_forward, start_date_field_name, stop_date_field_name
    ) -> str | tuple:
        valid_intervals_per_user = cascade["valid_intervals_per_user"]
        candidate_duration = cascade["candidates_durations"][self.id]
        users_ids = tuple(self.user_ids.ids) if self.user_ids else False
        if users_ids not in valid_intervals_per_user:
            return "no_intervals_error"
        self._web_gantt_add_bounds_of_tasks_left_in_place(
            cascade, search_forward, start_date_field_name, stop_date_field_name
        )

        (
            used_intervals,
            intervals_durations,
            compute_start_date,
            compute_end_date,
        ) = self._web_gantt_place_candidate(
            cascade,
            search_forward,
            users_ids,
            candidate_duration,
            start_date_field_name,
            stop_date_field_name,
        )
        cascade["used_intervals"][self.id] = (users_ids, used_intervals)

        if (
            users_ids not in cascade["move_in_conflicts_users"]
            and candidate_duration == intervals_durations
            and compute_start_date
            and compute_end_date
        ):
            cascade["passed_initial_deadline"] = cascade["passed_initial_deadline"] or (
                not self[start_date_field_name]
                and compute_end_date > self[stop_date_field_name].astimezone(UTC)
            )
            return compute_start_date, compute_end_date

        initial_valid_intervals_per_user = cascade["initial_valid_intervals_per_user"]
        if (
            users_ids not in initial_valid_intervals_per_user
            or len(initial_valid_intervals_per_user[users_ids]._items) == 0
        ):
            return "no_intervals_error"

        cascade["moved_with_conflicts"] = True
        cascade["move_in_conflicts_users"].add(users_ids)
        final_interval_index = -1 if search_forward else 0
        ranges = initial_valid_intervals_per_user[users_ids]._items
        compute_start_date = ranges[final_interval_index][0]
        compute_end_date = ranges[final_interval_index][1]
        needed_intervals_duration = 0
        searching_step = -1 if search_forward else 1
        searching_index = len(ranges) if search_forward else -1
        while (
            (search_forward and searching_index - 1 > 0)
            or (not search_forward and searching_index + 1 < len(ranges))
        ) and candidate_duration > needed_intervals_duration:
            searching_index += searching_step
            start, end, _dummy = ranges[searching_index]
            start, end = start.astimezone(UTC), end.astimezone(UTC)
            if search_forward:
                compute_start_date = start
            else:
                compute_end_date = end

            needed_intervals_duration += (end - start).total_seconds()

        if candidate_duration <= needed_intervals_duration:
            remaining = needed_intervals_duration - candidate_duration
            if search_forward:
                compute_start_date += timedelta(seconds=remaining)
            else:
                compute_end_date += timedelta(seconds=-remaining)
        elif candidate_duration > needed_intervals_duration:
            needed = candidate_duration - needed_intervals_duration
            if search_forward:
                compute_start_date += timedelta(seconds=-needed)
            else:
                compute_end_date += timedelta(seconds=needed)
        return compute_start_date, compute_end_date

    def _web_gantt_cascade_moved(
        self,
        cascade,
        search_forward,
        consume_buffer,
        start_date_field_name,
        stop_date_field_name,
        dependency_field_name,
        dependency_inverted_field_name,
        old_start_date,
        old_end_date,
        start_date,
        end_date,
    ) -> str | None:
        valid_intervals_per_user = cascade["valid_intervals_per_user"]
        if not self._web_gantt_update_next_candidates_dates(
            cascade,
            dependency_field_name,
            dependency_inverted_field_name,
            search_forward,
            consume_buffer,
            start_date_field_name,
            stop_date_field_name,
            old_start_date,
            old_end_date,
            start_date,
            end_date,
        ):
            return "no_intervals_error"

        cascade["moved_ids"].add(self.id)
        users_ids, used_intervals = cascade["used_intervals"].pop(self.id)
        used_intervals = Intervals(used_intervals)
        if not users_ids:
            valid_intervals_per_user[False] -= used_intervals
        else:
            users_ids_set = set(users_ids)
            for user in valid_intervals_per_user:
                if user and not users_ids_set.isdisjoint(user):
                    valid_intervals_per_user[user] -= used_intervals
        return None

    def _web_gantt_cascade_warnings(self, cascade):
        warnings = []
        if cascade["passed_initial_deadline"]:
            warnings.append("initial_deadline")
        if cascade["moved_with_conflicts"]:
            warnings.append("conflict")
        return warnings

    def _web_gantt_record_has_dependencies(self):
        self.check_singleton()
        return self.project_id.allow_dependencies

    def _web_gantt_reschedule_can_record_be_rescheduled(
        self, start_date_field_name, stop_date_field_name
    ):
        self.check_singleton()
        return (
            super()._web_gantt_reschedule_can_record_be_rescheduled(
                start_date_field_name, stop_date_field_name
            )
            and not self.is_closed
        )

    def _web_gantt_reschedule_is_record_candidate(
        self, start_date_field_name, stop_date_field_name
    ):
        self.check_singleton()
        return (
            super()._web_gantt_reschedule_is_record_candidate(
                start_date_field_name, stop_date_field_name
            )
            and self._web_gantt_record_has_dependencies()
        )

    def _web_gantt_get_reschedule_message_per_key(self, key, params=None):
        message = super()._web_gantt_get_reschedule_message_per_key(key, params)
        if message:
            return message

        if key == "no_intervals_error":
            return self.env._(
                "The tasks could not be rescheduled due to the assignees' lack of availability at this time."
            )
        elif key == "initial_deadline":
            return self.env._("Some tasks were planned after their initial deadline.")
        elif key == "conflict":
            return self.env._(
                "Some tasks were scheduled concurrently, resulting in a conflict due to the limited availability of the assignees. The planned dates for these tasks may not align with their allocated hours."
            )
        else:
            return ""

    @api.model
    def _gantt_unavailability(self, field_name, res_ids, start, stop, scale):
        resources = self.env["resource.resource"]
        if field_name in ["user_ids", "user_id"]:
            resources = self.env["resource.resource"].search(
                [
                    ("user_id", "in", res_ids),
                    ("company_id", "in", self.env.companies.ids),
                ],
                order="create_date",
            )
        user_resource_mapping = {
            resource.user_id.id: resource.id for resource in resources
        }
        leaves_mapping = resources._get_unavailable_intervals(start, stop)
        company_calendar = self.env.company.resource_calendar_id
        company_leaves = (
            []
            if company_calendar.schedule_type == "flexible"
            else company_calendar._unavailable_intervals(
                start.replace(tzinfo=UTC), stop.replace(tzinfo=UTC)
            )
        )

        cell_dt = (
            timedelta(hours=1) if scale in ["day", "week"] else timedelta(hours=12)
        )

        result = {}
        for user_id in res_ids + [False]:
            resource_id = user_resource_mapping.get(user_id)
            calendar = leaves_mapping.get(resource_id, company_leaves)
            notable_intervals = filter(
                lambda interval: interval[1] - interval[0] >= cell_dt, calendar
            )
            result[user_id] = [
                {"start": interval[0], "stop": interval[1]}
                for interval in notable_intervals
            ]

        return result

    def web_gantt_write(self, data):
        res = True

        if any(
            f_name in self._fields
            and self._fields[f_name].type == "many2many"
            and value
            and len(value) == 1
            for f_name, value in data.items()
        ):
            record_ids_per_m2m_field_names = defaultdict(list)
            full_write_record_ids = []
            for record in self:
                fields_to_remove = []
                for f_name, value in data.items():
                    if (
                        value
                        and f_name in record._fields
                        and record._fields[f_name].type == "many2many"
                        and len(value) == 1
                        and value[0] in record[f_name].ids
                    ):
                        fields_to_remove.append(f_name)
                if fields_to_remove:
                    record_ids_per_m2m_field_names[tuple(fields_to_remove)].append(
                        record.id
                    )
                else:
                    full_write_record_ids.append(record.id)
            if record_ids_per_m2m_field_names:
                if full_write_record_ids:
                    res &= self.browse(full_write_record_ids).write(data)
                for (
                    fields_to_remove_from_data,
                    record_ids,
                ) in record_ids_per_m2m_field_names.items():
                    res &= self.browse(record_ids).write(
                        {
                            f_name: value
                            for f_name, value in data.items()
                            if f_name not in fields_to_remove_from_data
                        }
                    )
            else:
                res &= self.write(data)
        else:
            res &= self.write(data)

        return res

    def _gantt_progress_bar_user_ids(self, res_ids, start, stop) -> dict:
        start_naive, stop_naive = start.replace(tzinfo=None), stop.replace(tzinfo=None)
        users = self.env["res.users"].search([("id", "in", res_ids)])
        self.env["project.task"].check_access("read")

        project_tasks = (
            self.env["project.task"]
            .sudo()
            .search(
                [
                    ("user_ids", "in", res_ids),
                    ("date_start", "<=", stop_naive),
                    ("date_end", ">=", start_naive),
                    ("company_id", "in", [*self.env.companies.ids, False]),
                ]
            )
        )
        project_tasks = project_tasks.with_context(prefetch_fields=False)
        project_tasks.fetch(["date_start", "date_end", "user_ids"])
        users_work_intervals, _dummy = users.sudo()._get_valid_work_intervals(
            start, stop
        )
        planned_hours_mapped = project_tasks._planned_hours_per_user_for_scale(
            users, start, stop
        )
        work_hours = {
            user_id: get_intervals_hours(work_intervals)
            for user_id, work_intervals in users_work_intervals.items()
        }
        return {
            user.id: {
                "value": planned_hours_mapped[user.id],
                "max_value": work_hours.get(user.id, 0.0),
            }
            for user in users
        }

    def _planned_hours_per_user_for_scale(self, users, start, stop):
        absolute_max_end, absolute_min_start = stop, start
        planned_hours_mapped = defaultdict(float)
        for task in self:
            absolute_max_end = max(absolute_max_end, task.date_end.replace(tzinfo=UTC))
            absolute_min_start = min(
                absolute_min_start, task.date_start.replace(tzinfo=UTC)
            )
        users_work_intervals, _dummy = users.sudo()._get_valid_work_intervals(
            absolute_min_start, absolute_max_end
        )
        for task in self:
            task_date_begin = task.date_start.replace(tzinfo=UTC)
            task_deadline = task.date_end.replace(tzinfo=UTC)
            max_start = max(start, task_date_begin)
            min_end = min(stop, task_deadline)
            for user in task.user_ids:
                work_intervals_for_scale = get_intervals_hours(
                    users_work_intervals[user.id]
                    & Intervals(
                        [(max_start, min_end, self.env["resource.calendar.attendance"])]
                    )
                )
                work_intervals_for_task = get_intervals_hours(
                    users_work_intervals[user.id]
                    & Intervals(
                        [
                            (
                                task_date_begin,
                                task_deadline,
                                self.env["resource.calendar.attendance"],
                            )
                        ]
                    )
                )
                ratio = 1
                if work_intervals_for_task:
                    ratio = work_intervals_for_scale / work_intervals_for_task
                planned_hours_mapped[user.id] += (
                    task.planned_hours / len(task.user_ids)
                ) * ratio

        return planned_hours_mapped

    def _gantt_progress_bar(self, field_name, res_ids, start, stop):
        if not self.env.user.has_group("project.group_project_user"):
            return {}
        if field_name == "user_ids":
            start, stop = start.replace(tzinfo=UTC), stop.replace(tzinfo=UTC)
            return dict(
                self._gantt_progress_bar_user_ids(res_ids, start, stop),
                warning=self.env._(
                    "This user isn't expected to have any tasks assigned during this period because they don't have any running contract."
                ),
            )
        raise NotImplementedError("This Progress Bar is not implemented.")

    def _prepare_domains_for_all_deadlines(self, date_start, date_end):
        return {
            "project": [
                ("date", ">=", date_start),
                ("date_start", "<=", date_end),
            ],
            "milestone": [
                ("date_deadline", ">=", date_start),
                ("date_deadline", "<=", date_end),
                ("project_allow_milestones", "=", True),
            ],
        }

    @api.model
    @api.readonly
    def get_all_deadlines(self, date_start, date_end):
        results = {}
        project_id = self.env.context.get("default_project_id", False)
        result_domains = self._prepare_domains_for_all_deadlines(date_start, date_end)
        project_domain = Domain(result_domains["project"])
        milestone_domain = Domain(result_domains["milestone"])

        if project_id:
            project_domain &= Domain("id", "=", project_id)
            milestone_domain &= Domain("project_id", "=", project_id)
        results["project_id"] = self.env["project.project"].search_read(
            project_domain, ["id", "name", "date", "date_start"]
        )
        results["milestone_id"] = self.env["project.milestone"].search_read(
            milestone_domain,
            [
                "name",
                "date_deadline",
                "is_deadline_exceeded",
                "is_reached",
                "project_id",
            ],
        )
        return results

    def action_view_overlapping_tasks(self):
        action = super().action_view_overlapping_tasks()
        if "views" in action:
            gantt_view = self.env.ref(
                "project_gantt.project_task_dependency_view_gantt"
            )
            action["views"] = [(gantt_view.id, "gantt")] + [
                (view_id, view_type)
                for view_id, view_type in action["views"]
                if view_type != "gantt"
            ]
        return action

    def action_dependent_tasks(self):
        action = super().action_dependent_tasks()
        action["view_mode"] = self._add_gantt_view_mode(action["view_mode"])
        return action

    def action_recurring_tasks(self):
        action = super().action_recurring_tasks()
        action["view_mode"] = self._add_gantt_view_mode(action["view_mode"])
        return action

    @api.model
    def _add_gantt_view_mode(self, view_mode) -> str:
        modes = view_mode.split(",")
        if "gantt" not in modes:
            index = modes.index("activity") if "activity" in modes else len(modes)
            modes.insert(max(index, 1), "gantt")
        return ",".join(modes)
