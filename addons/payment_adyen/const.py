API_ENDPOINT_VERSIONS = {
    "/disable": 68,
    "/paymentMethods": 71,
    "/payments": 71,
    "/payments/details": 71,
    "/payments/{}/cancels": 71,
    "/payments/{}/captures": 71,
    "/payments/{}/refunds": 71,
}

CHILD_OPERATION_EVENT_CODES = ("CANCELLATION", "CAPTURE", "CAPTURE_FAILED")

CURRENCY_DECIMALS = {
    "CLP": 2,
    "CVE": 0,
    "IDR": 0,
    "ISK": 2,
}

DEFAULT_PAYMENT_METHOD_CODES = {
    "card",
    "visa",
    "mastercard",
    "amex",
    "discover",
}

PAYMENT_METHODS_MAPPING = {
    "ach_direct_debit": "ach",
    "apple_pay": "applepay",
    "bacs_direct_debit": "directdebit_GB",
    "bancontact_card": "bcmc",
    "bancontact": "bcmc_mobile",
    "cash_app_pay": "cashapp",
    "gopay": "gopay_wallet",
    "becs_direct_debit": "au_becs_debit",
    "afterpay": "afterpaytouch",
    "klarna_pay_over_time": "klarna_account",
    "momo": "momo_wallet",
    "napas_card": "momo_atm",
    "paytrail": "ebanking_FI",
    "online_banking_czech_republic": "onlineBanking_CZ",
    "online_banking_india": "onlinebanking_IN",
    "fpx": "molpay_ebanking_fpx_MY",
    "p24": "onlineBanking_PL",
    "mastercard": "mc",
    "online_banking_slovakia": "onlineBanking_SK",
    "online_banking_thailand": "molpay_ebanking_TH",
    "open_banking": "paybybank",
    "samsung_pay": "samsungpay",
    "sepa_direct_debit": "sepadirectdebit",
    "sofort": "directEbanking",
    "unionpay": "cup",
    "wallets_india": "wallet_IN",
    "wechat_pay": "wechatpayQR",
}

RESULT_CODES_MAPPING = {
    "pending": (
        "ChallengeShopper",
        "IdentifyShopper",
        "Pending",
        "PresentToShopper",
        "Received",
        "RedirectShopper",
    ),
    "done": ("Authorised",),
    "cancel": ("Cancelled",),
    "error": ("Error",),
    "refused": ("Refused",),
}
