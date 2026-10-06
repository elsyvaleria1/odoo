from odoo import fields, models


class SignTemplate(models.Model):
    _name = "sign.template"
    _inherit = ["sign.template", "mixin.documents.unlink"]

    folder_id = fields.Many2one(
        comodel_name="document.document",
        string="Signed Document Folder",
        domain="[('type', '=', 'folder'), ('shortcut_document_id', '=', False)]",
        context=lambda env: {
            "default_type": "folder",
            "default_folder_id": env.ref("document_sign.document_sign_folder").id,
        },
    )
    documents_tag_ids = fields.Many2many(
        comodel_name="document.tag",
        string="Signed Document Tags",
    )
