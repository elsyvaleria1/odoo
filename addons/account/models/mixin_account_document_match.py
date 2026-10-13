from odoo import api, fields, models
from odoo.tools import SQL, formatLang


class MixinAccountDocumentMatch(models.AbstractModel):
    _name = "mixin.account.document.match"
    _description = "Accounting Document Autocomplete Sources"

    company_id = fields.Many2one(
        comodel_name="res.company",
        readonly=True,
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        readonly=True,
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        readonly=True,
    )
    move_id = fields.Many2one(
        comodel_name="account.move",
        readonly=True,
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        readonly=True,
    )
    date = fields.Date(readonly=True)
    amount = fields.Float(readonly=True)
    name = fields.Char(
        string="Reference",
        readonly=True,
    )
    reference = fields.Char(
        string="Source",
        readonly=True,
    )
    move_type = fields.Selection(
        selection=lambda self: (
            self.env["account.move"]
            ._fields["move_type"]
            ._description_selection(self.env)
        ),
        readonly=True,
    )

    @api.depends("currency_id", "name", "reference", "amount")
    def _compute_display_name(self):
        for doc in self:
            label = doc.name or ""
            if doc.reference:
                label += " - " + doc.reference
            doc.display_name = (
                label
                + ": "
                + formatLang(
                    self.env,
                    doc.amount,
                    currency_obj=doc.currency_id,
                )
            )

    @property
    def _table_query(self):
        queries = [self._query_moves(), *self._get_additional_queries()]
        return SQL(" UNION ALL ").join(queries)

    @api.model
    def _get_additional_queries(self):
        return []

    @api.model
    def _get_document_columns(self):
        return {
            "id": SQL("NULL::BIGINT"),
            "name": SQL("NULL::VARCHAR"),
            "reference": SQL("NULL::VARCHAR"),
            "partner_id": SQL("NULL::INTEGER"),
            "date": SQL("NULL::DATE"),
            "amount": SQL("0.0"),
            "currency_id": SQL("NULL::INTEGER"),
            "company_id": SQL("NULL::INTEGER"),
            "move_id": SQL("NULL::INTEGER"),
            "user_id": SQL("NULL::INTEGER"),
            "move_type": SQL("NULL::VARCHAR"),
        }

    @api.model
    def _select_document_columns(self, values):
        columns = self._get_document_columns()
        columns.update(values)
        return SQL(", ").join(
            SQL("%s AS %s", value, SQL.identifier(name))
            for name, value in columns.items()
        )

    @api.model
    def _query_moves(self):
        return SQL(
            "SELECT %s FROM %s WHERE %s",
            self._select_moves(),
            self._from_moves(),
            self._where_moves(),
        )

    @api.model
    def _select_moves(self):
        return self._select_document_columns(
            {
                "id": SQL("am.id"),
                "name": SQL("am.name"),
                "reference": SQL("am.ref"),
                "partner_id": SQL("am.partner_id"),
                "date": SQL("am.date"),
                "amount": SQL("am.amount_untaxed"),
                "currency_id": SQL("am.currency_id"),
                "company_id": SQL("am.company_id"),
                "move_id": SQL("am.id"),
                "user_id": SQL("am.invoice_user_id"),
                "move_type": SQL("am.move_type"),
            }
        )

    @api.model
    def _from_moves(self):
        return SQL("account_move am")

    @api.model
    def _get_source_move_types(self):
        return ("in_invoice", "in_refund", "out_invoice", "out_refund")

    @api.model
    def _where_moves(self):
        Move = self.env["account.move"]
        if not Move.has_access("read"):
            return SQL("FALSE")
        readable = Move._search(
            [
                (
                    "move_type",
                    "in",
                    self._get_source_move_types(),
                ),
            ]
        )
        return SQL("am.id IN (%s)", readable.select())
