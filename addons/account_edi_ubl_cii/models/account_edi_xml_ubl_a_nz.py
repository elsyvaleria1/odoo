from odoo import models

from odoo.addons.account_edi_ubl_cii.tools.ubl_line import update_ubl_discount_node


class AccountEdiXmlUbl_A_Nz(models.AbstractModel):
    _name = "account.edi.xml.ubl_a_nz"
    _inherit = ["account.edi.xml.ubl_bis3"]
    _description = "A-NZ BIS Billing 3.0"

    """
    * Documentation: https://github.com/A-NZ-PEPPOL/A-NZ-PEPPOL-BIS-3.0/tree/master/Specifications
    """


    def _export_invoice_filename(self, invoice):
        return f"{invoice.name.replace('/', '_')}_a_nz.xml"


    def _get_customization_id(self, process_type="billing"):
        if process_type == "billing":
            return "urn:cen.eu:en16931:2017#conformant#urn:fdc:peppol.eu:2017:poacc:billing:international:aunz:3.0"
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

    def _get_party_node(self, vals):
        party_node = super()._get_party_node(vals)
        partner = vals["partner"]
        commercial_partner = partner.commercial_partner_id

        if commercial_partner.country_code == "AU" and commercial_partner.vat:
            vat = commercial_partner.vat.replace(" ", "")
            party_node["cbc:EndpointID"]["_text"] = vat
            party_node["cac:PartyTaxScheme"][0]["cbc:CompanyID"]["_text"] = vat
            party_node["cac:PartyLegalEntity"]["cbc:CompanyID"] = {
                "_text": vat,
                "schemeID": "0151",
            }

        elif commercial_partner.country_code == "NZ":
            party_node["cbc:EndpointID"]["_text"] = commercial_partner.company_registry
            party_node["cac:PartyTaxScheme"][0]["cbc:CompanyID"]["_text"] = (
                commercial_partner.company_registry
            )
            party_node["cac:PartyLegalEntity"]["cbc:CompanyID"] = {
                "_text": commercial_partner.company_registry,
                "schemeID": "0088",
            }

        party_node["cac:PartyTaxScheme"][0]["cac:TaxScheme"]["cbc:ID"]["_text"] = "GST"

        return party_node
