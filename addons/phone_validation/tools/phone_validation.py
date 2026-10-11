import logging

from odoo.exceptions import UserError
from odoo.tools import LazyTranslate

_lt = LazyTranslate(
    __name__, default_lang="en_US"
)
_logger = logging.getLogger(__name__)
_phonenumbers_lib_warning = [
    False
]


try:
    import phonenumbers

    def phone_parse(number, country_code):
        try:
            phone_nbr = phonenumbers.parse(
                number, region=country_code or None, keep_raw_input=True
            )
            formatted_intl = phonenumbers.format_number(
                phone_nbr, phonenumbers.PhoneNumberFormat.INTERNATIONAL
            )
            phone_nbr = phonenumbers.parse(
                formatted_intl, region=country_code or None, keep_raw_input=True
            )
        except phonenumbers.phonenumberutil.NumberParseException as e:
            raise UserError(
                _lt("Unable to parse %(phone)s: %(error)s", phone=number, error=str(e))
            ) from e

        if not phonenumbers.is_possible_number(phone_nbr):
            reason = phonenumbers.is_possible_number_with_reason(phone_nbr)
            if reason == phonenumbers.ValidationResult.INVALID_COUNTRY_CODE:
                raise UserError(
                    _lt("Impossible number %s: not a valid country prefix.", number)
                )
            if reason == phonenumbers.ValidationResult.TOO_SHORT:
                raise UserError(_lt("Impossible number %s: not enough digits.", number))
            if reason == phonenumbers.ValidationResult.TOO_LONG:
                if number.startswith("00"):
                    try:
                        phone_nbr = phone_parse(
                            f"+{number.removeprefix('00')}", country_code
                        )
                    except UserError:
                        raise UserError(
                            _lt("Impossible number %s: too many digits.", number)
                        ) from None
                elif not number.startswith("+"):
                    try:
                        phone_nbr = phone_parse(f"+{number}", country_code)
                    except UserError:
                        raise UserError(
                            _lt("Impossible number %s: too many digits.", number)
                        ) from None
                else:
                    raise UserError(
                        _lt("Impossible number %s: too many digits.", number)
                    )
            else:
                raise UserError(
                    _lt(
                        "The phone number %s is invalid! Let's fix it - you are not dialing aliens.",
                        number,
                    )
                )
        if not phonenumbers.is_valid_number(phone_nbr):
            raise UserError(
                _lt("Invalid number %s: probably incorrect prefix.", number)
            )

        return phone_nbr

    def phone_format(
        number,
        country_code,
        country_phone_code,
        force_format="INTERNATIONAL",
        raise_exception=True,
    ):
        try:
            phone_nbr = phone_parse(number, country_code)
        except UserError:
            if raise_exception:
                raise
            return number
        if force_format == "E164":
            phone_fmt = phonenumbers.PhoneNumberFormat.E164
        elif force_format == "RFC3966":
            phone_fmt = phonenumbers.PhoneNumberFormat.RFC3966
        elif (
            force_format == "INTERNATIONAL"
            or phone_nbr.country_code != country_phone_code
        ):
            phone_fmt = phonenumbers.PhoneNumberFormat.INTERNATIONAL
        else:
            phone_fmt = phonenumbers.PhoneNumberFormat.NATIONAL
        return phonenumbers.format_number(phone_nbr, phone_fmt)

    def phone_get_country_code_for_number(number):
        region_data = phone_get_region_data_for_number(number)
        return region_data["code"]

    def phone_get_region_data_for_number(number) -> dict:
        try:
            phone_obj = phone_parse(number, None)
        except UserError:
            return {
                "code": "",
                "national_number": "",
                "phone_code": "",
            }
        return {
            "code": phonenumbers.phonenumberutil.region_code_for_number(phone_obj),
            "national_number": str(phone_obj.national_number),
            "phone_code": str(phone_obj.country_code),
        }

except ImportError:

    def phone_parse(number, country_code):
        return False

    def phone_format(
        number,
        country_code,
        country_phone_code,
        force_format="INTERNATIONAL",
        raise_exception=True,
    ):
        if not _phonenumbers_lib_warning[0]:
            _logger.info(
                "The `phonenumbers` Python module is not installed, contact numbers will not be "
                "verified. Please install the `phonenumbers` Python module."
            )
            _phonenumbers_lib_warning[0] = True
        return number

    def phone_get_country_code_for_number(number):
        return ""

    def phone_get_region_data_for_number(number) -> dict:
        return {
            "code": "",
            "national_number": "",
            "phone_code": "",
        }
