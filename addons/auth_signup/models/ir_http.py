from odoo import models
from odoo.http import request

SIGNUP_TOKEN_ROUTES = frozenset({"/web/signup", "/web/reset_password", "/mail/view"})


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    @classmethod
    def _pre_dispatch(cls, rule, args) -> None:
        super()._pre_dispatch(rule, args)

        args_in = request.httprequest.args
        if (login := args_in.get("auth_login")) is not None:
            request.session["auth_login"] = login
        token = args_in.get("auth_signup_token")
        if token is not None and rule.rule in SIGNUP_TOKEN_ROUTES:
            request.session["auth_signup_token"] = token
