from odoo import models


class AccountTax(models.Model):
    _inherit = "account.tax"

    def _prepare_base_line_tax_repartition_grouping_key(
        self, base_line, base_line_grouping_key, tax_data, tax_rep_data
    ):
        res = super()._prepare_base_line_tax_repartition_grouping_key(
            base_line, base_line_grouping_key, tax_data, tax_rep_data
        )
        record = base_line["record"]
        if (
            isinstance(record, models.Model)
            and record._name == "account.move.line"
            and record.move_id.is_tax_computed_externally
        ):
            res["__keep_zero_line"] = True
        return res
