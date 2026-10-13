from odoo import api, fields, models
from odoo.tools import SQL, frozendict


class ExchangeTransmissionDispatch(models.Model):
    _name = "exchange.transmission.dispatch"
    _description = "Exchange Transmission Dispatch"
    _order = "id"
    _log_access = False
    _access_anchors = frozendict(
        {
            "company": models.Anchor("transmission_id.company_id", shared=True),
        }
    )

    transmission_id = fields.Many2one(
        comodel_name="exchange.transmission",
        required=True,
        ondelete="cascade",
    )
    generation = fields.Integer(
        required=True,
        help="The dispatch count this hand-off brings its transmission to. "
        "While it is ahead of the transmission's own count, the answer to the "
        "hand-off was never recorded.",
    )
    date_dispatched = fields.Datetime(required=True)

    _generation_uniq = models.UniqueIndex(
        "(transmission_id, generation)",
        "A transmission is handed to its counterparty once per dispatch.",
    )

    @api.model
    def _insert_claims(
        self, dispatch_counts: dict[int, int]
    ) -> tuple[set[int], set[int]]:
        cr = self.env.cr
        ids = list(dispatch_counts)
        cr.execute(
            SQL("SELECT id FROM exchange_transmission WHERE id = ANY(%s)", ids),
        )
        unseen = set(ids) - {transmission_id for [transmission_id] in cr.fetchall()}
        cr.execute(
            SQL(
                """
                INSERT INTO exchange_transmission_dispatch
                       (transmission_id, generation, date_dispatched)
                SELECT transmission.id,
                       COALESCE(transmission.dispatch_count, 0) + 1,
                       now() AT TIME ZONE 'UTC'
                  FROM exchange_transmission transmission
                  JOIN unnest(%s::int[], %s::int[]) AS seen(id, dispatch_count)
                    ON seen.id = transmission.id
                 WHERE COALESCE(transmission.dispatch_count, 0) = seen.dispatch_count
                   AND transmission.state IN ('draft', 'queued')
                    ON CONFLICT (transmission_id, generation) DO NOTHING
             RETURNING transmission_id
                """,
                ids,
                [dispatch_counts[transmission_id] for transmission_id in ids],
            )
        )
        return {transmission_id for [transmission_id] in cr.fetchall()}, unseen

    @api.model
    def _get_unanswered(self, transmission_ids: list[int] | None = None) -> dict:
        self.env["exchange.transmission"].flush_model(["dispatch_count"])
        self.env.cr.execute(
            SQL(
                """
                SELECT dispatch.transmission_id,
                       max(dispatch.generation),
                       max(dispatch.date_dispatched)
                  FROM exchange_transmission_dispatch dispatch
                  JOIN exchange_transmission transmission
                    ON transmission.id = dispatch.transmission_id
                 WHERE dispatch.generation > COALESCE(transmission.dispatch_count, 0)
                   %s
              GROUP BY dispatch.transmission_id
                """,
                SQL("AND dispatch.transmission_id = ANY(%s)", transmission_ids)
                if transmission_ids is not None
                else SQL(),
            )
        )
        return {
            transmission_id: (generation, date_dispatched)
            for transmission_id, generation, date_dispatched in self.env.cr.fetchall()
        }

    @api.model
    def _gc_answered(self) -> None:
        self.env["exchange.transmission"].flush_model(["dispatch_count"])
        self.env.cr.execute(
            SQL(
                """
                DELETE FROM exchange_transmission_dispatch dispatch
                 USING exchange_transmission transmission
                 WHERE transmission.id = dispatch.transmission_id
                   AND dispatch.generation <= COALESCE(transmission.dispatch_count, 0)
                """
            )
        )
