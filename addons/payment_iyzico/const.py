PAYMENT_RETURN_ROUTE = "/payment/iyzico/return"
WEBHOOK_ROUTE = "/payment/iyzico/webhook"

SUPPORTED_CURRENCIES = [
    "CHF",
    "EUR",
    "GBP",
    "IRR",
    "NOK",
    "RUB",
    "TRY",
    "USD",
]

DEFAULT_PAYMENT_METHOD_CODES = {
    "card",
    "mastercard",
    "visa",
    "amex",
    "troy",
}

PAYMENT_METHODS_MAPPING = {
    "amex": "american_express",
    "mastercard": "master_card",
}

PAYMENT_STATUS_MAPPING = {
    "pending": (
        "INIT_THREEDS",
        "CALLBACK_THREEDS",
        "INIT_BANK_TRANSFER",
        "INIT_CREDIT",
        "PENDING_CREDIT",
    ),
    "done": ("SUCCESS",),
    "error": ("FAILURE",),
}
