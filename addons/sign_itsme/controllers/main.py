from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from odoo import http
from odoo.http import request
from odoo.libs.web import urljoin as url_join
from odoo.tools import iap

from odoo.addons.sign.controllers.main import Sign as SignController

if TYPE_CHECKING:
    from odoo.addons.sign.models.sign_request_item import SignRequestItem

IAP_DEFAULT_DOMAIN = "https://itsme.api.odoo.com"
IAP_SERVICE_NAME = "itsme_proxy"


class SignItsme(SignController):
    def _prepare_document_rendering_data(self, sign_request_id, token, **post):
        res = super()._prepare_document_rendering_data(sign_request_id, token, **post)
        if res.get("rendering_context"):
            res["rendering_context"]["show_thank_you_dialog"] = bool(
                res["rendering_context"]["show_thank_you_dialog"]
            ) or bool(post.get("show_thank_you_dialog"))
            res["rendering_context"]["error_message"] = post.get("error_message")
        return res

    def _acquire_auth_method_result(
        self, request_item_sudo: SignRequestItem, **kwargs
    ) -> dict[str, Any]:
        if request_item_sudo.role_id.auth_method == "itsme":
            referrer = request.httprequest.referrer
            if not referrer:
                return {"success": False}
            account = (
                request.env["iap.account"].sudo().acquire_account(IAP_SERVICE_NAME)
            )
            if not account.sudo().account_token:
                return {
                    "success": False,
                    "message": request.env._("itsme® IAP service could not be found."),
                }
            parsed_referrer = urlsplit(referrer)
            endpoint = request.env.registry.settings.get(
                request.env, "sign_itsme.iap_endpoint", IAP_DEFAULT_DOMAIN
            )
            itsme_credits = (
                request.env["iap.account"].sudo().get_credits(IAP_SERVICE_NAME)
            )
            if itsme_credits < 1:
                request_item_sudo.signed_without_extra_auth = True
                return {"success": True}
            return iap.jsonrpc(
                url_join(endpoint, "/itsme/v1/sign_identity_request"),
                params={
                    "account_token": account.sudo().account_token,
                    "itsme_state": "%s.%s"
                    % (
                        request_item_sudo.sign_request_id.id,
                        request_item_sudo.access_token,
                    ),
                    "referrer": parsed_referrer._replace(
                        path="", query="", fragment=""
                    ).geturl(),
                },
                env=request.env,
            )
        else:
            return super()._acquire_auth_method_result(request_item_sudo, **kwargs)

    @http.route(["/itsme/has_itsme_credits"], type="jsonrpc", auth="public")
    def has_itsme_credits(self) -> bool:
        return request.env["iap.account"].sudo().get_credits(IAP_SERVICE_NAME) >= 1

    def get_iap_credit_warnings(self):
        warnings = super().get_iap_credit_warnings()
        roles_with_itsme = (
            request.env["sign.item.role"].sudo().search([("auth_method", "=", "itsme")])
        )
        if roles_with_itsme:
            if self.has_warning_for_service(roles_with_itsme, IAP_SERVICE_NAME):
                warnings.append(
                    {
                        "auth_method": "itsme®",
                        "iap_url": request.env["iap.account"]
                        .sudo()
                        .get_credits_url(service_name=IAP_SERVICE_NAME),
                    }
                )
        return warnings
