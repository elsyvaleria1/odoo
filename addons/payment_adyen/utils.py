import base64
import binascii
import hashlib
import hmac

from odoo.addons.payment import utils as payment_utils


def format_partner_name(partner_name) -> dict:
    first_name, last_name = payment_utils.split_partner_name(partner_name)
    return {
        "firstName": first_name,
        "lastName": last_name,
    }


def include_partner_addresses(tx_sudo) -> dict:
    tx_sudo.check_singleton()

    if "sale_order_ids" in tx_sudo._fields:
        order = tx_sudo.sale_order_ids[:1]
        if order:
            return {
                "billingAddress": format_partner_address(order.partner_invoice_id),
                "deliveryAddress": format_partner_address(order.partner_shipping_id),
            }
    return {}


def format_partner_address(partner):
    street_data = partner._get_street_split()
    return {
        "city": partner.city or "Unknown",
        "country": partner.country_id.code or "ZZ",
        "stateOrProvince": partner.state_id.code or "Unknown",
        "postalCode": partner.zip or "",
        "street": street_data.get("street_name", partner.street) or "Unknown",
        "houseNumberOrName": street_data.get("street_number") or "",
    }


def compute_notification_signature(payload, hmac_key):

    def _flatten_dict(_value, _path_base="", _separator="."):
        if isinstance(_value, dict):
            _path_base = _path_base if not _path_base else _path_base + _separator
            for _key in _value:
                yield from _flatten_dict(_value[_key], _path_base + str(_key))
        else:
            yield _path_base, _value

    def _to_escaped_string(_value):
        if isinstance(_value, str):
            return _value.replace("\\", "\\\\").replace(":", "\\:")
        elif _value is None:
            return ""
        else:
            return str(_value)

    signature_keys = [
        "pspReference",
        "originalReference",
        "merchantAccountCode",
        "merchantReference",
        "amount.value",
        "amount.currency",
        "eventCode",
        "success",
    ]
    flattened_payload = dict(_flatten_dict(payload))
    signature_values = [flattened_payload.get(key) for key in signature_keys]
    escaped_values = [_to_escaped_string(value) for value in signature_values]
    signing_string = ":".join(escaped_values)
    binary_hmac_key = binascii.a2b_hex(hmac_key.encode("ascii"))
    binary_hmac = hmac.new(
        binary_hmac_key, signing_string.encode("utf-8"), hashlib.sha256
    )
    return base64.b64encode(binary_hmac.digest()).decode()


def get_minor_amount(payment_data):
    amount = payment_data.get("amount")
    value = amount.get("value") if isinstance(amount, dict) else None
    return value if type(value) is int else None
