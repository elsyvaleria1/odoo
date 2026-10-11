import contextlib

__all__ = ["NumberFormat", "PhoneMetadata", "PhoneNumberDesc"]

with contextlib.suppress(ImportError):
    from phonenumbers.phonemetadata import NumberFormat, PhoneMetadata, PhoneNumberDesc
