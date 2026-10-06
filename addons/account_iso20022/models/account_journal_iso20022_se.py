from lxml import etree

from odoo import models


class AccountJournal(models.Model):
    _inherit = "account.journal"

    def _get_SvcLvlText(self, payment_method_code) -> str | None:
        if payment_method_code == "iso20022_se":
            return "NURG"
        return super()._get_SvcLvlText(payment_method_code)

    def _prepare_company_identification_elements(
        self,
        payment_method_code,
        postal_address=True,
        nm=True,
        issr=True,
        schme_nm=False,
    ) -> list[etree._Element]:
        result = super()._prepare_company_identification_elements(
            postal_address=postal_address,
            issr=issr,
            schme_nm=schme_nm,
            payment_method_code=payment_method_code,
        )
        if payment_method_code == "iso20022_se":
            if not nm:
                result = list(filter(lambda x: x.tag != "Nm", result))
        return result

    def _prepare_initiating_party_element(self, payment_method_code) -> etree._Element:
        if payment_method_code == "iso20022_se":
            InitgPty = etree.Element("InitgPty")
            InitgPty.extend(
                self._prepare_company_identification_elements(
                    postal_address=False,
                    issr=False,
                    nm=False,
                    schme_nm="BANK",
                    payment_method_code=payment_method_code,
                )
            )
            return InitgPty
        return super()._prepare_initiating_party_element(payment_method_code)

    def _prepare_debtor_element(self, payment_method_code) -> etree._Element:
        if payment_method_code == "iso20022_se":
            Dbtr = etree.Element("Dbtr")
            Dbtr.extend(
                self._prepare_company_identification_elements(
                    postal_address=True,
                    issr=False,
                    schme_nm="CUST",
                    payment_method_code=payment_method_code,
                )
            )
            return Dbtr
        return super()._prepare_debtor_element(payment_method_code)

    def get_postal_address(self, partner_id, payment_method_code):
        if payment_method_code == "iso20022_se":
            pstl_addr_list = [
                address for address in partner_id._get_all_addr() if address["country"]
            ]
            if not pstl_addr_list:
                return None
            for addr_dict in pstl_addr_list:
                if addr_dict["contact_type"] == "employee":
                    return addr_dict
            return pstl_addr_list[0]
        return super().get_postal_address(partner_id, payment_method_code)

    def _prepare_credit_transfer_element(
        self, PmtInfId, payment, payment_method_code, include_charge_bearer=True
    ) -> etree._Element:
        # For Sweden, country is sufficient ; handle the case where the city was not specified beforehand
        CdtTrfTxInf = super()._prepare_credit_transfer_element(
            PmtInfId, payment, payment_method_code, include_charge_bearer
        )
        if payment_method_code == "iso20022_se":
            partner = self.env["res.partner"].sudo().browse(payment["partner_id"])
            if not partner.city and partner.country_id.code:
                Cdtr = CdtTrfTxInf.find("Cdtr")
                PstlAdr = Cdtr.find("PstlAdr")
                if PstlAdr is None:
                    Cdtr.append(
                        self._prepare_postal_address_element(
                            partner, payment_method_code
                        )
                    )
        return CdtTrfTxInf
