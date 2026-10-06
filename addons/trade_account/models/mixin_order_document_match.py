from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL, formatLang

from odoo.addons.trade.tools import TradeDirection, direction_of

_debug = DebugLog(__name__)


class MixinOrderDocumentMatch(models.AbstractModel):
    _name = "mixin.order.document.match"
    _inherit = "mixin.account.document.match"
    _description = "Orders & Invoices Union"

    _order_table = ""
    _direction: TradeDirection | None = None
    _order_reference_column = "partner_ref"

    order_id = fields.Many2one(
        comodel_name="mixin.order",
        readonly=True,
    )

    @api.depends("currency_id", "name", "reference", "amount", "order_id")
    def _compute_display_name(self):
        super()._compute_display_name()
        for doc in self.filtered(lambda source: source.order_id.invoice_state == "no"):
            label = doc.name or ""
            if doc.reference:
                label += " - " + doc.reference
            doc.display_name = (
                label
                + ": "
                + formatLang(
                    self.env,
                    0.0,
                    currency_obj=doc.currency_id,
                )
            )

    @api.model
    def _get_document_columns(self):
        return {**super()._get_document_columns(), "order_id": SQL("NULL::INTEGER")}

    @api.model
    def _get_additional_queries(self):
        return [*super()._get_additional_queries(), self._query_orders()]

    @api.model
    def _get_source_move_types(self):
        return direction_of(self).move_types

    @api.model
    def _where_moves(self):
        return SQL("am.state = 'posted' AND %s", super()._where_moves())

    @api.model
    def _query_orders(self):
        return SQL(
            """
            SELECT
                %s
            FROM
                %s
            WHERE
                %s
            """,
            self._select_orders(),
            self._from_orders(),
            self._where_orders(),
        )

    @api.model
    def _select_orders(self):
        return self._select_document_columns(
            {
                "id": SQL("-o.id"),
                "name": SQL("o.name"),
                "reference": SQL("o.%s", SQL.identifier(self._order_reference_column)),
                "partner_id": SQL("o.partner_id"),
                "date": SQL("o.date_order::DATE"),
                "amount": SQL("o.amount_untaxed"),
                "currency_id": SQL("o.currency_id"),
                "company_id": SQL("o.company_id"),
                "order_id": SQL("o.id"),
                "user_id": SQL("o.user_id"),
                "move_type": SQL("%s", direction_of(self).move_types[0]),
            }
        )

    @api.model
    def _get_order_table(self):
        if not self._order_table:
            _debug.logic("order_table_undeclared", model=self._name)
            raise NotImplementedError(f"{self._name} must declare _order_table")
        return self._order_table

    @api.model
    def _from_orders(self):
        return SQL("%s o", SQL.identifier(self._get_order_table()))

    @api.model
    def _where_orders(self):
        Order = self.env[self._fields["order_id"].comodel_name]
        if not Order.has_access("read"):
            return SQL("FALSE")
        readable = Order._search([])
        return SQL(
            """
            o.state = 'done'
            AND o.invoice_state IN ('to do', 'no', 'partial')
            AND o.id IN (%s)
            """,
            readable.select(),
        )
