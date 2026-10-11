import hashlib
import traceback
import typing
from pathlib import Path

from werkzeug.exceptions import HTTPException

import odoo
from odoo.exceptions import RedirectWarning, UserError
from odoo.http import SessionExpiredException
from odoo.modules.module import get_resource_from_path

FINGERPRINT_VERSION = 1

EXPECTED = (UserError, RedirectWarning, SessionExpiredException, HTTPException)

_CORE_ROOT = Path(odoo.__path__[0]).resolve()


class Origin(typing.NamedTuple):
    module: str
    path: str
    function: str
    line: int


def is_expected(exc: BaseException) -> bool:
    return isinstance(exc, EXPECTED)


def exception_type(exc: BaseException) -> str:
    cls = type(exc)
    if cls.__module__ in ("builtins", "__main__"):
        return cls.__qualname__
    return f"{cls.__module__}.{cls.__qualname__}"


def _locate(filename: str) -> tuple[str, str] | None:
    resource = get_resource_from_path(filename)
    if resource:
        return resource.module, resource.relative_path
    try:
        relative = Path(filename).resolve().relative_to(_CORE_ROOT)
    except ValueError:
        return None
    return "odoo", relative.as_posix()


def origin(exc: BaseException) -> Origin:
    frames = traceback.extract_tb(exc.__traceback__)
    for frame in reversed(frames):
        located = _locate(frame.filename)
        if located:
            return Origin(located[0], located[1], frame.name, frame.lineno or 0)
    if frames:
        frame = frames[-1]
        return Origin("", Path(frame.filename).name, frame.name, frame.lineno or 0)
    return Origin("", "", "", 0)


def fingerprint(kind: str, where: Origin) -> str:
    raw = f"v{FINGERPRINT_VERSION}|{kind}|{where.module}|{where.path}|{where.function}"
    return hashlib.sha256(raw.encode()).hexdigest()[:20]


def format_traceback(exc: BaseException) -> str:
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
