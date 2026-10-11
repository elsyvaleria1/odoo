CURRENCY_MAPPING = {
    "AE": "AED",
    "EG": "EGP",
    "OM": "OMR",
    "PK": "PKR",
    "SA": "SAR",
}

API_MAPPING = {
    "AE": "uae",
    "EG": "accept",
    "OM": "oman",
    "PK": "pakistan",
    "SA": "ksa",
}

PAYMENT_METHODS_MAPPING = {
    "VPC": "card",
    "MIGS": "card",
    "UIG": "mobile_wallet_eg",
    "CAGG": "kiosk",
    "HALAN": "halan",
    "SYMPL": "sympl",
    "VALU": "valu",
    "AMANV3": "aman",
    "SOUHOOLAV3": "souhoola",
    "CONTACT": "contact",
    "PREMIUM6": "premium_card",
    "FORSA": "forsa",
    "TABBY": "tabby",
    "TAMARA": "tamara",
    "STCPAY": "stcpay",
    "OMANNET": "omannet",
    "EASYPAISADIRECT": "easypaisa",
    "JAZZCASH": "jazzcash",
}

DEFAULT_PAYMENT_METHOD_CODES = {
    "card",
}

SIGNATURE_FIELDS = [
    "amount_cents",
    "created_at",
    "currency",
    "error_occured",
    "has_parent_transaction",
    "id",
    "integration_id",
    "is_3d_secure",
    "is_auth",
    "is_capture",
    "is_refunded",
    "is_standalone_payment",
    "is_voided",
    "order",
    "owner",
    "pending",
    "source_data.pan",
    "source_data.sub_type",
    "source_data.type",
    "success",
]
