from datetime import datetime

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError

from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment.const import REPORT_REASONS_MAPPING
from odoo.addons.payment_sepa_direct_debit import const


class PaymentProvider(models.Model):
    _inherit = "payment.provider"

    custom_mode = fields.Selection(
        selection_add=[("sepa_direct_debit", "SEPA Direct Debit")]
    )

    def _compute_feature_support_fields(self) -> None:
        super()._compute_feature_support_fields()
        self.filtered(lambda p: p.custom_mode == "sepa_direct_debit").update(
            {
                "support_tokenization": True,
            }
        )

    def _get_supported_currencies(self):
        supported_currencies = super()._get_supported_currencies()
        if self.custom_mode == "sepa_direct_debit":
            supported_currencies = supported_currencies.filtered(
                lambda c: c.name == "EUR"
            )
        return supported_currencies

    @api.constrains("state", "journal_id")
    def _check_journal_iban_is_valid(self) -> None:
        for provider in self.filtered(
            lambda p: p.custom_mode == "sepa_direct_debit" and p.state == "enabled"
        ):
            if provider.journal_id.bank_account_id.acc_type != "iban":
                raise ValidationError(
                    self.env._("The bank account of the journal is not a valid IBAN.")
                )

    @api.constrains("state", "company_id")
    def _check_has_creditor_identifier(self) -> None:
        for provider in self.filtered(
            lambda p: p.custom_mode == "sepa_direct_debit" and p.state == "enabled"
        ):
            if not provider.company_id.sdd_creditor_identifier:
                raise ValidationError(
                    self.env._(
                        "Your company must have a creditor identifier in order to issue a SEPA Direct "
                        "Debit payment request. It can be set in Accounting settings."
                    )
                )

    @api.constrains("available_country_ids")
    def _check_country_in_sepa_zone(self) -> None:
        sepa_countries = self.env.ref("base.sepa_zone").country_ids
        for provider in self.filtered(lambda p: p.custom_mode == "sepa_direct_debit"):
            non_sepa_countries = provider.available_country_ids - sepa_countries
            if non_sepa_countries:
                raise ValidationError(
                    self.env._(
                        "Restricted to countries in the SEPA zone. Forbidden countries: %s",
                        ", ".join(non_sepa_countries.mapped("name")),
                    )
                )

    def _get_default_payment_method_codes(self):
        self.check_singleton()
        if self.custom_mode != "sepa_direct_debit":
            return super()._get_default_payment_method_codes()
        return const.DEFAULT_PAYMENT_METHOD_CODES

    @api.model
    def _get_compatible_providers(
        self, *args, is_validation=False, report=None, **kwargs
    ):
        providers = super()._get_compatible_providers(
            *args, is_validation=is_validation, report=report, **kwargs
        )

        if is_validation:
            unfiltered_providers = providers
            providers = providers.filtered(
                lambda p: p.code != "custom" or p.custom_mode != "sepa_direct_debit"
            )
            payment_utils.add_to_report(
                report,
                unfiltered_providers - providers,
                available=False,
                reason=REPORT_REASONS_MAPPING["validation_not_supported"],
            )

        return providers

    def _is_tokenization_required(self, **kwargs) -> bool:
        res = super()._is_tokenization_required(**kwargs)
        if len(self) != 1 or self.custom_mode != "sepa_direct_debit":
            return res

        return True

    def _sdd_find_or_create_mandate(self, partner_id, iban):
        self.check_singleton()

        commercial_partner_id = (
            self.env["res.partner"].browse(partner_id).commercial_partner_id.id
        )
        partner_bank = self._sdd_find_or_create_partner_bank(partner_id, iban)
        mandate = self.env["sdd.mandate"].search(
            [
                ("state", "not in", ["closed", "revoked"]),
                ("start_date", "<=", datetime.now()),
                "|",
                ("end_date", ">=", datetime.now()),
                ("end_date", "=", None),
                ("partner_id", "=", commercial_partner_id),
                ("bank_account_id", "=", partner_bank.id),
                ("company_id", "=", self.company_id.id),
            ],
            limit=1,
        )
        if not mandate:
            mandate = self.env["sdd.mandate"].create(
                {
                    "partner_id": commercial_partner_id,
                    "bank_account_id": partner_bank.id,
                    "start_date": datetime.now(),
                    "state": "draft",
                    "company_id": self.company_id.id,
                }
            )
        return mandate

    def _sdd_find_or_create_partner_bank(self, partner_id, iban):
        self.check_singleton()

        ResPartnerBankAccount = self.env["res.partner.bank.account"]
        commercial_partner_id = (
            self.env["res.partner"].browse(partner_id).commercial_partner_id.id
        )
        partner_bank = ResPartnerBankAccount.search(
            [
                ("sanitized_acc_number", "=", iban),
                ("partner_id", "child_of", commercial_partner_id),
            ]
        )
        if not partner_bank:
            partner_bank = ResPartnerBankAccount.create(
                {
                    "acc_number": iban,
                    "partner_id": partner_id,
                    "company_id": self.company_id.id,
                }
            )
        return partner_bank

    def _sdd_create_token_for_mandate(self, partner, mandate):
        if mandate.partner_id != partner.commercial_partner_id:
            raise AccessError(
                self.env._("The mandate owner and customer do not match.")
            )

        return self.env["payment.token"].create(
            {
                "provider_id": self.id,
                "payment_method_id": self.payment_method_ids[:1].id,
                "payment_details": mandate.bank_account_id.acc_number,
                "partner_id": partner.id,
                "provider_ref": mandate.name,
                "sdd_mandate_id": mandate.id,
            }
        )

    def _get_code(self):
        res = super()._get_code()
        if self.code == "custom" and self.custom_mode == "sepa_direct_debit":
            return self.custom_mode
        return res
