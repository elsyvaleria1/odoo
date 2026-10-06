from odoo import models


class AccountTax(models.Model):
    _inherit = "account.tax"

    def _prepare_base_line_for_taxes_computation(self, record, **kwargs):
        # EXTENDS 'account'
        results = super()._prepare_base_line_for_taxes_computation(record, **kwargs)
        results["asset_id"] = self._get_base_line_field_value_from_record(
            record, "asset_id", kwargs, self.env["resource.asset"]
        )
        return results

    def _prepare_tax_line_for_taxes_computation(self, record, **kwargs):
        # EXTENDS 'account'
        results = super()._prepare_tax_line_for_taxes_computation(record, **kwargs)
        results["asset_id"] = self._get_base_line_field_value_from_record(
            record, "asset_id", kwargs, self.env["resource.asset"]
        )
        return results

    def _prepare_base_line_grouping_key(self, base_line):
        # EXTENDS 'account'
        results = super()._prepare_base_line_grouping_key(base_line)
        results["asset_id"] = base_line["asset_id"].id
        return results

    def _prepare_base_line_tax_repartition_grouping_key(
        self, base_line, base_line_grouping_key, tax_data, tax_rep_data
    ):
        # EXTENDS 'account'
        results = super()._prepare_base_line_tax_repartition_grouping_key(
            base_line, base_line_grouping_key, tax_data, tax_rep_data
        )
        results["asset_id"] = (
            base_line_grouping_key["asset_id"]
            if not tax_rep_data["tax_rep"].use_in_tax_closing
            else False
        )
        return results

    def _prepare_tax_line_repartition_grouping_key(self, tax_line):
        # EXTENDS 'account'
        results = super()._prepare_tax_line_repartition_grouping_key(tax_line)
        results["asset_id"] = tax_line["asset_id"].id
        return results
