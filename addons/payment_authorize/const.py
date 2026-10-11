DEFAULT_PAYMENT_METHOD_CODES = {
    "ach_direct_debit",
    "card",
    "visa",
    "mastercard",
    "amex",
    "discover",
}

PAYMENT_METHODS_MAPPING = {
    "amex": "americanexpress",
    "diners": "dinersclub",
    "card": "creditcard",
}

TRANSACTION_STATUS_MAPPING = {
    "authorized": ["authorizedPendingCapture", "capturedPendingSettlement"],
    "captured": ["settledSuccessfully"],
    "voided": ["voided"],
    "refunded": ["refundPendingSettlement", "refundSettledSuccessfully"],
}
