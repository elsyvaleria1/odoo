import logging

from odoo.tools import SQL

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Tick the evidence of the transfers that carry only the customer's signature.

    "Valid Evidence" now counts the signature as well as the photo. A transfer
    with a photo keeps its tick as it is, since a reviewer may have rejected it;
    an empty attachment is neither.
    """
    if not version:
        return
    cr.execute(
        SQL(
            """
            UPDATE stock_picking p
               SET delivery_proof_ok = TRUE
             WHERE p.delivery_proof_ok IS NOT TRUE
               AND EXISTS (SELECT 1
                             FROM ir_attachment a
                            WHERE a.res_model = 'stock.picking'
                              AND a.res_field = 'signature'
                              AND a.res_id = p.id
                              AND a.file_size > 0)
               AND NOT EXISTS (SELECT 1
                                 FROM ir_attachment a
                                WHERE a.res_model = 'stock.picking'
                                  AND a.res_field = 'delivery_proof'
                                  AND a.res_id = p.id
                                  AND a.file_size > 0)
            """
        )
    )
    if cr.rowcount:
        _logger.info(
            "stock_fleet: %s transfer(s) signed by the customer now count as evidence",
            cr.rowcount,
        )
