def get_payment_option(payment_method_code):
    return payment_method_code.upper() if payment_method_code != "card" else ""
