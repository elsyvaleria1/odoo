import logging

from odoo.db import schema

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version or not schema.table_exists(cr, "exchange_transmission"):
        return
    cr.execute(
        """
        WITH ranked AS (
            SELECT id,
                   reference,
                   first_value(id) OVER holders AS holder_id,
                   row_number() OVER holders AS rank
              FROM exchange_transmission
             WHERE reference IS NOT NULL
            WINDOW holders AS (
                PARTITION BY channel_id, reference, intent, document_kind
                ORDER BY state = 'accepted' DESC, id
            )
        )
        UPDATE exchange_transmission transmission
           SET reference = NULL
          FROM ranked
         WHERE ranked.id = transmission.id
           AND ranked.rank > 1
     RETURNING transmission.id, ranked.reference, ranked.holder_id
        """
    )
    cleared = sorted(cr.fetchall())
    if cleared:
        _logger.warning(
            "exchange: %s transmission(s) repeated a counterparty reference "
            "another transmission of the same ask already holds, and lost it so "
            "that one transmission holds each reference: %s",
            len(cleared),
            ", ".join(
                f"#{transmission_id} ({reference}, kept on #{holder_id})"
                for transmission_id, reference, holder_id in cleared
            ),
        )
