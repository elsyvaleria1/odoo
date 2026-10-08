from odoo import models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    def write(self, vals):
        result = super().write(vals)
        if "active" in vals and not vals["active"]:
            # an employee who left keeps no Telegram account acting as them
            self.env["telegram.binding"]._revoke_for_departed(self._telegram_partners())
        return result

    def unlink(self):
        partners = self._telegram_partners()
        result = super().unlink()
        self.env["telegram.binding"]._revoke_for_departed(partners.exists())
        return result

    def _telegram_partners(self):
        """The contacts a Telegram account of these employees is bound to."""
        return self.partner_id | self.user_id.partner_id
