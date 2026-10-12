from odoo import api, fields, models
from odoo.exceptions import UserError


class AiToolModelAccess(models.Model):
    _name = "ai.tool.model.access"
    _description = "Model an AI Tool May Create or Update"
    _order = "model_id"

    model_id = fields.Many2one(
        comodel_name="ir.model",
        index=True,
        required=True,
        ondelete="cascade",
    )
    model_name = fields.Char(related="model_id.model")
    allow_create = fields.Boolean(default=True)
    allow_write = fields.Boolean(default=False)
    active = fields.Boolean(default=True)

    _model_unique = models.Constraint(
        "UNIQUE(model_id)", "This model is already in the list."
    )

    @api.model
    def _check(self, model_name: str, operation: str) -> None:
        entry = self.sudo().search([("model_name", "=", model_name)], limit=1)
        if entry and entry[f"allow_{operation}"]:
            return
        raise UserError(
            self.env._(
                "An AI tool may not %(operation)s %(model)s records.",
                operation=self.env._("create")
                if operation == "create"
                else self.env._("update"),
                model=model_name,
            )
        )
