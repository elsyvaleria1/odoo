import logging

from odoo.db import schema

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    _take_rule_constraint_from_base(cr)
    if not schema.column_exists(cr, "calendar_recurrence", "week_start"):
        _backfill_week_start(cr)


def _take_rule_constraint_from_base(cr):
    cr.execute(
        """
        DELETE FROM ir_model_data moved
              USING ir_model_data kept
              WHERE moved.module = 'base'
                AND kept.module = 'calendar'
                AND moved.name = kept.name
                AND moved.name = 'constraint_calendar_recurrence_month_day'
        """
    )
    cr.execute(
        """
        DELETE FROM ir_model_constraint moved
              USING ir_model_constraint kept, ir_module_module base, ir_module_module calendar
              WHERE base.name = 'base'
                AND calendar.name = 'calendar'
                AND moved.module = base.id
                AND kept.module = calendar.id
                AND moved.name = kept.name
                AND moved.name = 'calendar_recurrence_month_day'
        """
    )
    cr.execute(
        """
        UPDATE ir_model_constraint
           SET module = (SELECT id FROM ir_module_module WHERE name = 'calendar')
         WHERE name = 'calendar_recurrence_month_day'
           AND module = (SELECT id FROM ir_module_module WHERE name = 'base')
        """
    )
    cr.execute(
        """
        UPDATE ir_model_data
           SET module = 'calendar'
         WHERE module = 'base'
           AND model = 'ir.model.constraint'
           AND name = 'constraint_calendar_recurrence_month_day'
        """
    )


def _backfill_week_start(cr):
    schema.create_column(cr, "calendar_recurrence", "week_start", "varchar")
    cr.execute(
        """
        UPDATE calendar_recurrence
           SET week_start = CASE substring(rrule FROM 'WKST=(MO|TU|WE|TH|FR|SA|SU)')
                   WHEN 'MO' THEN 'MON' WHEN 'TU' THEN 'TUE' WHEN 'WE' THEN 'WED'
                   WHEN 'TH' THEN 'THU' WHEN 'FR' THEN 'FRI' WHEN 'SA' THEN 'SAT'
                   WHEN 'SU' THEN 'SUN'
               END
         WHERE rrule ~ 'WKST=(MO|TU|WE|TH|FR|SA|SU)'
        """
    )
    from_rule = cr.rowcount
    cr.execute(
        """
        UPDATE calendar_recurrence
           SET week_start = 'MON'
         WHERE week_start IS NULL AND rrule ~ 'FREQ=WEEKLY'
        """
    )
    weekly_monday = cr.rowcount
    cr.execute(
        """
        UPDATE calendar_recurrence recurrence
           SET week_start = (ARRAY['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN'])[
                   lang.week_start::int
               ]
          FROM res_users users
          JOIN res_partner partner ON partner.id = users.partner_id
          JOIN res_lang lang ON lang.code = partner.lang
         WHERE recurrence.week_start IS NULL
           AND users.id = recurrence.create_uid
        """
    )
    from_creator = cr.rowcount
    cr.execute(
        "UPDATE calendar_recurrence SET week_start = 'MON' WHERE week_start IS NULL"
    )
    _logger.info(
        "calendar: week start of %s recurrence(s) read from their rule, %s weekly "
        "one(s) set to Monday, %s taken from their creator's language, %s defaulted "
        "to Monday",
        from_rule,
        weekly_monday,
        from_creator,
        cr.rowcount,
    )
