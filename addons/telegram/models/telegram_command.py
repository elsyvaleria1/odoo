import logging

from odoo import api, fields, models, tools

from ..tools.authority import keeping, operating

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

    company_ids = fields.Many2many(
        comodel_name="res.company",
        relation="telegram_command_res_company_rel",
        string="Available In",
        help="The companies this command acts for: a person offered it only "
        "where they belong to one of them, and choosing among those alone. "
        "Empty, it acts for every company a bot serves.",
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
        self.env.registry.clear_cache()
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("name"):
            vals["name"] = self._normalize(vals["name"])
        if vals.keys() & {"name", "company_ids"}:
            self.env.registry.clear_cache()
        result = super().write(vals)
        if "company_ids" in vals:
            operating(self.env["telegram.chat"]).search(
                [("chat_type", "=", "private"), ("account_id", "!=", False)]
            )._sync_command_menu()
        return result

    def unlink(self):
        self.env.registry.clear_cache()
        return super().unlink()

    @api.model
    @tools.ormcache()
    def _get_company_availability(self) -> dict:
        commands = keeping(self).search([("company_ids", "!=", False)])
        return {
            command.name: frozenset(command.company_ids.ids) for command in commands
        }
