import re
import time
from collections import defaultdict
from uuid import uuid4

from lxml import etree

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_repr

import odoo.addons.account.tools.structured_reference as sr
from odoo.addons.account_batch_payment.models.sepa_mapping import (
    normalize_communication,
)
from odoo.addons.account_iban.models.res_partner_bank_account import get_iban_part
from odoo.addons.account_iso20022.models.account_payment import (
    ISO20022_CHARGE_BEARER_SELECTION,
    ISO20022_PRIORITY_HELP,
    ISO20022_PRIORITY_SELECTION,
)


class AccountJournal(models.Model):
    _inherit = "account.journal"

    sepa_pain_version = fields.Selection(
        selection=[
            ("pain.001.001.03.austrian.004", "Austrian"),
            ("pain.001.001.03.de", "German"),
            ("pain.001.001.09", "pain.001.001.09"),
            ("pain.001.001.03", "pain.001.001.03"),
        ],
        string="SEPA XML Format",
        compute="_compute_sepa_pain_version",
        store=True,
        readonly=False,
        help="SEPA version to use to generate Credit Transfer XML files from this journal",
    )
    has_sepa_ct_payment_method = fields.Boolean(
        compute="_compute_has_sepa_ct_payment_method"
    )
    iso20022_default_priority = fields.Selection(
        selection=ISO20022_PRIORITY_SELECTION,
        string="Default Priority",
        default="NORM",
        required=True,
        help=ISO20022_PRIORITY_HELP,
    )
    iso20022_charge_bearer = fields.Selection(
        selection=ISO20022_CHARGE_BEARER_SELECTION,
        string="ISO 20022 Charge Bearer",
        default="SHAR",
        help="Specifies which party/parties will bear the charges associated with the processing of ISO 20022 payment transactions from this journal.",
    )
    has_iso20022_payment_method = fields.Boolean(
        compute="_compute_has_iso20022_payment_method"
    )

    @api.depends(
        "bank_acc_number",
        "company_id.tax_config_id.account_fiscal_country_id",
        "company_id.country_id",
    )
    def _compute_sepa_pain_version(self) -> None:
        pains_by_country = {
            "DE": "pain.001.001.03.de",
            "AT": "pain.001.001.03.austrian.004",
        }
        for rec in self:
            if rec.bank_account_id and rec.bank_account_id.acc_type == "iban":
                country_code = rec.bank_acc_number[:2].upper()
            else:
                country_code = (
                    rec.company_id.tax_config_id.account_fiscal_country_id.code
                    or rec.company_id.country_code
                )
            if country_code in pains_by_country:
                rec.sepa_pain_version = pains_by_country.get(country_code)
            else:
                rec.sepa_pain_version = (
                    "pain.001.001.09"
                    if rec.sepa_pain_version != "pain.001.001.03"
                    else rec.sepa_pain_version
                )

    @api.depends("outbound_payment_channel_ids.payment_method_id.code")
    def _compute_has_sepa_ct_payment_method(self) -> None:
        for rec in self:
            payment_method_codes = rec.mapped(
                "outbound_payment_channel_ids.payment_method_id.code"
            )
            rec.has_sepa_ct_payment_method = "sepa_ct" in payment_method_codes or (
                "iso20022_ch" in payment_method_codes
                and self.env.registry.settings.get(
                    self.env, "iso20022_ch_force_sepa", False
                )
            )

    @api.depends("outbound_payment_channel_ids.payment_method_id.code")
    def _compute_has_iso20022_payment_method(self) -> None:
        for journal in self:
            journal.has_iso20022_payment_method = any(
                journal.mapped(
                    "outbound_payment_channel_ids.payment_method_id.is_iso20022"
                )
            )

    def _default_outbound_payment_methods(self):
        res = super()._default_outbound_payment_methods()
        if self._is_payment_method_available("sepa_ct"):
            res |= self.env.ref("account_iso20022.account_payment_method_sepa_ct")
        elif self._is_payment_method_available("iso20022_se"):
            res |= self.env.ref("account_iso20022.account_payment_method_iso20022_se")
        elif self._is_payment_method_available("iso20022_ch"):
            res |= self.env.ref("account_iso20022.account_payment_method_iso20022_ch")
        elif self._is_payment_method_available("iso20022_us"):
            res |= self.env.ref("account_iso20022.account_payment_method_iso20022_us")
        elif self._is_payment_method_available("iso20022"):
            res |= self.env.ref("account_iso20022.account_payment_method_iso20022")

        return res


    def create_iso20022_credit_transfer(
        self, payments, payment_method_code, batch_booking=False
    ):
        Document = self.create_iso20022_credit_transfer_content(
            payments, payment_method_code, batch_booking=batch_booking
        )
        return etree.tostring(
            Document, pretty_print=True, xml_declaration=True, encoding="utf-8"
        )

    def create_iso20022_credit_transfer_content(
        self, payments, payment_method_code, batch_booking=False
    ):
        Document = etree.Element(
            "Document",
            nsmap={
                None: self.get_document_namespace(payment_method_code),
                "xsi": "http://www.w3.org/2001/XMLSchema-instance",
            },
        )
        CstmrCdtTrfInitn = etree.SubElement(Document, "CstmrCdtTrfInitn")

        GrpHdr = etree.SubElement(CstmrCdtTrfInitn, "GrpHdr")
        MsgId = etree.SubElement(GrpHdr, "MsgId")
        val_MsgId = str(time.time())
        MsgId.text = val_MsgId
        CreDtTm = etree.SubElement(GrpHdr, "CreDtTm")
        CreDtTm.text = time.strftime("%Y-%m-%dT%H:%M:%S")
        NbOfTxs = etree.SubElement(GrpHdr, "NbOfTxs")
        val_NbOfTxs = str(len(payments))
        if len(val_NbOfTxs) > 15:
            raise ValidationError(
                self.env._("Too many transactions for a single file.")
            )
        NbOfTxs.text = val_NbOfTxs
        CtrlSum = etree.SubElement(GrpHdr, "CtrlSum")
        CtrlSum.text = self._get_CtrlSum(payments)
        GrpHdr.append(self._prepare_initiating_party_element(payment_method_code))

        eur_currency = self.env.ref("base.EUR")
        chf_currency = self.env.ref("base.CHF")
        payments_date_instr_wise = defaultdict(list)
        today = fields.Date.today()
        iso20022_ch_force_sepa = self.env.registry.settings.get(
            self.env, "iso20022_ch_force_sepa", False
        )
        for payment in payments:
            required_payment_date = max(payment["payment_date"], today)
            currency_id = payment["currency_id"] or self.company_id.currency_id.id
            priority = payment["iso20022_priority"]
            payments_date_instr_wise[
                required_payment_date, currency_id, priority
            ].append(payment)
        for count, ((payment_date, currency_id, priority), payments_list) in enumerate(
            payments_date_instr_wise.items()
        ):
            PmtInf = etree.SubElement(CstmrCdtTrfInitn, "PmtInf")
            PmtInfId = etree.SubElement(PmtInf, "PmtInfId")
            PmtInfId.text = (val_MsgId + str(self.id) + str(count))[-30:]
            PmtMtd = etree.SubElement(PmtInf, "PmtMtd")
            PmtMtd.text = "TRF"
            BtchBookg = etree.SubElement(PmtInf, "BtchBookg")
            BtchBookg.text = (batch_booking and "true") or "false"
            NbOfTxs = etree.SubElement(PmtInf, "NbOfTxs")
            NbOfTxs.text = str(len(payments_list))
            CtrlSum = etree.SubElement(PmtInf, "CtrlSum")
            CtrlSum.text = self._get_CtrlSum(payments_list)

            group_payment_method_code = payment_method_code
            if iso20022_ch_force_sepa and payment_method_code == "iso20022_ch":
                if currency_id == eur_currency.id:
                    group_payment_method_code = "sepa_ct"
                elif currency_id != chf_currency.id:
                    group_payment_method_code = "iso20022"

            PmtTpInf = self._prepare_payment_type_element(
                group_payment_method_code, priority
            )
            if (
                len(PmtTpInf) != 0
            ):
                PmtInf.append(PmtTpInf)

            ReqdExctnDt = self._prepare_execution_date_element(
                payment_date, group_payment_method_code
            )
            PmtInf.append(ReqdExctnDt)

            PmtInf.append(self._prepare_debtor_element(group_payment_method_code))
            PmtInf.append(
                self._prepare_debtor_account_element(group_payment_method_code)
            )
            DbtrAgt = etree.SubElement(PmtInf, "DbtrAgt")
            DbtrAgt.append(
                self._prepare_financial_institution_element(
                    self.bank_account_id, group_payment_method_code, mode="DbtrAgt"
                )
            )
            unique_chrgbr_values = {
                payment.get("iso20022_charge_bearer") for payment in payments_list
            }
            unique_chrgbr = (
                unique_chrgbr_values.pop() if len(unique_chrgbr_values) == 1 else None
            )
            if unique_chrgbr:
                PmtInf.append(
                    self._prepare_charge_bearer_element(
                        group_payment_method_code, unique_chrgbr
                    )
                )

            for payment in payments_list:
                PmtInf.append(
                    self._prepare_credit_transfer_element(
                        PmtInfId,
                        payment,
                        group_payment_method_code,
                        include_charge_bearer=not unique_chrgbr,
                    )
                )
        return Document

    def _get_CtrlSum(self, payments):
        return float_repr(sum(payment["amount"] for payment in payments), 2)

    def _prepare_initiating_party_element(self, payment_method_code) -> etree._Element:
        InitgPty = etree.Element("InitgPty")
        InitgPty.extend(
            self._prepare_company_identification_elements(
                postal_address=False, issr=True, payment_method_code=payment_method_code
            )
        )
        return InitgPty

    def _prepare_payment_type_element(
        self, payment_method_code: str, priority: str | None
    ) -> etree._Element:
        PmtTpInf = etree.Element("PmtTpInf")
        if priority:
            InstrPrty = etree.SubElement(PmtTpInf, "InstrPrty")
            InstrPrty.text = priority
        SvcLvlTxt = self._get_SvcLvlText(payment_method_code)
        if SvcLvlTxt:
            SvcLvl = etree.SubElement(PmtTpInf, "SvcLvl")
            Cd = etree.SubElement(SvcLvl, "Cd")
            Cd.text = SvcLvlTxt

        CtgyPurp = self._prepare_category_purpose_element(payment_method_code)
        if CtgyPurp is not None:
            PmtTpInf.append(CtgyPurp)

        LclInstrm = self._prepare_local_instrument_element(payment_method_code)
        if LclInstrm is not None:
            PmtTpInf.append(LclInstrm)
        return PmtTpInf

    def _prepare_local_instrument_element(
        self, payment_method_code: str
    ) -> etree._Element | None:
        if payment_method_code == "iso20022" and (
            local_instrument_code := self.env.registry.settings.get(
                self.env, "account_iso20022.local_instrument_code", False
            )
        ):
            LclInstrm = etree.Element("LclInstrm")
            Cd = etree.SubElement(LclInstrm, "Cd")
            Cd.text = local_instrument_code
            return LclInstrm
        return None

    def _prepare_category_purpose_element(
        self, payment_method_code: str
    ) -> etree._Element | None:
        if self.env.context.get("sepa_payroll_sala"):
            CtgyPurp = etree.Element("CtgyPurp")
            Cd = etree.SubElement(CtgyPurp, "Cd")
            Cd.text = "SALA"
            return CtgyPurp
        return None

    def _prepare_execution_date_element(
        self, payment_date, payment_method_code
    ) -> etree._Element:
        ReqdExctnDt = etree.Element("ReqdExctnDt")
        ReqdExctnDt.text = fields.Date.to_string(payment_date)
        return ReqdExctnDt

    def _prepare_debtor_element(self, payment_method_code) -> etree._Element:
        Dbtr = etree.Element("Dbtr")
        Dbtr.extend(
            self._prepare_company_identification_elements(
                postal_address=True, payment_method_code=payment_method_code
            )
        )
        return Dbtr

    def _prepare_debtor_account_element(
        self, payment_method_code=None, payments=None
    ) -> etree._Element:
        if not self.bank_account_id.sanitized_acc_number:
            raise UserError(
                self.env._("This journal does not have a bank account defined.")
            )
        DbtrAcct = etree.Element("DbtrAcct")
        Id = etree.SubElement(DbtrAcct, "Id")
        if self.bank_account_id.acc_type != "iban":
            Id.append(self._prepare_debtor_other_account_element(payment_method_code))
        else:
            IBAN = etree.SubElement(Id, "IBAN")
            IBAN.text = self.bank_account_id.sanitized_acc_number
        Ccy = etree.SubElement(DbtrAcct, "Ccy")
        Ccy.text = (
            self.currency_id and self.currency_id.name
        ) or self.company_id.currency_id.name
        return DbtrAcct

    def _prepare_debtor_other_account_element(
        self, payment_method_code=None, partner_acc_type=None
    ) -> etree._Element:
        Othr = etree.Element("Othr")
        OthrId = etree.SubElement(Othr, "Id")
        OthrId.text = self.bank_account_id.sanitized_acc_number
        return Othr

    def _prepare_charge_bearer_element(
        self, payment_method_code, forced_value
    ) -> etree._Element:
        ChrgBr = etree.Element("ChrgBr")
        ChrgBr.text = forced_value or "SHAR"
        return ChrgBr

    def _prepare_credit_transfer_element(
        self, PmtInfId, payment, payment_method_code, include_charge_bearer=True
    ) -> etree._Element:
        CdtTrfTxInf = etree.Element("CdtTrfTxInf")
        PmtId = etree.SubElement(CdtTrfTxInf, "PmtId")
        if payment["name"]:
            InstrId = etree.SubElement(PmtId, "InstrId")
            InstrId.text = normalize_communication(payment["name"], 35)
        EndToEndId = etree.SubElement(PmtId, "EndToEndId")
        EndToEndId.text = payment.get("end_to_end_uuid") or uuid4().hex
        Amt = etree.SubElement(CdtTrfTxInf, "Amt")

        journal_id = self.env["account.journal"].search(
            [("id", "=", payment["journal_id"])], limit=1
        )
        currency_id = (
            self.env["res.currency"].search(
                [("id", "=", payment["currency_id"])], limit=1
            )
            or journal_id.company_id.currency_id
        )
        val_Ccy = currency_id.name
        val_InstdAmt = float_repr(
            currency_id.round(payment["amount"]), currency_id.decimal_places
        )
        InstdAmt = etree.SubElement(Amt, "InstdAmt", Ccy=val_Ccy)
        InstdAmt.text = val_InstdAmt

        if include_charge_bearer:
            CdtTrfTxInf.append(
                self._prepare_charge_bearer_element(
                    payment_method_code, payment["iso20022_charge_bearer"]
                )
            )

        partner = self.env["res.partner"].sudo().browse(payment["partner_id"])

        bank_account_id = payment.get("bank_account_id")
        if not bank_account_id:
            raise UserError(
                self.env._("Partner %s has not bank account defined.", partner.name)
            )

        partner_bank = (
            self.env["res.partner.bank.account"].sudo().browse(bank_account_id)
        )

        if not self._skip_CdtrAgt(partner_bank, payment_method_code):
            CdtTrfTxInf.append(
                self._prepare_creditor_agent_element(partner_bank, payment_method_code)
            )

        Cdtr = etree.SubElement(CdtTrfTxInf, "Cdtr")
        Nm = etree.SubElement(Cdtr, "Nm")
        Nm.text = (
            normalize_communication(
                (
                    partner_bank.acc_holder_name
                    or partner.name
                    or partner.commercial_partner_id.name
                    or "/"
                )[:70]
            ).strip()
            or "/"
        )

        PstlAdr = self._prepare_postal_address_element(partner, payment_method_code)
        if PstlAdr is not None:
            Cdtr.append(PstlAdr)

        CdtTrfTxInf.append(
            self._prepare_creditor_account_element(partner_bank, payment_method_code)
        )

        val_RmtInf = self._prepare_remittance_element(payment_method_code, payment)
        if val_RmtInf is not None:
            CdtTrfTxInf.append(val_RmtInf)
        return CdtTrfTxInf

    def _prepare_creditor_agent_element(
        self, bank_account, payment_method_code
    ) -> etree._Element:
        CdtrAgt = etree.Element("CdtrAgt")
        CdtrAgt.append(
            self._prepare_financial_institution_element(
                bank_account, payment_method_code, mode="CdtrAgt"
            )
        )
        return CdtrAgt

    def _prepare_financial_institution_element(
        self, bank_account, payment_method_code, mode=None
    ) -> etree._Element:
        FinInstnId = etree.Element("FinInstnId")
        bic_code = self._get_cleaned_bic_code(bank_account, payment_method_code)
        if bic_code:
            BIC = etree.SubElement(FinInstnId, self._get_bic_tag(payment_method_code))
            BIC.text = bic_code
        else:
            Othr = etree.SubElement(FinInstnId, "Othr")
            Id = etree.SubElement(Othr, "Id")
            Id.text = "NOTPROVIDED"
        if bank_account.clearing_number:
            ClrSysMmbId = etree.SubElement(FinInstnId, "ClrSysMmbId")
            MmbId = etree.SubElement(ClrSysMmbId, "MmbId")
            MmbId.text = bank_account.clearing_number
        return FinInstnId

    def _prepare_creditor_account_element(
        self, bank_account, payment_method_code=None
    ) -> etree._Element:
        CdtrAcct = etree.Element("CdtrAcct")
        Id = etree.SubElement(CdtrAcct, "Id")
        if bank_account.acc_type == "iban":
            IBAN = etree.SubElement(Id, "IBAN")
            IBAN.text = bank_account.sanitized_acc_number
        else:
            Id.append(
                self._prepare_creditor_other_account_element(
                    bank_account, payment_method_code
                )
            )
        return CdtrAcct

    def _prepare_creditor_other_account_element(
        self, bank_account, payment_method_code=None
    ) -> etree._Element:
        Othr = etree.Element("Othr")
        Id = etree.SubElement(Othr, "Id")
        acc_number = bank_account.acc_number

        if " " in bank_account.sanitized_acc_number and " " in bank_account.acc_number:
            acc_number = bank_account.acc_number.split(" ")[0]
        Id.text = acc_number
        return Othr

    def _prepare_remittance_element(
        self, payment_method_code, payment
    ) -> etree._Element | None:
        def get_reference_type(reference, partner_country_code):
            if partner_country_code == "BE" and sr.is_valid_structured_reference_be(
                reference
            ):
                return "be"
            elif self._is_qr_iban(payment):
                return "ch"
            elif partner_country_code == "FI" and sr.is_valid_structured_reference_fi(
                reference
            ):
                return "fi"
            elif (
                partner_country_code == "NO"
                and sr.is_valid_structured_reference_no_se(reference)
            ):
                return "no"
            elif (
                partner_country_code == "SE"
                and sr.is_valid_structured_reference_no_se(reference)
            ):
                return "se"
            elif sr.is_valid_structured_reference_iso(reference):
                return "iso"
            else:
                return None

        if not payment["memo"]:
            return None
        RmtInf = etree.Element("RmtInf")
        ref = sr.normalize_structured_reference(payment["memo"])
        partner_country_code = payment.get("partner_country_code")
        reference_type = get_reference_type(ref, partner_country_code)
        if reference_type:
            RmtInf.append(
                self._prepare_remittance_reference_element(ref, reference_type)
            )
        else:
            Ustrd = etree.SubElement(RmtInf, "Ustrd")
            Ustrd.text = normalize_communication(payment["memo"])
        return RmtInf

    def _prepare_company_identification_elements(
        self,
        payment_method_code,
        postal_address=True,
        nm=True,
        issr=True,
        schme_nm=False,
    ) -> list[etree._Element]:
        ret = []

        Nm = etree.Element("Nm")
        Nm.text = self.iso20022_get_company_name()
        ret.append(Nm)

        if postal_address:
            PstlAdr = self._prepare_postal_address_element(
                self.company_id.partner_id, payment_method_code
            )
            if PstlAdr is not None:
                ret.append(PstlAdr)

        if self.company_id.iso20022_orgid_id:
            Id = etree.Element("Id")
            OrgId = etree.SubElement(Id, "OrgId")
            company = self.company_id
            if self.sepa_pain_version != "pain.001.001.03" and company.iso20022_lei:
                LEI = etree.Element("LEI")
                LEI.text = self.company_id.iso20022_lei
                OrgId.insert(0, LEI)
            Othr = etree.SubElement(OrgId, "Othr")
            _Id = etree.SubElement(Othr, "Id")
            _Id.text = normalize_communication(self.company_id.iso20022_orgid_id)
            if issr and company.iso20022_orgid_issr:
                Issr = etree.SubElement(Othr, "Issr")
                Issr.text = normalize_communication(company.iso20022_orgid_issr)
            if schme_nm:
                SchmeNm = etree.SubElement(Othr, "SchmeNm")
                Cd = etree.SubElement(SchmeNm, "Cd")
                Cd.text = schme_nm
            ret.append(Id)

        return ret


    def get_document_namespace(self, payment_method_code):
        namespace = "pain.001.001.03"
        if self.sepa_pain_version == "pain.001.001.09":
            namespace = "pain.001.001.09"
        return "urn:iso:std:iso:20022:tech:xsd:%s" % namespace

    def _get_bic_tag(self, payment_method_code):
        return "BIC"

    def iso20022_get_company_name(self):
        company = self.company_id
        name_length = 35 if company.iso20022_initiating_party_name else 70
        name = company.iso20022_initiating_party_name or company.name
        return normalize_communication(name[:name_length])

    def _get_SvcLvlText(self, payment_method_code) -> str | None:
        if payment_method_code == "iso20022":
            return "NURG"
        return None

    def _prepare_postal_address_element(
        self, partner_id, payment_method_code
    ) -> etree._Element | None:
        partner_address = self.get_postal_address(partner_id, payment_method_code)
        if partner_address:
            PstlAdr = etree.Element("PstlAdr")
            Ctry = etree.SubElement(PstlAdr, "Ctry")
            Ctry.text = partner_address["country"]
            if partner_address.get("street"):
                AdrLine = etree.SubElement(PstlAdr, "AdrLine")
                AdrLine.text = normalize_communication(partner_address["street"][:70])
            if partner_address.get("zip") and partner_address.get("city"):
                AdrLine = etree.SubElement(PstlAdr, "AdrLine")
                AdrLine.text = normalize_communication(
                    (partner_address["zip"] + " " + partner_address["city"])[:70]
                )
            return PstlAdr
        return None

    def get_postal_address(self, partner_id, payment_method_code):
        pstl_addr_list = [
            address for address in partner_id._get_all_addr() if address["country"]
        ]
        if not pstl_addr_list:
            if partner_id.is_company:
                raise ValidationError(
                    self.env._(
                        "Partner %s has no country code defined.", partner_id.name
                    )
                )
            raise ValidationError(
                self.env._(
                    "Employee %s has no country in their address.", partner_id.name
                )
            )
        pstl_addr_list = [addr for addr in pstl_addr_list if addr["city"]]
        if not pstl_addr_list:
            return None
        for addr_dict in pstl_addr_list:
            if addr_dict["contact_type"] == "employee":
                return addr_dict
        return pstl_addr_list[0]

    def _skip_CdtrAgt(self, partner_bank, payment_method_code):
        return self.env.context.get("skip_bic", False) or not partner_bank.bank_id.bic

    def _prepare_remittance_reference_element(
        self, ref, reference_type=""
    ) -> etree._Element:
        return self._prepare_structured_remittance_element(ref, cd="SCOR", issr="ISO")

    def _get_cleaned_bic_code(self, bank_account, payment_method_code):
        if not bank_account.bank_bic:
            return None
        regex = self._get_regex_for_bic_code(payment_method_code)
        if not re.match(regex, bank_account.bank_bic):
            raise UserError(
                self.env._(
                    "The BIC code '%(bic_code)s' associated to the bank '%(bank)s' of bank account '%(account)s' "
                    "of partner '%(partner)s' does not respect the required convention.\n"
                    "It must contain 8 or 11 characters and match the following structure:\n"
                    "- 4 letters: institution code or bank code\n"
                    "- 2 letters: country code\n"
                    "- 2 letters or digits: location code\n"
                    "- 3 letters or digits: branch code, optional\n",
                    bic_code=bank_account.bank_bic,
                    bank=bank_account.bank_id.name,
                    account=bank_account.sanitized_acc_number,
                    partner=bank_account.partner_id.name,
                )
            )
        return bank_account.bank_bic.replace(" ", "").upper()

    def _get_regex_for_bic_code(self, payment_method_code):
        return "[A-Z]{6,6}[A-Z2-9][A-NP-Z0-9]([A-Z0-9]{3,3}){0,1}"

    def _is_qr_iban(self, payment_dict) -> bool:
        partner_bank = self.env["res.partner.bank.account"].browse(
            payment_dict["bank_account_id"]
        )
        company = (
            self.env["account.journal"].browse(payment_dict["journal_id"]).company_id
        )
        iban = partner_bank.sanitized_acc_number
        if (
            partner_bank.acc_type != "iban"
            or (partner_bank.sanitized_acc_number or "")[:2] not in ("CH", "LI")
            or partner_bank.company_id.id not in (False, company.id)
            or len(iban) < 9
        ):
            return False
        iid = get_iban_part(iban, "bank")
        return bool(
            re.match(r"\d+", iid) and 30000 <= int(iid) <= 31999
        )

    def _prepare_structured_remittance_element(
        self,
        ref: str,
        cd: str | None = None,
        prtry: str | None = None,
        issr: str | None = None,
    ) -> etree._Element:
        strd = etree.Element("Strd")
        CdtrRefInf = etree.SubElement(strd, "CdtrRefInf")
        Tp = etree.SubElement(CdtrRefInf, "Tp")
        CdOrPrtry = etree.SubElement(Tp, "CdOrPrtry")
        if cd:
            Cd = etree.SubElement(CdOrPrtry, "Cd")
            Cd.text = cd
        if prtry:
            Prtry = etree.SubElement(CdOrPrtry, "Prtry")
            Prtry.text = prtry
        if issr:
            Issr = etree.SubElement(Tp, "Issr")
            Issr.text = issr
        Ref = etree.SubElement(CdtrRefInf, "Ref")
        Ref.text = ref
        return strd
