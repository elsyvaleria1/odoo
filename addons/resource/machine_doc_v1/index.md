# resource — machine doc

| Key | Value |
|---|---|
| Module | `resource` |
| Version | 1.39 |
| Depends | `web`, `uom` |
| Models | 20 (15 concrete, 5 abstract) |
| `mixin.resource` hosts in this checkout | 4 |
| `mixin.resource.scheduling` hosts in this checkout | 4 |
| `mixin.resource.allocation` hosts in this checkout | 2 |

Every figure here is derived by `factcheck.sh` from the tree; a mismatch is a red, not a
note. `MODEL_MAP.md` holds the models, their fields and the hook contracts. The design
reasons live in `doc/architecture/resource.rst`.

## What the module is

- **Identity.** `resource.resource` is a person (a party, `partner_id`), a material
  thing or an intangible capacity. It carries its identifiers (`resource.identifier`), its
  meters (`resource.meter`) and its acquisition, disposal and original value. It carries the working zone (`tz`), schedule (`calendar_id`), capacity and booking
  ceiling. A business record *is* a resource through `mixin.resource`: an owner
  (`_resource_owns = True`) creates, copies and deletes its identity (under
  `resource.privilege_owner_deletes_resource`; a resource with operational history refuses
  and is archived instead), a reference shares one.
- **Schedule.** `resource.calendar` with its `resource.calendar.attendance` lines, minus
  `resource.schedule.exception` rows whose `resource.time.type` is not work. A resource
  reads any schedule in its own zone. Every resource has a schedule: an empty one
  written anywhere becomes the shared Fully Flexible schedule
  (`resource.resource_calendar_fully_flexible`), available at any hour.
- **Ledger.** `resource.reservation` holds time-bounded claims projected from business
  records through `mixin.resource.scheduling`, reconciled by `mixin.resource.ledger`.
- **Custody and composition.** `resource.assignment` (effective-dated roles: custodian,
  operator, manager, technician) and `resource.relation` (containment and dependencies).

## Contracts other modules rely on

- **The schedule read decides.** `_attendance_intervals_batch` reads the calendar it is
  called on by that calendar's `schedule_type`, whoever the resources are; a caller
  wanting a resource's own hours passes the resource's calendar.
- **Booked time is working time.** `_work_intervals_batch` returns attendance minus
  leaves. A caller looking for *free* time passes `exclude_bookings=True`, which also
  removes enforced reservations. The unavailability readers take the same flag and default
  to `True`.
- **Occupancy** is `resource.reservation._get_domain_occupancy`: active, positive share,
  non-empty, in a half-open window. Conflicts, booking load, slot search and in-use checks
  all read it.
- **A cancelled plan** is an assignment that ends where it starts
  (`_get_domain_cancelled`). It is neither planned, open nor in use.
- **Exceptions** belong to the resource whatever schedule reads them; only a
  schedule-wide closure matches on `calendar_id`. A stored 23:59:59 local end covers the
  whole day (`_get_interval_end`).
- **Days** passed to `_get_unusual_days` are read in the schedule's own zone.

## Hosts

`mixin.resource`:
- `hr.employee` (hr)
- `mrp.workcenter` (mrp)
- `resource.asset` (resource_asset)
- `resource.test` (test_resource)

`mixin.resource.scheduling`:
- `calendar.event` (calendar)
- `maintenance.order` (maintenance)
- `mrp.workorder` (mrp)
- `planning.slot` (planning)

`mixin.resource.allocation`:
- `project.task` (project)
- `resource.scheduling.test` (test_resource)

## Tests

Files are named after their subject:

- `test_calendar_schedule.py`: days, hours, planning and intervals.
- `test_calendar_attendance.py`: attendance lines and their constraints.
- `test_resource_calendar.py`: calendar settings and integrity.
- `test_flexible_resource_calendar.py`: flexible schedules.
- `test_schedule_exception.py`: exceptions, their company and access.
- `test_resource_reservation.py`: reservations, conflicts and enforcement.
- `test_reservation_load.py`: booking load and stored hours.
- `test_reservation_status.py`: occupancy status.
- `test_booking_capacity.py`: booking capacity.
- `test_slot_search.py`: exclusive slot search.
- `test_resource_assignment.py`: custody.
- `test_resource_relation.py`: composition.
- `test_resource_origin.py`: where and when a resource came to be, and its nationalities.
- `test_resource_party.py`: a person is a party.
- `test_resource_resource_crud.py`: the identity's lifecycle and zone.
- `test_resource_identity.py`: identifiers, meters and the acquisition record of a resource.
- `test_resource_lifecycle.py`: the states a resource goes through, maintenance and disposal.
- `test_resource_roles.py`: roles.
- `test_resource_acl_coverage.py`: access.
- `test_views.py`: view structure.
- `test_utils.py`: the pure helpers in `models/utils.py`.

Shared fixture: `tests/common.py` (`ResourceCase`). Tests needing a concrete host live in
`test_resource`. The JS tests are `static/tests/resource_avatar.test.js` and
`static/tests/ask_recurrence_update_dialog.test.js`.
