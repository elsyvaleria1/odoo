from odoo.http import request

from odoo.addons.auth_signup.controllers.main import AuthSignupHome


class AddPolicyData(AuthSignupHome):
    def get_auth_signup_config(self):
        d = super().get_auth_signup_config()
        d["password_minimum_length"] = request.env.registry.settings.get(
            request.env, "auth_password_policy.minlength", False
        )
        return d
