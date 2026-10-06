from __future__ import annotations

from odoo import api, fields, models


def _read_untaxed_total(result: dict) -> float:
    subtotal = (result.get("subtotal") or {}).get("value")
    if subtotal is not None:
        return subtotal
    total = (result.get("total") or {}).get("value") or 0.0
    tax = (result.get("tax_amount") or {}).get("value")
    return total - tax if tax is not None else total


class WizardAccountMoveAddExtractedLineProposal(models.TransientModel):
    _name = "wizard.account.move.add.extracted.line.proposal"
    _description = "Line Read From a Document, Awaiting a Person"
    _order = "sequence, id"

    wizard_id = fields.Many2one(
        comodel_name="wizard.account.move.add.extracted.line",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(default=10)
    read_index = fields.Integer(
        readonly=True,
        help="Position of this line in what the document said. Kept so a "
        "correction is attributed to the line it was made on even after the "
        "rows are reordered.",
    )
    accepted = fields.Boolean(default=True)
    description = fields.Char(required=True)
    quantity = fields.Float(default=1.0)
    price_unit = fields.Monetary(currency_field="currency_id")
    product_id = fields.Many2one(comodel_name="product.product")
    read_by = fields.Char(readonly=True)
    confidence = fields.Float(
        digits=(3, 2),
        readonly=True,
    )
    currency_id = fields.Many2one(related="wizard_id.move_id.currency_id")
    subtotal = fields.Monetary(
        currency_field="currency_id",
        compute="_compute_subtotal",
    )

    @api.depends("quantity", "price_unit")
    def _compute_subtotal(self) -> None:
        for proposal in self:
            proposal.subtotal = proposal.quantity * proposal.price_unit
