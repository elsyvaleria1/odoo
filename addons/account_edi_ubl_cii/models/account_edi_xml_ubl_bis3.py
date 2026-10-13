from typing import TYPE_CHECKING, Literal, TypedDict

from markupsafe import Markup
from stdnum.no import mva

from odoo import api, models
from odoo.fields import Domain
from odoo.tools.misc import NON_BREAKING_SPACE, formatLang
from odoo.tools.xml_utils import dict_to_xml

from odoo.addons.account_edi_ubl_cii.models.account_edi_common import FloatFmt
from odoo.addons.account_edi_ubl_cii.models.account_edi_xml_ubl_20 import UBL_NAMESPACES
from odoo.addons.account_edi_ubl_cii.tools.ubl_line import update_ubl_line_price_node

if TYPE_CHECKING:
    from odoo.addons.base.models.res_company import ResCompany
    from odoo.addons.base.models.res_currency import ResCurrency


class TaxTotalCurrencyKey(TypedDict):
    currency: ResCurrency


class TaxTotalKeys(TypedDict):
    tax_total_key: TaxTotalCurrencyKey | None


class TaxTotalCurrencyValues(TypedDict):
    company: ResCompany
    currency: ResCurrency


CHORUS_PRO_PEPPOL_ID = "0009:11000201100044"


class AccountEdiXmlUbl_Bis3(models.AbstractModel):
    _name = "account.edi.xml.ubl_bis3"
    _inherit = ["account.edi.xml.ubl_21"]
    _description = "UBL BIS Billing 3.0.12"

    """
    * Documentation of EHF Billing 3.0: https://anskaffelser.dev/postaward/g3/
    * EHF 2.0 is no longer used:
      https://anskaffelser.dev/postaward/g2/announcement/2019-11-14-removal-old-invoicing-specifications/
    * Official doc for EHF Billing 3.0 is the OpenPeppol BIS 3 doc +
      https://anskaffelser.dev/postaward/g3/spec/current/billing-3.0/norway/

        "Based on work done in PEPPOL BIS Billing 3.0, Difi has included Norwegian rules in PEPPOL BIS Billing 3.0 and
        does not see a need to implement a different CIUS targeting the Norwegian market. Implementation of EHF Billing
        3.0 is therefore done by implementing PEPPOL BIS Billing 3.0 without extensions or extra rules."

    Thus, EHF 3 and Bis 3 are actually the same format. The specific rules for NO defined in Bis 3 are added in Bis 3.

    To avoid multi-parental inheritance in case of UBL 4.0, we're adding the sale/purchase logic here.
    * Documentation for Peppol Order transaction 3.5: https://docs.peppol.eu/poacc/upgrade-3/syntax/Order/tree/
    """

    @api.model
    def _is_customer_behind_chorus_pro(self, customer) -> bool:
        return bool(
            customer.peppol_eas
            and customer.peppol_endpoint
            and f"{customer.peppol_eas}:{customer.peppol_endpoint}"
            == CHORUS_PRO_PEPPOL_ID
        )

    def _export_invoice_filename(self, invoice):
        return f"{invoice.name.replace('/', '_')}_ubl_bis3.xml"

    def _add_document_currency_vals(self, vals):
        super()._add_document_currency_vals(vals)
        vals["currency_dp"] = 2

    def _add_invoice_config_vals(self, vals):
        super()._add_invoice_config_vals(vals)
        invoice = vals["invoice"]
        vals["process_type"] = (
            "selfbilling"
            if invoice.is_purchase_document() and invoice.journal_id.is_self_billing
            else "billing"
        )

    def _can_export_selfbilling(self) -> bool:
        return bool(self._get_customization_id(process_type="selfbilling"))

    def _get_customization_id(
        self, process_type: Literal["billing", "selfbilling"] = "billing"
    ):
        if process_type == "billing":
            return "urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0"
        else:
            return "urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:selfbilling:3.0"

    def _add_invoice_header_nodes(self, document_node, vals):
        super()._add_invoice_header_nodes(document_node, vals)
        invoice = vals["invoice"]
        ubl_values = vals["_ubl_values"]

        document_node.update(
            {
                "cbc:UBLVersionID": None,
                "cbc:CustomizationID": {
                    "_text": self._get_customization_id(vals["process_type"])
                },
                "cbc:ProfileID": {
                    "_text": f"urn:fdc:peppol.eu:2017:poacc:{vals['process_type']}:01:1.0"
                },
                "cbc:TaxCurrencyCode": {"_text": vals["tax_currency_code"]},
            }
        )
        if invoice.commercial_partner_id.peppol_eas == "0204":
            document_node.update(
                {
                    "cbc:BuyerReference": {
                        "_text": invoice.commercial_partner_id.peppol_endpoint
                    }
                }
            )

        if tax_withholding_amount := ubl_values[
            "payable_amount_tax_withholding_currency"
        ]:
            note = self.env._(
                "The prepaid amount of %s corresponds to the withholding tax applied.",
                formatLang(
                    self.env, tax_withholding_amount, currency_obj=vals["currency_id"]
                ).replace(NON_BREAKING_SPACE, ""),
            )
            narration_note = document_node["cbc:Note"]["_text"]
            if narration_note:
                note = f"{note} {narration_note}"
            document_node["cbc:Note"]["_text"] = note

        if vals["supplier"].country_id.code == "NL" and "refund" in invoice.move_type:
            document_node["cac:BillingReference"] = {
                "cac:InvoiceDocumentReference": {
                    "cbc:ID": {"_text": invoice.ref},
                }
            }

    def _add_invoice_delivery_nodes(self, document_node, vals):
        super()._add_invoice_delivery_nodes(document_node, vals)

        invoice = vals["invoice"]
        customer = vals["customer"]
        supplier = vals["supplier"]
        shipping_partner = vals["partner_shipping"]

        intracom_delivery = (
            customer.country_id.code
            in (
                economic_area := self.env.ref("base.europe").country_ids.mapped("code")
                + ["NO"]
            )
            and supplier.country_id.code in economic_area
            and supplier.country_id != customer.country_id
        )
        delivery_date = (
            invoice.invoice_date if intracom_delivery else invoice.delivery_date
        )

        document_node["cac:Delivery"] = {
            "cbc:ActualDeliveryDate": {"_text": delivery_date},
            "cac:DeliveryParty": {
                "cac:PartyName": {
                    "cbc:Name": {"_text": shipping_partner.name or customer.name},
                }
            },
            "cac:DeliveryLocation": {
                "cac:Address": self._get_address_node({"partner": shipping_partner})
            },
        }
        if (
            gln := "global_location_number" in shipping_partner._fields
            and shipping_partner.global_location_number
        ):
            document_node["cac:Delivery"]["cac:DeliveryLocation"].update(
                {
                    "cbc:ID": {"schemeID": "0088", "_text": gln},
                }
            )

    def _add_invoice_payment_means_nodes(self, document_node, vals):
        super()._add_invoice_payment_means_nodes(document_node, vals)
        document_node["cac:PaymentMeans"]["cbc:PaymentDueDate"] = None
        document_node["cac:PaymentMeans"]["cbc:InstructionID"] = None

    def _get_address_node(self, vals):
        address_node = super()._get_address_node(vals)
        address_node["cbc:CountrySubentityCode"] = None
        address_node["cac:Country"]["cbc:Name"] = None
        return address_node

    def _get_party_node(self, vals):
        party_node = super()._get_party_node(vals)

        partner = vals["partner"]
        role = vals["role"]
        commercial_partner = partner.commercial_partner_id

        if commercial_partner.peppol_endpoint:
            party_node["cbc:EndpointID"]["_text"] = commercial_partner.peppol_endpoint
            party_node["cbc:EndpointID"]["schemeID"] = commercial_partner.peppol_eas

        if (
            commercial_partner.country_code == "NL"
            and commercial_partner.peppol_endpoint
        ):
            if role == "customer":
                party_node["cac:PartyIdentification"] = [
                    {"cbc:ID": {"_text": commercial_partner.peppol_endpoint}}
                ]
            else:
                party_node["cac:PartyIdentification"] = [
                    party_node["cac:PartyIdentification"],
                    {"cbc:ID": {"_text": commercial_partner.peppol_endpoint}},
                ]
        elif (
            commercial_partner.country_code == "BE"
            and commercial_partner.company_registry
        ):
            party_node["cac:PartyIdentification"] = {
                "cbc:ID": {"_text": commercial_partner.company_registry}
            }

        party_node["cac:PartyTaxScheme"] = party_tax_scheme = [
            {
                "cbc:CompanyID": {
                    "_text": commercial_partner.vat
                    if commercial_partner.vat and commercial_partner.vat != "/"
                    else commercial_partner.peppol_endpoint
                },
                "cac:TaxScheme": {
                    "cbc:ID": {
                        "_text": (
                            "NOT_EU_VAT"
                            if commercial_partner.country_id
                            and commercial_partner.vat
                            and not commercial_partner.vat[:2].isalpha()
                            and commercial_partner.vat != "/"
                            else "VAT"
                            if commercial_partner.vat and commercial_partner.vat != "/"
                            else commercial_partner.peppol_eas
                        )
                    },
                },
            }
        ]
        if partner.country_id.code == "NO" and role == "supplier":
            party_tax_scheme.append(
                {
                    "cbc:CompanyID": {"_text": "Foretaksregisteret"},
                    "cac:TaxScheme": {"cbc:ID": {"_text": "TAX"}},
                }
            )

        if commercial_partner.country_code == "NL":
            nl_id = (
                commercial_partner.company_registry
                if commercial_partner.peppol_eas not in ("0106", "0190")
                else commercial_partner.peppol_endpoint
            )
            party_node["cac:PartyLegalEntity"]["cbc:CompanyID"] = {
                "_text": nl_id,
                "schemeID": "0190" if nl_id and len(nl_id) == 20 else "0106",
            }
        elif (
            commercial_partner.country_id.code == "LU"
            and commercial_partner.company_registry
        ):
            party_node["cac:PartyLegalEntity"]["cbc:CompanyID"] = {
                "_text": commercial_partner.company_registry
            }
        elif (
            commercial_partner.country_code == "SE"
            and commercial_partner.company_registry
        ):
            party_node["cac:PartyLegalEntity"]["cbc:CompanyID"] = {
                "_text": "".join(
                    char
                    for char in commercial_partner.company_registry
                    if char.isdigit()
                )
            }
        elif (
            commercial_partner.country_code == "BE"
            and commercial_partner.company_registry
        ):
            party_node["cac:PartyLegalEntity"]["cbc:CompanyID"] = {
                "_text": commercial_partner.company_registry
            }
        else:
            party_node["cac:PartyLegalEntity"]["cbc:CompanyID"] = {
                "_text": commercial_partner.vat or commercial_partner.peppol_endpoint,
                "schemeID": "0184"
                if commercial_partner.country_id.code == "DK"
                else None,
            }

        party_node["cac:PartyLegalEntity"]["cac:RegistrationAddress"] = None

        party_node["cac:Contact"]["cbc:ID"] = None
        return party_node

    def _get_financial_account_node(self, vals):
        financial_account_node = super()._get_financial_account_node(vals)

        if financial_account_node["cac:FinancialInstitutionBranch"]:
            financial_account_node["cac:FinancialInstitutionBranch"][
                "cac:FinancialInstitution"
            ] = None

            if financial_account_node["cac:FinancialInstitutionBranch"]["cbc:ID"]:
                financial_account_node["cac:FinancialInstitutionBranch"]["cbc:ID"][
                    "schemeID"
                ] = None

        return financial_account_node

    def _setup_base_lines(self, vals):
        AccountTax = self.env["account.tax"]
        company = vals["company"]

        self._ubl_turn_base_lines_price_unit_as_always_positive(vals)

        vals["base_lines"] = self._ubl_turn_emptying_taxes_as_new_base_lines(
            vals["base_lines"], company, vals
        )

        vals["_ubl_values"] = {}
        for base_line in vals["base_lines"]:
            base_line["_ubl_values"] = {}

        AccountTax._round_raw_total_excluded(vals["base_lines"], company)
        AccountTax._round_raw_total_excluded(
            vals["base_lines"], company, in_foreign_currency=False
        )
        AccountTax._add_and_round_raw_gross_total_excluded_and_discount(
            vals["base_lines"], company
        )
        AccountTax._add_and_round_raw_gross_total_excluded_and_discount(
            vals["base_lines"], company, in_foreign_currency=False
        )
        AccountTax._round_raw_gross_total_excluded_and_discount(
            vals["base_lines"], company
        )
        AccountTax._round_raw_gross_total_excluded_and_discount(
            vals["base_lines"], company, in_foreign_currency=False
        )

        self._ubl_add_base_line_ubl_values_price(vals)

        self._ubl_add_values_tax_currency_code(vals)

        self._ubl_add_values_payable_rounding_amount(vals)

        vals["base_lines"] = [
            base_line
            for base_line in vals["base_lines"]
            if base_line not in vals["_ubl_values"]["payable_rounding_base_lines"]
        ]

        self._ubl_add_values_payable_amount_tax_withholding(vals)

        self._ubl_add_values_allowance_charge_early_payment(vals)

    def _add_invoice_line_vals(self, vals):
        pass

    def _ubl_default_tax_category_grouping_key(
        self, base_line, tax_data, vals, currency
    ):
        if (
            self._ubl_is_cash_rounding_base_line(base_line)
            or self._ubl_is_recycling_contribution_tax(tax_data)
            or self._ubl_is_excise_tax(tax_data)
        ):
            return None
        return super()._ubl_default_tax_category_grouping_key(
            base_line, tax_data, vals, currency
        )

    def _add_invoice_line_allowance_charge_nodes(self, line_node, vals):
        self._update_line_allowance_charge_nodes(line_node, vals)

    def _update_line_allowance_charge_nodes(self, line_node, vals) -> None:
        sub_vals = {
            **vals,
            "line_node": line_node,
            "line_vals": {
                "base_line": vals["base_line"],
            },
        }
        self._ubl_add_line_allowance_charge_nodes(sub_vals)

        self._ubl_add_line_allowance_charge_nodes_for_discount(sub_vals)

        self._ubl_add_line_allowance_charge_nodes_for_recycling_contribution_taxes(
            sub_vals
        )

        self._ubl_add_line_allowance_charge_nodes_for_excise_taxes(sub_vals)

    def _add_invoice_line_amount_nodes(self, line_node, vals):
        sub_vals = {
            **vals,
            "line_node": line_node,
            "line_vals": {
                "base_line": vals["base_line"],
            },
        }

        if vals["document_type"] == "credit_note":
            self._ubl_add_line_credited_quantity_node(sub_vals)
        elif vals["document_type"] == "debit_note":
            self._ubl_add_line_debited_quantity_node(sub_vals)
        else:
            self._ubl_add_line_invoiced_quantity_node(sub_vals)

        self._ubl_add_line_extension_amount_node(sub_vals)

    def _add_invoice_line_item_nodes(self, line_node, vals):
        sub_vals = {
            **vals,
            "line_node": line_node,
            "line_vals": {
                "base_line": vals["base_line"],
            },
        }
        self._ubl_add_line_item_node(sub_vals)

    def _add_invoice_line_tax_category_nodes(self, line_node, vals):
        pass

    def _add_invoice_line_tax_total_nodes(self, line_node, vals):
        pass

    def _add_invoice_line_price_nodes(self, line_node, vals):
        update_ubl_line_price_node(line_node, vals)

    def _add_invoice_allowance_charge_nodes(self, document_node, vals):
        ubl_values = vals["_ubl_values"]
        document_node["cac:AllowanceCharge"] = [
            self._ubl_get_allowance_charge_early_payment(vals, early_payment_values)
            for early_payment_values in ubl_values[
                "allowance_charges_early_payment_currency"
            ]
        ]

    def _ubl_get_tax_subtotal_node(self, vals, tax_subtotal):
        node = super()._ubl_get_tax_subtotal_node(vals, tax_subtotal)

        currency = tax_subtotal["currency"]
        corresponding_line_node_amounts = (
            [
                line_node["cbc:LineExtensionAmount"]["_text"]
                for tax_category_node in node["cac:TaxCategory"]
                if tax_category_node["cbc:ID"]["_text"] == "S"
                for line_key in (
                    "cac:InvoiceLine",
                    "cac:CreditNoteLine",
                    "cac:DebitNoteLine",
                )
                for line_node in vals["document_node"].get(line_key, [])
                for line_node_tax_category_node in line_node["cac:Item"][
                    "cac:ClassifiedTaxCategory"
                ]
                if (
                    line_node_tax_category_node["cbc:ID"]["_text"] == "S"
                    and line_node_tax_category_node["cbc:Percent"]["_text"]
                    == tax_category_node["cbc:Percent"]["_text"]
                    and line_node_tax_category_node["_currency"]
                    == tax_category_node["_currency"]
                )
            ]
            + [
                -allowance_node["cbc:Amount"]["_text"]
                for tax_category_node in node["cac:TaxCategory"]
                if tax_category_node["cbc:ID"]["_text"] == "S"
                for allowance_node in vals["document_node"]["cac:AllowanceCharge"]
                if allowance_node["cbc:ChargeIndicator"]["_text"] == "false"
                for allowance_node_tax_category_node in allowance_node[
                    "cac:TaxCategory"
                ]
                if (
                    allowance_node_tax_category_node["cbc:ID"]["_text"] == "S"
                    and allowance_node_tax_category_node["cbc:Percent"]["_text"]
                    == tax_category_node["cbc:Percent"]["_text"]
                    and allowance_node_tax_category_node["_currency"]
                    == tax_category_node["_currency"]
                )
            ]
            + [
                allowance_node["cbc:Amount"]["_text"]
                for tax_category_node in node["cac:TaxCategory"]
                if tax_category_node["cbc:ID"]["_text"] == "S"
                for allowance_node in vals["document_node"]["cac:AllowanceCharge"]
                if allowance_node["cbc:ChargeIndicator"]["_text"] == "true"
                for allowance_node_tax_category_node in allowance_node[
                    "cac:TaxCategory"
                ]
                if (
                    allowance_node_tax_category_node["cbc:ID"]["_text"] == "S"
                    and allowance_node_tax_category_node["cbc:Percent"]["_text"]
                    == tax_category_node["cbc:Percent"]["_text"]
                    and allowance_node_tax_category_node["_currency"]
                    == tax_category_node["_currency"]
                )
            ]
        )
        if corresponding_line_node_amounts:
            node["cbc:TaxableAmount"] = {
                "_text": FloatFmt(
                    sum(corresponding_line_node_amounts), min_dp=currency.decimal_places
                ),
                "currencyID": currency.name,
            }

        return node

    def _ubl_tax_totals_node_grouping_key(self, base_line, tax_data, vals, currency):
        tax_total_keys = super()._ubl_tax_totals_node_grouping_key(
            base_line, tax_data, vals, currency
        )

        if (
            tax_total_keys["tax_total_key"]
            and tax_total_keys["tax_total_key"]["is_withholding"]
        ):
            tax_total_keys["tax_total_key"] = None

        company_currency = vals["company"].currency_id
        if (
            tax_total_keys["tax_subtotal_key"]
            and company_currency != vals["currency"]
            and tax_total_keys["tax_subtotal_key"]["currency"] == company_currency
        ):
            tax_total_keys["tax_subtotal_key"] = None

        return tax_total_keys

    def _update_tax_total_keys_without_company_currency(
        self, tax_total_keys: TaxTotalKeys, vals: TaxTotalCurrencyValues
    ) -> None:
        company_currency = vals["company"].currency_id
        if (
            tax_total_keys["tax_total_key"]
            and company_currency != vals["currency"]
            and tax_total_keys["tax_total_key"]["currency"] == company_currency
        ):
            tax_total_keys["tax_total_key"] = None

    def _add_invoice_tax_total_nodes(self, document_node, vals):
        sub_vals = {
            **vals,
            "document_node": document_node,
            "currency": vals["currency_id"],
        }
        self._ubl_add_tax_totals_nodes(sub_vals)

    def _add_invoice_monetary_total_vals(self, vals):
        pass

    def _add_invoice_monetary_total_nodes(self, document_node, vals):
        monetary_total_tag = self._get_tags_for_document_type(vals)["monetary_total"]
        ubl_values = vals["_ubl_values"]
        invoice = vals["invoice"]
        line_tag = self._get_tags_for_document_type(vals)["document_line"]

        line_extension_amount = sum(
            line_node["cbc:LineExtensionAmount"]["_text"]
            for line_node in document_node[line_tag]
        )
        tax_amount = sum(
            tax_total["cbc:TaxAmount"]["_text"]
            for tax_total in document_node["cac:TaxTotal"]
            if tax_total["cbc:TaxAmount"]["currencyID"] == vals["currency_id"].name
        )
        total_allowance = sum(
            allowance_charge["cbc:Amount"]["_text"]
            for allowance_charge in document_node["cac:AllowanceCharge"]
            if allowance_charge["cbc:ChargeIndicator"]["_text"] == "false"
        )
        total_charge = sum(
            allowance_charge["cbc:Amount"]["_text"]
            for allowance_charge in document_node["cac:AllowanceCharge"]
            if allowance_charge["cbc:ChargeIndicator"]["_text"] == "true"
        )
        payable_rounding_amount = ubl_values["payable_rounding_amount_currency"]
        payable_amount_tax_withholding_currency = ubl_values[
            "payable_amount_tax_withholding_currency"
        ]

        document_node[monetary_total_tag] = {
            "cbc:LineExtensionAmount": {
                "_text": FloatFmt(line_extension_amount, min_dp=vals["currency_dp"]),
                "currencyID": vals["currency_name"],
            },
            "cbc:TaxExclusiveAmount": {
                "_text": FloatFmt(line_extension_amount, min_dp=vals["currency_dp"]),
                "currencyID": vals["currency_name"],
            },
            "cbc:TaxInclusiveAmount": {
                "_text": FloatFmt(
                    line_extension_amount + tax_amount, min_dp=vals["currency_dp"]
                ),
                "currencyID": vals["currency_name"],
            },
            "cbc:AllowanceTotalAmount": {
                "_text": FloatFmt(total_allowance, min_dp=vals["currency_dp"]),
                "currencyID": vals["currency_name"],
            }
            if total_allowance
            else None,
            "cbc:ChargeTotalAmount": {
                "_text": FloatFmt(total_charge, min_dp=vals["currency_dp"]),
                "currencyID": vals["currency_name"],
            }
            if total_charge
            else None,
            "cbc:PrepaidAmount": {
                "_text": FloatFmt(
                    payable_amount_tax_withholding_currency
                    + invoice.amount_total
                    - invoice.amount_residual,
                    min_dp=vals["currency_dp"],
                ),
                "currencyID": vals["currency_name"],
            },
            "cbc:PayableRoundingAmount": {
                "_text": FloatFmt(payable_rounding_amount, min_dp=vals["currency_dp"]),
                "currencyID": vals["currency_name"],
            }
            if payable_rounding_amount
            else None,
            "cbc:PayableAmount": {
                "_text": FloatFmt(invoice.amount_residual, min_dp=vals["currency_dp"]),
                "currencyID": vals["currency_name"],
            },
        }

    def _export_invoice_constraints(self, invoice, vals):
        constraints = super()._export_invoice_constraints(invoice, vals)

        constraints.update(self._invoice_constraints_peppol_en16931_ubl(invoice, vals))
        constraints.update(self._invoice_constraints_cen_en16931_ubl(invoice, vals))

        return constraints

    def _invoice_constraints_cen_en16931_ubl(self, invoice, vals):
        eu_countries = self.env.ref("base.europe").country_ids
        intracom_delivery = (
            vals["customer"].country_id in eu_countries
            and vals["supplier"].country_id in eu_countries
            and vals["customer"].country_id != vals["supplier"].country_id
        )

        nsmap = self._get_document_nsmap(vals)

        constraints = {
            "cen_en16931_payment_account_identifier": self._check_required_fields(
                invoice, "bank_account_id"
            )
            if vals["document_node"]["cac:PaymentMeans"]["cbc:PaymentMeansCode"][
                "_text"
            ]
            in (30, 58)
            else None,
            "cen_en16931_delivery_country_code": (
                self.env._(
                    "For intracommunity supply, the delivery address should be included."
                )
            )
            if intracom_delivery
            and dict_to_xml(
                vals["document_node"]["cac:Delivery"]["cac:DeliveryLocation"],
                nsmap=nsmap,
                tag="cac:DeliveryLocation",
            )
            is None
            else None,
            "cen_en16931_delivery_date_invoicing_period": (
                self.env._(
                    "For intracommunity supply, the actual delivery date or the invoicing period should be included."
                )
                if (
                    intracom_delivery
                    and dict_to_xml(
                        vals["document_node"]["cac:Delivery"]["cbc:ActualDeliveryDate"],
                        nsmap=nsmap,
                        tag="cbc:ActualDeliveryDate",
                    )
                    is None
                    and dict_to_xml(
                        vals["document_node"]["cac:InvoicePeriod"],
                        nsmap=nsmap,
                        tag="cac:InvoicePeriod",
                    )
                    is None
                )
                else None
            ),
        }

        line_tag = self._get_tags_for_document_type(vals)["document_line"]
        line_nodes = vals["document_node"][line_tag]

        for line_node in line_nodes:
            if not (line_node["cac:Item"]["cbc:Name"] or {}).get("_text"):
                constraints.update(
                    {
                        "cen_en16931_item_name": self.env._(
                            "Each invoice line should have a product or a label."
                        )
                    }
                )
                break

            if len(line_node["cac:Item"]["cac:ClassifiedTaxCategory"]) != 1:
                constraints["cen_en16931_tax_line"] = self.env._(
                    "Each invoice line shall have one and only one tax."
                )

        for role in ("supplier", "customer"):
            party_node = (
                vals["document_node"]["cac:AccountingCustomerParty"]
                if role == "customer"
                else vals["document_node"]["cac:AccountingSupplierParty"]
            )
            constraints[f"cen_en16931_{role}_country"] = (
                self.env._("The country is required for the %s.", role)
                if not party_node["cac:Party"]["cac:PostalAddress"]["cac:Country"][
                    "cbc:IdentificationCode"
                ]["_text"]
                else None
            )
            tax_scheme_node = party_node["cac:Party"]["cac:PartyTaxScheme"]
            if tax_scheme_node and (
                self._name
                in (
                    "account.edi.xml.ubl_bis3",
                    "account.edi.xml.ubl_nl",
                    "account.edi.xml.ubl_de",
                )
                and (tax_scheme_node[0]["cac:TaxScheme"]["cbc:ID"]["_text"] == "VAT")
                and not (tax_scheme_node[0]["cbc:CompanyID"]["_text"][:2].isalpha())
            ):
                constraints.update(
                    {
                        f"cen_en16931_{role}_vat_country_code": self.env._(
                            "The VAT of the %s should be prefixed with its country code.",
                            role,
                        )
                    }
                )

        if invoice.partner_shipping_id:
            constraints["cen_en16931_delivery_address"] = self._check_required_fields(
                invoice.partner_shipping_id, "country_id"
            )
        return constraints

    def _invoice_constraints_peppol_en16931_ubl(self, invoice, vals):
        nsmap = self._get_document_nsmap(vals)
        constraints = {
            "peppol_en16931_ubl_buyer_ref_po_ref": "A buyer reference or purchase order reference must be provided."
            if (
                dict_to_xml(
                    vals["document_node"]["cbc:BuyerReference"],
                    nsmap=nsmap,
                    tag="cbc:BuyerReference",
                )
                is None
                and dict_to_xml(
                    vals["document_node"]["cac:OrderReference"],
                    nsmap=nsmap,
                    tag="cac:OrderReference",
                )
                is None
            )
            else None,
        }

        if vals["supplier"].country_id.code == "NL":
            constraints.update(
                {
                    "nl_r_001": self._check_required_fields(invoice, "ref")
                    if "refund" in invoice.move_type
                    else "",
                    "nl_r_002_street": self._check_required_fields(
                        vals["supplier"], "street"
                    ),
                    "nl_r_002_zip": self._check_required_fields(
                        vals["supplier"], "zip"
                    ),
                    "nl_r_002_city": self._check_required_fields(
                        vals["supplier"], "city"
                    ),
                    "nl_r_003": self.env._(
                        "%s should have a KVK or OIN number set in Company ID field or as Peppol e-address (EAS code 0106 or 0190).",
                        vals["supplier"].display_name,
                    )
                    if (
                        vals["supplier"].peppol_eas not in ("0106", "0190")
                        and (
                            not vals["supplier"].company_registry
                            or len(vals["supplier"].company_registry) not in (8, 9)
                        )
                    )
                    else "",
                    "nl_r_007": self._check_required_fields(invoice, "bank_account_id"),
                }
            )

            if vals["customer"].country_id.code == "NL":
                constraints.update(
                    {
                        "nl_r_004_street": self._check_required_fields(
                            vals["customer"], "street"
                        ),
                        "nl_r_004_city": self._check_required_fields(
                            vals["customer"], "city"
                        ),
                        "nl_r_004_zip": self._check_required_fields(
                            vals["customer"], "zip"
                        ),
                        "nl_r_005": self.env._(
                            "%s should have a KVK or OIN number set in Company ID field or as Peppol e-address (EAS code 0106 or 0190).",
                            vals["customer"].display_name,
                        )
                        if (
                            vals["customer"].commercial_partner_id.peppol_eas
                            not in ("0106", "0190")
                            and (
                                not vals[
                                    "customer"
                                ].commercial_partner_id.company_registry
                                or len(
                                    vals[
                                        "customer"
                                    ].commercial_partner_id.company_registry
                                )
                                not in (8, 9)
                            )
                        )
                        else "",
                    }
                )

        if vals["supplier"].country_id.code == "NO":
            vat = vals["supplier"].vat
            constraints.update(
                {
                    "no_r_001": self.env._(
                        "The VAT number of the supplier does not seem to be valid. It should be of the form: NO179728982MVA."
                    )
                    if not mva.is_valid(vat)
                    or len(vat) != 14
                    or vat[:2] != "NO"
                    or vat[-3:] != "MVA"
                    else "",
                }
            )

        return constraints

    def _prepare_partner_import_params(self, tree, role):
        partner_vals = super()._prepare_partner_import_params(tree, role)
        endpoint_node = tree.find(
            f".//cac:{role}Party/cac:Party/cbc:EndpointID", UBL_NAMESPACES
        )
        if endpoint_node is not None:
            peppol_eas = endpoint_node.attrib.get("schemeID")
            peppol_endpoint = endpoint_node.text
            if peppol_eas and peppol_endpoint:
                partner_vals.update(
                    {
                        "peppol_eas": peppol_eas,
                        "peppol_endpoint": peppol_endpoint,
                    }
                )
        return partner_vals

    def _import_order_payment_terms_id(self, company_id, tree, xpath):
        payment_term_name = self._find_value(xpath, tree)
        if not payment_term_name:
            return False
        PaymentTerm = self.env["account.payment.term"]
        return PaymentTerm.search(
            PaymentTerm._get_domain_company_compatible(company_id)
            & Domain("name", "=", payment_term_name),
            limit=1,
        )

    def _prepare_order_vals(self, order, tree):
        order_vals = {}
        logs = []

        order_vals["date_order"] = tree.findtext(".//{*}EndDate") or tree.findtext(
            ".//{*}IssueDate"
        )
        order_vals["notes"] = self._import_description(tree, xpaths=["./{*}Note"])
        order_vals["payment_term_id"] = self._import_order_payment_terms_id(
            order.company_id, tree, ".//cac:PaymentTerms/cbc:Note"
        )
        order_vals["currency_id"], currency_logs = self._import_currency(
            tree, ".//{*}DocumentCurrencyCode"
        )

        logs += currency_logs
        return order_vals, logs

    def _import_order_ubl(self, order, file_data, new):
        tree = file_data["xml_tree"]

        order_vals, logs = self._prepare_order_vals(order, tree)
        if order:
            order.write(order_vals)
            order.message_post(
                body=Markup("<strong>%s</strong>")
                % self.env._(
                    "Format used to import the document: %s", self._description
                )
            )
            if logs:
                order._create_activity_set_details(
                    Markup("<ul>%s</ul>")
                    % Markup().join(Markup("<li>%s</li>") % l for l in logs)
                )
