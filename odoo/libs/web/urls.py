import re
import urllib.parse

__all__ = ["SAFE_LINK_SCHEMES", "contains_dot_segments", "url_scheme", "urljoin"]

SAFE_LINK_SCHEMES = frozenset({"http", "https", "ftp", "ftps", "mailto", "tel"})


_MAX_UNQUOTE_PASSES = 4
_TAB_AND_NEWLINES = str.maketrans("", "", "\t\r\n")
_C0_CONTROL_OR_SPACE = "".join(map(chr, range(0x21)))
_SCHEME_RE = re.compile(r"([A-Za-z][A-Za-z0-9+.-]*):")


def url_scheme(url: str) -> str:
    # urlsplit's reading of the scheme, which is a browser's, without its netloc
    # validation: a bracketed host that is no IPv6 literal must not hide one.
    url = url.lstrip(_C0_CONTROL_OR_SPACE).translate(_TAB_AND_NEWLINES)
    match = _SCHEME_RE.match(url)
    return match[1].lower() if match else ""


def _get_segment_core(segment: str) -> str:
    segment = segment.split(";", 1)[0]
    for i, ch in enumerate(segment):
        if ch < "\x20" or ch == "\x7f":
            return segment[:i]
    return segment


def contains_dot_segments(path: str) -> bool:
    current = path
    for _ in range(_MAX_UNQUOTE_PASSES):
        if any(
            _get_segment_core(seg) in (".", "..")
            for seg in current.replace("\\", "/").split("/")
        ):
            return True
        decoded = urllib.parse.unquote(current, errors="replace")
        if decoded == current:
            return False
        current = decoded
    return True


def _is_path_prefix(base_path: str, path: str) -> bool:
    prefix = base_path.rstrip("/")
    if not prefix:
        return True
    return path == prefix or path.startswith(prefix + "/")


def urljoin(base: str, extra: str) -> str:
    if not isinstance(base, str):
        msg = "Base URL must be a string"
        raise TypeError(msg)
    if not isinstance(extra, str):
        msg = "Extra URL must be a string"
        raise TypeError(msg)

    b_scheme, b_netloc, path, _, _ = urllib.parse.urlsplit(base)
    e_scheme, e_netloc, e_path, e_query, e_fragment = urllib.parse.urlsplit(extra)

    if e_scheme or e_netloc:
        if (
            (e_scheme != b_scheme)
            or (e_netloc.lower() != b_netloc.lower())
            or not _is_path_prefix(path, e_path)
        ):
            msg = "Extra URL must use same scheme and host as base, and begin with base path"
            raise ValueError(msg)

        e_path = e_path.removeprefix(path.rstrip("/"))

    if e_path:
        e_path = e_path.lstrip("/\\" + _C0_CONTROL_OR_SPACE)
        path = f"{path}/{e_path}"

    path = re.sub(r"/+", "/", path)

    if contains_dot_segments(path):
        msg = "Dot segments are not allowed"
        raise ValueError(msg)

    return urllib.parse.urlunsplit((b_scheme, b_netloc, path, e_query, e_fragment))
