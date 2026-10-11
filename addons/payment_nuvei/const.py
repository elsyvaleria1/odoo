SUPPORTED_CURRENCIES = [
    "ARS",
    "BRL",
    "CAD",
    "CLP",
    "COP",
    "MXN",
    "PEN",
    "USD",
    "UYU",
]

DEFAULT_PAYMENT_METHOD_CODES = {
    "card",
    "visa",
    "mastercard",
    "amex",
    "discover",
    "tarjeta_mercadopago",
    "naranja",
}

INTEGER_METHODS = [
    "webpay",
]

FULL_NAME_METHODS = [
    "boleto",
]

PAYMENT_METHODS_MAPPING = {
    "astropay": "apmgw_Astropay_TEF",
    "boleto": "apmgw_BOLETO",
    "card": "cc_card",
    "nuvei_local": "apmgw_Local_Payments",
    "oxxopay": "apmgw_OXXO_PAY",
    "pix": "apmgw_PIX",
    "pse": "apmgw_PSE",
    "spei": "apmgw_SPEI",
    "webpay": "apmgw_Webpay",
}


def normalize_product_id(product_id):
    return str(product_id or "").replace("+", " ")


SIGNATURE_KEYS = [
    "totalAmount",
    "currency",
    "responseTimeStamp",
    "PPP_TransactionID",
    "Status",
    "productId",
]

PAYMENT_STATUS_MAPPING = {
    "pending": ("pending",),
    "done": (
        "approved",
        "ok",
    ),
    "error": (
        "declined",
        "error",
        "fail",
    ),
}
