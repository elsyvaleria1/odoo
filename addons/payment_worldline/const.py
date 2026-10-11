DEFAULT_PAYMENT_METHOD_CODES = {
    "card",
    "amex",
    "discover",
    "mastercard",
    "visa",
}

PAYMENT_METHODS_MAPPING = {
    "alipay_plus": 5405,
    "amex": 2,
    "bancontact": 3012,
    "bizum": 5001,
    "cartes_bancaires": 130,
    "cofidis": 3012,
    "diners": 132,
    "discover": 128,
    "eps": 5406,
    "floa_bank": 5139,
    "ideal": 809,
    "jcb": 125,
    "klarna": 3301,
    "maestro": 117,
    "mastercard": 3,
    "mbway": 5908,
    "multibanco": 5500,
    "p24": 3124,
    "paypal": 840,
    "post_finance_pay": 3203,
    "twint": 5407,
    "upi": 56,
    "visa": 1,
    "wechat_pay": 5404,
}

REDIRECT_PAYMENT_METHODS = {
    "alipay_plus",
    "bizum",
    "eps",
    "floa_bank",
    "ideal",
    "klarna",
    "mbway",
    "multibanco",
    "p24",
    "paypal",
    "post_finance_pay",
    "twint",
    "wechat_pay",
}

PAYMENT_STATUS_MAPPING = {
    "pending": (
        "CREATED",
        "REDIRECTED",
        "AUTHORIZATION_REQUESTED",
        "PENDING_CAPTURE",
        "CAPTURE_REQUESTED",
    ),
    "done": ("CAPTURED",),
    "cancel": ("CANCELLED",),
    "declined": ("REJECTED", "REJECTED_CAPTURE"),
}

VALID_RESPONSE_CODES = {
    200: "Successful",
    201: "Created",
    402: "Payment Rejected",
}
