from odoo import api, models

from odoo.addons.account.tools import (
    is_valid_structured_reference_for_country,
    normalize_structured_reference,
)


class ResPartnerBankAccount(models.Model):
    _inherit = "res.partner.bank.account"

    def _prepare_qr_payload(
        self,
        qr_method,
        amount,
        currency,
        debtor_partner,
        free_communication,
        structured_communication,
    ):
        if qr_method == "sct_qr":
            if is_valid_structured_reference_for_country(
                structured_communication, (self.sanitized_acc_number or "")[:2]
            ):
                structured_communication = normalize_structured_reference(
                    structured_communication
                )
                comment = ""
            else:
                structured_communication = ""
                comment = free_communication or ""

            return [
                "BCD",
                "002",
                "1",
                "SCT",
                self.bank_bic or "",
                (self.acc_holder_name or self.partner_id.name)[:71],
                self.sanitized_acc_number,
                currency.name + str(amount),
                "",
                structured_communication,
                comment[:141],
                "",
            ]
        return super()._prepare_qr_payload(
            qr_method,
            amount,
            currency,
            debtor_partner,
            free_communication,
            structured_communication,
        )

    def _prepare_qr_rendering_params(
        self,
        qr_method,
        amount,
        currency,
        debtor_partner,
        free_communication,
        structured_communication,
    ):
        if qr_method == "sct_qr":
            return {
                "barcode_type": "QR",
                "quiet": 0,
                "width": 128,
                "height": 128,
                "humanreadable": 1,
                "value": "\n".join(
                    self._prepare_qr_payload(
                        qr_method,
                        amount,
                        currency,
                        debtor_partner,
                        free_communication,
                        structured_communication,
                    )
                ),
            }
        return super()._prepare_qr_rendering_params(
            qr_method,
            amount,
            currency,
            debtor_partner,
            free_communication,
            structured_communication,
        )

    def _get_error_messages_for_qr(self, qr_method, debtor_partner, currency):
        if qr_method == "sct_qr":
            sepa_country_codes = self.env.ref("base.sepa_zone").country_ids.mapped(
                "code"
            )
            non_iban_codes = {
                "AX",
                "NC",
                "YT",
                "TF",
                "BL",
                "RE",
                "MF",
                "GP",
                "PM",
                "PF",
                "GF",
                "MQ",
                "JE",
                "GG",
                "IM",
            }
            sepa_iban_codes = {
                code for code in sepa_country_codes if code not in non_iban_codes
            }
            error_messages = []
            if currency.name != "EUR":
                error_messages.append(
                    self.env._(
                        "Can't generate a SEPA QR Code with the %s currency.",
                        currency.name,
                    )
                )
            if self.acc_type != "iban":
                error_messages.append(
                    self.env._(
                        "Can't generate a SEPA QR code if the account type isn't IBAN."
                    )
                )
            if not (
                self.sanitized_acc_number
                and self.sanitized_acc_number[:2] in sepa_iban_codes
            ):
                error_messages.append(
                    self.env._("Can't generate a SEPA QR code with a non SEPA iban.")
                )
            if len(error_messages) > 0:
                return "\r\n".join(error_messages)
            return None
        return super()._get_error_messages_for_qr(qr_method, debtor_partner, currency)

    def _check_for_qr_code_errors(
        self,
        qr_method,
        amount,
        currency,
        debtor_partner,
        free_communication,
        structured_communication,
    ):
        if qr_method == "sct_qr":
            if not self.acc_holder_name and not self.partner_id.name:
                return self.env._(
                    "The account receiving the payment must have an account holder name or partner name set."
                )

        return super()._check_for_qr_code_errors(
            qr_method,
            amount,
            currency,
            debtor_partner,
            free_communication,
            structured_communication,
        )

    @api.model
    def _get_available_qr_methods(self):
        rslt = super()._get_available_qr_methods()
        rslt.append(("sct_qr", self.env._("SEPA Credit Transfer QR"), 20))
        return rslt
