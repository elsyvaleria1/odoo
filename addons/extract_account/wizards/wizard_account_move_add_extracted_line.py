from __future__ import annotations

from odoo import Command, api, fields, models
from odoo.exceptions import UserError

from .wizard_account_move_add_extracted_line_proposal import _read_untaxed_total


class WizardAccountMoveAddExtractedLine(models.TransientModel):
    _name = "wizard.account.move.add.extracted.line"
    _description = "Review Lines Read From a Document"

    move_id = fields.Many2one(
        comodel_name="account.move",
        readonly=True,
        required=True,
    )
    line_ids = fields.One2many(
        comodel_name="wizard.account.move.add.extracted.line.proposal",
        inverse_name="wizard_id",
    )
    currency_id = fields.Many2one(related="move_id.currency_id")
    read_total = fields.Monetary(
        currency_field="currency_id",
        readonly=True,
    )
    read_untaxed_total = fields.Monetary(
        currency_field="currency_id",
        readonly=True,
    )
    proposed_total = fields.Monetary(
        currency_field="currency_id",
        compute="_compute_proposed_total",
    )
    totals_agree = fields.Boolean(compute="_compute_totals_agree")

    @api.depends("line_ids.subtotal", "line_ids.accepted")
    def _compute_proposed_total(self) -> None:
        for wizard in self:
            wizard.proposed_total = sum(
                line.subtotal for line in wizard.line_ids if line.accepted
            )

    @api.depends("proposed_total", "read_untaxed_total", "currency_id")
    def _compute_totals_agree(self) -> None:
        for wizard in self:
            currency = wizard.currency_id or wizard.move_id.company_id.currency_id
            wizard.totals_agree = (
                currency.compare_amounts(
                    wizard.proposed_total, wizard.read_untaxed_total
                )
                == 0
                if wizard.read_untaxed_total
                else True
            )

    @api.model
    def _prepare_from_move(self, move) -> dict:
        result = move.extract_result or {}
        envelope = move._extract_read_lines()
        lines = envelope.get("value") or []
        return {
            "move_id": move.id,
            "read_total": (result.get("total") or {}).get("value") or 0.0,
            "read_untaxed_total": _read_untaxed_total(result),
            "line_ids": [
                Command.create(
                    {
                        "sequence": index * 10,
                        "read_index": index,
                        "read_by": envelope.get("source") or "",
                        "confidence": envelope.get("confidence") or 0.0,
                        **move._extract_line_seed(line),
                    }
                )
                for index, line in enumerate(lines)
            ],
        }

    def action_apply(self):
        self.check_singleton()
        move = self.move_id
        if move.state != "draft":
            raise UserError(
                self.env._("Only a draft bill can take lines read from its document.")
            )
        if move.extract_lines_applied:
            raise UserError(
                self.env._(
                    "The lines read from this document were already added to "
                    "this bill. Read the document again to offer them afresh."
                )
            )

        accepted = self.line_ids.filtered("accepted")
        if not accepted:
            raise UserError(self.env._("No line was accepted, so nothing was added."))

        move.write(
            {
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": line.description,
                            "quantity": line.quantity,
                            "price_unit": line.price_unit,
                            **(
                                {"product_id": line.product_id.id}
                                if line.product_id
                                else {}
                            ),
                        }
                    )
                    for line in accepted
                ]
            }
        )
        move._add_extraction_correction_for_lines(self.line_ids)
        move.extract_lines_applied = True
        return {"type": "ir.actions.act_window_close"}
