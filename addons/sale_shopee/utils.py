import hashlib
import hmac
import logging
import time
from datetime import datetime, timedelta

from odoo.exceptions import UserError, ValidationError

from odoo.addons.sale_shopee import const

_logger = logging.getLogger(__name__)




class ShopeeRateLimitError(Exception):
    """When the API rate limit of Shopee is reached."""

    def __init__(self, operation) -> None:
        self.operation = operation
        super().__init__()




def get_public_sign(account, path, timestamp):
    account.check_singleton()
    return hmac.new(
        account.partner_key.encode(),
        _get_public_signing_string(account, path, timestamp).encode(),
        hashlib.sha256,
    ).hexdigest()




def request_access_token(shop, main_account_id=False, is_refresh=False):
    shop.check_singleton()

    authorization_code = shop.env.context.get("authorization_code")
    if not is_refresh and not authorization_code:
        raise UserError(
            shop.env._(
                "Authorization Code is required to request an Access Token."
                " Please authorize the connection first."
            )
        )

    body = {
        "partner_id": shop.account_id.partner_identifier,
    }
    if main_account_id:
        body["main_account_id"] = main_account_id
    else:
        body["shop_id"] = shop.shop_identifier

    if is_refresh:
        body["refresh_token"] = shop.refresh_token
        operation = "refresh_token"
    else:
        body["code"] = authorization_code
        operation = "get_token"

    response = send_shopee_api_request(shop, operation, body=body, method="POST")
    expire_in = response["expire_in"]
    shop.update(
        {
            "refresh_token": response["refresh_token"],
            "access_token": response["access_token"],
            "access_token_expiration_date": datetime.now()
            + timedelta(seconds=expire_in),
        }
    )
    return response.get("shop_id_list")


def send_shopee_api_request(shop, operation, params=None, body=None, method="GET"):
    shop.check_singleton()
    account = shop.account_id
    api_type = const.API_OPERATIONS_MAPPING[operation]["api_type"]

    if not params:
        params = {}

    if api_type != "public":
        params["shop_id"] = shop.shop_identifier
        if not shop.access_token or not shop.access_token_expiration_date:
            request_access_token(shop)
        elif shop.access_token_expiration_date < datetime.now() + timedelta(minutes=5):
            request_access_token(shop, is_refresh=True)
        params["access_token"] = shop.access_token

    path = const.API_OPERATIONS_MAPPING[operation]["url_path"]
    timestamp = int(time.time())
    params.update(
        {
            "partner_id": account.partner_identifier,
            "sign": get_api_sign(shop, operation, timestamp),
            "timestamp": timestamp,
        }
    )

    _logger.info(
        "Operation: %(operation)s\n\tParams: %(params)s\n\tBody: %(body)s",
        {"operation": operation, "params": params, "body": body or "/"},
    )

    resp = shop.env["ir.egress"].request(
        method,
        f"{const.API_PATHS[account.api_endpoint]}{path}",
        purpose="shopee",
        params=params,
        json=body,
    )
    if resp.status_code == 429:
        raise ShopeeRateLimitError(operation)
    if resp.status_code != 200:
        raise ValidationError(
            shop.env._(
                "At shop - %(shop_name)s, error %(error_code)s occurred during operation"
                " %(operation)s when contacting the Shopee API:\n\n%(error_message)s",
                shop_name=shop.name,
                operation=operation,
                error_code=resp.status_code,
                error_message=resp.text,
            )
        )
    if "application/json" not in resp.headers.get("Content-Type", ""):
        response_content = resp.content
    else:
        response_content = resp.json()

        if response_content.get("error"):
            message = _get_error_message(response_content)
            raise UserError(
                shop.env._(
                    "At shop - %(shop_name)s, error %(error_code)s occurred during operation"
                    " %(operation)s when contacting the Shopee API. Shopee sent:\n\n%(error_message)s",
                    shop_name=shop.name,
                    operation=operation,
                    error_code=response_content["error"],
                    error_message=message,
                )
            )
        _logger.info(response_content)
    if isinstance(response_content, dict) and response_content.get("response"):
        return response_content["response"]
    return response_content


def get_api_sign(shop, operation, timestamp):
    shop.check_singleton()
    account = shop.account_id
    api_type = const.API_OPERATIONS_MAPPING[operation]["api_type"]
    path = const.API_OPERATIONS_MAPPING[operation]["url_path"]
    signing_string = _get_public_signing_string(account, path, timestamp)
    if api_type != "public":
        signing_string += f"{shop.access_token}{shop.shop_identifier}"
    return hmac.new(
        account.partner_key.encode(),
        signing_string.encode(),
        hashlib.sha256,
    ).hexdigest()


def _get_public_signing_string(account, path, timestamp) -> str:
    return f"{account.partner_identifier}{path}{timestamp}"


def _get_error_message(response_content):
    message = response_content["message"]
    if response_content.get("response"):
        for order in response_content["response"].get("result_list", []):
            if order and order.get("fail_message"):
                message += f"\n{order['order_sn']}: {order['fail_message']}"
    return message
