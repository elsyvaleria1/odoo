from odoo.addons.phone_validation.tools import phone_validation


def wa_phone_format(
    record,
    fname=False,
    number=False,
    country=None,
    force_format="INTERNATIONAL",
    raise_exception=True,
):
    if not number and record and fname:
        record.check_singleton()
        number = record[fname]
        if record._fields[fname].type == "many2many":
            phone = number._primary("whatsapp", "mobile")
            number = phone.number
            if not country and phone.country_id:
                country = phone.country_id
    if not number:
        return False

    if not country and record:
        country = record._phone_get_country().get(record.id)
    if not country:
        country = record.env.company.country_id

    try:
        formatted = phone_validation.phone_format(
            number,
            country.code,
            country.phone_code,
            force_format=force_format if force_format != "WHATSAPP" else "E164",
            raise_exception=True,
        )
    except Exception:
        if raise_exception:
            raise
        formatted = False

    if formatted and force_format == "WHATSAPP":
        try:
            parsed = phone_validation.phone_parse(formatted, country.code)
        except Exception:
            if raise_exception:
                raise
            return False
        zeros = ""
        if parsed.italian_leading_zero:
            zeros = "0"
            if parsed.number_of_leading_zeros:
                zeros = "0" * parsed.number_of_leading_zeros
        return f"{parsed.country_code}" + zeros + f"{parsed.national_number}"
    return formatted


def wa_phone_format_for_blacklist(number):

    if not number:
        return False

    if str(number).startswith("+"):
        return number

    return f"+{number}"
