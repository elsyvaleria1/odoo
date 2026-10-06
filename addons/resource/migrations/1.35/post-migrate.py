import logging

from odoo import SUPERUSER_ID, api
from odoo.db import schema

_logger = logging.getLogger(__name__)


def _every_person_is_a_party(cr, env):
    cr.execute(
        """
        UPDATE resource_resource r
           SET partner_id = u.partner_id
          FROM res_users u
         WHERE u.id = r.user_id
           AND r.type = 'human'
           AND r.partner_id IS NULL
        """
    )
    if cr.rowcount:
        _logger.info(
            "resource: %s human resource(s) bound to their user's party", cr.rowcount
        )

    # hr binds an employee's resource to the employee's own party; a party made
    # here would be orphaned by that as soon as hr's migrations run.
    employee_resource_ids = set()
    if schema.table_exists(cr, "hr_employee"):
        cr.execute("SELECT resource_id FROM hr_employee")
        employee_resource_ids = {row[0] for row in cr.fetchall()}
    cr.execute(
        """
        SELECT id, name, tz FROM resource_resource
         WHERE type = 'human' AND partner_id IS NULL
         ORDER BY id
        """
    )
    unbound = [row for row in cr.fetchall() if row[0] not in employee_resource_ids]
    if unbound:
        parties = env["res.partner"].create(
            [{"name": name, "tz": tz} for _id, name, tz in unbound]
        )
        env.flush_all()
        cr.execute(
            """
            UPDATE resource_resource r
               SET partner_id = bound.partner_id
              FROM unnest(%s::int[], %s::int[]) AS bound(resource_id, partner_id)
             WHERE r.id = bound.resource_id
            """,
            [[row[0] for row in unbound], parties.ids],
        )
        _logger.info("resource: %s human resource(s) given a party", len(unbound))

    cr.execute(
        """
        UPDATE resource_resource r
           SET name = p.name
          FROM res_partner p
         WHERE p.id = r.partner_id
           AND p.name IS NOT NULL
           AND r.name IS DISTINCT FROM p.name
           AND NOT EXISTS (
               SELECT 1 FROM resource_resource other
                WHERE other.partner_id = r.partner_id
                  AND other.company_id IS NOT DISTINCT FROM r.company_id
                  AND other.type = 'human'
                  AND other.id <> r.id)
        """
    )
    if cr.rowcount:
        _logger.info("resource: %s resource(s) took their party's name", cr.rowcount)

    cr.execute(
        """
        SELECT partner_id, company_id, array_agg(id ORDER BY id)
          FROM resource_resource
         WHERE type = 'human'
         GROUP BY partner_id, company_id
        HAVING count(*) > 1
        """
    )
    for partner_id, company_id, resource_ids in cr.fetchall():
        _logger.warning(
            "resource: party %s holds human resources %s in company %s; one person"
            " is one resource per company, so the unique index waits on this",
            partner_id,
            resource_ids,
            company_id,
        )


def _user_follows_the_party(cr, env):
    cr.execute("SELECT id, user_id FROM resource_resource WHERE type = 'human'")
    before = dict(cr.fetchall())
    resources = env["resource.resource"].with_context(active_test=False).browse(before)
    env.add_to_compute(resources._fields["user_id"], resources)
    env.flush_all()
    cr.execute("SELECT id, user_id FROM resource_resource WHERE type = 'human'")
    changed = {
        resource_id: (before[resource_id], user_id)
        for resource_id, user_id in cr.fetchall()
        if before.get(resource_id) != user_id
    }
    if changed:
        _logger.info(
            "resource: %s human resource(s) took their party's user (before, after): %s",
            len(changed),
            changed,
        )


def _give_exceptions_a_kind(cr, env):
    # time_type was a Selection; the ORM filled the new required time_type_id
    # with its default while adding it, so every row says "absence" by now and
    # every row is mapped, not only the empty ones.
    if not schema.column_exists(cr, "resource_schedule_exception", "time_type"):
        return
    leave = env.ref("resource.time_type_leave", raise_if_not_found=False)
    work = env.ref("resource.time_type_work", raise_if_not_found=False)
    if not (leave and work):
        _logger.error(
            "resource: the kernel kinds of time are missing; schedule exceptions"
            " keep their old kind column"
        )
        return
    cr.execute(
        """
        UPDATE resource_schedule_exception
           SET time_type_id = CASE WHEN time_type = 'other' THEN %s ELSE %s END
        """,
        (work.id, leave.id),
    )
    _logger.info("resource: %s schedule exception(s) given a kind", cr.rowcount)
    schema.drop_columns(cr, "resource_schedule_exception", ["time_type"])


def _company_settings_move_to_config(cr, env):
    if not schema.column_exists(cr, "res_company", "resource_calendar_id"):
        return
    # the rows through the ORM, so every default and required value applies;
    # the value by SQL, straight from the company's column
    companies = env["res.company"].with_context(active_test=False).search([])
    env["resource.config"]._for_each(companies)
    env.flush_all()
    cr.execute(
        """
        UPDATE resource_config x
           SET resource_calendar_id = c.resource_calendar_id
          FROM res_company c
         WHERE c.id = x.company_id
        """
    )
    env.invalidate_all()


def _reservations_follow_their_resource(cr):
    # a reservation's company is its resource's; rows an older version
    # stamped with the host's company never recompute, since the resource's
    # company did not change
    cr.execute(
        """
        UPDATE resource_reservation reservation
           SET company_id = resource.company_id
          FROM resource_resource resource
         WHERE resource.id = reservation.resource_id
           AND resource.company_id IS NOT NULL
           AND reservation.company_id IS DISTINCT FROM resource.company_id
        """
    )
    if cr.rowcount:
        _logger.info(
            "resource: %s reservation(s) moved to their resource's company",
            cr.rowcount,
        )


def _whole_days_end_at_midnight(cr):
    # a day is [midnight, next midnight): an exception older versions closed at
    # 23:59:59 local ends a second later, at its zone's next midnight
    cr.execute(
        """
        UPDATE resource_schedule_exception exception
           SET date_to = exception.date_to + interval '1 second'
          FROM resource_schedule_exception zoned
          LEFT JOIN resource_resource resource ON resource.id = zoned.resource_id
          LEFT JOIN resource_calendar calendar ON calendar.id = zoned.calendar_id
          LEFT JOIN res_company company ON company.id = zoned.company_id
          LEFT JOIN resource_calendar company_calendar
                 ON company_calendar.id = company.resource_calendar_id
         WHERE zoned.id = exception.id
           AND ((exception.date_to AT TIME ZONE 'UTC') AT TIME ZONE COALESCE(
                    resource.tz, calendar.tz, company_calendar.tz, 'UTC'
               ))::time = '23:59:59'
        """
    )
    if cr.rowcount:
        _logger.info("resource: %s exception(s) end at midnight", cr.rowcount)


def _only_fixed_hours_have_lines(cr):
    # a flexible schedule is read from its daily and weekly hours; the lines an
    # older version kept on it (a copy of the company's) meant nothing
    cr.execute(
        """
        DELETE FROM resource_calendar_attendance attendance
         USING resource_calendar calendar
         WHERE calendar.id = attendance.calendar_id
           AND calendar.schedule_type <> 'fully_fixed'
        """
    )
    if cr.rowcount:
        _logger.info(
            "resource: %s working hours line(s) dropped from flexible schedules",
            cr.rowcount,
        )


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    _every_person_is_a_party(cr, env)
    _user_follows_the_party(cr, env)
    _give_exceptions_a_kind(cr, env)
    _company_settings_move_to_config(cr, env)
    _reservations_follow_their_resource(cr)
    _whole_days_end_at_midnight(cr)
    _only_fixed_hours_have_lines(cr)
    schema.drop_columns(cr, "resource_assignment", ["company_id", "name"])
    # schedule_type is the only statement of a calendar's kind.
    schema.drop_columns(cr, "resource_calendar", ["flexible_hours"])
