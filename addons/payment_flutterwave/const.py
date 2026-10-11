SUPPORTED_CURRENCIES = [
    "GBP",
    "CAD",
    "XAF",
    "CLP",
    "COP",
    "EGP",
    "EUR",
    "GHS",
    "GNF",
    "KES",
    "MWK",
    "MAD",
    "NGN",
    "RWF",
    "SLL",
    "STD",
    "ZAR",
    "TZS",
    "UGX",
    "USD",
    "XOF",
    "ZMW",
]

PAYMENT_STATUS_MAPPING = {
    "pending": ["pending", "pending auth"],
    "done": ["successful"],
    "cancel": ["cancelled"],
    "error": ["failed"],
}

DEFAULT_PAYMENT_METHOD_CODES = {
    "card",
    "mpesa",
    "visa",
    "mastercard",
    "amex",
    "discover",
}

PAYMENT_METHODS_MAPPING = {
    "bank_transfer": "banktransfer",
}
