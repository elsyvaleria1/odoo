import dataclasses
import logging
import typing
from datetime import UTC, date, datetime

from odoo.libs.collections import ReadonlyDict as _ReadonlyDict
from odoo.libs.func import lazy as _lazy
from odoo.libs.json import ScriptSafeJSON as JSON
from odoo.libs.json import dataclass_attributes as _dataclass_attributes
from odoo.libs.json import dumps as fast_dumps
from odoo.libs.json import scriptsafe
from odoo.libs.secret import Secret as _Secret

from .config import config as _config

__all__ = [
    "JSON",
    "fast_dumps",
    "json_default",
    "scriptsafe",
]


_logger = logging.getLogger(__name__)

_fields: typing.Any = None


def _odoo_fields() -> typing.Any:
    global _fields  # noqa: PLW0603 -- Updates process-wide state shared by callers of this module.
    if _fields is None:
        from odoo import fields

        _fields = fields
    return _fields


def _convert(obj: object) -> object:
    if isinstance(obj, _Secret):
        raise TypeError(
            "a Secret is never serialized: reveal it where it is sent, or send "
            "its fingerprint()"
        )
    fields = _odoo_fields()

    if isinstance(obj, datetime):
        if obj.tzinfo is not None:
            obj = obj.astimezone(UTC).replace(tzinfo=None)
        return fields.Datetime.to_string(obj)
    if isinstance(obj, date):
        return fields.Date.to_string(obj)
    if isinstance(obj, _ReadonlyDict):
        return dict(obj)
    if isinstance(obj, bytes):
        return obj.decode()
    if isinstance(obj, fields.Domain):
        return list(obj)
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return _dataclass_attributes(obj)
    if isinstance(obj, (set, frozenset)):
        return list(obj)
    msg = f"Object of type {type(obj).__name__} is not JSON serializable"
    if _config["test_enable"]:
        raise TypeError(msg)
    _logger.error("%s; it is sent as its str()", msg)
    return str(obj)


def json_default(obj: object) -> object:
    if type(obj) is datetime:
        if obj.tzinfo is not None:
            obj = obj.astimezone(UTC).replace(tzinfo=None)
        return obj.isoformat(" ", "seconds")
    if type(obj) is date:
        return obj.isoformat()
    if isinstance(obj, _lazy):
        return obj._value
    return _convert(obj)
