from collections import defaultdict
from datetime import datetime
from typing import TYPE_CHECKING, Self

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.models import ValuesType
from odoo.tools.date_utils import localized

if TYPE_CHECKING:
    from .resource_calendar import ResourceCalendar


class MixinResource(models.AbstractModel):
    _name = "mixin.resource"
    _description = "Resource Mixin"
    _resource_type = "human"
    _resource_owns = True

    resource_id = fields.Many2one(
        comodel_name="resource.resource",
        index="unique",
        required=True,
        ondelete="restrict",
        bypass_search_access=True,
    )
    tz = fields.Selection(
        related="resource_id.tz",
        string="Timezone",
        readonly=False,
        help="The time zone where this resource works. Its working schedule is read in this zone: an 08:00-17:00 schedule means 08:00-17:00 here, whatever zone the schedule names. For an employee deployed away from the corporate office, set the zone of the place of work.",
    )
    company_id = fields.Many2one(  # noqa: E8529 -- multi-company key of hr.employee: UNIQUE (user_id, company_id) and two more on hr_employee, and the raw SQL that joins it
        comodel_name="res.company",
        related="resource_id.company_id",
        string="Company",
        precompute=True,
        default=lambda self: self.env.company,
        store=True,
        index=True,
        readonly=False,
    )
    resource_calendar_id = fields.Many2one(
        comodel_name="resource.calendar",
        related="resource_id.calendar_id",
        string="Working Hours",
        readonly=False,
    )

    def _get_resource_model_as_system(self):
        return self.env["resource.resource"].sudo()

    @api.model_create_multi
    def create(self, vals_list: list[ValuesType]) -> Self:
        vals_list = [self._normalize_calendar_vals(vals) for vals in vals_list]
        self._check_resource_ownership(
            [vals["resource_id"] for vals in vals_list if vals.get("resource_id")]
        )
        Resource = self._get_resource_model_as_system()
        resources_vals_list = []
        for vals in vals_list:
            if not vals.get("resource_id"):
                prepared = self._prepare_resource_values(vals, vals.pop("tz", False))
                resource_vals = self._pop_delegated_resource_vals(vals) | prepared
                resource_vals["type"] = self._resource_type
                resources_vals_list.append(resource_vals)
            elif delegated := self._pop_delegated_resource_vals(vals):
                vals.update(delegated)
        if resources_vals_list:
            resources = Resource.create(resources_vals_list)
            resources_iter = iter(resources.ids)
            for vals in vals_list:
                if not vals.get("resource_id"):
                    vals["resource_id"] = next(resources_iter)

        attached = [vals for vals in vals_list if vals.get("resource_id")]
        if attached:
            resources_by_id = {
                resource.id: resource
                for resource in Resource.browse(
                    [vals["resource_id"] for vals in attached]
                ).exists()
            }
            defaults = {
                "company_id": "company_id",
                "resource_calendar_id": "calendar_id",
            }
            for name, field in self._fields.items():
                path = field.related.split(".") if field.related else ()
                if (
                    field.default is not None
                    and not field.readonly
                    and len(path) == 2
                    and path[0] == "resource_id"
                ):
                    defaults[name] = path[1]
            for vals in attached:
                resource = resources_by_id.get(vals["resource_id"])
                if not resource:
                    continue
                for name, source in defaults.items():
                    if name not in vals:
                        key = f"default_{name}"
                        vals[name] = (
                            self.env.context[key]
                            if key in self.env.context
                            else self._fields[name].convert_to_write(
                                resource[source], self
                            )
                        )
        records = super(
            MixinResource, self.with_context(check_idempotence=True)
        ).create(vals_list)
        return records.with_env(self.env)

    def write(self, vals):
        if vals.get("resource_id"):
            self._check_resource_ownership(
                [vals["resource_id"]] * len(self), exclude_ids=self.ids
            )
        return super().write(self._normalize_calendar_vals(vals))

    def unlink(self):
        owned = (
            self.with_privilege(
                "base.privilege_owner_deletes_resource",
                reason="deleting what owns a resource deletes the resource",
            ).resource_id
            if self._resource_owns
            else self.env["resource.resource"]
        )
        result = super().unlink()
        owned.exists().unlink()
        return result

    def _unlink_inherits_shared_parents(self, parents):
        if self._resource_owns:
            parents = parents.with_privilege(
                "base.privilege_owner_deletes_resource",
                reason="deleting what owns a resource deletes the resource",
            )
        super()._unlink_inherits_shared_parents(parents)

    def _pop_delegated_resource_vals(self, vals: ValuesType) -> ValuesType:
        if self._inherits.get("resource.resource") != "resource_id":
            return {}
        delegated = {
            name: vals.pop(name)
            for name in list(vals)
            if (field := self._fields.get(name))
            and field.inherited
            and field.related_field.model_name == "resource.resource"
        }
        delegated.pop("type", None)
        return delegated

    @api.model
    def _normalize_calendar_vals(self, vals: ValuesType) -> ValuesType:
        return self.env["resource.calendar"]._normalize_calendar_vals(
            vals, "resource_calendar_id"
        )

    def _check_resource_ownership(self, resource_ids, *, exclude_ids=()):
        if not resource_ids:
            return
        if self._resource_owns and len(resource_ids) != len(set(resource_ids)):
            raise ValidationError(
                self.env._("A resource cannot have several owning records.")
            )
        resources = (
            self.env["resource.resource"].sudo().browse(sorted(set(resource_ids)))
        )
        if not self._resource_owns:
            resources.with_env(self.env).check_access("read")
        resources._lock_for_integrity()
        resources.exists()._check_host_type(self._resource_type)
        if not self._resource_owns:
            if self._fields["resource_id"].index == "unique":
                if len(resource_ids) != len(
                    set(resource_ids)
                ) or self.sudo().with_context(active_test=False).search_count(
                    [
                        ("resource_id", "in", resource_ids),
                        ("id", "not in", exclude_ids),
                    ],
                    limit=1,
                ):
                    raise ValidationError(
                        self.env._(
                            "This resource already has this kind of representation."
                        )
                    )
            return
        resource_ids = resources.ids
        namespace = self._get_root_model_name()
        for owner_model in self._resource_owner_models():
            owners = self.env[owner_model].sudo().with_context(active_test=False)
            if owners.search_count(  # noqa: E8507 -- one query per owner model, not per resource
                [
                    ("resource_id", "in", resource_ids),
                    ("id", "not in", exclude_ids if owner_model == namespace else ()),
                ],
                limit=1,
            ):
                raise ValidationError(
                    self.env._("This resource already has an owning record.")
                )

    @api.model
    def _resource_owner_models(self):
        return self.env["resource.resource"]._get_owner_model_names()

    def copy_data(self, default: ValuesType | None = None) -> list[ValuesType]:
        default = dict(default or {})
        vals_list = super().copy_data(default=default)

        resource_default = {}
        if "company_id" in default:
            resource_default["company_id"] = default["company_id"]
        if "resource_calendar_id" in default:
            resource_default["calendar_id"] = default["resource_calendar_id"]
        if not self._resource_owns:
            for vals in vals_list:
                vals.pop("resource_id", None)
            return vals_list
        resources_to_copy = self._get_resource_model_as_system().concat(
            *(record.resource_id for record in self)
        )
        new_resources = resources_to_copy.copy(resource_default)
        for resource, vals in zip(new_resources, vals_list, strict=True):
            vals["resource_id"] = resource.id
            vals["company_id"] = resource.company_id.id
            vals["resource_calendar_id"] = resource.calendar_id.id
            if self._rec_name in default:
                resource.name = default[self._rec_name]
        return vals_list

    @staticmethod
    def _fan_out_per_record(
        result_per_resource: dict[int, dict[str, float]],
        records_per_resource: dict[int, list[int]],
    ) -> dict[int, dict[str, float]]:
        return {
            record_id: result_per_resource[resource_id]
            for resource_id, record_ids in records_per_resource.items()
            for record_id in record_ids
            if resource_id in result_per_resource
        }

    def _get_calendars(
        self, date_from: datetime | None = None
    ) -> dict[int, ResourceCalendar]:
        return {record.id: record.resource_calendar_id for record in self}

    def _get_leave_duration_data_batch(
        self,
        from_datetime: datetime,
        to_datetime: datetime,
        calendar: ResourceCalendar | None = None,
        domain: list | None = None,
    ) -> dict[int, dict[str, float]]:
        records_per_resource = self._get_records_per_resource()
        result = {}

        from_datetime = localized(from_datetime)
        to_datetime = localized(to_datetime)

        calendar_by_record = {} if calendar else self._get_calendars(from_datetime)
        mapped_resources = defaultdict(lambda: self.env["resource.resource"])
        for record in self:
            mapped_resources[calendar or calendar_by_record[record.id]] |= (
                record.resource_id
            )

        for resource_calendar, calendar_resources in mapped_resources.items():
            attendances = resource_calendar._attendance_intervals_batch(
                from_datetime, to_datetime, calendar_resources
            )
            leaves = resource_calendar._leave_intervals_batch(
                from_datetime, to_datetime, calendar_resources, domain
            )

            for calendar_resource in calendar_resources:
                result[calendar_resource.id] = resource_calendar._get_duration_data(
                    attendances[calendar_resource.id] & leaves[calendar_resource.id]
                )

        return self._fan_out_per_record(result, records_per_resource)

    def _get_work_duration_data_batch(
        self,
        from_datetime: datetime,
        to_datetime: datetime,
        compute_leaves: bool = True,
        calendar: ResourceCalendar | None = None,
        domain: list | None = None,
    ) -> dict[int, dict[str, float]]:
        records_per_resource = self._get_records_per_resource()
        result = {}

        from_datetime = localized(from_datetime)
        to_datetime = localized(to_datetime)

        if calendar:
            mapped_resources = {calendar: self.resource_id}
        else:
            calendar_by_resource = self._get_calendars(from_datetime)
            mapped_resources = defaultdict(lambda: self.env["resource.resource"])
            for record in self:
                mapped_resources[calendar_by_resource[record.id]] |= record.resource_id

        for resource_calendar, calendar_resources in mapped_resources.items():
            if compute_leaves:
                intervals = resource_calendar._work_intervals_batch(
                    from_datetime, to_datetime, calendar_resources, domain
                )
            else:
                intervals = resource_calendar._attendance_intervals_batch(
                    from_datetime, to_datetime, calendar_resources
                )

            for calendar_resource in calendar_resources:
                result[calendar_resource.id] = resource_calendar._get_duration_data(
                    intervals[calendar_resource.id]
                )

        return self._fan_out_per_record(result, records_per_resource)

    def _get_work_time_per_day(
        self,
        from_datetime: datetime,
        to_datetime: datetime,
        calendar: ResourceCalendar | None = None,
        domain: list | None = None,
        compute_leaves: bool = True,
    ) -> dict[int, list[tuple]]:
        result = {}
        from_datetime = localized(from_datetime)
        to_datetime = localized(to_datetime)
        calendar_by_record = {} if calendar else self._get_calendars(from_datetime)
        records_by_calendar = defaultdict(lambda: self.env[self._name])
        for record in self:
            records_by_calendar[calendar or calendar_by_record[record.id]] += record

        for resource_calendar, records in records_by_calendar.items():
            resources = records.resource_id
            all_intervals = resource_calendar._work_intervals_batch(
                from_datetime,
                to_datetime,
                resources,
                domain,
                compute_leaves=compute_leaves,
            )
            for record in records:
                intervals = all_intervals[record.resource_id.id]
                result[record.id] = sorted(
                    resource_calendar._get_hours_by_day(intervals).items()
                )
        return result

    def _pop_resource_vals(self, vals):
        resource_vals = {}
        for name in list(vals):
            field = self._fields.get(name)
            path = field.related.split(".") if field and field.related else ()
            if len(path) == 2 and path[0] == "resource_id":
                resource_vals[path[1]] = vals.pop(name)
        return resource_vals

    def _prepare_resource_values(self, vals: ValuesType, tz: str | bool) -> ValuesType:
        resource_vals = {
            "name": vals.get(self._rec_name),
            "type": self._resource_type,
        }
        if tz:
            resource_vals["tz"] = tz
        company_id = vals.get("company_id", self.env.company.id)
        if company_id:
            resource_vals["company_id"] = company_id
        calendar_id = vals.get("resource_calendar_id")
        if calendar_id:
            resource_vals["calendar_id"] = calendar_id
        return resource_vals

    def _get_records_per_resource(self) -> dict[int, list[int]]:
        grouped = defaultdict(list)
        for record in self:
            grouped[record.resource_id.id].append(record.id)
        return grouped
