from lxml import etree

from odoo import models


class AccountJournal(models.Model):
    _inherit = "account.journal"

    def _prepare_initiating_party_element(self, payment_method_code) -> etree._Element:
        if (
            payment_method_code == "sepa_ct"
            and self.sepa_pain_version == "pain.001.001.03.austrian.004"
        ):
            InitgPty = etree.Element("InitgPty")
            InitgPty.extend(
                self._prepare_company_identification_elements(
                    postal_address=False,
                    issr=False,
                    payment_method_code=payment_method_code,
                )
            )
            return InitgPty
        return super()._prepare_initiating_party_element(payment_method_code)
