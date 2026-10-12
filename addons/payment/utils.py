from hashlib import sha1

from odoo import api, fields
from odoo.http import request
from odoo.tools import float_round, is_hmac_valid, register_signed_scope
from odoo.tools.misc import hmac as hmac_tool

from odoo.addons.payment.const import CURRENCY_MINOR_UNITS

PAYMENT_ACCESS_SCOPE = register_signed_scope(
    "generate_access_token",
    purpose="reach a payment form or transaction for the partner, amount and "
    "currency the token signs",
    lifetime="undated: the page that carries it is the payment flow itself",
)


def generate_access_token(*values, env=None):
    env = env or (request and request.bound_env)
    assert isinstance(env, api.Environment), (
        "Environment required to generate access token."
    )
    token_str = "|".join(str(val) for val in values)
    return hmac_tool(env(su=True), PAYMENT_ACCESS_SCOPE, token_str)


def is_access_token_valid(access_token, *values) -> bool:
    env = request and request.bound_env
    assert isinstance(env, api.Environment), (
        "Environment required to check an access token."
    )
    token_str = "|".join(str(val) for val in values)
    return bool(is_hmac_valid(env, PAYMENT_ACCESS_SCOPE, token_str, access_token))


def add_to_report(report, records, available=True, reason="") -> None:
    if report is None or not records:
        return

    category = "providers" if records._name == "payment.provider" else "payment_methods"
    report.setdefault(category, {})
    for r in records:
        report[category][r] = {
            "available": available,
            "reason": reason,
        }
        if category == "payment_methods" and "providers" in report:
            report[category][r]["supported_providers"] = [
                (p, report["providers"][p]["available"])
                for p in r.provider_ids
                if p in report["providers"]
            ]


def singularize_reference_prefix(prefix="tx", separator="-", max_length=None) -> str:
    if prefix is None:
        prefix = "tx"
    if max_length:
        DATETIME_LENGTH = 14
        assert max_length >= 1 + len(separator) + DATETIME_LENGTH
        prefix = prefix[: max_length - len(separator) - DATETIME_LENGTH]
    return f"{prefix}{separator}{fields.Datetime.now().strftime('%Y%m%d%H%M%S')}"


def minor_to_major_currency_units(
    minor_amount, currency, arbitrary_decimal_number=None
):
    if arbitrary_decimal_number is None:
        currency.check_singleton()
        decimal_number = CURRENCY_MINOR_UNITS.get(
            currency.name, currency.decimal_places
        )
    else:
        decimal_number = arbitrary_decimal_number
    return float_round(minor_amount, precision_digits=0) / (10**decimal_number)


def major_to_minor_currency_units(
    major_amount, currency, arbitrary_decimal_number=None
) -> int:
    if arbitrary_decimal_number is None:
        currency.check_singleton()
        decimal_number = CURRENCY_MINOR_UNITS.get(
            currency.name, currency.decimal_places
        )
    else:
        decimal_number = arbitrary_decimal_number
    return int(
        float_round(
            major_amount * (10**decimal_number),
            precision_digits=0,
            rounding_method="DOWN",
        )
    )


def format_partner_address(address1="", address2=""):
    address1 = address1 or ""
    address2 = address2 or ""
    return f"{address1} {address2}".strip()


def split_partner_name(partner_name) -> tuple:
    parts = partner_name.split()
    if len(parts) == 1:
        return parts[0], ""

    return " ".join(parts[:-1]), parts[-1]


def get_customer_ip_address():
    return (request and request.httprequest.remote_addr) or ""


def check_rights_on_recordset(recordset) -> None:
    recordset.check_access("write")


def generate_idempotency_key(tx, scope=None):
    database_uuid = tx.env.registry.settings.get(tx.env, "database.uuid", False)
    return sha1(f"{database_uuid}{tx.reference}{scope or ''}".encode()).hexdigest()
