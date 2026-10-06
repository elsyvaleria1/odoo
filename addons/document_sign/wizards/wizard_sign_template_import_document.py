from odoo import fields, models
from odoo.exceptions import UserError


class WizardSignTemplateImportDocument(models.TransientModel):
    _name = "wizard.sign.template.import.document"
    _description = "Wizard to select PDF documents from the Documents app to sign"

    selected_document = fields.Many2one(
        comodel_name="document.document",
        required=True,
        domain="[('mimetype', '=', 'application/pdf')]",
    )

    def action_import_and_create(self):
        self.check_singleton()

        if not self.selected_document:
            raise UserError(self.env._("No document selected to import and sign."))

        return self.selected_document.document_sign_create_sign_template()
