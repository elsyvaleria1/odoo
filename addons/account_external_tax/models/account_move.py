from typing import Self

from odoo import models


class AccountMove(models.Model):
    _name = "account.move"
    _inherit = ["account.move", "mixin.account.external.tax"]

    def action_draft(self):
        res = super().action_draft()
        self._filtered_external_tax_moves()._uncommit_external_taxes()
        return res

    def unlink(self):
        self._filtered_external_tax_moves()._void_external_taxes()
        return super().unlink()

    def _post_entries(self):
        """Ensure taxes are correct before posting."""
        self._get_and_set_external_taxes_on_eligible_records()
        return super()._post_entries()

    def _filtered_external_tax_moves(self) -> Self:
        return self.filtered(
            lambda move: move.is_tax_computed_externally and not move._is_downpayment()
        )

    def _get_and_set_external_taxes_on_eligible_records(self):
        """mixin.account.external.tax override."""
        eligible_moves = self._filtered_external_tax_moves().filtered(
            lambda move: move.state != "posted"
        )
        eligible_moves._set_external_taxes(eligible_moves._get_external_taxes())
        return super()._get_and_set_external_taxes_on_eligible_records()

    def _prepare_line_data_for_external_taxes(self):
        """mixin.account.external.tax override."""
        base_lines_values = [
            value
            for value in self._get_rounded_base_and_tax_lines()[0]
            if not value["record"]._get_downpayment_lines()
        ]

        return [
            {
                "base_line": base_line,
                "description": base_line["record"].name,
            }
            for base_line in base_lines_values
        ]
