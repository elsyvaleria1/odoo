from collections import defaultdict
from datetime import UTC, datetime, timedelta

from lxml.builder import E

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import OrderedSet, unique

DATE_FIELD_ADAPTERS = {
    "date": {
        "parse": fields.Date.to_date,
        "now": fields.Date.today,
    },
    "datetime": {
        "parse": fields.Datetime.to_datetime,
        "now": fields.Datetime.now,
    },
}


def _as_utc(value):
    if isinstance(value, datetime):
        return value.astimezone(UTC)
    return value


def _relational_group_id(value):
    return value[0] if isinstance(value, list | tuple) and value else None


def _as_stored(value):
    if isinstance(value, datetime):
        return value.astimezone(UTC).replace(tzinfo=None)
    return value


class Base(models.AbstractModel):
    _inherit = "base"

    _start_name = "date_start"
    _stop_name = "date_stop"

    _WEB_GANTT_RESCHEDULE_FORWARD = "forward"
    _WEB_GANTT_RESCHEDULE_BACKWARD = "backward"
    _WEB_GANTT_RESCHEDULE_MAINTAIN_BUFFER = "maintainBuffer"
    _WEB_GANTT_RESCHEDULE_CONSUME_BUFFER = "consumeBuffer"
    _WEB_GANTT_LOOP_ERROR = "loop_error"

    @api.model
    def _get_default_gantt_view(self):
        view = E.gantt(string=self._description)

        gantt_field_names = {
            "date_start": (
                self._start_name,
                ["date_start", "start_date", "x_date_start", "x_start_date"],
            ),
            "date_stop": (
                self._stop_name,
                [
                    "date_stop",
                    "stop_date",
                    "date_end",
                    "end_date",
                    "x_date_stop",
                    "x_stop_date",
                    "x_date_end",
                    "x_end_date",
                ],
            ),
        }
        for attribute, (declared, candidates) in gantt_field_names.items():
            field_name = declared if declared in self._fields else None
            if field_name is None:
                field_name = next((dt for dt in candidates if dt in self._fields), None)
            if field_name is None:
                raise UserError(self.env._("Insufficient fields for Gantt View!"))
            view.set(attribute, field_name)

        return view

    @api.model
    def _get_fields_view(self, view_type, view_models):
        if view_type == "gantt":
            view_models[self._name] = set(self._fields)
            return view_models
        return super()._get_fields_view(view_type, view_models)

    @api.model
    @api.readonly
    def get_gantt_data(
        self,
        domain,
        groupby,
        read_specification,
        limit=None,
        offset=0,
        unavailability_fields=None,
        progress_bar_fields=None,
        start_date=None,
        stop_date=None,
        scale=None,
    ):
        if groupby:
            groups, length = self.with_context(
                read_group_expand=True
            )._get_formatted_read_group_with_length(
                domain,
                groupby,
                ["id:array_agg"],
                offset=offset,
                limit=limit,
            )

            final_result = {
                "groups": groups,
                "length": length,
            }

            all_record_ids = tuple(
                unique(
                    record_id
                    for one_group in groups
                    for record_id in one_group["id:array_agg"]
                )
            )

            all_records = self.with_context(active_test=False).search_fetch(
                [("id", "in", all_record_ids)], read_specification.keys()
            )
        else:
            all_records = self.search_fetch(domain, read_specification.keys())
            final_result = {
                "groups": [
                    {
                        "id:array_agg": all_records._ids,
                        "__extra_domain": [],
                    }
                ],
                "length": 1,
            }

        final_result["records"] = all_records.with_env(self.env).web_read(
            read_specification
        )

        if unavailability_fields is None:
            unavailability_fields = []
        if progress_bar_fields is None:
            progress_bar_fields = []

        start = fields.Datetime.from_string(start_date)
        stop = fields.Datetime.from_string(stop_date)

        ordered_set_ids = OrderedSet(all_records._ids)
        res_ids_for_unavailabilities = defaultdict(set)
        res_ids_for_progress_bars = defaultdict(set)
        for group in final_result["groups"]:
            for field in unavailability_fields:
                if res_id := _relational_group_id(group.get(field)):
                    res_ids_for_unavailabilities[field].add(res_id)
            for field in progress_bar_fields:
                if res_id := _relational_group_id(group.get(field)):
                    res_ids_for_progress_bars[field].add(res_id)
            group["__record_ids"] = list(
                ordered_set_ids & OrderedSet(group.pop("id:array_agg"))
            )
            del group["__extra_domain"]
            group.pop("__fold", None)

        unavailabilities = {}
        for field in unavailability_fields:
            unavailabilities[field] = self._gantt_unavailability(
                field, list(res_ids_for_unavailabilities[field]), start, stop, scale
            )
        final_result["unavailabilities"] = unavailabilities

        progress_bars = {}
        for field in progress_bar_fields:
            progress_bars[field] = self._gantt_progress_bar(
                field, list(res_ids_for_progress_bars[field]), start, stop
            )
        final_result["progress_bars"] = progress_bars

        return final_result

    def web_gantt_init_old_vals_per_pill_id(self, vals):
        old_vals_per_pill_id = defaultdict(dict)
        fields_data = self.fields_get(list(vals))
        for field in vals:
            field_type = fields_data[field]["type"]
            if field_type in ["many2many", "one2many"]:
                old_vals_per_pill_id[self.id][field] = self[field].ids or False
            elif field_type == "many2one":
                old_vals_per_pill_id[self.id][field] = self[field].id or False
            else:
                old_vals_per_pill_id[self.id][field] = self[field]

        return old_vals_per_pill_id

    @api.model
    def web_gantt_reschedule(
        self,
        vals,
        reschedule_method,
        record_id,
        dependency_field_name,
        dependency_inverted_field_name,
        start_date_field_name,
        stop_date_field_name,
    ) -> dict:

        if reschedule_method not in (
            self._WEB_GANTT_RESCHEDULE_CONSUME_BUFFER,
            self._WEB_GANTT_RESCHEDULE_MAINTAIN_BUFFER,
        ):
            raise ValueError(f"Invalid reschedule method {reschedule_method}")
        self._web_gantt_check_field_names(
            (start_date_field_name, stop_date_field_name),
            ("date", "datetime"),
        )
        self._web_gantt_check_field_names(
            (dependency_field_name, dependency_inverted_field_name),
            ("many2many", "one2many"),
        )

        record = self.env[self._name].browse(record_id)
        record.check_singleton()

        message = self.env._("Tasks rescheduled")
        start_date_field = self.env[self._name]._fields[start_date_field_name]
        start_date = now_value = None
        if start_date_field_name in vals:
            start_date = DATE_FIELD_ADAPTERS[start_date_field.type]["parse"](
                vals[start_date_field_name]
            )
            now_value = DATE_FIELD_ADAPTERS[start_date_field.type]["now"]()
        if not (
            start_date_field_name in vals
            and stop_date_field_name in vals
            and dependency_field_name
            and dependency_inverted_field_name
        ) or (start_date and start_date < now_value):
            old_vals_per_pill_id = record.web_gantt_init_old_vals_per_pill_id(vals)
            record.write(vals)
            return {
                "type": "success",
                "message": message,
                "old_vals_per_pill_id": old_vals_per_pill_id,
            }

        try:
            with self.env.cr.savepoint() as sp:
                log_messages, old_vals_per_pill_id = (
                    record._web_gantt_action_reschedule_candidates(
                        dependency_field_name,
                        dependency_inverted_field_name,
                        start_date_field_name,
                        stop_date_field_name,
                        reschedule_method,
                        vals,
                    )
                )
                has_errors = bool(log_messages.get("errors"))
                sp.close(rollback=has_errors)
        except AccessError as error:
            return {
                "type": "warning",
                "message": str(error.args[0]) if error.args else "",
                "old_vals_per_pill_id": {},
            }
        notification_type = "success"
        if has_errors or log_messages.get("warnings"):
            message = self._web_gantt_get_reschedule_message(log_messages)
            notification_type = "warning" if has_errors else "info"
        return {
            "type": notification_type,
            "message": message,
            "old_vals_per_pill_id": old_vals_per_pill_id,
        }

    def action_rollback_scheduling(self, old_vals_per_pill_id) -> None:
        for record in self:
            vals = old_vals_per_pill_id.get(
                str(record.id), old_vals_per_pill_id.get(record.id)
            )
            if vals:
                record.write(vals)

    def gantt_undo_drag_drop(self, drag_action, data=None):
        if not self.exists():
            return False
        if drag_action == "copy":
            return self.unlink()
        elif drag_action == "reschedule" and data:
            return self.write(data)
        return False

    @api.model
    def _gantt_progress_bar(
        self, field_name: str, res_ids: list[int], start: datetime, stop: datetime
    ):
        return {}

    @api.model
    def _gantt_unavailability(self, field_name, res_ids, start, stop, scale):
        return {}

    def _web_gantt_get_reschedule_message_per_key(self, key, params=None):
        if key == self._WEB_GANTT_LOOP_ERROR:
            return self.env._("The dependencies are not valid, there is a cycle.")
        elif key == "past_error":
            if params:
                return self.env._(
                    "%s cannot be scheduled in the past", params.display_name
                )
            else:
                return self.env._("Impossible to schedule in the past.")
        else:
            return ""

    def _web_gantt_get_reschedule_message(self, log_messages) -> str:
        def get_messages(logs):
            messages = []
            for key in logs:
                message = self._web_gantt_get_reschedule_message_per_key(
                    key, log_messages.get(key)
                )
                if message:
                    messages.append(message)
            return messages

        errors = log_messages.get("errors")
        keys = errors or log_messages.get("warnings", [])
        return "\n".join(get_messages(keys))

    @api.model
    def _web_gantt_check_field_names(self, names, types) -> None:
        for name in names:
            field = self._fields.get(name)
            if not field or field.type not in types:
                raise UserError(
                    self.env._(
                        "%(field)s is not a %(types)s field of %(model)s",
                        field=name,
                        types=" / ".join(types),
                        model=self._name,
                    )
                )

    def _web_gantt_get_direction(self, start_date_field_name, vals):
        start_date_field = self.env[self._name]._fields[start_date_field_name]
        date_start = DATE_FIELD_ADAPTERS[start_date_field.type]["parse"](
            vals[start_date_field_name]
        )
        old_start = self[start_date_field_name]
        return (
            self._WEB_GANTT_RESCHEDULE_FORWARD
            if not old_start or date_start > old_start
            else self._WEB_GANTT_RESCHEDULE_BACKWARD
        )

    def _web_gantt_action_reschedule_candidates(
        self,
        dependency_field_name,
        dependency_inverted_field_name,
        start_date_field_name,
        stop_date_field_name,
        reschedule_method,
        vals,
    ):

        search_forward = (
            self._web_gantt_get_direction(start_date_field_name, vals)
            == self._WEB_GANTT_RESCHEDULE_FORWARD
        )
        candidates_ids = []
        if self._web_gantt_check_cycle_existence_and_get_rescheduling_candidates(
            candidates_ids,
            dependency_inverted_field_name if search_forward else dependency_field_name,
            start_date_field_name,
            stop_date_field_name,
        ):
            return {"errors": [self._WEB_GANTT_LOOP_ERROR]}, {}
        candidates_ids.reverse()

        return self._web_gantt_move_candidates(
            start_date_field_name,
            stop_date_field_name,
            dependency_field_name,
            dependency_inverted_field_name,
            search_forward,
            candidates_ids,
            reschedule_method == self._WEB_GANTT_RESCHEDULE_CONSUME_BUFFER,
            vals,
        )

    def _web_gantt_is_candidate_in_conflict(
        self,
        start_date_field_name,
        stop_date_field_name,
        dependency_field_name,
        dependency_inverted_field_name,
    ) -> bool:
        return any(
            r[start_date_field_name]
            and r[stop_date_field_name]
            and self[start_date_field_name] < r[stop_date_field_name]
            for r in self[dependency_field_name]
        ) or any(
            r[start_date_field_name]
            and r[stop_date_field_name]
            and self[stop_date_field_name] > r[start_date_field_name]
            for r in self[dependency_inverted_field_name]
        )

    def _web_gantt_update_next_pills_first_possible_date(
        self,
        dependency_field_name,
        dependency_inverted_field_name,
        search_forward,
        first_possible_start_date_per_candidate,
        last_possible_end_date_per_candidate,
        consume_buffer,
        start_date_field_name,
        stop_date_field_name,
        start_date,
        end_date,
        old_start_date,
        old_end_date,
    ) -> None:
        for neighbour in self[
            dependency_inverted_field_name if search_forward else dependency_field_name
        ]:
            if not (
                neighbour[start_date_field_name] and neighbour[stop_date_field_name]
            ):
                continue
            if search_forward:
                end_date = _as_utc(end_date)
                first_possible_start_date_per_candidate[neighbour.id] = max(
                    first_possible_start_date_per_candidate.get(neighbour.id, end_date),
                    end_date,
                )
                if (
                    not consume_buffer
                    and neighbour[start_date_field_name] > old_end_date
                ):
                    buffer_duration = (
                        neighbour[start_date_field_name] - old_end_date
                    ).total_seconds()
                    start_date_after_buffer = end_date + timedelta(
                        seconds=buffer_duration
                    )
                    first_possible_start_date_per_candidate[neighbour.id] = max(
                        first_possible_start_date_per_candidate.get(
                            neighbour.id, start_date_after_buffer
                        ),
                        start_date_after_buffer,
                    )
            else:
                start_date = _as_utc(start_date)
                last_possible_end_date_per_candidate[neighbour.id] = min(
                    last_possible_end_date_per_candidate.get(neighbour.id, start_date),
                    start_date,
                )
                if (
                    not consume_buffer
                    and neighbour[stop_date_field_name] < old_start_date
                ):
                    buffer_duration = (
                        old_start_date - neighbour[stop_date_field_name]
                    ).total_seconds()
                    end_date_after_buffer = start_date - timedelta(
                        seconds=buffer_duration
                    )
                    last_possible_end_date_per_candidate[neighbour.id] = min(
                        last_possible_end_date_per_candidate.get(
                            neighbour.id, end_date_after_buffer
                        ),
                        end_date_after_buffer,
                    )

    def _web_gantt_get_first_and_last_possible_dates(
        self,
        dependency_field_name,
        dependency_inverted_field_name,
        search_forward,
        stop_date_field_name,
        start_date_field_name,
    ) -> tuple:
        first_possible_start_date_per_candidate = {}
        last_possible_end_date_per_candidate = {}

        for candidate in self:
            related_candidates = (
                candidate[dependency_field_name]
                if search_forward
                else candidate[dependency_inverted_field_name]
            ).filtered(
                lambda pill: pill[start_date_field_name] and pill[stop_date_field_name]
            )
            not_replanned_candidates = related_candidates - self

            if not not_replanned_candidates:
                continue

            boundary_date = (
                stop_date_field_name if search_forward else start_date_field_name
            )
            boundary_dates = not_replanned_candidates.mapped(boundary_date)

            if search_forward:
                first_possible_start_date_per_candidate[candidate.id] = _as_utc(
                    max(boundary_dates)
                )
            else:
                last_possible_end_date_per_candidate[candidate.id] = _as_utc(
                    min(boundary_dates)
                )

        return (
            first_possible_start_date_per_candidate,
            last_possible_end_date_per_candidate,
        )

    def _web_gantt_move_candidates(
        self,
        start_date_field_name,
        stop_date_field_name,
        dependency_field_name,
        dependency_inverted_field_name,
        search_forward,
        candidates_ids,
        consume_buffer,
        vals,
    ) -> tuple:
        result = {
            "errors": [],
            "warnings": [],
        }

        old_vals_per_pill_id = self.web_gantt_init_old_vals_per_pill_id(vals)
        candidates = self.browse([id for id in candidates_ids if id != self.id])
        cascade = self._web_gantt_start_cascade(
            candidates,
            vals,
            old_vals_per_pill_id,
            search_forward,
            consume_buffer,
            start_date_field_name,
            stop_date_field_name,
            dependency_field_name,
            dependency_inverted_field_name,
        )
        if cascade.get("error"):
            result["errors"].append(cascade["error"])
            return result, {}

        for candidate in candidates:
            if consume_buffer and not candidate._web_gantt_is_candidate_in_conflict(
                start_date_field_name,
                stop_date_field_name,
                dependency_field_name,
                dependency_inverted_field_name,
            ):
                continue

            dates = candidate._web_gantt_cascade_dates(
                cascade, search_forward, start_date_field_name, stop_date_field_name
            )
            if isinstance(dates, str):
                result["errors"].append(dates)
                return result, {}
            start_date, end_date = dates
            old_start_date, old_end_date = (
                candidate[start_date_field_name],
                candidate[stop_date_field_name],
            )
            if not candidate._web_gantt_reschedule_write_new_dates(
                start_date, end_date, start_date_field_name, stop_date_field_name
            ):
                result["errors"].append("past_error")
                result["past_error"] = candidate
                return result, {}

            old_vals_per_pill_id[candidate.id] = {
                start_date_field_name: old_start_date,
                stop_date_field_name: old_end_date,
            }

            error = candidate._web_gantt_cascade_moved(
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
            )
            if error:
                result["errors"].append(error)
                return result, {}

        result["warnings"].extend(self._web_gantt_cascade_warnings(cascade))
        return result, old_vals_per_pill_id

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
        self.write(vals)
        (
            first_possible_start_date_per_candidate,
            last_possible_end_date_per_candidate,
        ) = candidates._web_gantt_get_first_and_last_possible_dates(
            dependency_field_name,
            dependency_inverted_field_name,
            search_forward,
            stop_date_field_name,
            start_date_field_name,
        )
        self._web_gantt_update_next_pills_first_possible_date(
            dependency_field_name,
            dependency_inverted_field_name,
            search_forward,
            first_possible_start_date_per_candidate,
            last_possible_end_date_per_candidate,
            consume_buffer,
            start_date_field_name,
            stop_date_field_name,
            self[start_date_field_name],
            self[stop_date_field_name],
            old_vals_per_pill_id[self.id][start_date_field_name],
            old_vals_per_pill_id[self.id][stop_date_field_name],
        )
        return {
            "first_possible_start_date_per_candidate": first_possible_start_date_per_candidate,
            "last_possible_end_date_per_candidate": last_possible_end_date_per_candidate,
        }

    def _web_gantt_cascade_dates(
        self, cascade, search_forward, start_date_field_name, stop_date_field_name
    ) -> str | tuple:
        if search_forward:
            bound = cascade["first_possible_start_date_per_candidate"].get(
                self.id, _as_utc(self[start_date_field_name])
            )
        else:
            bound = cascade["last_possible_end_date_per_candidate"].get(
                self.id, _as_utc(self[stop_date_field_name])
            )
        start_date, end_date = self._web_gantt_reschedule_compute_dates(
            bound, search_forward, start_date_field_name, stop_date_field_name
        )
        return _as_utc(start_date), _as_utc(end_date)

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
    ):
        self._web_gantt_update_next_pills_first_possible_date(
            dependency_field_name,
            dependency_inverted_field_name,
            search_forward,
            cascade["first_possible_start_date_per_candidate"],
            cascade["last_possible_end_date_per_candidate"],
            consume_buffer,
            start_date_field_name,
            stop_date_field_name,
            self[start_date_field_name],
            self[stop_date_field_name],
            old_start_date,
            old_end_date,
        )

    def _web_gantt_cascade_warnings(self, cascade):
        return []

    def _web_gantt_record_has_dependencies(self):
        return True

    def _web_gantt_check_cycle_existence_and_get_rescheduling_candidates(
        self,
        candidates_ids,
        dependency_field_name,
        start_date_field_name,
        stop_date_field_name,
        visited=None,
        ancestors=None,
    ) -> bool:
        if visited is None:
            visited = set()
        if ancestors is None:
            ancestors = set()
        visited.add(self.id)
        ancestors.add(self.id)

        for child in (
            self[dependency_field_name]
            if self._web_gantt_record_has_dependencies()
            else []
        ):
            if child.id in ancestors:
                return True

            if (
                child.id not in visited
                and child._web_gantt_reschedule_is_record_candidate(
                    start_date_field_name, stop_date_field_name
                )
                and child._web_gantt_check_cycle_existence_and_get_rescheduling_candidates(
                    candidates_ids,
                    dependency_field_name,
                    start_date_field_name,
                    stop_date_field_name,
                    visited,
                    ancestors,
                )
            ):
                return True

        ancestors.discard(self.id)
        candidates_ids.append(self.id)

        return False

    def _web_gantt_reschedule_compute_dates(
        self,
        date_candidate,
        search_forward,
        start_date_field_name,
        stop_date_field_name,
    ):
        search_factor = 1 if search_forward else -1
        duration = search_factor * (
            self[stop_date_field_name] - self[start_date_field_name]
        )
        return sorted([date_candidate, date_candidate + duration])

    def _web_gantt_reschedule_is_record_candidate(
        self, start_date_field_name, stop_date_field_name
    ):
        return self._web_gantt_reschedule_can_record_be_rescheduled(
            start_date_field_name, stop_date_field_name
        )

    def _web_gantt_reschedule_can_record_be_rescheduled(
        self, start_date_field_name, stop_date_field_name
    ):
        self.check_singleton()
        now = DATE_FIELD_ADAPTERS[self._fields[start_date_field_name].type]["now"]()
        return bool(
            self[start_date_field_name]
            and self[stop_date_field_name]
            and self[start_date_field_name] > now
        )

    def _web_gantt_reschedule_write_new_dates(
        self, new_start_date, new_stop_date, start_date_field_name, stop_date_field_name
    ):
        start_field = self._fields[start_date_field_name]
        new_start_date = _as_stored(new_start_date)
        now = DATE_FIELD_ADAPTERS[start_field.type]["now"]()
        if start_field.type == "datetime":
            now -= timedelta(seconds=30)
        if new_start_date < now:
            return False

        self.write(
            {
                start_date_field_name: new_start_date,
                stop_date_field_name: _as_stored(new_stop_date),
            }
        )
        return True
