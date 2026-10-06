# One migration for every 19.0 database, whatever resource version it holds:
# each step reads the state it repairs instead of trusting the version, so a
# database that skipped steps, or already holds their outcome, is brought to
# the same place. Odoo runs every pre-, then post-, then end- script of the
# pending versions in that order, so the steps keep the order they had as
# separate versions.
import logging

from odoo.db.schema import column_exists, table_exists
from odoo.tools import SQL, module_data

_logger = logging.getLogger(__name__)

SCHEDULE_EXCEPTION_RECORD_MODELS = (
    "ir.ui.view",
    "ir.actions.act_window",
    "ir.access",
    "ir.ui.menu",
)
ROLE_FIELDS_FROM_PLANNING = (
    "field_resource_resource__role_ids",
    "field_resource_resource__default_role_id",
    "field_resource_role__resource_ids",
)


def _check_series(version):
    if not version.startswith("19.0."):
        raise RuntimeError(
            f"resource upgrades only a 19.0 database; this one holds {version}"
        )


def _absorb_mixin_recurrence(cr):
    # mixin_recurrence was dissolved into resource: re-point its rows rather
    # than let the loader orphan the abstract model and its access.
    cr.execute(
        """
        DELETE FROM ir_model_data dissolved
              USING ir_model_data surviving
              WHERE dissolved.module = 'mixin_recurrence'
                AND surviving.module = 'resource'
                AND surviving.name = dissolved.name
        """
    )
    cr.execute(
        "UPDATE ir_model_data SET module = 'resource' WHERE module = 'mixin_recurrence'"
    )
    cr.execute(
        """
        UPDATE ir_module_module SET state = 'uninstalled'
         WHERE name = 'mixin_recurrence'
           AND state NOT IN ('uninstalled', 'uninstallable')
        """
    )
    cr.execute(
        "DELETE FROM ir_module_module_dependency WHERE name = 'mixin_recurrence'"
    )


def _take_roles_from_planning(cr):
    cr.execute(
        """
        UPDATE ir_model_data AS source
           SET module = 'resource'
         WHERE source.module = 'planning'
           AND source.model = 'ir.model.fields'
           AND source.name = ANY(%s)
           AND NOT EXISTS (
               SELECT 1 FROM ir_model_data AS target
                WHERE target.module = 'resource' AND target.name = source.name
           )
        """,
        [list(ROLE_FIELDS_FROM_PLANNING)],
    )
    cr.execute(
        """
        UPDATE ir_model_relation
           SET module = (SELECT id FROM ir_module_module WHERE name = 'resource')
         WHERE name = 'resource_resource_role_rel'
           AND module = (SELECT id FROM ir_module_module WHERE name = 'planning')
        """
    )


def _rename_calendar_leaves(cr):
    if table_exists(cr, "resource_calendar_leaves") and not table_exists(
        cr, "resource_schedule_exception"
    ):
        module_data.rename_model(
            cr, "resource.calendar.leaves", "resource.schedule.exception"
        )
    cr.execute(
        """
        UPDATE ir_model_data d
           SET name = regexp_replace(
                   d.name, 'resource_calendar_leaves?', 'resource_schedule_exception', 'g'
               )
         WHERE d.model = ANY(%s)
           AND d.name ~ 'resource_calendar_leave'
           AND NOT EXISTS (
                SELECT 1 FROM ir_model_data e
                 WHERE e.module = d.module
                   AND e.name = regexp_replace(
                       d.name, 'resource_calendar_leaves?', 'resource_schedule_exception', 'g'
                   )
           )
        """,
        [list(SCHEDULE_EXCEPTION_RECORD_MODELS)],
    )


def _name_the_custody_role(cr):
    if not table_exists(cr, "resource_assignment"):
        return
    # One custody role: a vehicle's driver is the operator of a vehicle.
    for column in ("role", "custody_role"):
        if column_exists(cr, "resource_assignment", column):
            cr.execute(
                SQL(
                    "UPDATE resource_assignment SET %s = 'operator' WHERE %s = 'driver'",
                    SQL.identifier(column),
                    SQL.identifier(column),
                )
            )
    module_data.rename_field(cr, "resource.assignment", "role", "custody_role")


def _repair_attendances(cr):
    cr.execute(
        """
        UPDATE resource_calendar_attendance att
           SET week_type = '0'
          FROM resource_calendar cal
         WHERE att.calendar_id = cal.id
           AND cal.two_weeks_calendar
           AND att.display_type IS NULL
           AND att.week_type IS NULL
        """
    )
    if cr.rowcount:
        _logger.warning(
            "resource: %s line(s) of two-week schedules had no week and were"
            " given the first, the week they already behaved as",
            cr.rowcount,
        )


def _repair_reservation_shares(cr):
    # end-migrate recomputes every reservation's hours, these included.
    if not table_exists(cr, "resource_reservation"):
        return
    cr.execute(
        """
        UPDATE resource_reservation
           SET allocated_percentage = 100
         WHERE allocated_percentage IS NULL
        """
    )
    if cr.rowcount:
        _logger.warning(
            "resource: %s reservation(s) held no share and now claim 100%%: a"
            " NULL passed the CHECK while the ORM read it as 0",
            cr.rowcount,
        )
    cr.execute(
        """
        UPDATE resource_reservation
           SET allocated_percentage = LEAST(100, GREATEST(0, allocated_percentage))
         WHERE allocated_percentage < 0 OR allocated_percentage > 100
        """
    )
    if cr.rowcount:
        _logger.warning(
            "resource: %s reservation share(s) outside 0..100 were clamped",
            cr.rowcount,
        )


def _state_the_schedule_type(cr):
    if not column_exists(cr, "resource_calendar", "schedule_type"):
        cr.execute("ALTER TABLE resource_calendar ADD COLUMN schedule_type varchar")
    if column_exists(cr, "resource_calendar", "flexible_hours"):
        # flexible_hours is the statement every version before this one kept;
        # a schedule_type column found beside it may be a stale copy.
        cr.execute(
            """
            UPDATE resource_calendar
               SET schedule_type = CASE WHEN flexible_hours THEN 'flexible'
                                        ELSE 'fully_fixed' END
             WHERE schedule_type IS DISTINCT FROM 'fully_flexible'
            """
        )
    cr.execute(
        "UPDATE resource_calendar SET schedule_type = 'fully_fixed'"
        " WHERE schedule_type IS NULL"
    )


def _hold_the_fully_flexible_calendar(cr):
    # A resource without a calendar was fully flexible; it now holds the one
    # schedule that says so, created here so calendar_id can become NOT NULL
    # in this upgrade. The data file finds it by its external id. It has no
    # zone, which tz therefore stops requiring at the column.
    cr.execute("ALTER TABLE resource_calendar ALTER COLUMN tz DROP NOT NULL")
    cr.execute(
        """
        SELECT res_id FROM ir_model_data
         WHERE module = 'resource' AND name = 'resource_calendar_fully_flexible'
        """
    )
    row = cr.fetchone()
    if row:
        calendar_id = row[0]
    else:
        cr.execute(
            """
            INSERT INTO resource_calendar
                   (name, active, tz, schedule_type, hours_per_day, hours_per_week,
                    full_time_required_hours,
                    create_uid, write_uid, create_date, write_date)
            VALUES ('Fully Flexible', TRUE, NULL, 'fully_flexible', 8, 40, 40,
                    1, 1, now() AT TIME ZONE 'UTC', now() AT TIME ZONE 'UTC')
            RETURNING id
            """
        )
        calendar_id = cr.fetchone()[0]
        cr.execute(
            """
            INSERT INTO ir_model_data (module, name, model, res_id, noupdate)
            VALUES ('resource', 'resource_calendar_fully_flexible',
                    'resource.calendar', %s, TRUE)
            """,
            [calendar_id],
        )
    cr.execute(
        "UPDATE resource_resource SET calendar_id = %s WHERE calendar_id IS NULL",
        [calendar_id],
    )
    if cr.rowcount:
        _logger.info(
            "resource: %s resource(s) without a schedule hold Fully Flexible",
            cr.rowcount,
        )


def migrate(cr, version):
    if not version:
        return
    _check_series(version)
    _absorb_mixin_recurrence(cr)
    _take_roles_from_planning(cr)
    _rename_calendar_leaves(cr)
    _name_the_custody_role(cr)
    _repair_attendances(cr)
    _repair_reservation_shares(cr)
    _state_the_schedule_type(cr)
    _hold_the_fully_flexible_calendar(cr)
