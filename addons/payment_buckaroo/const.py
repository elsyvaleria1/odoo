DEFAULT_PAYMENT_METHOD_CODES = {
    "card",
    "ideal",
    "visa",
    "mastercard",
    "amex",
    "discover",
}

PAYMENT_METHODS_MAPPING = {
    "alipay": "Alipay",
    "apple_pay": "applepay",
    "bancontact": "bancontactmrcash",
    "belfius": "belfius",
    "billink": "Billink",
    "card": "mastercard",
    "cartes_bancaires": "CarteBancaire",
    "eps": "eps",
    "giropay": "GiroPay",
    "in3": "Capayable",
    "ideal": "ideal",
    "kbc": "KBCPaymentButton",
    "bank_reference": "PayByBank",
    "p24": "Przelewy24",
    "paypal": "paypal",
    "poste_pay": "PostePay",
    "sepa_direct_debit": "SepaDirectDebit",
    "sofort": "sofortueberweisung",
    "tinka": "Tinka",
    "trustly": "Trustly",
    "wechat_pay": "WeChatPay",
    "klarna": "klarna",
    "afterpay_riverty": "afterpay",
}

STATUS_CODES_MAPPING = {
    "pending": (790, 791, 792, 793),
    "done": (190,),
    "cancel": (890, 891),
    "refused": (690,),
    "error": (
        490,
        491,
        492,
    ),
}

SUPPORTED_CURRENCIES = [
    "EUR",
    "GBP",
    "PLN",
    "DKK",
    "NOK",
    "SEK",
    "CHF",
    "USD",
]
