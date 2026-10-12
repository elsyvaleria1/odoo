import logging
from datetime import datetime

from lxml import etree

from odoo import Command, models
from odoo.tools import cleanup_xml_node, float_repr, html2plaintext, is_html_empty

_logger = logging.getLogger(__name__)

DEFAULT_FACTURX_DATE_FORMAT = "%Y%m%d"
CII_NAMESPACES = {
    "ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100",
    "rsm": "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100",
    "udt": "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100",
}

PAYMENT_MEAN_CODES = {"Payment to bank account": 42, "SEPA direct debit": 59}


class AccountEdiXmlCii(models.AbstractModel):
    _name = "account.edi.xml.cii"
    _inherit = ["account.edi.common"]
    _description = "Factur-x/XRechnung CII 2.2.0"

    def _find_value(self, xpath, tree, nsmap=False):
        return super()._find_value(xpath, tree, CII_NAMESPACES)

    def _export_invoice_filename(self, invoice):
        return f"{invoice.name.replace('/', '_')}_factur_x.xml"

    def _export_invoice_ecosio_schematrons(self) -> dict:
        return {
            "invoice": "de.xrechnung:cii:2.2.0",
            "credit_note": "de.xrechnung:cii:2.2.0",
        }

    def _export_invoice_constraints(self, invoice, vals):
        constraints = self._invoice_constraints_common(invoice)
        if invoice.move_type == "out_invoice":
            constraints.update(
                {
                    "seller_payment_instructions_1": self._check_required_fields(
                        vals["record"], "bank_account_id"
                    ),
                    "seller_payment_instructions_2": self._check_required_fields(
                        vals["record"]["bank_account_id"],
                        "sanitized_acc_number",
                        self.env._(
                            "The field 'Sanitized Account Number' is required on the Recipient Bank."
                        ),
                    ),
                }
            )
        constraints.update(
            {
                "seller_postal_address": self._check_required_fields(
                    vals["record"]["company_id"]["partner_id"]["commercial_partner_id"],
                    "country_id",
                ),
                "seller_identifier": self._check_required_fields(
                    vals["record"]["company_id"],
                    ["vat"],
                ),
                "seller_phone": self._check_required_fields(
                    vals["record"]["company_id"]["partner_id"]["commercial_partner_id"],
                    ["phone_ids"],
                ),
                "seller_email": self._check_required_fields(
                    vals["record"]["company_id"], "email"
                ),
                "tax_invoice_line": self._check_required_tax(vals),
                "intracom_seller_vat": self._check_required_fields(
                    vals["record"]["company_id"], "vat"
                )
                if vals["intracom_delivery"]
                else None,
                "intracom_buyer_vat": self._check_required_fields(
                    vals["record"]["commercial_partner_id"], "vat"
                )
                if vals["intracom_delivery"]
                else None,
                "igic_tax_rate": self._check_non_0_rate_tax(vals)
                if vals["record"]["partner_id"]["country_id"]["code"] == "ES"
                and vals["record"]["partner_id"]["zip"]
                and vals["record"]["partner_id"]["zip"][:2] in ["35", "38"]
                else None,
            }
        )
        return constraints

    def _check_required_tax(self, vals) -> str | None:
        for line_vals in vals["invoice_line_vals_list"]:
            line = line_vals["line"]
            if not vals["tax_details"]["tax_details_per_record"][line]["tax_details"]:
                return self.env._(
                    "You should include at least one tax per invoice line. [BR-CO-04]-Each Invoice line (BG-25) "
                    "shall be categorized with an Invoiced item VAT category code (BT-151)."
                )
        return None

    def _check_non_0_rate_tax(self, vals) -> str | None:
        for line_vals in vals["tax_details"]["tax_details_per_record"]:
            tax_rate_list = line_vals.tax_ids.flatten_taxes_hierarchy().mapped("amount")
            if not any(rate > 0 for rate in tax_rate_list):
                return self.env._(
                    "When the Canary Island General Indirect Tax (IGIC) applies, the tax rate on "
                    "each invoice line should be greater than 0."
                )
        return None

    def _get_scheduled_delivery_time(self, invoice):
        return invoice.delivery_date or invoice.invoice_date

    def _get_invoicing_period(self, invoice) -> list:
        return [invoice.invoice_date]

    def _prepare_exchanged_document_data(self, invoice) -> dict:
        return {
            "id": invoice.name,
            "type_code": "380" if invoice.move_type == "out_invoice" else "381",
            "issue_date_time": invoice.invoice_date,
            "included_note": html2plaintext(invoice.narration)
            if invoice.narration
            else "",
        }

    def _export_invoice_vals(self, invoice):
        customer = invoice.partner_id
        supplier = invoice.company_id.partner_id.commercial_partner_id

        def format_date(dt):
            dt = dt or datetime.now()
            return dt.strftime(DEFAULT_FACTURX_DATE_FORMAT)

        def format_monetary(number, decimal_places=2):
            return float_repr(number, decimal_places)

        def grouping_key_generator(base_line, tax_data):
            tax = tax_data["tax"]
            grouping_key = {
                "tax_category_code": self._get_tax_category_code(
                    customer.commercial_partner_id, supplier, tax
                ),
                **self._get_tax_exemption_reason(
                    customer.commercial_partner_id, supplier, tax
                ),
                "amount": tax.amount,
                "amount_type": tax.amount_type,
            }
            if tax.amount_type == "fixed":
                grouping_key["tax_name"] = tax.name
            return grouping_key

        self._check_taxes(invoice.invoice_line_ids.tax_ids)

        tax_details = invoice._prepare_invoice_aggregated_taxes(
            grouping_key_generator=grouping_key_generator
        )

        fixed_taxes_keys = [
            k for k in tax_details["tax_details"] if k["amount_type"] == "fixed"
        ]
        for key in fixed_taxes_keys:
            fixed_tax_details = tax_details["tax_details"].pop(key)
            tax_details["tax_amount_currency"] -= fixed_tax_details[
                "tax_amount_currency"
            ]
            tax_details["tax_amount"] -= fixed_tax_details["tax_amount"]
            tax_details["base_amount_currency"] += fixed_tax_details[
                "tax_amount_currency"
            ]
            tax_details["base_amount"] += fixed_tax_details["tax_amount"]

        template_values = {
            **invoice._prepare_edi_vals_to_export(),
            "tax_details": tax_details,
            "format_date": format_date,
            "format_monetary": format_monetary,
            "is_html_empty": is_html_empty,
            "scheduled_delivery_time": self._get_scheduled_delivery_time(invoice),
            "intracom_delivery": False,
            "ExchangedDocument_vals": self._prepare_exchanged_document_data(invoice),
            "seller_specified_legal_organization": invoice.company_id.company_registry,
            "buyer_specified_legal_organization": invoice.commercial_partner_id.company_registry,
            "ship_to_trade_party": invoice.partner_shipping_id
            if "partner_shipping_id" in invoice._fields and invoice.partner_shipping_id
            else invoice.commercial_partner_id,
            "buyer_reference": invoice.buyer_reference
            if "buyer_reference" in invoice._fields and invoice.buyer_reference
            else invoice.commercial_partner_id.ref,
            "purchase_order_reference": invoice.purchase_order_reference
            if "purchase_order_reference" in invoice._fields
            and invoice.purchase_order_reference
            else invoice.ref or invoice.name,
            "contract_reference": invoice.contract_reference
            if "contract_reference" in invoice._fields and invoice.contract_reference
            else "",
            "document_context_id": "urn:cen.eu:en16931:2017#conformant#urn:factur-x.eu:1p0:extended",
        }

        for line_vals in template_values["invoice_line_vals_list"]:
            line = line_vals["line"]
            line_vals["unece_uom_code"] = self._get_uom_unece_code(line.product_uom_id)

            if line._fields.get("deferred_start_date") and (
                line.deferred_start_date or line.deferred_end_date
            ):
                line_vals["billing_start"] = line.deferred_start_date
                line_vals["billing_end"] = line.deferred_end_date

        billing_start_dates = [invoice.invoice_date] if invoice.invoice_date else []
        billing_start_dates += [
            line_vals["billing_start"]
            for line_vals in template_values["invoice_line_vals_list"]
            if line_vals.get("billing_start")
        ]
        billing_end_dates = (
            [invoice.invoice_date_due] if invoice.invoice_date_due else []
        )
        billing_end_dates += [
            line_vals["billing_end"]
            for line_vals in template_values["invoice_line_vals_list"]
            if line_vals.get("billing_end")
        ]
        if billing_start_dates:
            template_values["billing_start"] = min(billing_start_dates)
        if billing_end_dates:
            template_values["billing_end"] = max(billing_end_dates)

        for tax_detail_vals in template_values["tax_details"]["tax_details"].values():
            amount_currency = tax_detail_vals["tax_amount_currency"]
            tax_detail_vals["calculated_amount"] = (
                amount_currency
                if not invoice.currency_id.is_zero(amount_currency)
                else 0
            )

            if tax_detail_vals.get("tax_category_code") == "K":
                template_values["intracom_delivery"] = True

        for line_vals in template_values["invoice_line_vals_list"]:
            line_vals["allowance_charge_vals_list"] = []
            for grouping_key, tax_detail in tax_details["tax_details_per_record"][
                line_vals["line"]
            ]["tax_details"].items():
                if grouping_key["amount_type"] == "fixed":
                    line_vals["allowance_charge_vals_list"].append(
                        {
                            "indicator": "true",
                            "reason": tax_detail["tax_name"],
                            "reason_code": "AEO",
                            "amount": tax_detail["tax_amount_currency"],
                        }
                    )
            sum_fixed_taxes = sum(
                x["amount"] for x in line_vals["allowance_charge_vals_list"]
            )
            line_vals["line_total_amount"] = (
                line_vals["line"].price_subtotal + sum_fixed_taxes
            )

            line_vals["quantity"] = line_vals["line"].quantity

            if (
                line_vals["line"].currency_id.compare_amounts(
                    line_vals["gross_price_total_unit"], 0
                )
                == -1
            ):
                line_vals["quantity"] *= -1
                line_vals["gross_price_total_unit"] *= -1
                line_vals["price_subtotal_unit"] *= -1

        template_values["tax_basis_total_amount"] = tax_details["base_amount_currency"]
        template_values["tax_total_amount"] = tax_details["tax_amount_currency"]

        if (
            self.env["account.payment"]._fields.get("sdd_mandate_id")
            and invoice.reconciled_payment_ids.sdd_mandate_id
        ):
            template_values["payment_means_code"] = PAYMENT_MEAN_CODES[
                "SEPA direct debit"
            ]
        else:
            template_values["payment_means_code"] = PAYMENT_MEAN_CODES[
                "Payment to bank account"
            ]

        return template_values

    def _export_invoice(self, invoice):
        vals = self._export_invoice_vals(
            invoice.with_context(lang=invoice.partner_id.lang)
        )
        errors = [
            constraint
            for constraint in self._export_invoice_constraints(invoice, vals).values()
            if constraint
        ]
        xml_content = self.env["ir.qweb"]._render(
            "account_edi_ubl_cii.account_invoice_facturx_export_22", vals
        )
        return etree.tostring(
            cleanup_xml_node(xml_content), xml_declaration=True, encoding="UTF-8"
        ), set(errors)

    def _prepare_partner_import_params(self, tree, role):
        return {
            "vat": self._find_value(
                f".//ram:{role}/ram:SpecifiedTaxRegistration/ram:ID[string-length(text()) > 5]",
                tree,
            ),
            "name": self._find_value(f".//ram:{role}/ram:Name", tree),
            "phone": self._find_value(
                f".//ram:{role}/ram:DefinedTradeContact/ram:TelephoneUniversalCommunication/ram:CompleteNumber",
                tree,
            ),
            "email": self._find_value(
                f".//ram:{role}//ram:EmailURIUniversalCommunication/ram:URIID", tree
            ),
            "postal_address": self._get_postal_address(tree, role),
        }

    def _get_postal_address(self, tree, role) -> dict:
        return {
            "country_code": self._find_value(
                f".//ram:{role}/ram:PostalTradeAddress//ram:CountryID", tree
            ),
            "street": self._find_value(
                f".//ram:{role}/ram:PostalTradeAddress//ram:LineOne", tree
            ),
            "additional_street": self._find_value(
                f".//ram:{role}/ram:PostalTradeAddress//ram:LineTwo", tree
            ),
            "city": self._find_value(
                f".//ram:{role}/ram:PostalTradeAddress//ram:CityName", tree
            ),
            "zip": self._find_value(
                f".//ram:{role}/ram:PostalTradeAddress//ram:PostcodeCode", tree
            ),
        }

    def _update_invoice_from_xml(self, invoice, tree, qty_factor):
        logs = []
        invoice_values = {}
        if qty_factor == -1:
            logs.append(
                self.env._(
                    "The invoice has been converted into a credit note and the quantities have been reverted."
                )
            )
        role = (
            "SellerTradeParty"
            if invoice.journal_id.type == "purchase"
            else "BuyerTradeParty"
        )
        partner, partner_logs = self._import_partner(
            invoice.company_id, **self._prepare_partner_import_params(tree, role)
        )
        invoice.partner_id = partner.id
        invoice_values["currency_id"], currency_logs = self._import_currency(
            tree, ".//{*}InvoiceCurrencyCode"
        )

        bank_detail_nodes = tree.findall(".//{*}SpecifiedTradeSettlementPaymentMeans")
        bank_details = [
            bank_detail_node.findtext("{*}PayeePartyCreditorFinancialAccount/{*}IBANID")
            or bank_detail_node.findtext(
                "{*}PayeePartyCreditorFinancialAccount/{*}ProprietaryID"
            )
            for bank_detail_node in bank_detail_nodes
            if bank_detail_node.findtext(
                "{*}PayeePartyCreditorFinancialAccount/{*}IBANID"
            )
            or bank_detail_node.findtext(
                "{*}PayeePartyCreditorFinancialAccount/{*}ProprietaryID"
            )
        ]
        if bank_details:
            self._import_partner_bank(invoice, bank_details=bank_details)

        invoice_values["ref"] = tree.findtext("./{*}ExchangedDocument/{*}ID")
        invoice_values["invoice_origin"] = tree.findtext(
            ".//{*}BuyerOrderReferencedDocument/{*}IssuerAssignedID"
        )
        invoice_values["narration"] = self._import_description(
            tree,
            xpaths=[
                "./{*}ExchangedDocument/{*}IncludedNote/{*}Content",
                ".//{*}SpecifiedTradePaymentTerms/{*}Description",
            ],
        )
        invoice_values["payment_reference"] = tree.findtext(
            "./{*}SupplyChainTradeTransaction/{*}ApplicableHeaderTradeSettlement/{*}PaymentReference"
        )

        issue_date = tree.findtext(
            "./{*}ExchangedDocument/{*}IssueDateTime/{*}DateTimeString"
        )
        if issue_date:
            invoice_values["invoice_date"] = datetime.strptime(
                issue_date.strip(), DEFAULT_FACTURX_DATE_FORMAT
            )
        due_date = tree.findtext(
            ".//{*}SpecifiedTradePaymentTerms/{*}DueDateDateTime/{*}DateTimeString"
        )
        if due_date:
            invoice_values["invoice_date_due"] = datetime.strptime(
                due_date.strip(), DEFAULT_FACTURX_DATE_FORMAT
            )

        allowance_charges_line_vals, allowance_charges_logs = (
            self._import_document_allowance_charges(
                tree,
                invoice,
                invoice.journal_id.type,
                qty_factor,
            )
        )
        logs += self._import_prepaid_amount(
            invoice,
            tree,
            ".//{*}ApplicableHeaderTradeSettlement/{*}SpecifiedTradeSettlementHeaderMonetarySummation/{*}TotalPrepaidAmount",
            qty_factor,
        )
        invoice_line_vals, line_logs = self._import_lines(
            invoice,
            tree,
            "./{*}SupplyChainTradeTransaction/{*}IncludedSupplyChainTradeLineItem",
            document_type=invoice.move_type,
            tax_type=invoice.journal_id.type,
            qty_factor=qty_factor,
        )
        line_vals = allowance_charges_line_vals + invoice_line_vals

        invoice_values = {
            **invoice_values,
            "invoice_line_ids": [
                Command.create(line_value) for line_value in line_vals
            ],
        }
        invoice.write(invoice_values)
        logs += partner_logs + currency_logs + line_logs + allowance_charges_logs
        return logs

    def _get_tax_nodes(self, tree):
        return tree.findall(".//{*}ApplicableTradeTax/{*}RateApplicablePercent")

    def _get_document_allowance_charge_xpaths(self):
        return {
            "root": "./{*}SupplyChainTradeTransaction/{*}ApplicableHeaderTradeSettlement/{*}SpecifiedTradeAllowanceCharge",
            "charge_indicator": "./{*}ChargeIndicator/{*}Indicator",
            "base_amount": "./{*}BasisAmount",
            "amount": "./{*}ActualAmount",
            "reason": "./{*}Reason",
            "percentage": "./{*}CalculationPercent",
            "tax_percentage": "./{*}CategoryTradeTax/{*}RateApplicablePercent",
        }

    def _get_invoice_line_xpaths(self, document_type=False, qty_factor=1):
        return {
            "deferred_start_date": "./{*}SpecifiedLineTradeSettlement/{*}BillingSpecifiedPeriod/{*}StartDateTime/{*}DateTimeString",
            "deferred_end_date": "./{*}SpecifiedLineTradeSettlement/{*}BillingSpecifiedPeriod/{*}EndDateTime/{*}DateTimeString",
            "date_format": DEFAULT_FACTURX_DATE_FORMAT,
        }

    def _get_line_xpaths(self, document_type=False, qty_factor=1):
        return {
            "basis_qty": (
                "./ram:SpecifiedLineTradeAgreement/ram:GrossPriceProductTradePrice/ram:BasisQuantity",
                "./ram:SpecifiedLineTradeAgreement/ram:NetPriceProductTradePrice/ram:BasisQuantity",
            ),
            "gross_price_unit": "./{*}SpecifiedLineTradeAgreement/{*}GrossPriceProductTradePrice/{*}ChargeAmount",
            "rebate": "./{*}SpecifiedLineTradeAgreement/{*}GrossPriceProductTradePrice/{*}AppliedTradeAllowanceCharge/{*}ActualAmount",
            "net_price_unit": "./{*}SpecifiedLineTradeAgreement/{*}NetPriceProductTradePrice/{*}ChargeAmount",
            "delivered_qty": "./{*}SpecifiedLineTradeDelivery/{*}BilledQuantity",
            "allowance_charge": ".//{*}SpecifiedLineTradeSettlement/{*}SpecifiedTradeAllowanceCharge",
            "allowance_charge_indicator": "./{*}ChargeIndicator/{*}Indicator",
            "allowance_charge_amount": "./{*}ActualAmount",
            "allowance_charge_reason": "./{*}Reason",
            "allowance_charge_reason_code": "./{*}ReasonCode",
            "line_total_amount": "./{*}SpecifiedLineTradeSettlement/{*}SpecifiedTradeSettlementLineMonetarySummation/{*}LineTotalAmount",
            "name": [
                "./ram:SpecifiedTradeProduct/ram:Description",
                "./ram:SpecifiedTradeProduct/ram:Name",
            ],
            "product": {
                "default_code": "./ram:SpecifiedTradeProduct/ram:SellerAssignedID",
                "name": "./ram:SpecifiedTradeProduct/ram:Name",
                "barcode": "./ram:SpecifiedTradeProduct/ram:GlobalID",
            },
        }

    def _get_import_document_amount_sign(self, tree) -> tuple:
        move_type_code = tree.find(".//{*}ExchangedDocument/{*}TypeCode")
        if move_type_code is None:
            return None, None
        if move_type_code.text == "381":
            return "refund", 1
        if move_type_code.text == "380":
            amount_node = tree.find(
                ".//{*}SpecifiedTradeSettlementHeaderMonetarySummation/{*}TaxBasisTotalAmount"
            )
            if amount_node is not None and float(amount_node.text) < 0:
                return "refund", -1
            return "invoice", 1
        return None, None
