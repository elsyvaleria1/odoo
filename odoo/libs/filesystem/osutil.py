__all__ = [
    "WINDOWS_RESERVED",
    "clean_filename",
    "is_running_as_nt_service",
]

import os
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator

WINDOWS_RESERVED = re.compile(
    r"""
    ^
    # forbidden stems: reserved keywords
    # ``(?:`` non-capturing group -- ``(:?`` was a capturing group starting with
    # an optional colon, so it also matched ``":CON"`` (false positive).
    # Windows reads the superscript digits as digits here
    (?:CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])
    # spaces closing the stem are dropped, and an extension does not help
    \x20*(?:\..*)?
    $
""",
    flags=re.IGNORECASE | re.VERBOSE,
)
_CLEAN_FILENAME_RE = re.compile(r"[^\w_.()\[\] -]+")


def clean_filename(name: str, replacement: str = "") -> str:
    cleaned = _CLEAN_FILENAME_RE.sub(replacement, name)
    stripped = cleaned.lstrip(".-")
    if not stripped:
        return "Untitled"
    if "." in cleaned[: len(cleaned) - len(stripped)] and "." not in stripped:
        return f"Untitled.{stripped}"
    if WINDOWS_RESERVED.match(stripped):
        return f"_{stripped}"
    return stripped


if os.name != "nt":

    def is_running_as_nt_service(service_name: str) -> bool:
        return False
else:
    from contextlib import contextmanager

    import win32service as ws
    import win32serviceutil as wsu

    def is_running_as_nt_service(service_name: str) -> bool:

        @contextmanager
        def close_srv(srv: Any) -> Iterator[Any]:
            try:
                yield srv
            finally:
                ws.CloseServiceHandle(srv)

        try:
            with close_srv(
                ws.OpenSCManager(None, None, ws.SC_MANAGER_ALL_ACCESS)
            ) as hscm:
                with close_srv(
                    wsu.SmartOpenService(hscm, service_name, ws.SERVICE_ALL_ACCESS)
                ) as hs:
                    info = ws.QueryServiceStatusEx(hs)
                    return info["ProcessId"] == os.getppid()
        except Exception:
            return False
