import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    cr.execute(
        """
        UPDATE frontdesk_visitor AS visitor
           SET company_id = station.company_id
          FROM frontdesk_frontdesk AS station
         WHERE station.id = visitor.station_id
           AND visitor.company_id IS DISTINCT FROM station.company_id
        """
    )
    _logger.info("frontdesk: %s visitors moved to their station's company", cr.rowcount)
