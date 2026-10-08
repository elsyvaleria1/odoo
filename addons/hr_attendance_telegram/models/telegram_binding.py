from odoo import api, models


class TelegramBinding(models.Model):
    _inherit = "telegram.binding"

    @api.model
    def _is_present(self, partner) -> bool:
        # an employee with no Odoo user still records attendance through the
        # bot: they are there while an employee of theirs is active
        # an employee keeps being found through their user once it is
        # archived: only the employee's own active flag decides
        return super()._is_present(partner) or bool(
            self.env["hr.employee"]
            .sudo()
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
