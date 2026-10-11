
SUPPORTED_CURRENCIES = (
    "AUD",
    "BRL",
    "CAD",
    "CZK",
    "DKK",
    "EUR",
    "HKD",
    "HUF",
    "ILS",
    "JPY",
    "MYR",
    "MXN",
    "TWD",
    "NZD",
    "NOK",
    "PHP",
    "PLN",
    "GBP",
    "RUB",
    "SGD",
    "SEK",
    "CHF",
    "THB",
    "USD",
)

DEFAULT_PAYMENT_METHOD_CODES = {
    "paypal",
}

PAYMENT_STATUS_MAPPING = {
    "pending": (
        "PENDING",
        "CREATED",
        "APPROVED",
    ),
    "done": (
        "COMPLETED",
        "CAPTURED",
    ),
    "cancel": (
        "DECLINED",
        "DENIED",
        "VOIDED",
    ),
    "error": ("FAILED",),
}

HANDLED_WEBHOOK_EVENTS = [
    "CHECKOUT.ORDER.COMPLETED",
    "CHECKOUT.ORDER.APPROVED",
    "CHECKOUT.PAYMENT-APPROVAL.REVERSED",
]
