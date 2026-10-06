# hr_attendance — conventions

The contracts a change here must not break. Each was learned from a defect, and
the paragraph says which, because a rule whose cost is not stated gets
"simplified" away by the next reader.

## One attendance, one zone

Every local-time decision about one attendance — the `date` it is filed under,
which day's schedule prices it, where its lunch falls, when the auto-check-out
cron thinks its day ends — resolves through **one** pair of methods:

```python
version = attendance._schedule_version()  # which hr.version was in force
tz = attendance._schedule_tz(version)  # and that version's timezone
```

`_schedule_version()` is a fixed point, not a lookup: the version is chosen by
the check-in's local day, and the local day depends on the version's timezone.
It iterates at most `_SCHEDULE_VERSION_PASSES` times and stops as soon as two
passes agree. Three is not a guess about convergence — it is a cap, so a
pathological calendar cannot spin.

**Pass the version down.** Every helper that needs a zone takes `version=None`
and forwards what it was given. Recomputing it per helper is correct and cost
63% on a 6,300-record sweep before the parameter existed — 6.8s to 11.1s,
measured on 2026-09-14 and recovered to 7.5s in the same change. **Frozen**: a
profile is not re-derivable from the tree, and its base commit went with the
2026-10-03 history squash, so this reading stays as measured and is not to be
"corrected" to a current one.

Do **not** reach for `employee._get_tz()` here. It prefers the inherited company
calendar over an explicitly set personal timezone, so it answers a different
question from the one an attendance asks, and it answered it differently enough
to move `hours_today` by a full hour on a fresh database.

## `[False]`, never `[resource.id]`

`resource.calendar._attendance_intervals_batch(..., lunch=True)` keys its result
by resource id, and the `False` key is the calendar's own generic intervals.
`_lunch_intervals()` asks without a resource and reads `[False]`: the breaks of
the schedule in force, in the schedule's zone.

The schedule decides how it is read: one that is not fully fixed (flexible, or
the shared Fully Flexible schedule an employee without hours holds) has no
breaks, so a flexible employee is charged none without a guard of its own.

The guard this replaced (`_is_flexible()` on the resource) and the company
lunch it fended off came from the version falling back to the company calendar
when it had none. Dropping that guard then charged a flexible employee a
company lunch (9.00 → 8.00); reading the resource's key zeroed them (0.00).
**Frozen** as measured on 2026-09-14, before the 2026-10-03 history squash took
its base commit; `TestFlexibleResourceKeepsItsHours` is the live assertion, and
it is the one to read for a current figure.

## The deferral may not span a read of what it defers

`_deferring_overtime()` batches overtime regeneration: writes inside the block
record their windows and one `_defer_overtime()` prices them all at the end.

The constraint is that **nothing inside the block may read a derived overtime
figure**. Inside, `overtime_hours` is whatever the last regeneration left, which
for a record created in the block is zero.

`_cron_absence_detection` is the worked example. Wrapping it in the deferral
made every absence marker read `overtime_hours == 0`, so the cron's own cleanup
deleted all of them. `TestAbsenceDetection.test_yesterday` caught it. The cron
is deliberately not deferred, and that is not an oversight to tidy.

## Evidence is ungated; inference is gated

`hr.employee._compute_hr_presence_state` has two branches and they are not
symmetric:

- **checked in → `present`.** Ungated. An attendance record is evidence that the
  employee is there, whatever the company's presence policy says.
- **expected, checked out → `absent`.** Gated on
  `company_id.hr_presence_control_attendance`. This is an inference from an
  absent record, and only a company that has said attendance governs presence
  has agreed to it.

Gating both, which reads as the tidier shape, reports a checked-in employee as
absent whenever the company has not enabled the control.

## `duration` and `manual_duration` are different questions

On `hr.attendance.overtime.line`, `duration` is what the rules computed and
`manual_duration` is what stands. `_regeneration_key()` identifies a line across
a regeneration **by `duration`**, so a manager's correction to `manual_duration`
survives a recompute of the same shape, while a change in what the rules produce
is a different line.

Accordingly:

- `hr.attendance.overtime_hours` sums `manual_duration` — the corrected figure is
  the one a payslip wants;
- `hr.attendance.expected_hours` is derived from `duration` — what was expected
  of the employee does not move because a manager granted them an hour.

## A non-stored compute still needs `@api.depends`

`hours_today`, `hours_this_month` and their siblings are `compute` without
`store`. Without a `depends` the ORM has nothing to invalidate on, so the value
is computed once per environment and held — the systray then shows a figure from
before the check-out that just happened. They depend on `attendance_ids` and on
`tz`.

## The kiosk refuses in one shape

Every public kiosk route validates through `_refuse()`, which returns the same
`{"error": ...}` shape for a bad token, an unknown employee, a wrong PIN and a
throttled retry. A route that invents its own refusal tells an unauthenticated
caller which of those it was.

`_employee_of()` is the only way a kiosk route turns a request into an employee.

## Domains from the client are allowlisted, not trusted

`controllers/main.py` refuses a domain term it does not recognise rather than
passing it to `search`. An unrecognised term is a refusal, not a silent drop: a
dropped term widens the search.

## An attendance is not copyable

`copy()` raises. An attendance is a record of something that happened; a
duplicate of one is a claim that it happened twice.

## Instrumentation

`_debug = DebugLog(__name__)` in every module that logs, on the four channels
of `odoo.libs.debug_log` (`logic`, `perf`, `pipeline`, `lifecycle`). Arm every
channel, not one, when tracing a pipeline:

```
--log-handler odoo.debug:DEBUG
```

A probe that reasons about which schedule priced an attendance should read
`pipeline` rather than re-deriving the version itself — re-derivation is how
three probes this module's audit ran reached a confident wrong answer.

`tools/debug_log.py` retains compatibility imports for existing instrumentation;
new call sites use the shared `odoo.libs.debug_log.DebugLog` service.
