from odoo import api, models
from odoo.exceptions import AccessDenied
from odoo.tools import SQL


class ResUsers(models.Model):
    _inherit = "res.users"

    def _login(self, credential, user_agent_env):
        login = credential["login"]
        canonical = login.lower().strip()
        if canonical != login and not self._login_taken(SQL("login = %s", login)):
            credential["login"] = canonical
        return super()._login(credential, user_agent_env=user_agent_env)

    @api.model
    def _login_unknown(self, credential, user_agent_env):
        login, password = credential["login"], credential.get("password")
        taken = self._login_taken(SQL("lower(login) = lower(%s)", login))
        if credential["type"] == "password" and password and not taken:
            Ldap = self.env["res.company.ldap"].sudo()
            for conf in Ldap._get_ldap_dicts():
                if entry := Ldap._authenticate(conf, login, password):
                    return {
                        "uid": Ldap._get_or_create_user(conf, login, entry),
                        "auth_method": "ldap",
                        "mfa": "default",
                    }
        return super()._login_unknown(credential, user_agent_env)

    @api.model
    def _login_taken(self, condition):
        self.flush_model(["login"])
        self.env.cr.execute(SQL("SELECT 1 FROM res_users WHERE %s LIMIT 1", condition))
        return self.env.cr.fetchone() is not None

    def _check_credentials(self, credential, env):
        try:
            return super()._check_credentials(credential, env)
        except AccessDenied:
            if not (credential["type"] == "password" and credential.get("password")):
                raise
            passwd_allowed = self._password_allowed(env)
            if passwd_allowed and self.active:
                Ldap = self.env["res.company.ldap"]
                for conf in Ldap._get_ldap_dicts():
                    if Ldap._authenticate(conf, self.login, credential["password"]):
                        return {
                            "uid": self.id,
                            "auth_method": "ldap",
                            "mfa": "default",
                        }
            raise

    @api.model
    def change_password(self, old_passwd, new_passwd):
        if new_passwd:
            Ldap = self.env["res.company.ldap"]
            for conf in Ldap._get_ldap_dicts():
                changed = Ldap._change_password(
                    conf, self.env.user.login, old_passwd, new_passwd
                )
                if changed:
                    self.env.user._clear_password()
                    return True
        return super().change_password(old_passwd, new_passwd)
