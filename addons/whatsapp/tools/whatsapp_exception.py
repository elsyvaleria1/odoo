from odoo.tools import LazyTranslate

_lt = LazyTranslate(__name__)


class WhatsAppError(Exception):
    def __init__(self, message="", error_code=False, failure_type=False) -> None:
        self.failure_type = failure_type
        self.error_code = error_code
        self.error_message = message

        formated_message = ""
        if error_code:
            formated_message = f"{error_code}: {message}"
        elif failure_type == "account":
            formated_message = _lt("Whatsapp account is misconfigured or shared.")
        elif failure_type == "network":
            formated_message = _lt(
                "Whatsapp could not be reached or the query was malformed."
            )
        else:
            formated_message = _lt("Unknown error when processing whatsapp request.")

        super().__init__(formated_message)
