from odoo import api, fields, models
from odoo.tools import SQL, frozendict


class ExchangeTransmissionDispatch(models.Model):
    _name = "exchange.transmission.dispatch"
    _description = "Exchange Transmission Dispatch"
    _order = "id"
    _log_access = False
    _access_anchors = frozendict(
        {
            "company": models.Anchor("company_id", shared=True),
        }
    )

    transmission_id = fields.Integer(
        required=True,
        help="The transmission handed off. Not a foreign key: a transmission "
        "created in the transaction that sends it is claimed before it is "
        "committed, and its claim must outlive that transaction rolling back.",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        required=True,
        ondelete="cascade",
    )
    ask_identity = fields.Char(
        index="btree_not_null",
        help="The ask a transmission claimed before it was committed carries: "
        "its subject, channel, intent and document kind. A claim whose "
        "transmission never committed tells the next transmission of the same "
        "ask that the document was already handed off.",
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
        self, claims: dict[int, tuple[int, str, int]]
    ) -> tuple[set[int], dict[int, tuple]]:
        cr = self.env.cr
        ids = list(claims)
        cr.execute(
            SQL("SELECT id FROM exchange_transmission WHERE id = ANY(%s)", ids),
        )
        seen = {transmission_id for [transmission_id] in cr.fetchall()}
        unseen = [
            transmission_id for transmission_id in ids if transmission_id not in seen
        ]
        claimed = self._insert_committed_claims(
            {transmission_id: claims[transmission_id][0] for transmission_id in seen}
        )
        lost = self._take_over_lost_claims({i: claims[i] for i in unseen})
        claimed |= self._insert_uncommitted_claims(
            {i: claims[i] for i in unseen if i not in lost}
        )
        return claimed, lost

    @api.model
    def _insert_committed_claims(self, dispatch_counts: dict[int, int]) -> set[int]:
        if not dispatch_counts:
            return set()
        ids = list(dispatch_counts)
        self.env.cr.execute(
            SQL(
                """
                INSERT INTO exchange_transmission_dispatch
                       (transmission_id, company_id, generation, date_dispatched)
                SELECT transmission.id,
                       transmission.company_id,
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
        return {transmission_id for [transmission_id] in self.env.cr.fetchall()}

    @api.model
    def _take_over_lost_claims(
        self, claims: dict[int, tuple[int, str, int]]
    ) -> dict[int, tuple]:
        if not claims:
            return {}
        ids = list(claims)
        self.env.cr.execute(
            SQL(
                """
                WITH lost AS (
                    DELETE FROM exchange_transmission_dispatch dispatch
                     USING unnest(%s::int[], %s::varchar[]) AS ask(id, ask_identity)
                     WHERE dispatch.ask_identity = ask.ask_identity
                       AND dispatch.transmission_id <> ask.id
                       AND NOT EXISTS (
                               SELECT 1
                                 FROM exchange_transmission transmission
                                WHERE transmission.id = dispatch.transmission_id
                           )
                 RETURNING ask.id, dispatch.date_dispatched
                )
                SELECT id, max(date_dispatched) FROM lost GROUP BY id
                """,
                ids,
                [claims[transmission_id][1] for transmission_id in ids],
            )
        )
        lost = dict(self.env.cr.fetchall())
        if not lost:
            return {}
        self.env.cr.execute(
            SQL(
                """
                INSERT INTO exchange_transmission_dispatch
                       (transmission_id, company_id, ask_identity, generation,
                        date_dispatched)
                SELECT lost.id, lost.company_id, lost.ask_identity,
                       lost.dispatch_count + 1, lost.date_dispatched
                  FROM unnest(%s::int[], %s::int[], %s::varchar[], %s::int[],
                              %s::timestamp[])
                       AS lost(id, company_id, ask_identity, dispatch_count,
                               date_dispatched)
             RETURNING transmission_id, generation, date_dispatched
                """,
                list(lost),
                [claims[transmission_id][2] for transmission_id in lost],
                [claims[transmission_id][1] for transmission_id in lost],
                [claims[transmission_id][0] for transmission_id in lost],
                list(lost.values()),
            )
        )
        return {
            transmission_id: (generation, date_dispatched)
            for transmission_id, generation, date_dispatched in self.env.cr.fetchall()
        }

    @api.model
    def _insert_uncommitted_claims(
        self, claims: dict[int, tuple[int, str, int]]
    ) -> set[int]:
        if not claims:
            return set()
        ids = list(claims)
        self.env.cr.execute(
            SQL(
                """
                INSERT INTO exchange_transmission_dispatch
                       (transmission_id, company_id, ask_identity, generation,
                        date_dispatched)
                SELECT claim.id, claim.company_id, claim.ask_identity,
                       claim.dispatch_count + 1, now() AT TIME ZONE 'UTC'
                  FROM unnest(%s::int[], %s::int[], %s::varchar[], %s::int[])
                       AS claim(id, company_id, ask_identity, dispatch_count)
                    ON CONFLICT (transmission_id, generation) DO NOTHING
             RETURNING transmission_id
                """,
                ids,
                [claims[transmission_id][2] for transmission_id in ids],
                [claims[transmission_id][1] for transmission_id in ids],
                [claims[transmission_id][0] for transmission_id in ids],
            )
        )
        return {transmission_id for [transmission_id] in self.env.cr.fetchall()}

    @api.model
    def _release_claims(self, dispatch_counts: dict[int, int]) -> None:
        ids = list(dispatch_counts)
        self.env.cr.execute(
            SQL(
                """
                DELETE FROM exchange_transmission_dispatch dispatch
                 USING unnest(%s::int[], %s::int[]) AS claim(id, dispatch_count)
                 WHERE dispatch.transmission_id = claim.id
                   AND dispatch.generation = claim.dispatch_count + 1
                """,
                ids,
                [dispatch_counts[transmission_id] for transmission_id in ids],
            )
        )

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

    @api.model
    def _gc_unlinked(self, transmission_ids: list[int]) -> None:
        self.env.cr.execute(
            SQL(
                "DELETE FROM exchange_transmission_dispatch"
                " WHERE transmission_id = ANY(%s)",
                transmission_ids,
            )
        )
