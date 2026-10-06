import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class TelegramCommand(models.Model):
    _name = "telegram.command"
    _description = "Telegram Command"
    _order = "name"

    name = fields.Char(
        string="Command",
        required=True,
        help="Command name including the '/' prefix (e.g., /start)",
    )

    _name_uniq = models.Constraint(
        "UNIQUE (name)",
        "This Telegram command already exists!",
    )

    @api.model
    def _normalize(self, name):
        name = (name or "").strip().split()[0].lower() if (name or "").strip() else ""
        if name and not name.startswith("/"):
            name = f"/{name}"
        return name

    @api.model
    def _for_name(self, name):
        normalized = self._normalize(name)
        existing = self.search([("name", "=", normalized)], limit=1)
        return existing or self.create({"name": normalized})

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name"):
                vals["name"] = self._normalize(vals["name"])
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("name"):
            vals["name"] = self._normalize(vals["name"])
        return super().write(vals)
