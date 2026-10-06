from odoo import fields, models


class DocumentsAccountFolderSetting(models.Model):
    _name = "document.account.folder.setting"
    _description = "Journal and Folder settings"

    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        required=True,
        ondelete="cascade",
    )
    company_account_folder_id = fields.Many2one(related="company_id.account_folder_id")
    journal_id = fields.Many2one(
        comodel_name="account.journal",
        required=True,
        ondelete="cascade",
    )
    folder_id = fields.Many2one(
        comodel_name="document.document",
        required=True,
        domain=lambda self: [
            ("type", "=", "folder"),
            ("shortcut_document_id", "=", False),
            ("id", "child_of", self.env.company.account_folder_id.ids),
            "|",
            ("company_id", "=", False),
            ("company_id", "=", self.env.company.id),
        ],
    )
    tag_ids = fields.Many2many(
        comodel_name="document.tag",
        string="Tags",
    )

    _journal_unique = models.Constraint(
        "unique (journal_id)",
        "A setting already exists for this journal",
    )
