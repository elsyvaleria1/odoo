from datetime import datetime

from markupsafe import Markup

from odoo import Command, api, models
from odoo.exceptions import UserError, ValidationError
from odoo.libs.documents import mimetype_for
from odoo.tools import float_is_zero, float_repr
from odoo.tools.misc import formatLang, html_escape
from odoo.tools.xml_utils import get_xml_value

from odoo.addons.account.tools.display_types import NON_ACCOUNTABLE_DISPLAY_TYPES

UOM_TO_UNECE_CODE = {
    "base.product_uom_unit": "C62",
    "base.product_uom_dozen": "DZN",
    "base.product_uom_kgm": "KGM",
    "base.product_uom_gram": "GRM",
    "base.product_uom_day": "DAY",
    "base.product_uom_hour": "HUR",
    "base.product_uom_minute": "MIN",
    "base.product_uom_ton": "TNE",
    "base.product_uom_meter": "MTR",
    "base.product_uom_km": "KMT",
    "base.product_uom_cm": "CMT",
    "base.product_uom_litre": "LTR",
    "base.product_uom_cubic_meter": "MTQ",
    "base.product_uom_lb": "LBR",
    "base.product_uom_oz": "ONZ",
    "base.product_uom_inch": "INH",
    "base.product_uom_foot": "FOT",
    "base.product_uom_mile": "SMI",
    "base.product_uom_floz": "OZA",
    "base.product_uom_qt": "QT",
    "base.product_uom_gal": "GLL",
    "base.product_uom_cubic_inch": "INQ",
    "base.product_uom_cubic_foot": "FTQ",
    "base.product_uom_square_meter": "MTK",
    "base.product_uom_square_foot": "FTK",
    "base.product_uom_yard": "YRD",
    "base.product_uom_millimeter": "MMT",
    "base.product_uom_kwh": "KWH",
}

EAS_MAPPING = {
    "AD": {"9922": "vat"},
    "AE": {"0235": "vat"},
    "AL": {"9923": "vat"},
    "AT": {"9915": "vat"},
    "AU": {"0151": "vat"},
    "BA": {"9924": "vat"},
    "BE": {"0208": "company_registry", "9925": "vat"},
    "BG": {"9926": "vat"},
    "CH": {"9927": "vat", "0183": None},
    "CY": {"9928": "vat"},
    "CZ": {"9929": "vat"},
    "DE": {"9930": "vat"},
    "DK": {"0184": "vat", "0198": "vat"},
    "EE": {"9931": "vat"},
    "ES": {"9920": "vat"},
    "FI": {"0216": None, "0213": "vat"},
    "FR": {"0009": "company_registry", "9957": "vat", "0002": None},
    "SG": {"0195": "l10n_sg_unique_entity_number"},
    "GB": {"9932": "vat"},
    "GR": {"9933": "vat"},
    "HR": {"9934": "vat", "0088": "company_registry"},
    "HU": {"9910": "l10n_hu_eu_vat"},
    "IE": {"9935": "vat"},
    "IS": {"0196": "vat"},
    "IT": {"0211": "vat", "0210": "l10n_it_codice_fiscale"},
    "JP": {"0221": "vat"},
    "LI": {"9936": "vat"},
    "LT": {"9937": "vat"},
    "LU": {"9938": "vat"},
    "LV": {"0218": "company_registry", "9939": "vat"},
    "MC": {"9940": "vat"},
    "ME": {"9941": "vat"},
    "MK": {"9942": "vat"},
    "MT": {"9943": "vat"},
    "MY": {"0230": None},
    "NL": {"0106": None, "0190": None},
    "NO": {"0192": "l10n_no_bronnoysund_number"},
    "NZ": {"0088": "company_registry"},
    "PL": {"9945": "vat"},
    "PT": {"9946": "vat"},
    "RO": {"9947": "vat"},
    "RS": {"9948": "vat"},
    "SE": {"0007": "company_registry", "9955": "vat"},
    "SI": {"9949": "vat"},
    "SK": {"9950": "vat"},
    "SM": {"9951": "vat"},
    "TR": {"9952": "vat"},
    "VA": {"9953": "vat"},
    "BL": {"0009": "siret", "9957": "vat", "0002": None},
    "GF": {"0009": "siret", "9957": "vat", "0002": None},
    "GP": {"0009": "siret", "9957": "vat", "0002": None},
    "MF": {"0009": "siret", "9957": "vat", "0002": None},
    "MQ": {"0009": "siret", "9957": "vat", "0002": None},
    "NC": {"0009": "siret", "9957": "vat", "0002": None},
    "PF": {"0009": "siret", "9957": "vat", "0002": None},
    "PM": {"0009": "siret", "9957": "vat", "0002": None},
    "RE": {"0009": "siret", "9957": "vat", "0002": None},
    "TF": {
        "0009": "siret",
        "9957": "vat",
        "0002": None,
    },
    "WF": {"0009": "siret", "9957": "vat", "0002": None},
    "YT": {"0009": "siret", "9957": "vat", "0002": None},
}

TAX_EXEMPTION_MAPPING = {
    "VATEX-EU-79-C": "Exempt based on article 79, point c of Council Directive 2006/112/EC",
    "VATEX-EU-132": "Exempt based on article 132 of Council Directive 2006/112/EC",
    "VATEX-EU-132-1A": "Exempt based on article 132, section 1 (a) of Council Directive 2006/112/EC",
    "VATEX-EU-132-1B": "Exempt based on article 132, section 1 (b) of Council Directive 2006/112/EC",
    "VATEX-EU-132-1C": "Exempt based on article 132, section 1 (c) of Council Directive 2006/112/EC",
    "VATEX-EU-132-1D": "Exempt based on article 132, section 1 (d) of Council Directive 2006/112/EC",
    "VATEX-EU-132-1E": "Exempt based on article 132, section 1 (e) of Council Directive 2006/112/EC",
    "VATEX-EU-132-1F": "Exempt based on article 132, section 1 (f) of Council Directive 2006/112/EC",
    "VATEX-EU-132-1G": "Exempt based on article 132, section 1 (g) of Council Directive 2006/112/EC",
    "VATEX-EU-132-1H": "Exempt based on article 132, section 1 (h) of Council Directive 2006/112/EC",
    "VATEX-EU-132-1I": "Exempt based on article 132, section 1 (i) of Council Directive 2006/112/EC",
    "VATEX-EU-132-1J": "Exempt based on article 132, section 1 (j) of Council Directive 2006/112/EC",
    "VATEX-EU-132-1K": "Exempt based on article 132, section 1 (k) of Council Directive 2006/112/EC",
    "VATEX-EU-132-1L": "Exempt based on article 132, section 1 (l) of Council Directive 2006/112/EC",
    "VATEX-EU-132-1M": "Exempt based on article 132, section 1 (m) of Council Directive 2006/112/EC",
    "VATEX-EU-132-1N": "Exempt based on article 132, section 1 (n) of Council Directive 2006/112/EC",
    "VATEX-EU-132-1O": "Exempt based on article 132, section 1 (o) of Council Directive 2006/112/EC",
    "VATEX-EU-132-1P": "Exempt based on article 132, section 1 (p) of Council Directive 2006/112/EC",
    "VATEX-EU-132-1Q": "Exempt based on article 132, section 1 (q) of Council Directive 2006/112/EC",
    "VATEX-EU-143": "Exempt based on article 143 of Council Directive 2006/112/EC",
    "VATEX-EU-143-1A": "Exempt based on article 143, section 1 (a) of Council Directive 2006/112/EC",
    "VATEX-EU-143-1B": "Exempt based on article 143, section 1 (b) of Council Directive 2006/112/EC",
    "VATEX-EU-143-1C": "Exempt based on article 143, section 1 (c) of Council Directive 2006/112/EC",
    "VATEX-EU-143-1D": "Exempt based on article 143, section 1 (d) of Council Directive 2006/112/EC",
    "VATEX-EU-143-1E": "Exempt based on article 143, section 1 (e) of Council Directive 2006/112/EC",
    "VATEX-EU-143-1F": "Exempt based on article 143, section 1 (f) of Council Directive 2006/112/EC",
    "VATEX-EU-143-1FA": "Exempt based on article 143, section 1 (fa) of Council Directive 2006/112/EC",
    "VATEX-EU-143-1G": "Exempt based on article 143, section 1 (g) of Council Directive 2006/112/EC",
    "VATEX-EU-143-1H": "Exempt based on article 143, section 1 (h) of Council Directive 2006/112/EC",
    "VATEX-EU-143-1I": "Exempt based on article 143, section 1 (i) of Council Directive 2006/112/EC",
    "VATEX-EU-143-1J": "Exempt based on article 143, section 1 (j) of Council Directive 2006/112/EC",
    "VATEX-EU-143-1K": "Exempt based on article 143, section 1 (k) of Council Directive 2006/112/EC",
    "VATEX-EU-143-1L": "Exempt based on article 143, section 1 (l) of Council Directive 2006/112/EC",
    "VATEX-EU-144": "Exempt based on article 144 of Council Directive 2006/112/EC",
    "VATEX-EU-146-1E": "Exempt based on article 146 section 1 (e) of Council Directive 2006/112/EC",
    "VATEX-EU-148": "Exempt based on article 148 of Council Directive 2006/112/EC",
    "VATEX-EU-148-A": "Exempt based on article 148, section (a) of Council Directive 2006/112/EC",
    "VATEX-EU-148-B": "Exempt based on article 148, section (b) of Council Directive 2006/112/EC",
    "VATEX-EU-148-C": "Exempt based on article 148, section (c) of Council Directive 2006/112/EC",
    "VATEX-EU-148-D": "Exempt based on article 148, section (d) of Council Directive 2006/112/EC",
    "VATEX-EU-148-E": "Exempt based on article 148, section (e) of Council Directive 2006/112/EC",
    "VATEX-EU-148-F": "Exempt based on article 148, section (f) of Council Directive 2006/112/EC",
    "VATEX-EU-148-G": "Exempt based on article 148, section (g) of Council Directive 2006/112/EC",
    "VATEX-EU-151": "Exempt based on article 151 of Council Directive 2006/112/EC",
    "VATEX-EU-151-1A": "Exempt based on article 151, section 1 (a) of Council Directive 2006/112/EC",
    "VATEX-EU-151-1AA": "Exempt based on article 151, section 1 (aa) of Council Directive 2006/112/EC",
    "VATEX-EU-151-1B": "Exempt based on article 151, section 1 (b) of Council Directive 2006/112/EC",
    "VATEX-EU-151-1C": "Exempt based on article 151, section 1 (c) of Council Directive 2006/112/EC",
    "VATEX-EU-151-1D": "Exempt based on article 151, section 1 (d) of Council Directive 2006/112/EC",
    "VATEX-EU-151-1E": "Exempt based on article 151, section 1 (e) of Council Directive 2006/112/EC",
    "VATEX-EU-153": "Exempt based on article 153 of Council Directive 2006/112/EC",
    "VATEX-EU-159": "Exempt based on article 159 of Council Directive 2006/112/EC",
    "VATEX-EU-309": "Exempt based on article 309 of Council Directive 2006/112/EC",
    "VATEX-EU-AE": "Reverse charge",
    "VATEX-EU-D": "Intra-Community acquisition from second hand means of transport",
    "VATEX-EU-F": "Intra-Community acquisition of second hand goods",
    "VATEX-EU-G": "Export outside the EU",
    "VATEX-EU-I": "Intra-Community acquisition of works of art",
    "VATEX-EU-IC": "Intra-Community supply",
    "VATEX-EU-O": "Not subject to VAT",
    "VATEX-EU-J": "Intra-Community acquisition of collectors items and antiques",
    "VATEX-FR-FRANCHISE": "France domestic VAT franchise in base",
    "VATEX-FR-CNWVAT": "France domestic Credit Notes without VAT, due to supplier forfeit of VAT for discount",
    "VATEX-FR-CGI261-1": "Exempt based on 1 of article 261 of the Code Général des Impôts (CGI ; General tax code)",
    "VATEX-FR-CGI261-2": "Exempt based on 2 of article 261 of the Code Général des Impôts (CGI ; General tax code)",
    "VATEX-FR-CGI261-3": "Exempt based on 3 of article 261 of the Code Général des Impôts (CGI ; General tax code)",
    "VATEX-FR-CGI261-4": "Exempt based on 4 of article 261 of the Code Général des Impôts (CGI ; General tax code)",
    "VATEX-FR-CGI261-5": "Exempt based on 5 of article 261 of the Code Général des Impôts (CGI ; General tax code)",
    "VATEX-FR-CGI261-7": "Exempt based on 7 of article 261 of the Code Général des Impôts (CGI ; General tax code)",
    "VATEX-FR-CGI261-8": "Exempt based on 8 of article 261 of the Code Général des Impôts (CGI ; General tax code)",
    "VATEX-FR-CGI261A": "Exempt based on article 261 A of the Code Général des Impôts (CGI ; General tax code)",
    "VATEX-FR-CGI261B": "Exempt based on article 261 B of the Code Général des Impôts (CGI ; General tax code)",
    "VATEX-FR-CGI261C-1": "Exempt based on 1° of article 261 C of the Code Général des Impôts (CGI ; General tax code)",
    "VATEX-FR-CGI261C-2": "Exempt based on 2° of article 261 C of the Code Général des Impôts (CGI ; General tax code)",
    "VATEX-FR-CGI261C-3": "Exempt based on 3° of article 261 C of the Code Général des Impôts (CGI ; General tax code)",
    "VATEX-FR-CGI261D-1": "Exempt based on 1° of article 261 D of the Code Général des Impôts (CGI ; General tax code)",
    "VATEX-FR-CGI261D-1BIS": "Exempt based on 1°bis of article 261 D of the Code Général des Impôts (CGI ; General tax code)",
    "VATEX-FR-CGI261D-2": "Exempt based on 2° of article 261 D of the Code Général des Impôts (CGI ; General tax code)",
    "VATEX-FR-CGI261D-3": "Exempt based on 3° of article 261 D of the Code Général des Impôts (CGI ; General tax code) Exonération de TVA - Article 261 D-3° du Code Général des Impôts",
    "VATEX-FR-CGI261D-4": "Exempt based on 4° of article 261 D of the Code Général des Impôts (CGI ; General tax code)",
    "VATEX-FR-CGI261E-1": "Exempt based on 1° of article 261 E of the Code Général des Impôts (CGI ; General tax code)",
    "VATEX-FR-CGI261E-2": "Exempt based on 2° of article 261 E of the Code Général des Impôts (CGI ; General tax code)",
    "VATEX-FR-CGI277A": "Exempt based on article 277 A of the Code Général des Impôts (CGI ; General tax code)",
    "VATEX-FR-CGI275": "Exempt based on article 275 of the Code Général des Impôts (CGI ; General tax code)",
    "VATEX-FR-298SEXDECIESA": "Exempt based on article 298 sexdecies A of the Code Général des Impôts (CGI ; General tax code)",
    "VATEX-FR-CGI295": "Exempt based on article 295 of the Code Général des Impôts (CGI ; General tax code)",
    "VATEX-FR-AE": "Exempt based on 2 of article 283 of the Code Général des Impôts (CGI ; General tax code)",
}

SUPPORTED_FILE_TYPES = {
    mimetype_for(extension): f".{extension}"
    for extension in ("pdf", "ods", "xlsx", "jpeg", "png", "csv")
}


class FloatFmt(float):

    def __new__(cls, value, min_dp=2, max_dp=None):
        return super().__new__(cls, value)

    def __init__(self, value, min_dp=2, max_dp=None) -> None:
        self.min_dp = min_dp
        self.max_dp = max_dp

    def __str__(self):
        if not isinstance(self.min_dp, int) or (
            self.max_dp is not None and not isinstance(self.max_dp, int)
        ):
            return "<FloatFmt()>"
        self_float = float(self)
        min_dp_int = int(self.min_dp)
        if self.max_dp is None:
            return float_repr(self_float, min_dp_int)
        else:
            max_dp_int = int(self.max_dp)
            amount_max_dp = float_repr(self_float, max_dp_int)
            num_trailing_zeros = len(amount_max_dp) - len(amount_max_dp.rstrip("0"))
            return float_repr(
                self_float, max(max_dp_int - num_trailing_zeros, min_dp_int)
            )

    def __repr__(self) -> str:
        if not isinstance(self.min_dp, int) or (
            self.max_dp is not None and not isinstance(self.max_dp, int)
        ):
            return "<FloatFmt()>"
        self_float = float(self)
        min_dp_int = int(self.min_dp)
        if self.max_dp is None:
            return f"FloatFmt({self_float!r}, {min_dp_int!r})"
        else:
            max_dp_int = int(self.max_dp)
            return f"FloatFmt({self_float!r}, {min_dp_int!r}, {max_dp_int!r})"


class AccountEdiCommon(models.AbstractModel):
    _name = "account.edi.common"
    _description = (
        "Common functions for EDI documents: generate the data, the constraints, etc"
    )


    def module_installed(self, module_name) -> bool:
        return self.env["ir.module.module"]._get(module_name).state == "installed"

    def format_float(self, amount, precision_digits):
        if amount is None:
            return None
        return float_repr(amount, precision_digits)

    def _get_currency_decimal_places(self, currency_id):
        return currency_id.decimal_places

    def _get_uom_unece_code(self, uom):
        xmlid = uom.get_external_id()
        if xmlid and uom.id in xmlid:
            return UOM_TO_UNECE_CODE.get(xmlid[uom.id], "C62")
        return "C62"

    def _find_value(self, xpaths, tree, nsmap=False):
        if not isinstance(xpaths, (tuple, list)):
            xpaths = [xpaths]
        for xpath in xpaths:
            val = get_xml_value(xpath, tree, nsmap)
            if val:
                return val
        return None

    def _can_export_selfbilling(self) -> bool:
        return False


    def _check_taxes(self, tax_ids) -> None:
        for tax in tax_ids:
            try:
                tax._check_repartition_line_ids()
            except ValidationError as e:
                error_msg = self.env._(
                    "Tax '%(tax_name)s' is invalid: %(error_message)s",
                    tax_name=tax.name,
                    error_message=e.args[0],
                )
                raise ValidationError(error_msg) from None

    def _get_tax_category_code(self, customer, supplier, tax):
        european_economic_area = self.env.ref("base.europe").country_ids.mapped(
            "code"
        ) + ["NO", "IS", "LI"]

        if not tax:
            return "E"

        if tax.ubl_cii_tax_category_code:
            return tax.ubl_cii_tax_category_code

        if customer.country_id.code == "ES" and customer.zip:
            if customer.zip[:2] in ("35", "38"):
                return "L"
            if customer.zip[:2] in ("51", "52"):
                return "M"

        if supplier.country_id == customer.country_id:
            if not tax or tax.amount == 0:
                return "E"
            elif tax.has_negative_factor:
                return "AE"
            else:
                return "S"

        if supplier.country_id.code in european_economic_area and supplier.vat:
            if tax.amount != 0 and not tax.has_negative_factor:
                return "S"
            if customer.country_id.code not in european_economic_area:
                return "G"
            if customer.country_id.code in european_economic_area:
                return "K"

        if tax.amount != 0:
            return "S"
        else:
            return "E"

    def _get_tax_exemption_reason(self, customer, supplier, tax):

        if tax and (code := tax.ubl_cii_tax_exemption_reason_code):
            return {
                "tax_exemption_reason_code": code,
                "tax_exemption_reason": TAX_EXEMPTION_MAPPING.get(
                    code,
                    self.env._("Exempt from tax")
                    if tax.ubl_cii_requires_exemption_reason
                    else None,
                ),
            }

        tax_category_code = self._get_tax_category_code(customer, supplier, tax)
        tax_exemption_reason = tax_exemption_reason_code = None

        if not tax:
            tax_exemption_reason = self.env._("Exempt from tax")
        elif tax_category_code == "E":
            tax_exemption_reason = self.env._(
                "Articles 226 items 11 to 15 Directive 2006/112/EN"
            )
        elif tax_category_code == "G":
            tax_exemption_reason = self.env._("Export outside the EU")
            tax_exemption_reason_code = "VATEX-EU-G"
        elif tax_category_code == "K":
            tax_exemption_reason = self.env._("Intra-Community supply")
            tax_exemption_reason_code = "VATEX-EU-IC"

        return {
            "tax_exemption_reason": tax_exemption_reason,
            "tax_exemption_reason_code": tax_exemption_reason_code,
        }


    def _check_required_fields(self, record, field_names, custom_warning_message=""):
        if not record:
            return custom_warning_message or self.env._(
                "The element %(record)s is required on %(field_list)s.",
                record=record,
                field_list=field_names,
            )

        if not isinstance(field_names, (list, tuple)):
            field_names = (field_names,)

        has_values = any(
            (field_name in record and record[field_name]) for field_name in field_names
        )
        if has_values:
            return None

        if custom_warning_message or isinstance(record, dict):
            return custom_warning_message or self.env._(
                "The element %(record)s is required on %(field_list)s.",
                record=record,
                field_list=field_names,
            )

        display_field_names = record.fields_get(field_names)
        if len(field_names) == 1:
            display_field = f"'{display_field_names[field_names[0]]['string']}'"
            return self.env._(
                "The field %(field)s is required on %(record)s.",
                field=display_field,
                record=record.display_name,
            )
        else:
            display_fields = [
                f"'{display_field_names[x]['string']}'" for x in display_field_names
            ]
            return self.env._(
                "At least one of the following fields %(field_list)s is required on %(record)s.",
                field_list=display_fields,
                record=record.display_name,
            )


    def _invoice_constraints_common(self, invoice) -> dict:
        for line in invoice.invoice_line_ids.filtered(
            lambda x: (
                x.display_type not in NON_ACCOUNTABLE_DISPLAY_TYPES
                and x._is_edi_line_tax_required()
            )
        ):
            if not line.tax_ids:
                return {
                    "tax_on_line": self.env._(
                        "Each invoice line should have at least one tax."
                    )
                }
        return {}


    def _import_invoice_ubl_cii(self, invoice, file_data, new=False):
        invoice.check_singleton()
        if invoice.invoice_line_ids:
            return invoice._reason_cannot_decode_has_invoice_lines()

        tree = file_data["xml_tree"]

        move_type, qty_factor = self._get_import_document_amount_sign(tree)
        if not move_type:
            return None

        journal = invoice.journal_id
        if journal.type == "sale":
            move_type = "out_" + move_type
        elif journal.type == "purchase":
            move_type = "in_" + move_type
        else:
            return None
        if not new and invoice.move_type != move_type:
            types = {move_type, invoice.move_type}
            if types in ({"out_invoice", "out_refund"}, {"in_invoice", "in_refund"}):
                invoice.move_type = move_type
            else:
                return None

        invoice.move_type = move_type
        with invoice.with_context(
            disable_onchange_name_predictive=True
        )._open_edi_creation() as imported_invoice:
            fill_invoice_logs = self._update_invoice_from_xml(
                imported_invoice, tree, qty_factor
            )

        with imported_invoice.with_context(
            disable_onchange_name_predictive=True
        )._open_edi_creation() as corrected_invoice:
            self._correct_invoice_tax_amount(tree, corrected_invoice)

        source_attachment = file_data["attachment"] or self.env["ir.attachment"]
        attachments = source_attachment + self._import_attachments(
            corrected_invoice, tree
        )

        self._log_import_invoice_ubl_cii(
            corrected_invoice, invoice_logs=fill_invoice_logs, attachments=attachments
        )
        return None

    def _add_logs_import_invoice_ubl_cii(self, invoice, invoice_logs=None):
        invoice.check_singleton()
        if invoice_logs is None:
            invoice_logs = []
        format_log = self.env._(
            "Format: %s", self.env["ir.model"]._get(self._name).name
        )
        return [format_log] + invoice_logs

    def _log_import_invoice_ubl_cii(
        self, invoice, title_logs=None, invoice_logs=None, attachments=None
    ) -> None:
        invoice.check_singleton()
        body = Markup("<strong>%s</strong>") % (
            title_logs or self.env._("Invoice imported")
        )
        if invoice_logs := self._add_logs_import_invoice_ubl_cii(
            invoice, invoice_logs=invoice_logs
        ):
            body += Markup("<ul>%s</ul>") % Markup().join(
                Markup("<li>%s</li>") % l for l in invoice_logs
            )
        invoice.message_post(
            body=body, attachment_ids=attachments.ids if attachments else None
        )

    def _import_attachments(self, invoice, tree):
        attachments = self.env["ir.attachment"]
        additional_docs = tree.findall("./{*}AdditionalDocumentReference")
        for document in additional_docs:
            attachment_name = document.find("{*}ID")
            attachment_data = document.find(
                "{*}Attachment/{*}EmbeddedDocumentBinaryObject"
            )
            if attachment_name is not None and attachment_data is not None:
                mimetype = attachment_data.attrib.get("mimeCode")
                if not (extension := SUPPORTED_FILE_TYPES.get(mimetype)):
                    continue
                text = attachment_data.text
                name = (attachment_name.text or "invoice").split("\\")[-1].split("/")[
                    -1
                ].split(".")[0] + extension
                attachment = self.env["ir.attachment"].create(
                    {
                        "name": name,
                        "res_id": invoice.id,
                        "res_model": "account.move",
                        "datas": text + "=" * (len(text) % 3),
                        "type": "binary",
                        "mimetype": mimetype,
                    }
                )
                if (
                    invoice.message_main_attachment_id
                    and invoice.message_main_attachment_id.name.endswith(".xml")
                    and "pdf" not in invoice.message_main_attachment_id.mimetype
                    and mimetype == "application/pdf"
                ):
                    invoice._message_set_main_attachment_id(
                        attachment, force=True, filter_xml=False
                    )
                attachments |= attachment

        return attachments

    def _import_partner(
        self,
        company_id,
        name,
        phone,
        email,
        vat,
        *,
        peppol_eas=False,
        peppol_endpoint=False,
        postal_address=None,
        **kwargs,
    ) -> tuple:
        if postal_address is None:
            postal_address = {}
        logs = []
        if peppol_eas and peppol_endpoint:
            domain = [
                ("peppol_eas", "=", peppol_eas),
                ("peppol_endpoint", "=", peppol_endpoint),
            ]
        else:
            domain = False
        partner = (
            self.env["res.partner"]
            .with_company(company_id)
            ._get_matching_partner(
                name=name, phone=phone, email=email, vat=vat, domain=domain
            )
        )
        country_code = postal_address.get("country_code")
        country = (
            self.env["res.country"].search([("code", "=", country_code.upper())])
            if country_code
            else self.env["res.country"]
        )
        state_code = postal_address.get("state_code")
        state = (
            self.env["res.country.state"].search(
                [("country_id", "=", country.id), ("code", "=", state_code)],
                limit=1,
            )
            if state_code and country
            else self.env["res.country.state"]
        )
        if not partner and name and vat:
            partner_vals = {"name": name, "email": email, "is_company": True}
            if phone:
                partner_vals["phone_ids"] = [
                    Command.create({"number": phone, "type": "landline"})
                ]
            if peppol_eas and peppol_endpoint:
                partner_vals.update(
                    {"peppol_eas": peppol_eas, "peppol_endpoint": peppol_endpoint}
                )
            partner = self.env["res.partner"].create(partner_vals)
            if vat:
                partner.vat, _country_code = self.env["res.partner"]._run_vat_checks(
                    country, vat, validation="setnull"
                )
            logs.append(
                self.env._(
                    "Could not retrieve a partner corresponding to '%s'. A new partner was created.",
                    name,
                )
            )
        elif not partner and not logs:
            logs.append(
                self.env._(
                    "Could not retrieve partner with details: Name: %(name)s, Vat: %(vat)s, Phone: %(phone)s, Email: %(email)s",
                    name=name,
                    vat=vat,
                    phone=phone,
                    email=email,
                )
            )
        if (
            not partner.country_id
            and not partner.street
            and not partner.street2
            and not partner.city
            and not partner.zip
            and not partner.state_id
        ):
            partner.write(
                {
                    "country_id": country.id,
                    "street": postal_address.get("street"),
                    "street2": postal_address.get("additional_street"),
                    "city": postal_address.get("city"),
                    "zip": postal_address.get("zip"),
                    "state_id": state.id,
                }
            )
        return partner, logs

    def _import_partner_bank(self, invoice, bank_details) -> None:
        partner = None
        if invoice.move_type in ("out_refund", "in_invoice"):
            partner = invoice.partner_id
        elif invoice.move_type in ("out_invoice", "in_refund"):
            partner = invoice.company_id.partner_id
        if not partner:
            return

        banks = self.env["res.partner.bank.account"]
        for account_number in bank_details:
            try:
                banks += self.env[
                    "res.partner.bank.account"
                ]._get_or_create_bank_account(
                    account_number=account_number,
                    partner=partner,
                    company=invoice.company_id,
                    revive_archived_match=False,
                )
            except UserError as e:
                invoice._message_log(
                    body=self.env._("The bank account couldn't be fetched: %s", str(e))
                )
        if banks:
            invoice.bank_account_id = banks[0]

    def _import_document_allowance_charges(
        self, tree, record, tax_type, qty_factor=1
    ) -> tuple:
        logs = []
        xpaths = self._get_document_allowance_charge_xpaths()
        line_vals = []
        tax_amounts = {
            float(node.text)
            for allow_el in tree.iterfind(xpaths["root"])
            for node in allow_el.iterfind(xpaths["tax_percentage"])
        }
        tax_by_amount = {}
        if tax_amounts:
            for tax in self.env["account.tax"].search(
                [
                    *self.env["account.tax"]._check_company_domain(record.company_id),
                    ("amount", "in", list(tax_amounts)),
                    ("amount_type", "=", "percent"),
                    ("type_tax_use", "=", tax_type),
                ]
            ):
                tax_by_amount.setdefault(tax.amount, tax)
        for allow_el in tree.iterfind(xpaths["root"]):
            name = allow_el.findtext(xpaths["reason"]) or ""
            charge_indicator = (
                -1
                if allow_el.findtext(xpaths["charge_indicator"]).lower() == "false"
                else 1
            )
            amount = float(allow_el.findtext(xpaths["amount"]) or 0)
            base_amount = float(allow_el.findtext(xpaths["base_amount"]) or 0)
            if base_amount:
                price_unit = base_amount * charge_indicator * qty_factor
                percentage = float(allow_el.findtext(xpaths["percentage"]) or 100)
                quantity = percentage / 100
            else:
                price_unit = amount * charge_indicator * qty_factor
                quantity = 1

            tax_ids = []
            for tax_percent_node in allow_el.iterfind(xpaths["tax_percentage"]):
                tax_amount = float(tax_percent_node.text)
                tax = tax_by_amount.get(tax_amount)
                if tax:
                    tax_ids += tax.ids
                elif name:
                    logs.append(
                        self.env._(
                            "Could not retrieve the tax: %(tax_percentage)s %% for line '%(line)s'.",
                            tax_percentage=tax_amount,
                            line=name,
                        )
                    )
                else:
                    logs.append(
                        self.env._(
                            "Could not retrieve the tax: %s for the document level allowance/charge.",
                            tax_amount,
                        )
                    )

            line_vals.append([name, quantity, price_unit, tax_ids])
        return record._prepare_edi_line_vals(line_vals), logs

    def _import_currency(self, tree, xpath) -> tuple:
        logs = []
        currency_name = tree.findtext(xpath)
        currency = self.env.company.currency_id
        if currency_name is not None:
            currency = currency.with_context(active_test=False).search(
                [
                    ("name", "=", currency_name),
                ],
                limit=1,
            )
            if currency:
                if not currency.active:
                    logs.append(
                        self.env._("The currency '%s' is not active.", currency.name)
                    )
            else:
                logs.append(
                    self.env._(
                        "Could not retrieve currency: %s. Did you enable the multicurrency option "
                        "and activate the currency?",
                        currency_name,
                    )
                )
        return currency.id, logs

    def _import_description(self, tree, xpaths):
        description = ""
        for xpath in xpaths:
            note = tree.findtext(xpath)
            if note:
                description += f"<p>{html_escape(note)}</p>"
        return description

    def _import_prepaid_amount(self, invoice, tree, xpath, qty_factor):
        logs = []
        prepaid_amount = float(tree.findtext(xpath) or 0)
        if not invoice.currency_id.is_zero(prepaid_amount):
            amount = prepaid_amount * qty_factor
            formatted_amount = formatLang(
                self.env, amount, currency_obj=invoice.currency_id
            )
            logs.append(self.env._("A payment of %s was detected.", formatted_amount))
        return logs

    def _import_lines(
        self, record, tree, xpath, document_type=False, tax_type=False, qty_factor=1
    ) -> tuple:
        logs = []
        lines_values = []
        for line_tree in tree.iterfind(xpath):
            line_values = self.with_company(
                record.company_id
            )._prepare_invoice_line_vals(line_tree, document_type, qty_factor)
            if line_values is None:
                continue

            line_values["tax_ids"], tax_logs = self._get_taxes(
                record, line_values, tax_type
            )
            logs += tax_logs
            if not line_values["product_uom_id"]:
                line_values.pop(
                    "product_uom_id"
                )
            lines_values.append(line_values)
            lines_values += self._prepare_line_charge_vals(
                record, line_values, line_values["tax_ids"]
            )
        return lines_values, logs

    def _import_rounding_amount(
        self, invoice, tree, xpath, document_type=False, qty_factor=1
    ) -> tuple:
        logs = []
        lines_values = []

        currency = invoice.currency_id
        rounding_amount_currency = currency.round(
            qty_factor * float(tree.findtext(xpath) or 0)
        )

        if invoice.currency_id.is_zero(rounding_amount_currency):
            return lines_values, logs

        inverse_rate = (
            abs(invoice.amount_total_signed) / invoice.amount_total
            if invoice.amount_total
            else 0
        )
        rounding_amount = invoice.company_id.currency_id.round(
            rounding_amount_currency * inverse_rate
        )

        lines_values.append(
            {
                "display_type": "product",
                "name": self.env._("Rounding"),
                "quantity": 1,
                "product_id": False,
                "price_unit": rounding_amount_currency,
                "amount_currency": invoice.direction_sign * rounding_amount_currency,
                "balance": invoice.direction_sign * rounding_amount,
                "company_id": invoice.company_id.id,
                "move_id": invoice.id,
                "tax_ids": False,
            }
        )

        formatted_amount = formatLang(
            self.env, rounding_amount_currency, currency_obj=currency
        )
        logs.append(
            self.env._("A rounding amount of %s was detected.", formatted_amount)
        )

        return lines_values, logs

    def _prepare_invoice_line_vals(self, tree, document_type=False, qty_factor=1):
        xpath_dict = self._get_invoice_line_xpaths(document_type, qty_factor)
        deferred_values = {}
        start_date = end_date = None
        if self.env["account.move.line"]._fields.get("deferred_start_date"):
            start_date_node = tree.find(xpath_dict["deferred_start_date"])
            end_date_node = tree.find(xpath_dict["deferred_end_date"])
            if (
                start_date_node is not None and end_date_node is not None
            ):
                start_date = datetime.strptime(
                    start_date_node.text.strip(), xpath_dict["date_format"]
                )
                end_date = datetime.strptime(
                    end_date_node.text.strip(), xpath_dict["date_format"]
                )
            deferred_values = {
                "deferred_start_date": start_date,
                "deferred_end_date": end_date,
            }

        line_vals = self._prepare_import_line_vals(tree, document_type, qty_factor)
        if line_vals is None:
            return None

        return {
            **line_vals,
            **deferred_values,
        }

    @api.model
    def _get_rebate_val(self, tree, xpath_dict, quantity):
        rebate = 0
        rebate_node = tree.find(xpath_dict["rebate"])
        net_price_unit_node = tree.find(xpath_dict["net_price_unit"])
        gross_price_unit_node = tree.find(xpath_dict["gross_price_unit"])
        if rebate_node is not None:
            rebate = float(rebate_node.text)
        elif net_price_unit_node is not None and gross_price_unit_node is not None:
            rebate = float(gross_price_unit_node.text) - float(net_price_unit_node.text)
        return rebate

    @api.model
    def _prepare_charge_allowance_vals(self, tree, xpath_dict, quantity) -> tuple:
        charges = []
        discount_amount = 0
        for allowance_charge_node in tree.iterfind(xpath_dict["allowance_charge"]):
            charge_indicator = allowance_charge_node.findtext(
                xpath_dict["allowance_charge_indicator"]
            )
            amount = float(
                allowance_charge_node.findtext(
                    xpath_dict["allowance_charge_amount"], default="0"
                )
            )
            reason_code = allowance_charge_node.findtext(
                xpath_dict["allowance_charge_reason_code"], default=""
            )
            reason = allowance_charge_node.findtext(
                xpath_dict["allowance_charge_reason"], default=""
            )
            if charge_indicator.lower() == "true":
                charges.append(
                    {
                        "amount": amount,
                        "line_quantity": quantity,
                        "reason": reason,
                        "reason_code": reason_code,
                    }
                )
            else:
                discount_amount += amount
        return discount_amount, charges

    def _prepare_import_line_vals(self, tree, document_type=False, qty_factor=1):
        xpath_dict = self._get_line_xpaths(document_type, qty_factor)
        basis_qty = float(self._find_value(xpath_dict["basis_qty"], tree) or 1) or 1.0

        gross_price_unit = None
        gross_price_unit_node = tree.find(xpath_dict["gross_price_unit"])
        if gross_price_unit_node is not None:
            gross_price_unit = float(gross_price_unit_node.text)

        net_price_unit = None
        net_price_unit_node = tree.find(xpath_dict["net_price_unit"])
        if net_price_unit_node is not None:
            net_price_unit = float(net_price_unit_node.text)

        delivered_qty = 1
        product_vals = {
            k: self._find_value(v, tree) for k, v in xpath_dict["product"].items()
        }
        product = self._import_product(**product_vals)
        product_uom_id = self.env["uom.uom"]
        quantity_node = tree.find(xpath_dict["delivered_qty"])
        if quantity_node is not None:
            delivered_qty = float(quantity_node.text)
            uom_xml = quantity_node.attrib.get("unitCode")
            if uom_xml:
                uom_infered_xmlid = [
                    odoo_xmlid
                    for odoo_xmlid, uom_unece in UOM_TO_UNECE_CODE.items()
                    if uom_unece == uom_xml
                ]
                if uom_infered_xmlid:
                    product_uom_id = (
                        self.env.ref(uom_infered_xmlid[0], raise_if_not_found=False)
                        or self.env["uom.uom"]
                    )
        if (
            product
            and product_uom_id
            and not product_uom_id._has_common_reference(product.product_tmpl_id.uom_id)
        ):
            product_uom_id = self.env["uom.uom"]

        price_subtotal = None
        line_total_amount_node = tree.find(xpath_dict["line_total_amount"])
        if (
            line_total_amount_node is None
            or line_total_amount_node.text is None
            or not line_total_amount_node.text.strip()
        ):
            return None
        price_subtotal = float(line_total_amount_node.text)
        if price_subtotal == 0:
            return None

        quantity = delivered_qty * qty_factor

        rebate = self._get_rebate_val(tree, xpath_dict, quantity)

        discount_amount, charges = self._prepare_charge_allowance_vals(
            tree, xpath_dict, quantity
        )

        charge_amount = sum(d["amount"] for d in charges)
        allow_charge_amount = discount_amount - charge_amount
        if gross_price_unit is not None:
            price_unit = gross_price_unit / basis_qty
        elif net_price_unit is not None:
            price_unit = (net_price_unit + rebate) / basis_qty
        elif price_subtotal is not None:
            price_unit = (price_subtotal + allow_charge_amount) / (delivered_qty or 1)
        else:
            raise UserError(
                self.env._(
                    "No gross price, net price nor line subtotal amount found for line in xml"
                )
            )

        discount = 0
        currency = self.env.company.currency_id
        if (
            not float_is_zero(delivered_qty * price_unit, currency.decimal_places)
            and price_subtotal is not None
        ):
            inferred_discount = 100 * (
                1
                - (price_subtotal - charge_amount)
                / currency.round(delivered_qty * price_unit)
            )
            discount = (
                inferred_discount
                if not float_is_zero(inferred_discount, currency.decimal_places)
                else 0.0
            )

        if (
            net_price_unit is not None
            and price_subtotal
            != net_price_unit * (delivered_qty / basis_qty) - allow_charge_amount
        ):
            if net_price_unit == 0 and delivered_qty == 0:
                quantity = 1
                price_unit = price_subtotal
            elif net_price_unit == 0:
                price_unit = price_subtotal / delivered_qty
            elif delivered_qty == 0:
                quantity = price_subtotal / price_unit

        return {
            "name": self._find_value(xpath_dict["name"], tree),
            "product_id": product.id,
            "product_uom_id": product_uom_id.id,
            "price_unit": price_unit,
            "quantity": quantity,
            "discount": discount,
            "tax_nodes": self._get_tax_nodes(tree),
            "charges": charges,
        }

    def _import_product(self, **product_vals):
        return self.env["product.product"]._get_imported_product(**product_vals)

    def _get_fixed_tax(self, company_id, fixed_tax_vals):
        base_domain = [
            *self.env["account.tax"]._check_company_domain(company_id),
            ("amount_type", "=", "fixed"),
            ("amount", "=", fixed_tax_vals["amount"]),
        ]
        for price_include in (False, True):
            for name in (fixed_tax_vals["reason"], False):
                domain = base_domain + [("price_include", "=", price_include)]
                if name:
                    domain.append(("name", "=", name))
                tax = self.env["account.tax"].search(domain, limit=1)  # noqa: E8507 -- tax candidates are tried in priority order; the first hit wins
                if tax:
                    return tax
        return self.env["account.tax"]

    def _get_taxes(self, record, line_values, tax_type, tax_exigibility=None) -> tuple:
        logs = []
        taxes = []
        tax_country = record.fiscal_position_id._get_tax_country(record.company_id)
        fpos_domain = [("fiscal_position_ids", "=", record.fiscal_position_id.id)]
        if record.fiscal_position_id.is_domestic:
            fpos_domain = ["|", ("fiscal_position_ids", "=", False), *fpos_domain]
        for tax_node in line_values.pop("tax_nodes"):
            amount = float(tax_node.text)
            domain = [
                *self.env["account.tax"]._check_company_domain(record.company_id),
                ("amount_type", "=", "percent"),
                ("type_tax_use", "=", tax_type),
                ("amount", "=", amount),
                ("country_id", "=", tax_country.id),
            ]
            tax = self.env["account.tax"]
            if hasattr(record, "_get_specific_tax"):
                tax = record._get_specific_tax(
                    line_values["name"], "percent", amount, tax_type
                ).filtered_domain(domain)[:1]
            if tax_exigibility is not None:
                for extra, price_include in (
                    (fpos_domain, False),
                    (fpos_domain, True),
                    ([], False),
                    ([], True),
                ):
                    if tax:
                        break
                    tax = self.env["account.tax"].search(  # noqa: E8507 -- tax candidates are tried in priority order; the first hit wins
                        domain
                        + extra
                        + [
                            ("price_include", "=", price_include),
                            ("tax_exigibility", "=", tax_exigibility),
                        ],
                        limit=1,
                    )
                if not tax:
                    logs.append(
                        self.env._(
                            "Tax with matching exigibility could not be retrieved: '%(exigibility)s' for line '%(line)s'.",
                            exigibility=tax_exigibility,
                            line=line_values["name"],
                        ),
                    )
            for extra, price_include in (
                (fpos_domain, False),
                (fpos_domain, True),
                ([], False),
                ([], True),
            ):
                if tax:
                    break
                tax = self.env["account.tax"].search(  # noqa: E8507 -- tax candidates are tried in priority order; the first hit wins
                    domain + extra + [("price_include", "=", price_include)], limit=1
                )

            if not tax:
                logs.append(
                    self.env._(
                        "Could not retrieve the tax: %(amount)s %% for line '%(line)s'.",
                        amount=amount,
                        line=line_values["name"],
                    ),
                )
            else:
                taxes.append(tax.id)
                if tax.price_include:
                    line_values["price_unit"] *= 1 + tax.amount / 100
        return taxes, logs

    def _prepare_line_charge_vals(self, record, line_values, taxes):
        charges_vals = []
        for charge in line_values.pop("charges"):
            if charge["reason_code"] == "AEO":
                charge_copy = charge.copy()
                charge_copy["amount"] /= charge_copy["line_quantity"]
                if tax := self._get_fixed_tax(record.company_id, charge_copy):
                    taxes.append(tax.id)
                    if tax.price_include:
                        line_values["price_unit"] += tax.amount
                    continue
            charges_vals.append(
                [
                    charge["reason_code"] + " " + charge["reason"],
                    1,
                    charge["amount"],
                    taxes,
                ]
            )
        return record._prepare_edi_line_vals(charges_vals)

    def _get_document_allowance_charge_xpaths(self):
        pass

    def _get_invoice_line_xpaths(self, invoice_line, qty_factor):
        pass

    def _correct_invoice_tax_amount(self, tree, invoice):
        pass
