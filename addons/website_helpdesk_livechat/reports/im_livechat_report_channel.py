from odoo import fields, models
from odoo.tools import SQL, frozendict


class Im_LivechatReportChannel(models.Model):
    _inherit = "im_livechat.report.channel"
    _depends = frozendict(
        {
            "helpdesk.ticket": ["origin_channel_id"],
        }
    )

    tickets_created = fields.Integer(
        string="Tickets created",
        readonly=True,
        aggregator="sum",
    )

    def _select(self) -> SQL:
        return SQL(
            "%s, helpdesk_ticket_data.tickets_created AS tickets_created",
            super()._select(),
        )

    def _from(self) -> SQL:
        return SQL(
            """%s
            LEFT JOIN LATERAL
                (
                    SELECT count(*) AS tickets_created
                      FROM helpdesk_ticket
                     WHERE helpdesk_ticket.origin_channel_id = C.id
                ) AS helpdesk_ticket_data ON TRUE
            """,
            super()._from(),
        )
