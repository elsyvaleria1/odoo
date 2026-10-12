from odoo.libs.parse_version import parse_version


def _local_load_region(code) -> None:
    __import__(
        "region_%s" % code,
        globals(),
        locals(),
        fromlist=["PHONE_METADATA_%s" % code],
        level=1,
    )


try:
    import phonenumbers
except ImportError:
    pass
else:
    if (
        parse_version("7.6.1")
        <= parse_version(phonenumbers.__version__)
        < parse_version("8.12.32")
    ):
        phonenumbers.phonemetadata.PhoneMetadata.register_region_loader(
            "CI", _local_load_region
        )

    if parse_version(phonenumbers.__version__) < parse_version("8.12.39"):
        phonenumbers.phonemetadata.PhoneMetadata.register_region_loader(
            "CO", _local_load_region
        )

    if parse_version(phonenumbers.__version__) < parse_version("8.13.40"):
        phonenumbers.phonemetadata.PhoneMetadata.register_region_loader(
            "IL", _local_load_region
        )

    if parse_version(phonenumbers.__version__) < parse_version("8.13.32"):
        phonenumbers.phonemetadata.PhoneMetadata.register_region_loader(
            "MA", _local_load_region
        )

    if parse_version(phonenumbers.__version__) < parse_version("8.12.13"):
        phonenumbers.phonemetadata.PhoneMetadata.register_region_loader(
            "MU", _local_load_region
        )

    if parse_version(phonenumbers.__version__) < parse_version("8.12.43"):
        phonenumbers.phonemetadata.PhoneMetadata.register_region_loader(
            "PA", _local_load_region
        )

    if parse_version(phonenumbers.__version__) < parse_version("8.12.29"):
        phonenumbers.phonemetadata.PhoneMetadata.register_region_loader(
            "SN", _local_load_region
        )

    if parse_version(phonenumbers.__version__) < parse_version("8.13.31"):
        phonenumbers.phonemetadata.PhoneMetadata.register_region_loader(
            "KE", _local_load_region
        )

    def _hook_load_region_br(code) -> None:
        if parse_version(phonenumbers.__version__) < parse_version("8.13.39"):
            _local_load_region(code)
        else:
            phonenumbers.data._load_region(code)
        _region_metadata = phonenumbers.PhoneMetadata._region_metadata
        if "BR" in _region_metadata:
            _region_metadata["BR"].intl_number_format.append(
                phonenumbers.phonemetadata.NumberFormat(
                    pattern="(\\d{2})(\\d{4})(\\d{4})",
                    format="\\1 9\\2-\\3",
                    leading_digits_pattern=[
                        "(?:[14689][1-9]|2[12478]|3[1-578]|5[13-5]|7[13-579][689])"
                    ],
                )
            )

    phonenumbers.phonemetadata.PhoneMetadata.register_region_loader(
        "BR", _hook_load_region_br
    )

    def _hook_load_region_mx(code) -> None:
        phonenumbers.data._load_region(code)
        if parse_version(phonenumbers.__version__) > parse_version("8.13.37"):
            _region_metadata = phonenumbers.PhoneMetadata._region_metadata
            if "MX" in _region_metadata:
                _region_metadata["MX"].intl_number_format.append(
                    phonenumbers.phonemetadata.NumberFormat(
                        pattern="(\\d)(\\d{2})(\\d{4})(\\d{4})",
                        format="\\2 \\3 \\4",
                        leading_digits_pattern=["1(?:33|5[56]|81)"],
                    )
                )
                _region_metadata["MX"].intl_number_format.append(
                    phonenumbers.phonemetadata.NumberFormat(
                        pattern="(\\d)(\\d{3})(\\d{3})(\\d{4})",
                        format="\\2 \\3 \\4",
                        leading_digits_pattern=["1"],
                    )
                )

    phonenumbers.phonemetadata.PhoneMetadata.register_region_loader(
        "MX", _hook_load_region_mx
    )
