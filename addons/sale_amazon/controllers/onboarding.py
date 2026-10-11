import logging
import pprint

from odoo import http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request
from odoo.libs.json import loads as json_loads
from odoo.tools import (
    consume_session_state,
    issue_session_state,
    register_signed_scope,
)

from odoo.addons.sale_amazon import utils as amazon_utils

_logger = logging.getLogger(__name__)

_OAUTH_STATE_MAX_AGE_SECONDS = 1800

_ACCOUNTS_URL = "/odoo/action-sale_amazon.list_amazon_account_action"

OAUTH_SCOPE = register_signed_scope(
    "sale_amazon.oauth",
    purpose="the OAuth state that returns an Amazon authorization to the account "
    "and company it was started from, in the session and for the user that "
    "started it",
    lifetime=f"its expiry: the return refuses a state older than "
    f"{_OAUTH_STATE_MAX_AGE_SECONDS} seconds, or one already consumed",
)


def issue_oauth_state(account):
    return issue_session_state(
        account.env,
        OAUTH_SCOPE,
        request.session,
        {"account_id": account.id, "company_id": account.company_id.id},
        max_age_seconds=_OAUTH_STATE_MAX_AGE_SECONDS,
    )


def _signed_state(raw_state):
    try:
        metadata = json_loads(raw_state)
    except TypeError, ValueError:
        return None
    return metadata.get("token") if isinstance(metadata, dict) else None


class AmazonController(http.Controller):
    @http.route(
        "/amazon/return",
        type="http",
        methods=["GET"],
        auth="user",
        website=True,
        sitemap=False,
    )
    def amazon_return_from_authorization(self, **data):
        _logger.info(
            "Returning from authorization with data:\n%s", pprint.pformat(data)
        )

        seller_key = data["selling_partner_id"]
        authorization_code = data["spapi_oauth_code"]
        account = self._amazon_account_of_state(data.get("state"))
        if not account:
            _logger.warning(
                "Refused an Amazon authorization return whose state is not the one "
                "this session started."
            )
            return request.render(
                "sale_amazon.authorization_error",
                qcontext={
                    "error_message": request.env._(
                        "This authorization link is invalid, has expired or was "
                        "already used. Start the authorization again from the "
                        "Amazon account."
                    ),
                    "account_url": _ACCOUNTS_URL,
                },
                status=403,
            )
        account.seller_key = seller_key

        account_url = f"{_ACCOUNTS_URL}/{account.id}"

        try:
            amazon_utils.exchange_authorization_code(authorization_code, account)
            account.action_update_available_marketplaces()
        except (UserError, ValidationError) as e:
            return request.render(
                "sale_amazon.authorization_error",
                qcontext={"error_message": str(e), "account_url": account_url},
            )

        return request.redirect(account_url, local=False)

    def _amazon_account_of_state(self, raw_state):
        claims = consume_session_state(
            request.env, OAUTH_SCOPE, request.session, _signed_state(raw_state)
        )
        if claims is None:
            return None
        account = request.env["amazon.account"].browse(claims["account_id"]).exists()
        if account.company_id.id != claims["company_id"]:
            return None
        return account
