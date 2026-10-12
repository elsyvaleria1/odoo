__all__ = [
    "site_data_dir",
    "user_data_dir",
]

import os
import sys
from pathlib import Path


def _xdg_data_home() -> str:
    value = os.getenv("XDG_DATA_HOME") or ""
    if Path(value).is_absolute():
        return value.rstrip(os.sep) or os.sep
    return str(Path("~/.local/share").expanduser())


def user_data_dir(appname: str, appauthor: str | None = None) -> str:
    if sys.platform == "win32":
        path = Path(_get_win_folder("CSIDL_LOCAL_APPDATA"), appauthor or appname)
    elif sys.platform == "darwin":
        path = Path("~/Library/Application Support/").expanduser()
    else:
        path = Path(_xdg_data_home())
    return str(path / appname)


def site_data_dir(appname: str, appauthor: str | None = None) -> str:
    if sys.platform == "win32":
        path = Path(_get_win_folder("CSIDL_COMMON_APPDATA"), appauthor or appname)
    elif sys.platform == "darwin":
        path = Path("/Library/Application Support")
    else:
        path = Path("/var/lib")
    return str(path / appname)


if sys.platform == "win32":

    def _get_win_folder_with_pywin32(csidl_name: str) -> str:
        from win32com.shell import shell, shellcon

        raw_folder = shell.SHGetFolderPath(0, getattr(shellcon, csidl_name), 0, 0)
        folder: str = raw_folder
        try:
            folder = str(raw_folder)

            has_high_char = False
            for c in folder:
                if ord(c) > 255:
                    has_high_char = True
                    break
            if has_high_char:
                try:
                    import win32api

                    short_folder: str = win32api.GetShortPathName(folder)
                    folder = short_folder
                except ImportError:
                    pass
        except UnicodeError:
            pass
        return folder

    def _get_win_folder_with_ctypes(csidl_name: str) -> str:
        import ctypes

        csidl_const = {
            "CSIDL_COMMON_APPDATA": 35,
            "CSIDL_LOCAL_APPDATA": 28,
        }[csidl_name]

        buf = ctypes.create_unicode_buffer(1024)
        ctypes.windll.shell32.SHGetFolderPathW(None, csidl_const, None, 0, buf)

        has_high_char = False
        for c in buf:
            if ord(c) > 255:
                has_high_char = True
                break
        if has_high_char:
            buf2 = ctypes.create_unicode_buffer(1024)
            if ctypes.windll.kernel32.GetShortPathNameW(buf.value, buf2, 1024):
                buf = buf2

        return buf.value

    try:
        import win32com.shell  # noqa: F401 - import success selects the native Windows implementation

        _get_win_folder = _get_win_folder_with_pywin32
    except ImportError:
        _get_win_folder = _get_win_folder_with_ctypes
