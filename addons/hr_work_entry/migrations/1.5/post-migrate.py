import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
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
