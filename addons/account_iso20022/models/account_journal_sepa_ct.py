from lxml import etree

from odoo import fields, models
from odoo.exceptions import UserError

from odoo.addons.account_batch_payment.models.sepa_mapping import (
    normalize_communication,
)


class AccountJournal(models.Model):
    _inherit = "account.journal"

    def create_iso20022_credit_transfer(
        self, payments, payment_method_code, batch_booking=False
    ):
        if (
            payments
            and payment_method_code == "sepa_ct"
            and self.sepa_pain_version == "pain.001.001.09"
            and any(not payment["iso20022_uetr"] for payment in payments)
        ):
            raise UserError(
                self.env._(
                    "Some payments are missing a value for 'UETR', required for the SEPA Pain.001.001.09 format."
                )
            )
        return super().create_iso20022_credit_transfer(
            payments, payment_method_code, batch_booking=batch_booking
        )

    def _prepare_execution_date_element(
        self, payment_date, payment_method_code
    ) -> etree._Element:
        force_iso_20022_pain_09 = bool(
            self.env.registry.settings.get(
                self.env, "account_iso20022.force_iso_20022_pain_09", False
            )
        )
        ReqdExctnDt = etree.Element("ReqdExctnDt")
        use_pain_09 = (
            payment_method_code == "sepa_ct"
            and self.sepa_pain_version == "pain.001.001.09"
        ) or (payment_method_code == "iso20022" and force_iso_20022_pain_09)
        if use_pain_09:
            Dt = etree.SubElement(ReqdExctnDt, "Dt")
            Dt.text = fields.Date.to_string(payment_date)
            return ReqdExctnDt
        return super()._prepare_execution_date_element(
            payment_date, payment_method_code
        )

    def _skip_CdtrAgt(self, partner_bank, payment_method_code):
        if payment_method_code == "sepa_ct" and self.sepa_pain_version == "pain_de":
            return False
        return super()._skip_CdtrAgt(partner_bank, payment_method_code)

    def _prepare_creditor_agent_element(
        self, bank_account, payment_method_code
    ) -> etree._Element:
        CdtrAgt = super()._prepare_creditor_agent_element(
            bank_account, payment_method_code
        )
        force_iso_20022_pain_09 = bool(
            self.env.registry.settings.get(
                self.env, "account_iso20022.force_iso_20022_pain_09", False
            )
        )
        use_pain_09 = (
            payment_method_code == "sepa_ct"
            and self.sepa_pain_version == "pain.001.001.09"
        ) or (payment_method_code == "iso20022" and force_iso_20022_pain_09)
        if use_pain_09:
            FinInstnId = CdtrAgt.find(".//FinInstnId")
            partner_lei = bank_account.partner_id.iso20022_lei
            if partner_lei:
                LEI = etree.SubElement(FinInstnId, "LEI")
                LEI.text = partner_lei
            return CdtrAgt
        return CdtrAgt

    def _prepare_charge_bearer_element(
        self, payment_method_code, forced_value
    ) -> etree._Element:
        if payment_method_code == "sepa_ct":
            ChrgBr = etree.Element("ChrgBr")
            ChrgBr.text = "SLEV"
            return ChrgBr
        return super()._prepare_charge_bearer_element(payment_method_code, forced_value)

    def _prepare_postal_address_element(
        self, partner_id, payment_method_code
    ) -> etree._Element | None:
        force_iso_20022_pain_09 = bool(
            self.env.registry.settings.get(
                self.env, "account_iso20022.force_iso_20022_pain_09", False
            )
        )
        use_pain_09 = (
            payment_method_code == "sepa_ct"
            and self.sepa_pain_version == "pain.001.001.09"
        ) or (payment_method_code == "iso20022" and force_iso_20022_pain_09)
        if use_pain_09:
            postal_address = self.get_postal_address(partner_id, payment_method_code)
            if postal_address is not None:
                PstlAdr = etree.Element("PstlAdr")
                for node_name, attr, size in [
                    ("StrtNm", "street", 70),
                    ("PstCd", "zip", 140),
                    ("TwnNm", "city", 140),
                    ("Ctry", "country", 2),
                ]:
                    if postal_address[attr]:
                        address_element = etree.SubElement(PstlAdr, node_name)
                        address_element.text = normalize_communication(
                            postal_address[attr], size
                        )
                return PstlAdr
        return super()._prepare_postal_address_element(partner_id, payment_method_code)

    def _prepare_credit_transfer_element(
        self, PmtInfId, payment, payment_method_code, include_charge_bearer=True
    ) -> etree._Element:
        CdtTrfTxInf = super()._prepare_credit_transfer_element(
            PmtInfId, payment, payment_method_code, include_charge_bearer
        )
        force_iso_20022_pain_09 = bool(
            self.env.registry.settings.get(
                self.env, "account_iso20022.force_iso_20022_pain_09", False
            )
        )
        use_pain_09 = (
            payment_method_code == "sepa_ct"
            and self.sepa_pain_version == "pain.001.001.09"
        ) or (payment_method_code == "iso20022" and force_iso_20022_pain_09)
        partner = self.env["res.partner"].sudo().browse(payment["partner_id"])
        if use_pain_09 and payment.get("iso20022_uetr"):
            PmtId = CdtTrfTxInf.find(".//PmtId")
            UETR = etree.SubElement(PmtId, "UETR")
            UETR.text = payment["iso20022_uetr"]
        if (
            payment_method_code == "sepa_ct"
            and partner.country_id.code
            and partner.city
        ):
            Cdtr = CdtTrfTxInf.find("Cdtr")
            partner = self.env["res.partner"].sudo().browse(payment["partner_id"])
            PstlAdr = Cdtr.find(".//PstlAdr")
            if PstlAdr is not None:
                Cdtr.remove(PstlAdr)
            Cdtr.append(
                self._prepare_postal_address_element(partner, payment_method_code)
            )
        return CdtTrfTxInf

    def _prepare_remittance_reference_element(
        self, ref, reference_type=""
    ) -> etree._Element:
        if reference_type == "be":
            return self._prepare_structured_remittance_element(
                ref, cd="SCOR", issr="BBA"
            )
        elif reference_type == "ch":
            ref = ref.rjust(27, "0")
            return self._prepare_structured_remittance_element(ref, prtry="QRR")
        elif reference_type in ("fi", "no", "se"):
            return self._prepare_structured_remittance_element(ref, cd="SCOR")
        return super()._prepare_remittance_reference_element(ref, reference_type)

    def _prepare_remittance_element(
        self, payment_method_code, payment
    ) -> etree._Element | None:

        if self.env.context.get("l10n_be_hr_payroll_sepa_salary_payment"):
            RmtInf = super()._prepare_remittance_element(payment_method_code, payment)
            if RmtInf is None:
                RmtInf = etree.Element("RmtInf")
            if (Ustrd := RmtInf.find("Ustrd")) is None:
                Ustrd = etree.SubElement(RmtInf, "Ustrd")
            memo = normalize_communication(payment["memo"] or "")
            Ustrd.text = f"/A/ {memo}"
            return RmtInf
        return super()._prepare_remittance_element(payment_method_code, payment)

    def _get_bic_tag(self, payment_method_code):
        force_iso_20022_pain_09 = bool(
            self.env.registry.settings.get(
                self.env, "account_iso20022.force_iso_20022_pain_09", False
            )
        )
        use_pain_09 = (
            payment_method_code == "sepa_ct"
            and self.sepa_pain_version == "pain.001.001.09"
        ) or (payment_method_code == "iso20022" and force_iso_20022_pain_09)
        if use_pain_09:
            return "BICFI"
        return super()._get_bic_tag(payment_method_code)

    def _get_regex_for_bic_code(self, payment_method_code):
        force_iso_20022_pain_09 = bool(
            self.env.registry.settings.get(
                self.env, "account_iso20022.force_iso_20022_pain_09", False
            )
        )
        use_pain_09 = (
            payment_method_code == "sepa_ct"
            and self.sepa_pain_version == "pain.001.001.09"
        ) or (payment_method_code == "iso20022" and force_iso_20022_pain_09)
        if use_pain_09:
            return "[A-Z0-9]{4,4}[A-Z]{2,2}[A-Z0-9]{2,2}([A-Z0-9]{3,3}){0,1}"
        return super()._get_regex_for_bic_code(payment_method_code)

    def _get_SvcLvlText(self, payment_method_code) -> str | None:
        if payment_method_code == "sepa_ct":
            return "SEPA"
        return super()._get_SvcLvlText(payment_method_code)
