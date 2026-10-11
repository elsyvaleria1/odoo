from werkzeug.exceptions import Forbidden

from odoo import http
from odoo.exceptions import AccessError
from odoo.http import request
from odoo.tools import (
    consume_session_state,
    issue_session_state,
    register_signed_scope,
)

from odoo.addons.sale_shopee import utils

_AUTHORIZATION_STATE_MAX_AGE_SECONDS = 1800

AUTHORIZATION_STATE_SCOPE = register_signed_scope(
    "sale_shopee.authorization_state",
    purpose="the state Shopee's authorization redirect carries back, in its path, "
    "to the account and company it was started for, in the session and for the "
    "user that started it",
    lifetime=f"its expiry: the return refuses a state older than "
    f"{_AUTHORIZATION_STATE_MAX_AGE_SECONDS} seconds, or one already consumed",
)


def issue_authorization_state(account):
    return issue_session_state(
        account.env,
        AUTHORIZATION_STATE_SCOPE,
        request.session,
        {"account_id": account.id, "company_id": account.env.company.id},
        max_age_seconds=_AUTHORIZATION_STATE_MAX_AGE_SECONDS,
    )


class ShopeeController(http.Controller):
    @http.route(
        "/shopee/return_from_authorization/<string:state>",
        type="http",
        methods=["GET"],
        auth="user",
    )
    def shopee_return_from_authorization(
        self,
        state,
        code=False,
        shop_id=False,
        main_account_id=False,
    ):
        if not request.env.user.has_group("sale.group_sale_manager"):
            raise AccessError(request.env._("You are not allowed to access this page."))

        claims = consume_session_state(
            request.env, AUTHORIZATION_STATE_SCOPE, request.session, state
        )
        account = request.env["shopee.account"]
        if claims is not None:
            account = account.browse(claims["account_id"]).exists()
        if not account:
            raise Forbidden(
                request.env._(
                    "This Shopee authorization link is invalid, has expired or was "
                    "already used. Start the authorization again from the account."
                )
            )
        account_id, company_id = account.id, claims["company_id"]

        shop_identifiers = [shop_id]
        shop_vals = {}
        if main_account_id:
            temp_shop = request.env["shopee.shop"].create(
                {
                    "name": "temporary shop",
                    "shop_identifier": 1,
                    "account_id": account_id,
                }
            )
            shop_identifiers = utils.with_context(
                authorization_code=code
            ).request_access_token(temp_shop, main_account_id=main_account_id)
            shop_vals.update(
                {
                    "access_token": temp_shop.access_token,
                    "refresh_token": temp_shop.refresh_token,
                    "access_token_expiration_date": temp_shop.access_token_expiration_date,
                }
            )
            temp_shop.unlink()

        shop = request.env["shopee.shop"]
        for identifier in shop_identifiers:
            shop = shop.with_context(authorization_code=code).create_or_update_shop(
                company_id, account.id, identifier, shop_vals
            )

        redirect_url = (
            f"/odoo/action-sale_shopee.action_shopee_account_list/{account.id}"
        )
        if shop_id and shop:
            redirect_url = (
                f"{redirect_url}/action-sale_shopee.action_shopee_shop_list/{shop.id}"
            )

        return request.redirect(redirect_url, local=False)
