from markupsafe import Markup

from odoo import Command, api, fields, models
from odoo.exceptions import UserError

from .wizard_account_peppol_config_update_contact_service import (
    SELF_BILLING_DOCUMENT_TYPES,
)
from odoo.addons.account_edi_proxy_client.models.account_edi_proxy_user import (
    AccountEdiProxyError,
)


class WizardAccountPeppolConfigUpdateContact(models.TransientModel):
    _name = "wizard.account_peppol.config.update.contact"
    _description = "Peppol Configuration Wizard"

    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        required=True,
    )
    account_peppol_edi_user = fields.Many2one(
        related="company_id.account_peppol_config_id.account_peppol_edi_user"
    )
    account_peppol_edi_identification = fields.Char(
        related="account_peppol_edi_user.edi_identification"
    )
    account_peppol_proxy_state = fields.Selection(
        related="company_id.account_peppol_config_id.account_peppol_proxy_state",
        readonly=False,
    )
    account_peppol_contact_email = fields.Char(
        default=lambda self: (
            self.env.company.account_peppol_config_id.account_peppol_contact_email
        ),
        required=True,
    )
    account_peppol_migration_key = fields.Char(
        related="company_id.account_peppol_migration_key",
        readonly=False,
    )
    peppol_activate_self_billing = fields.Boolean(
        string="Activate self-billing",
        compute="_compute_peppol_activate_self_billing",
        inverse="_inverse_peppol_activate_self_billing",
        help="If activated, you will be able to send and receive self-billed invoices via Peppol."
        "You can still disable reception by disabling the self-billing document types below.",
    )
    peppol_self_billing_reception_journal_id = fields.Many2one(
        related="company_id.account_peppol_config_id.peppol_self_billing_reception_journal_id",
        readonly=False,
    )

    service_json = fields.Json(
        compute="_compute_service_json",
        store=True,
        readonly=False,
        help="JSON representation of peppol services as retrieved from the peppol server.",
    )
    service_info = fields.Html(compute="_compute_service_info")
    service_ids = fields.One2many(
        comodel_name="wizard.account_peppol.config.update.contact.service",
        inverse_name="wizard_id",
        compute="_compute_service_ids",
        store=True,
        readonly=False,
    )

    @api.depends("account_peppol_edi_user", "account_peppol_proxy_state")
    def _compute_service_json(self) -> None:
        for wizard in self:
            if wizard.account_peppol_proxy_state == "receiver":
                try:
                    wizard.service_json = (
                        wizard.account_peppol_edi_user._peppol_get_services().get(
                            "services"
                        )
                    )
                except AccountEdiProxyError, UserError:
                    wizard.service_json = False
            else:
                wizard.service_json = False

    @api.depends("account_peppol_proxy_state")
    def _compute_service_info(self) -> None:
        for wizard in self:
            message = ""
            if wizard.account_peppol_proxy_state == "receiver":
                supported_doctypes = self.env[
                    "res.company"
                ]._peppol_supported_document_types()
                if non_configurable := [
                    identifier
                    for identifier in (wizard.service_json or {})
                    if identifier not in supported_doctypes
                ]:
                    message = Markup("%s<ul>%s</ul>") % (
                        self.env._(
                            "The following services are listed on your participant but cannot be configured here. "
                            "If you wish to configure them differently, please contact support."
                        ),
                        Markup().join(
                            Markup("<li>%s</li>")
                            % (wizard.service_json[identifier]["document_name"])
                            for identifier in non_configurable
                        ),
                    )
            wizard.service_info = message

    @api.depends("account_peppol_proxy_state", "service_json")
    def _compute_service_ids(self) -> None:
        supported_doctypes = self.env["res.company"]._peppol_supported_document_types()
        for wizard in self:
            if wizard.account_peppol_proxy_state == "receiver" and wizard.service_json:
                wizard.service_ids = [
                    Command.create(
                        {
                            "document_identifier": identifier,
                            "document_name": document_name,
                            "enabled": identifier in (wizard.service_json or {}),
                            "wizard_id": wizard.id,
                        }
                    )
                    for identifier, document_name in supported_doctypes.items()
                ]
            else:
                wizard.service_ids = None

    @api.depends(
        "company_id.account_peppol_config_id.peppol_activate_self_billing_sending"
    )
    def _compute_peppol_activate_self_billing(self) -> None:
        for wizard in self:
            wizard.peppol_activate_self_billing = wizard.company_id.account_peppol_config_id.peppol_activate_self_billing_sending

    @api.onchange("peppol_activate_self_billing")
    def _inverse_peppol_activate_self_billing(self) -> None:
        for wizard in self:
            wizard.company_id.account_peppol_config_id.peppol_activate_self_billing_sending = wizard.peppol_activate_self_billing

            self_billing_services = wizard.service_ids.filtered(
                lambda s: s.document_identifier in SELF_BILLING_DOCUMENT_TYPES.values()
            )
            self_billing_services.write(
                {"enabled": wizard.peppol_activate_self_billing}
            )

    def button_sync_form_with_peppol_proxy(self) -> bool:
        self.check_singleton()

        if (
            self.account_peppol_contact_email
            != self.company_id.account_peppol_config_id.account_peppol_contact_email
        ):
            self.company_id.account_peppol_config_id.account_peppol_contact_email = (
                self.account_peppol_contact_email
            )
            params = {
                "update_data": {
                    "peppol_contact_email": self.account_peppol_contact_email,
                }
            }
            self.account_peppol_edi_user._call_peppol_proxy(
                endpoint="/api/peppol/1/update_user",
                params=params,
            )

        return True

    def button_peppol_unregister(self) -> bool:
        self.check_singleton()

        if self.account_peppol_edi_user:
            self.account_peppol_edi_user._peppol_deregister_participant()
        else:
            self.company_id._reset_peppol_configuration()
        return True

    def button_peppol_reset_to_sender(self) -> bool:
        self.check_singleton()
        if self.account_peppol_edi_user:
            self.account_peppol_edi_user._peppol_deregister_participant_to_sender()
        return True

    def button_peppol_register_sender_as_receiver(self):
        self.check_singleton()
        if self.account_peppol_edi_user:
            self.account_peppol_edi_user._peppol_register_sender_as_receiver()
            self.account_peppol_edi_user._peppol_get_participant_status()
            if self.account_peppol_proxy_state == "smp_registration":
                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": self.env._(
                            "Registered to receive documents via Peppol."
                        ),
                        "type": "success",
                        "message": self.env._(
                            "Your registration on Peppol network should be activated within a day. The updated status will be visible in Settings."
                        ),
                        "next": {"type": "ir.actions.act_window_close"},
                    },
                }
        return True
