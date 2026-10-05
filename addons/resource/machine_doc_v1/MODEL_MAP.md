# resource — models

## resource.resource

`models/resource_resource.py`. The identity: a person, a material thing or an intangible capacity.

**Fields:**
- Identity: `name` (a person's follows the party), `active`, `color`, `company_id`,
  `type` (`human` / `material` / `intangible`), `partner_id` (required for a person), `phone_ids`,
  `user_id` (the party's internal login), `avatar_128`, `share`, `email`.
- Schedule: `calendar_id` (required; none is the shared Fully Flexible schedule),
  `tz` (required: the working zone),
  `time_efficiency`, `capacity`, `booking_limit_percentage`, `enforce_booking_limit`.
- Roles: `role_ids`, `default_role_id`.
- Custody, computed from assignments: `assignment_ids`, `holder_id` (who has it: the
  live operator, else the live custodian, per `_get_holding_custody_roles`),
  `operator_id`, `manager_id`, `future_operator_id`, `date_future_operator`.
- Composition and ledger: `relation_ids`, `membership_ids`, `reservation_ids`.
- Lifecycle and value: `state` (draft, available, in service, maintenance, out of service,
  disposed; a disposed one has its `date_disposal`), `state_before_maintenance` (where ending
  maintenance returns), `date_acquisition`, `date_disposal` (not before acquisition),
  `currency_id` (the company's), `value_original`.
- Identity rows and measures: `identifier_ids`, `meter_ids`.
- Origin, one API computed per reader: `date_origin` (birth, manufacture), `year_origin`,
  `origin_country_id`, `place_origin`. A thing's are its own `date_built`,
  `country_built_id`, `place_built`; a person's are read from and written to their party's
  private facet as the reader, so base's guard on the facet decides who sees them and
  nothing private is copied here. `nationality_ids` (a thing's rows),
  `nationality_country_ids` (the countries held now). `_get_domain_by_holder` searches
  either.

**Key methods:**
- Hosts: `_get_host_model_names`, `_get_owner_model_names`, `_get_owners`.
- Lifecycle: `_get_in_use_resource_ids`, `_archive_if_unused`, `_lock_for_integrity`.
- Custody: `_sync_custody`, `_end_custody`, `_on_custody_changed` (hook).
- Occupancy and slots: `_get_reservation_status`, `_get_slot_intervals_batch`,
  `_get_slot_intervals`, `_find_free_window`.
- Calendar resolution: `_get_work_schedule`, `_get_valid_work_intervals`,
  `_get_calendars_validity_within_period` (hr overrides it),
  `_get_unavailable_intervals` (`exclude_bookings`), `_normalize_calendar_vals`.
- Flexible schedules: `_get_flexible_resource_valid_work_intervals`,
  `_get_flexible_resource_work_hours`, `_get_flexible_booking_hours_per_day`,
  `_is_flexible`, `_is_fully_flexible`.
- Local time: `_get_local_date`, `_get_local_day_bounds`.
- Lifecycle: `_transition`, `_get_transition_vals` (disposal archives and dates),
  `_end_maintenance`, `_get_state_after_maintenance`; `_check_transition` and
  `_check_reactivation` are hooks a representation extends (resource_asset defers to the
  asset's). Archiving ends custody; unarchiving a disposed resource puts it out of service.
- Identifiers and meters: `_get_identifier`, `_update_identifier` (silent for an unknown
  code). `fields.ResourceIdentifier` exposes one identifier as a column on
  any model that reaches a resource through `through`.

## resource.calendar

`models/resource_calendar.py`. A working schedule.

**Fields:**
- `name`, `active`, `company_id`, `tz` (required unless fully flexible: the shared
  schedule has no zone, so its holders read their own), `tz_offset`.
- Lines: `attendance_ids`, `attendance_ids_1st_week`, `attendance_ids_2nd_week`,
  `two_weeks_calendar`, `two_weeks_explanation`.
- Shape: `schedule_type` (`fully_fixed` / `flexible` / `fully_flexible`), `duration_based`.
- Figures: `hours_per_day`, `hours_per_week`, `full_time_required_hours`, `is_fulltime`,
  `work_time_rate`.
- `leave_ids`, `global_leave_ids`, `resource_ids`, `work_resources_count`.

**Key methods:**
- Intervals: `_attendance_intervals_batch`, `_leave_intervals_batch`, `_work_intervals_batch`
  (`compute_leaves`, `exclude_bookings`), `_hard_reservation_intervals_batch`,
  `_unavailable_intervals_batch`.
- Figures: `get_work_hours_count`, `get_work_duration_data`, `get_attendance_duration_data`,
  `_get_hours_by_day` (a fully flexible day counts at most `hours_per_day`),
  `_get_unusual_days`, `_get_hours_for_date`, `_is_working_day`.
- The shared schedule: `_get_fully_flexible_calendar`, `_get_company_calendar`,
  `_normalize_calendar_vals` (an empty schedule written anywhere becomes it).
- Planning: `plan_hours`, `plan_days`.
- Hooks: `_get_fields_schedule` (the fields whose change recomputes open reservation hours)
  and `_recompute_reservation_hours`.

## resource.calendar.attendance

`models/resource_calendar_attendance.py`. One line of a schedule.

**Fields:** `calendar_id`, `name`, `sequence`, `dayofweek`, `hour_from`, `hour_to` (24:00
is the end of the day), `duration_hours`, `duration_days`, `day_period`, `week_type`,
`display_type`, `duration_based` and `two_weeks_calendar` (related).

## resource.schedule.exception

`models/resource_schedule_exception.py`. Time taken out of, or carved into, a schedule.

**Fields:** `name`, `company_id`, `calendar_id`, `resource_id`, `time_type_id`, `date_from`,
`date_to`, `tz`, `local_date_from`, `local_date_to`, `local_hour_from`, `local_hour_to`.

**Key methods:** `_get_interval_end`, `_get_domain_public_holidays`,
`_get_fields_schedule_scope`, `_get_schedule_scopes`, `_on_schedule_changed` (hook: base
recomputes the reservations it overlaps; hr_holidays, planning_holidays and others extend
it).

## resource.time.type

`models/resource_time_type.py`. A kind of time.

**Fields:** `name`, `active`, `code`, `sequence`, `is_work` (unset = an absence the schedule
subtracts).

## resource.reservation

`models/resource_reservation.py`. A time-bounded claim on a resource.

**Fields:**
- `name`, `active`, `company_id`, `resource_id`, `resource_calendar_id`, `date_start`,
  `date_end`.
- `allocated_percentage`, `allocated_hours`, `enforcement_mode` (`soft` / `hard`).
- Computed load: `schedule_overlap_count`, `peak_booking_percentage`, `booking_state`.
- Source: `res_model`, `res_id`, `origin_display`.

**Key methods:**
- Occupancy: `_get_domain_occupancy`, `_get_domain_enforced_booking`, `_get_occupancy`,
  `_get_booking_load_batch`.
- Conflicts: `_get_sql_overlap_partners`, `_get_overlap_partners`, `_get_conflicting_reservations`,
  `_get_prospective_conflicts`.
- Hours: `_recompute_allocated_hours`, `_get_first_served_hours`. On a flexible
  schedule a person's claims draw on each day's and week's hours in date order:
  each takes its percentage of what it would hold alone (its own week filled from
  its first day), out of what earlier claims left, so together they never hold
  more than the schedule. `_walk_first_served` reads plain `FirstServedClaim`s,
  so an owner reads its records before their reservations exist
  (`_get_first_served_hours_of`), solves the percentage that holds typed hours
  (`_get_first_served_percentages_of`) or splits a claim by day
  (`_get_first_served_days_of`). Creating, moving, archiving or deleting one
  recomputes the others in its weeks (`_get_domain_first_served_neighbours`,
  `_recompute_first_served_neighbours`) and asks their owners to as well.
- Upkeep: `_get_reservation_intervals_batch`, `_gc_orphan_reservations`.

## resource.assignment

`models/resource_assignment.py`. An effective-dated role on a resource.

**Fields:** `name`, `active`, `resource_id`, `assignee_id`, `assignee_partner_id`,
`company_id`, `custody_role`, `date_start`, `date_end`, `state`, `note`.

**Key methods:**
- Domains: `_get_domain_custody` (`live` / `planned` / `open`), `_get_domain_cancelled`.
- Lookups: `_get_custody_assignments`, `_get_holder`, `_get_holding_custody_roles`,
  `_get_holding_by_resource`, `_get_sql_effective_custody`.
- Changes: `_supersede_rivals` (create, and write on `_get_fields_custody`), `_end`.

## resource.relation

`models/resource_relation.py`. Effective-dated containment or dependency.

**Fields:** `name`, `active`, `parent_id`, `member_id`, `relation_type`, `company_id`,
`date_start`, `date_end`, `note`.

**Key methods:** `_get_domain_live_relations`, `_set_containment_parent`, `_lock_graph`.

## resource.identifier.type

`models/resource_identifier_type.py`. A kind of identifier, resolved by `code`. **Fields:**
`name`, `code` (unique), `sequence`, `active`, `pattern` (on the normalized value),
`unique_scope` (`global` / `company` / `none`). Data: serial, plate, VIN, engine, IMEI,
cadastral, inventory tag.

## resource.identifier

`models/resource_identifier.py`. One value a resource carries under a type, one per type.
**Fields:** `resource_id`, `company_id`, `type_id`, `value`, `normalized_value`
(upper-case alphanumerics, searched and checked for uniqueness), `valid_until`.

## resource.nationality

`models/resource_nationality.py`. One country a holder belongs to: a person (through
their party's private facet) or a thing, never both. **Fields:** `partner_id`,
`resource_id`, `sequence` (the first held is a person's primary nationality), `country_id`,
`basis` (birth, descent, naturalization, marriage, importation, registration),
`date_acquired`, `date_lost`, `identifier_id` (a thing's proof), `partner_identifier_id`
(a person's). **Key methods:** `_filter_held`.

## resource.meter

`models/resource_meter.py`. A counter a resource carries, one per kind. **Fields:**
`resource_id`, `company_id`, `name`, `sequence`, `kind` (`odometer` / `hours` / `cycles`),
`uom_id`, `monotonic`, `reading_ids`, `last_reading_id`, `value`, `date`.
**Key methods:** `record`.

## resource.meter.reading

`models/resource_meter_reading.py`. **Fields:** `meter_id`, `resource_id`, `company_id`,
`date`, `value` (not negative; never below an earlier one on a monotonic meter unless
`skip_meter_monotonic`), `source`, `note`.

## resource.role

`models/resource_role.py`. **Fields:** `name`, `active`, `color`, `sequence`,
`resource_ids`.

## resource.config

`models/resource_config.py`. A company's resource configuration. **Fields:**
`resource_calendar_id`, `week_start` (the day a flexible schedule's weekly hours start over, Monday by default).

## mixin.resource

`models/mixin_resource.py`. A business record that is a resource.

**Fields:** `resource_id`, `tz`, `company_id`, `resource_calendar_id`.

**Hook contract:**
- Class attributes: `_resource_type` and `_resource_owns`.
- Overridable: `_resource_owner_models`, `_get_calendars` (hr answers with the contract
  version's calendar).
- Readers: `_get_work_duration_data_batch`, `_get_leave_duration_data_batch`,
  `_get_work_time_per_day`, all resolving the calendar through
  `_get_calendars`.

## mixin.resource.scheduling

`models/mixin_resource_scheduling.py`. A business record projected into the ledger.

**Fields:** `reservation_ids`, `schedule_overlap_count` (distinct foreign claims:
`_compute_schedule_overlap_count`, searched by `_search_schedule_overlap_count` in one SQL
subquery).

**Hook contract:**
- Class attribute: `_reservation_sync_manual`.
- Overridable: `_get_fields_reservation_date`, `_get_fields_sync_trigger`,
  `_get_fields_overlap_depends`, `_prepare_reservation_vals_list`,
  `_prepare_reservation_vals_by_record`.
- Provided: `_sync_reservations`, `_active_for_sync`,
  `_get_schedule_conflicts_batch`, `_recompute_first_served_hours` (a no-op that
  planning.slot overrides: its flexible slots read the week as their reservations do).

## mixin.resource.allocation

`models/mixin_resource_allocation.py`. Scheduling with a share. **Fields:**
`allocated_percentage`, `allocated_hours` (derived only: the sum of its active
reservations, 0 while unscheduled; a written value is recomputed away). Effort lives in
the host's own estimate, such as `project.task.planned_hours`.

## mixin.resource.ledger

`models/mixin_resource_ledger.py`. Reconciliation of projected rows by identity.

**Hook contract:** `_get_fields_projection_key`, `_get_domain_projection`,
`_prepare_projection_link_vals`, `_get_projection_key`, `_get_changed_vals`,
`_sync_projection_batch` (kept rows untouched, then delete, write,
create).

## mixin.resource.scheduling.tools

`models/mixin_resource_scheduling_tools.py`. `_scheduling_get_work_hours`,
`_scheduling_resolve_calendar`.

### Extensions

- `res.company`: `resource_calendar_ids`, `resource_config_id`, `resource_calendar_id`, `resource_week_start`.
- `res.partner`: `resource_ids`; `place_of_birth`, `country_of_birth` and `nationality_ids`,
  held on a person's private facet; `_get_resources`, `_get_or_create_resources`,
  `_get_private_facet`, `_ensure_private_facet`.
- `res.users`: `resource_ids`, `resource_calendar_id` (the schedule of the resource in the
  current company).
