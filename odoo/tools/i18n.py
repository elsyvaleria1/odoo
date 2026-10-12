from collections.abc import Iterable
from typing import TYPE_CHECKING, Any, Literal

from babel import lists

from odoo.tools.locale_utils import babel_locale_parse, get_lang

if TYPE_CHECKING:
    from odoo.api import Environment
else:
    Environment = Any


def format_list(
    env: Environment | None,
    lst: Iterable[object],
    style: Literal[
        "standard",
        "standard-short",
        "or",
        "or-short",
        "unit",
        "unit-short",
        "unit-narrow",
    ] = "standard",
    lang_code: str | None = None,
) -> str:
    locale = babel_locale_parse(
        lang_code or (get_lang(env).code if env is not None else "en_US")
    )
    items = [str(el) for el in lst]
    formatted: str
    try:
        formatted = lists.format_list(items, style, locale)
    except KeyError, ValueError:
        formatted = lists.format_list(items, "standard", locale)
    return formatted
