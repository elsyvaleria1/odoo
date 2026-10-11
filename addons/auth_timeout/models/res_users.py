from odoo import models


class ResUsers(models.Model):
    _inherit = "res.users"

    def _get_auth_methods(self):
        self.check_singleton()
        auth_methods = []
        if self.auth_passkey_key_ids:
            auth_methods.append("webauthn")
        if mfa_type := self._get_mfa_type():
            auth_methods.append(mfa_type)
        auth_methods.append("password")
        return auth_methods

    def _get_lock_timeouts(self):
        self.check_singleton()
        return self.env["res.groups"].browse(self._get_group_ids())._get_lock_timeouts()

    def _get_lock_timeout_inactivity(self):
        timeouts = self._get_lock_timeouts()
        return (
            timeouts.get("lock_timeout_inactivity")[0][0]
            if timeouts.get("lock_timeout_inactivity")
            else None
        )
