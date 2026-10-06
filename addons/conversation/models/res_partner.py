from odoo import models


class ResPartner(models.Model):
    _inherit = "res.partner"

    def _internal_user(self):
        if not self:
            return self.env["res.users"]
        self.check_singleton()
        return self.sudo().user_ids.filtered(lambda user: not user.share)[:1]

    def _is_colleague(self) -> bool:
        return bool(self._internal_user() or self.sudo().employee_ids)
