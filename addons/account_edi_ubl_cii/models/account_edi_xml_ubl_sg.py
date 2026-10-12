from odoo import models
from odoo.tools import float_is_zero

from odoo.addons.account_edi_ubl_cii.tools.ubl_line import update_ubl_discount_node


class AccountEdiXmlUbl_Sg(models.AbstractModel):
    _name = "account.edi.xml.ubl_sg"
    _inherit = ["account.edi.xml.ubl_bis3"]
    _description = "SG BIS Billing 3.0"

    """
    Documentation: https://www.peppolguide.sg/billing/bis/
    """

    def _export_invoice_filename(self, invoice):
        return f"{invoice.name.replace('/', '_')}_sg.xml"

    def _get_customization_id(self, process_type="billing"):
        if process_type == "billing":
            return "urn:cen.eu:en16931:2017#conformant#urn:fdc:peppol.eu:2017:poacc:billing:international:sg:3.0"
        return None

    def _ubl_default_tax_category_grouping_key(
        self, base_line, tax_data, vals, currency
    ):
        grouping_key = super()._ubl_default_tax_category_grouping_key(
            base_line, tax_data, vals, currency
        )
        if not grouping_key:
            return None

        grouping_key["scheme_id"] = "GST"
        grouping_key["tax_exemption_reason"] = None
        grouping_key["tax_exemption_reason_code"] = None

        if not tax_data or float_is_zero(tax_data["tax"].amount, precision_digits=4):
            grouping_key["tax_category_code"] = "ZR"
        else:
            grouping_key["tax_category_code"] = "SR"

        return grouping_key

    def _ubl_get_line_allowance_charge_discount_node(self, vals, discount_values):
        discount_node = super()._ubl_get_line_allowance_charge_discount_node(
            vals, discount_values
        )
        update_ubl_discount_node(discount_node)
        return discount_node

    def _ubl_add_values_tax_currency_code(self, vals):
        self._ubl_add_values_tax_currency_code_empty(vals)

    def _ubl_tax_totals_node_grouping_key(self, base_line, tax_data, vals, currency):
        tax_total_keys = super()._ubl_tax_totals_node_grouping_key(
            base_line, tax_data, vals, currency
        )

        self._update_tax_total_keys_without_company_currency(tax_total_keys, vals)

        return tax_total_keys

    def _add_invoice_payment_means_nodes(self, document_node, vals):
        super()._add_invoice_payment_means_nodes(document_node, vals)
        document_node["cac:PaymentMeans"]["cbc:PaymentMeansCode"] = {
            "_text": 54,
            "name": "Credit Card",
        }

    def _get_party_node(self, vals):
        party_node = super()._get_party_node(vals)
        party_node["cac:PartyTaxScheme"][0]["cac:TaxScheme"]["cbc:ID"]["_text"] = "GST"
        return party_node
