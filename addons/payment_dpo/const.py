PAYMENT_STATUS_MAPPING = {
    "pending": ("003", "007"),
    "authorized": ("001", "005"),
    "done": ("000", "002"),
    "cancel": ("900", "901", "902", "903", "904", "950"),
    "error": ("801", "802", "803", "804"),
}

DEFAULT_PAYMENT_METHOD_CODES = {
    "dpo",
}
