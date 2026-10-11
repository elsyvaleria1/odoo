from typing import Literal, Protocol, Self


class ShopWarningRecord(Protocol):
    shop_warning: str | Literal[False]

    def check_singleton(self) -> Self: ...


def acquire_shop_warning(
    record: ShopWarningRecord, *, clear: bool = True
) -> str | None:
    record.check_singleton()
    warning = record.shop_warning
    if clear:
        record.shop_warning = ""
    return warning or None
