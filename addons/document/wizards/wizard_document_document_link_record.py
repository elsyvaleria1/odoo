from odoo import api, fields, models
from odoo.exceptions import UserError


class WizardDocumentDocumentLinkRecord(models.TransientModel):
    _name = "wizard.document.document.link.record"
    _description = "Documents Link to Record"

    def _domain_model_id(self) -> list:
        thread = self.env.registry["mixin.mail.thread"]
        models = [
            name
            for name, model_class in self.env.registry.items()
            if name != "document.document"
            and not model_class._abstract
            and issubclass(model_class, thread)
            and self.env[name].has_access("write")
        ]
        return [("model", "in", models), ("is_mail_thread", "=", True)]

    @api.model
    def _selection_target_model(self) -> list:
        return [
            (model.model, model.name)
            for model in self.env["ir.model"]
            .sudo()
            .search(
                [("model", "!=", "document.document"), ("is_mail_thread", "=", True)]
            )
        ]

    document_ids = fields.Many2many(
        comodel_name="document.document",
        string="Documents",
        readonly=True,
    )
    model_id = fields.Many2one(
        comodel_name="ir.model",
        domain=_domain_model_id,
    )
    is_readonly_model = fields.Boolean(
        string="is_readonly_model",
        default=True,
    )
    resource_ref = fields.Reference(
        selection="_selection_target_model",
        string="Record",
    )

    def link_to(self) -> None:
        self.check_singleton()
        if not self.resource_ref:
            raise UserError(self.env._("Please select a record to link to."))
        self.resource_ref.check_access("write")
        if linked := self.document_ids.filtered("res_model"):
            raise UserError(
                self.env._(
                    "Already linked Documents: %s", ", ".join(linked.mapped("name"))
                )
            )
        self.document_ids.with_company(self.env.company).write(
            {
                "res_model": self.resource_ref._name,
                "res_id": self.resource_ref.id,
                "is_editable_attachment": True,
            }
        )
