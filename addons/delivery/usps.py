import re
from typing import Literal

ZIP_ZIP4 = re.compile(r"^[0-9]{5}(-[0-9]{4})?$")


def split_zip_plus_four(zipcode: str) -> list[str]:
    if ZIP_ZIP4.match(zipcode) and "-" in zipcode:
        return zipcode.split("-")
    else:
        return [zipcode, ""]


def prepare_usps_phone_number(phone: str) -> str | Literal[False]:
    phone_pattern = re.compile(
        r"""
            # don't match beginning of string, number can start anywhere
            (\d{3})     # area code is 3 digits (e.g. '800')
            \D*         # optional separator is any number of non-digits
            (\d{3})     # trunk is 3 digits (e.g. '555')
            \D*         # optional separator
            (\d{4})     # rest of number is 4 digits (e.g. '1212')
            \D*         # optional separator
            (\d*)       # extension is optional and can be any number of digits
            $           # end of string
            """,
        re.VERBOSE,
    )
    match = phone_pattern.search(phone)
    if match:
        return "".join(str(digits_number) for digits_number in match.groups())
    else:
        return False
