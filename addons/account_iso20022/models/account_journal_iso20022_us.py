import re

from lxml import etree

from odoo import models


class AccountJournal(models.Model):
    _inherit = "account.journal"

    def get_document_namespace(self, payment_method_code):
        if payment_method_code == "iso20022_us":
            return "urn:iso:std:iso:20022:tech:xsd:pain.001.001.03"
        return super().get_document_namespace(payment_method_code)

    def _get_SvcLvlText(self, payment_method_code) -> str | None:
        if payment_method_code == "iso20022_us":
            return "NURG"
        return super()._get_SvcLvlText(payment_method_code)

    def _prepare_payment_type_element(
        self, payment_method_code: str, priority: str | None
    ) -> etree._Element:
        """Right now the entry class code is a field stored in a different module
        `l10n_us_payment_nacha` which is not always installed. If it is we can take
        advantage of it, otherwise we default to CCD.
        """
        PmtTpInf = super()._prepare_payment_type_element(payment_method_code, priority)
        if payment_method_code == "iso20022_us":
            LclInstrm = etree.SubElement(PmtTpInf, "LclInstrm")
            Cd = etree.SubElement(LclInstrm, "Cd")
            cd_text = "CCD"
            nacha_module = self.env["ir.module.module"]._get("l10n_us_payment_nacha")
            if nacha_module.state == "installed" and self.nacha_entry_class_code:
                cd_text = self.nacha_entry_class_code

            Cd.text = cd_text
        return PmtTpInf

    def _prepare_debtor_element(self, payment_method_code) -> etree._Element:
        if payment_method_code == "iso20022_us":
            Dbtr = etree.Element("Dbtr")
            Dbtr.extend(
                self._prepare_company_identification_elements(
                    postal_address=True,
                    issr=False,
                    schme_nm="CHID",
                    payment_method_code=payment_method_code,
                )
            )
            return Dbtr
        return super()._prepare_debtor_element(payment_method_code)

    def _skip_CdtrAgt(self, partner_bank, payment_method_code):
        if payment_method_code == "iso20022_us":
            return False
        return super()._skip_CdtrAgt(partner_bank, payment_method_code)

    def _prepare_credit_transfer_element(
        self, PmtInfId, payment, payment_method_code, include_charge_bearer=True
    ) -> etree._Element:
        # In the US via BoA there are reserved characters not allowed in the memo or payment name.
        # They are (*+~:)
        CdtTrfTxInf = super()._prepare_credit_transfer_element(
            PmtInfId,
            payment,
            payment_method_code,
            include_charge_bearer=include_charge_bearer,
        )
        if payment_method_code == "iso20022_us":
            if (InstrId := CdtTrfTxInf.find(".//InstrId")) is not None:
                InstrId.text = re.sub(r"[\*\+:\'\~]", "", InstrId.text)
        return CdtTrfTxInf

    def _prepare_remittance_element(
        self, payment_method_code, payment
    ) -> etree._Element | None:
        # In the US via BoA there are reserved characters not allowed in the memo or payment name.
        # They are (*+~:)
        RmtInf = super()._prepare_remittance_element(payment_method_code, payment)
        if payment_method_code == "iso20022_us" and RmtInf is not None:
            if (Ustrd := RmtInf.find(".//Ustrd")) is not None:
                Ustrd.text = re.sub(r"[\*\+:\'\~]", "", Ustrd.text)
        return RmtInf

    def _prepare_financial_institution_element(
        self, bank_account, payment_method_code, mode=None
    ) -> etree._Element:
        FinInstnId = super()._prepare_financial_institution_element(
            bank_account, payment_method_code, mode
        )
        if payment_method_code == "iso20022_us":
            bank_country_code = bank_account.bank_id.country_code
            if bank_country_code:
                PstlAdr = etree.Element("PstlAdr")
                Ctry = etree.SubElement(PstlAdr, "Ctry")
                Ctry.text = bank_country_code
                FinInstnId.insert(0, PstlAdr)

            if bank_account.clearing_number:
                ClrSysMmbId = FinInstnId.find(".//ClrSysMmbId")
                if ClrSysMmbId is not None:
                    FinInstnId.remove(ClrSysMmbId)

                ClrSysMmbId = etree.Element("ClrSysMmbId")
                MmbId = etree.SubElement(ClrSysMmbId, "MmbId")
                MmbId.text = bank_account.clearing_number
                FinInstnId.insert(0, ClrSysMmbId)

            bic_code = self._get_cleaned_bic_code(bank_account, payment_method_code)
            if bic_code:
                BIC = FinInstnId.find(".//BIC")
                if BIC is not None:
                    FinInstnId.remove(BIC)

                BIC = etree.Element("BIC")
                BIC.text = bic_code
                FinInstnId.insert(0, BIC)
        return FinInstnId
