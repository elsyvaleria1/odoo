from odoo import models

from odoo.addons.account_edi_ubl_cii.tools.ubl_line import update_ubl_discount_node


class AccountEdiXmlUbl_De(models.AbstractModel):
    _name = "account.edi.xml.ubl_de"
    _inherit = ["account.edi.xml.ubl_bis3"]
    _description = "BIS3 DE (XRechnung)"

    def _export_invoice_filename(self, invoice):
        return f"{invoice.name.replace('/', '_')}_ubl_de.xml"

    def _export_invoice_constraints(self, invoice, vals):
        constraints = super()._export_invoice_constraints(invoice, vals)

        constraints.update(
            {
                "bis3_de_supplier_telephone_required": self._check_required_fields(
                    vals["supplier"], ["phone_ids"]
                ),
                "bis3_de_supplier_electronic_mail_required": self._check_required_fields(
                    vals["supplier"], "email"
                ),
            }
        )

        return constraints

    def _get_customization_id(self, process_type="billing"):
        if process_type == "billing":
            return (
                "urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0"
            )
        return None

    def _ubl_add_values_tax_currency_code(self, vals):
        self._ubl_add_values_tax_currency_code_empty(vals)

    def _ubl_tax_totals_node_grouping_key(self, base_line, tax_data, vals, currency):
        tax_total_keys = super()._ubl_tax_totals_node_grouping_key(
            base_line, tax_data, vals, currency
        )

        self._update_tax_total_keys_without_company_currency(tax_total_keys, vals)

        return tax_total_keys

    def _add_invoice_header_nodes(self, document_node, vals):
        super()._add_invoice_header_nodes(document_node, vals)
        if not document_node["cbc:BuyerReference"]["_text"]:
            document_node["cbc:BuyerReference"]["_text"] = "N/A"

    def _get_party_node(self, vals):
        party_node = super()._get_party_node(vals)
        partner = vals["partner"]
        if not party_node.get("cbc:EndpointID", {}).get("_text") and partner.email:
            party_node["cbc:EndpointID"] = {"_text": partner.email, "schemeID": "EM"}
        return party_node

    def _ubl_get_line_allowance_charge_discount_node(self, vals, discount_values):
        discount_node = super()._ubl_get_line_allowance_charge_discount_node(
            vals, discount_values
        )
        update_ubl_discount_node(discount_node)
        return discount_node
