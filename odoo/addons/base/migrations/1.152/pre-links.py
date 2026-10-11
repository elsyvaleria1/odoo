import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    cr.execute(
        """
        UPDATE access_link
           SET date_to = (now() AT TIME ZONE 'UTC')
                         + CASE cause WHEN 'share' THEN interval '30 days'
                                      ELSE interval '365 days' END
         WHERE date_to IS NULL
           AND revoked_at IS NULL
           AND expiry_waived IS NOT TRUE
        """
    )
    _logger.info("access links given an expiry: %s", cr.rowcount)
    cr.execute(
        "SELECT count(*) FROM access_link WHERE audience = 'partners' "
        "AND revoked_at IS NULL"
    )
    _logger.info("access links narrowed to their named people: %s", cr.fetchone()[0])
