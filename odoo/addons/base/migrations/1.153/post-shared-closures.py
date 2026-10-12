import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    cr.execute(
        """
        UPDATE resource_schedule_exception exception
           SET company_id = NULL
          FROM resource_calendar calendar
         WHERE exception.calendar_id = calendar.id
           AND calendar.company_id IS NULL
           AND exception.resource_id IS NULL
           AND exception.company_id IS NOT NULL
        """
    )
    if cr.rowcount:
        _logger.info(
            "Released %d closure(s) of shared calendars from the company of "
            "whoever entered them; every company on the calendar now sees them",
            cr.rowcount,
        )
