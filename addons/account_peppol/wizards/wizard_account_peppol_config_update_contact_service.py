from odoo import fields, models

SELF_BILLING_DOCUMENT_TYPES = {
    "bis3_self_billing_invoice": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2::Invoice##urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:selfbilling:3.0::2.1",
    "bis3_self_billing_credit_note": "urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2::CreditNote##urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:selfbilling:3.0::2.1",
}


class WizardAccountPeppolConfigUpdateContactService(models.TransientModel):
    _name = "wizard.account_peppol.config.update.contact.service"
    _order = "document_name, id"
    _description = "Peppol Service"

    wizard_id = fields.Many2one(
        comodel_name="wizard.account_peppol.config.update.contact"
    )
    document_identifier = fields.Char()
    document_name = fields.Char()
    enabled = fields.Boolean()
