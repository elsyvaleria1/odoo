import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    # a generated window ends at the midnight after its last day; older
    # versions closed it at 23:59:59.999999 local, the last instant before it.
    # Generated stops are otherwise whole minutes.
    cr.execute(
        """
        UPDATE hr_version
           SET date_generated_to = date_trunc('minute', date_generated_to)
                                   + interval '1 minute'
         WHERE date_generated_to <> date_generated_from
           AND extract(second FROM date_generated_to) >= 59
        """
    )
    if cr.rowcount:
        _logger.info(
            "hr_work_entry: %s version(s) generated up to their next midnight",
            cr.rowcount,
        )
