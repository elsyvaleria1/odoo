from odoo import api, models

from odoo.addons.telegram.tools.authority import counting_presence


class TelegramBinding(models.Model):
    _inherit = "telegram.binding"

    @api.model
    def _is_present(self, partner) -> bool:
        return super()._is_present(partner) or bool(
            counting_presence(self.env["hr.employee"])
            .with_context(active_test=False)
            .search_count(
                [
                    "|",
                    ("partner_id", "=", partner.id),
                    ("user_id.partner_id", "=", partner.id),
                    ("active", "=", True),
                ]
            )
        )
