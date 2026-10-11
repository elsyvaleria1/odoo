from odoo.addons.payment.const import SENSITIVE_KEYS as PAYMENT_SENSITIVE_KEYS

SENSITIVE_KEYS = {"client_secret"}
PAYMENT_SENSITIVE_KEYS.update(
    SENSITIVE_KEYS
)

API_VERSION = "2019-05-16"

PROXY_URL = "https://stripe.api.odoo.com/api/stripe/"

DEFAULT_PAYMENT_METHOD_CODES = {
    "card",
    "bancontact",
    "eps",
    "ideal",
    "p24",
    "visa",
    "mastercard",
    "amex",
    "discover",
}

PAYMENT_METHODS_MAPPING = {
    "ach_direct_debit": "us_bank_account",
    "bacs_direct_debit": "bacs_debit",
    "becs_direct_debit": "au_becs_debit",
    "sepa_direct_debit": "sepa_debit",
    "afterpay": "afterpay_clearpay",
    "clearpay": "afterpay_clearpay",
    "cash_app_pay": "cashapp",
    "mobile_pay": "mobilepay",
    "unknown": "card",
}

INDIAN_MANDATES_SUPPORTED_CURRENCIES = [
    "USD",
    "EUR",
    "GBP",
    "SGD",
    "CAD",
    "CHF",
    "SEK",
    "AED",
    "JPY",
    "NOK",
    "MYR",
    "HKD",
]

STATUS_MAPPING = {
    "draft": ("requires_confirmation", "requires_action"),
    "pending": ("processing", "pending"),
    "authorized": ("requires_capture",),
    "done": ("succeeded",),
    "cancel": ("canceled",),
    "error": (
        "requires_payment_method",
        "failed",
    ),
}

HANDLED_WEBHOOK_EVENTS = [
    "payment_intent.processing",
    "payment_intent.amount_capturable_updated",
    "payment_intent.succeeded",
    "payment_intent.payment_failed",
    "payment_intent.canceled",
    "setup_intent.succeeded",
    "charge.refunded",
    "charge.refund.updated",
]

SUPPORTED_COUNTRIES = {
    "AE",
    "AT",
    "AU",
    "BE",
    "BG",
    "BR",
    "CA",
    "CH",
    "CY",
    "CZ",
    "DE",
    "DK",
    "EE",
    "ES",
    "FI",
    "FR",
    "GB",
    "GI",
    "GR",
    "HK",
    "HR",
    "HU",
    "ID",
    "IE",
    "IT",
    "JP",
    "LI",
    "LT",
    "LU",
    "LV",
    "MT",
    "MX",
    "MY",
    "NL",
    "NO",
    "NZ",
    "PH",
    "PL",
    "PT",
    "RO",
    "SE",
    "SG",
    "SI",
    "SK",
    "TH",
    "US",
}

COUNTRY_MAPPING = {
    "MQ": "FR",
    "GP": "FR",
    "GF": "FR",
    "RE": "FR",
    "YT": "FR",
    "MF": "FR",
}

CURRENCY_DECIMALS = {
    "ISK": 2,
    "UGX": 2,
    "MGA": 0,
}
