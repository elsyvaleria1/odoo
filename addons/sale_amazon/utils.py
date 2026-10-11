import gzip
import json
import logging
from datetime import UTC, datetime, timedelta
from pprint import pformat
from urllib.parse import urlsplit as url_parse
from xml.etree import ElementTree as ET

import requests
from defusedxml import ElementTree as DefusedET

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads
from odoo.tools.urls import urljoin as url_join

from odoo.addons.sale_amazon import const

_logger = logging.getLogger(__name__)




class AmazonRateLimitError(Exception):

    def __init__(self, operation) -> None:
        self.operation = operation
        super().__init__()




def exchange_authorization_code(authorization_code, account) -> None:
    data = {
        "grant_type": "authorization_code",
        "code": authorization_code,
    }
    endpoint = const.PROXY_ENDPOINTS["authorization"]
    response_content = send_proxy_request(endpoint, account.env, payload=data)
    account.sudo().refresh_token = response_content["refresh_token"]


def check_account_is_set_up(account, require_marketplaces=True) -> None:
    if not account.sudo().credential_id or not account.seller_key:
        raise UserError(
            account.env._(
                "You first need to authorize the Amazon account %s.", account.name
            )
        )
    if require_marketplaces and not account.active_marketplace_ids:
        raise UserError(
            account.env._(
                "You first need to set the marketplaces to synchronize for the Amazon account %s.",
                account.name,
            )
        )




def send_proxy_request(endpoint, env, payload=None):
    url = url_join(const.PROXY_URL, endpoint)
    ICP = env["ir.config_parameter"]
    data = {
        "db_uuid": ICP.sudo().get_param("database.uuid"),
        "db_enterprise_code": ICP.sudo().get_param("database.enterprise_code"),
        "amazon_data": json_dumps(payload or {}),
    }
    try:
        response = env["ir.egress"].request(
            "POST", url, purpose="amazon", policy="private", data=data, timeout=60
        )
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as err:
            response_content = response.json()
            error_code = response_content.get("error")
            error_description = response_content.get("error_description")
            _logger.exception(
                "Invalid API request (error code: %s, description: %s) with data:\n%s",
                error_code,
                error_description,
                pformat(data),
            )
            raise ValidationError(
                env._(
                    "Error code: %(error_code)s; description: %(error_message)s",
                    error_code=error_code,
                    error_message=error_description,
                )
            ) from err
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as err:
        _logger.warning(
            "Could not establish the connection to the proxy.", exc_info=True
        )
        raise ValidationError(
            env._("Could not establish the connection to the proxy.")
        ) from err
    return response.json()




def send_sp_api_request(
    account, operation, path_parameter="", payload=None, method="GET"
):
    account.check_singleton()

    path = const.API_OPERATIONS_MAPPING[operation]["url_path"].format(
        param=path_parameter
    )
    domain = const.API_DOMAINS_MAPPING[account.base_marketplace_id.region]
    url = url_join(domain, path)

    payload = payload or {}

    if (
        const.API_OPERATIONS_MAPPING[operation]["restricted_resource_path"] is None
    ):
        refresh_access_token(account)
        access_token = account.access_token
    else:
        refresh_restricted_data_token(account)
        access_token = account.restricted_data_token

    host = url_parse(domain).netloc
    now = datetime.now(UTC)
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json; charset=utf-8",
        "host": host,
        "x-amz-access-token": access_token,
        "x-amz-date": now.strftime("%Y%m%dT%H%M%SZ"),
    }
    try:
        if method == "GET":
            response = account.env["ir.egress"].request(
                "GET",
                url,
                purpose="amazon",
                params=payload,
                headers=headers,
                timeout=60,
            )
        else:
            response = account.env["ir.egress"].request(
                "POST", url, purpose="amazon", json=payload, headers=headers, timeout=60
            )
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as err:
            if response.status_code == 429:
                raise AmazonRateLimitError(operation) from err
            errors = response.json().get("errors")
            error_code = errors and errors[0].get("code")
            error_message = errors and errors[0].get("message")
            _logger.exception(
                "Invalid API request (error code: %s, description: %s) with data:\n%s",
                error_code,
                error_message,
                pformat(payload),
            )
            raise ValidationError(
                account.env._(
                    "The communication with the API failed.\nError code: %(error_code)s; description: %(error_message)s",
                    error_code=error_code,
                    error_message=error_message,
                )
            ) from err
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as err:
        _logger.exception("Unable to reach endpoint at %s", url)
        raise ValidationError(
            account.env._("Could not establish the connection to the API.")
        ) from err
    json_response = response.json()
    if const.API_OPERATIONS_MAPPING[operation].get("log_response", True):
        _logger.info(
            "SPAPI response for operation %s: %s", operation, pformat(json_response)
        )
    return json_response


def refresh_access_token(account):
    if fields.Datetime.now() > account.access_token_expiry - timedelta(minutes=5):
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": account.sudo().refresh_token,
        }
        endpoint = const.PROXY_ENDPOINTS["authorization"]
        response_content = send_proxy_request(endpoint, account.env, payload=payload)
        account.write(
            {
                "access_token": response_content["access_token"],
                "access_token_expiry": datetime.now(UTC)
                + timedelta(seconds=response_content["expires_in"]),
            }
        )


def refresh_restricted_data_token(account) -> None:
    if datetime.now(UTC).replace(
        tzinfo=None
    ) > account.restricted_data_token_expiry - timedelta(minutes=5):
        all_restricted_operations = [
            k
            for k, operation_map in const.API_OPERATIONS_MAPPING.items()
            if operation_map["restricted_resource_path"]
        ]
        OPERATIONS_MAPPING = const.API_OPERATIONS_MAPPING
        payload = {
            "restrictedResources": [
                {
                    "method": "GET",
                    "path": OPERATIONS_MAPPING[operation]["restricted_resource_path"],
                    "dataElements": OPERATIONS_MAPPING[operation][
                        "restricted_resource_data_elements"
                    ],
                }
                for operation in all_restricted_operations
            ]
        }
        response_content = send_sp_api_request(
            account, "createRestrictedDataToken", payload=payload, method="POST"
        )
        account.write(
            {
                "restricted_data_token": response_content["restrictedDataToken"],
                "restricted_data_token_expiry": datetime.now(UTC)
                + timedelta(seconds=response_content["expiresIn"]),
            }
        )




def get_json_feed(account, messages):
    return json.dumps(
        {
            "header": {
                "sellerId": account.seller_key,
                "version": "2.0",
                "issueLocale": account.env.lang,
            },
            "messages": [
                {
                    "messageId": int(datetime.now(UTC).timestamp() + i) % 2147483647
                    + 1,
                    **message,
                }
                for i, message in enumerate(messages)
            ],
        },
        separators=(",", ":"),
    )


def get_feed(account, message_type, messages_builder, *args, **kwargs):
    XSI = "http://www.w3.org/2001/XMLSchema-instance"
    root = ET.Element(
        "AmazonEnvelope",
        {f"{'{' + XSI + '}'}noNamespaceSchemaLocation": "amzn-envelope.xsd"},
    )
    header = ET.SubElement(root, "Header")
    ET.SubElement(header, "DocumentVersion").text = "1.01"
    ET.SubElement(header, "MerchantIdentifier").text = account.seller_key
    ET.SubElement(root, "MessageType").text = message_type
    messages_builder(root, *args, **kwargs)
    for i, message in enumerate(root.findall("Message")):
        message_id = ET.Element("MessageID")
        message_id.text = f"{int(datetime.now(UTC).timestamp())}{i}"
        message.insert(
            0, message_id
        )
    return ET.tostring(root, encoding="UTF-8", method="xml")


def submit_feed(
    account, feed, feed_type, feed_content_type=None, marketplace_api_refs=None
):
    feed_content_type = feed_content_type or "text/xml; charset=UTF-8"
    marketplace_api_refs = (
        marketplace_api_refs or account.active_marketplace_ids.mapped("api_ref")
    )

    def _create_feed_document():
        _payload = {"contentType": feed_content_type}
        _response_content = send_sp_api_request(
            account, "createFeedDocument", payload=_payload, method="POST"
        )
        return _response_content["feedDocumentId"], _response_content["url"]

    def _upload_feed_data():
        headers = {"content-Type": feed_content_type}
        try:
            response = account.env["ir.egress"].request(
                "PUT",
                upload_url,
                purpose="amazon",
                data=feed,
                headers=headers,
                timeout=60,
            )
            try:
                response.raise_for_status()
            except requests.exceptions.HTTPError as err:
                _logger.exception("Invalid API request with data:\n%s", feed)
                raise ValidationError(
                    account.env._("The communication with the API failed.")
                ) from err
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
        ) as err:
            _logger.exception("Could not establish the connection to the feed URL.")
            raise ValidationError(
                account.env._("Could not establish the connection to the feed URL.")
            ) from err

    def _create_feed():
        _payload = {
            "feedType": feed_type,
            "marketplaceIds": marketplace_api_refs,
            "inputFeedDocumentId": feed_document_id,
        }
        _response_content = send_sp_api_request(
            account, "createFeed", payload=_payload, method="POST"
        )
        return _response_content["feedId"]

    feed_document_id, upload_url = _create_feed_document()
    _upload_feed_data()
    return _create_feed()


def get_feed_document(account, document_ref):
    document_infos = send_sp_api_request(
        account, "getFeedDocument", path_parameter=document_ref
    )
    document_url = document_infos["url"]
    try:
        response = account.env["ir.egress"].request(
            "GET", document_url, purpose="amazon", timeout=60, max_bytes=None
        )
        response.raise_for_status()
        document = response.content
        if document_infos.get("compressionAlgorithm") == "GZIP":
            document = gzip.decompress(document)
        if "application/json" in response.headers.get("Content-Type", ""):
            document = json_loads(document)
        else:
            document = DefusedET.fromstring(document)
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as err:
        _logger.exception(
            "Could not establish the connection to download the feed document at %s",
            document_url,
        )
        raise ValidationError(
            account.env._("Could not establish the connection to the API.")
        ) from err
    except requests.exceptions.HTTPError as err:
        _logger.exception(
            "Invalid API request while downloading the feed document at %s",
            document_url,
        )
        raise ValidationError(
            account.env._("The communication with the API failed.")
        ) from err
    except (ET.ParseError, json.JSONDecodeError) as err:
        _logger.exception("Could not parse the feed document at %s", document_url)
        raise ValidationError(
            account.env._("Could not process the feed document send by Amazon.")
        ) from err
    return document




def pull_batch_data(
    account, operation, payload, path_parameter="", method="GET"
) -> tuple:
    response_content = send_sp_api_request(
        account,
        operation,
        path_parameter=path_parameter,
        payload=payload,
        method=method,
    )
    batch_data = response_content["payload"]
    next_token = response_content["payload"].get("NextToken")
    has_next_page = bool(next_token)
    payload["NextToken"] = next_token
    return batch_data, has_next_page


def commit_preserving_credentials(account, processed=0) -> None:
    fields_to_preserve = [
        "access_token",
        "access_token_expiry",
        "restricted_data_token",
        "restricted_data_token_expiry",
    ]
    credentials = {field: account[field] for field in fields_to_preserve}
    account.env["ir.cron"]._commit_progress(processed=processed)
    account.write(credentials)
