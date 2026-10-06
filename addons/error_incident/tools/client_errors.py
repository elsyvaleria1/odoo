import hashlib
import re
import typing
from pathlib import Path
from urllib.parse import urlsplit

from odoo.libs.json import loads as json_loads
from odoo.libs.sourcemap import SourceMap
from odoo.tools.files import file_path

from .fingerprint import FINGERPRINT_VERSION

# A frame as V8 and Gecko print it: `at fn (url:line:col)`, `fn@url:line:col`.
_V8_FRAME = re.compile(
    r"^\s*at\s+(?:(?P<function>.*?)\s+\()?(?P<url>\S+?):(?P<line>\d+):(?P<column>\d+)\)?\s*$"
)
_GECKO_FRAME = re.compile(
    r"^\s*(?:(?P<function>[^@\s]*)@)?(?P<url>\S+?):(?P<line>\d+):(?P<column>\d+)\s*$"
)
_FIRST_LINE = re.compile(r"^(?P<kind>[A-Za-z_$][\w$.]{0,99}): ?(?P<message>.*)$")
# Where a bundle names an addon's own source: `layout/<module>/static/src/...`
# in an esbuild map, `/<module>/static/src/...` for a file served as is.
_OWN_SOURCE = re.compile(
    r"(?:^|/)(?P<module>[a-z0-9_]+)/(?P<path>static/(?!lib/)[^?#:]+\.(?:js|mjs|ts))$"
)
_ESM_BUNDLE = re.compile(r"^/web/assets/esm/[^/]+/[^/]+\.esm\.js$")
# A name a minifier did not keep is a letter or two; `Class.method` survives.
_KEPT_NAME = re.compile(r"(?:^|\.)(?P<name>[A-Za-z_$][\w$]{2,})$")
_DIGITS = re.compile(r"\d+")
_QUOTED = re.compile(r"""(["'`]).*?\1""")
MAX_FRAMES = 50


class Frame(typing.NamedTuple):
    function: str
    url: str
    line: int
    column: int


class Located(typing.NamedTuple):
    module: str
    path: str
    line: int
    function: str
    text: str


class ClientError(typing.NamedTuple):
    kind: str
    message: str
    origin: Located | None
    traceback: str


def split_head(stack: str) -> tuple[str, str]:
    """The error's type and message, from the stack's first line."""
    first = stack.split("\n", 1)[0].strip()
    match = _FIRST_LINE.match(first)
    if match:
        return match["kind"], match["message"]
    return "Error", first


def parse_frames(stack: str) -> list[Frame]:
    """The frames of the error itself: what a `Caused by:` chain adds is
    another error, with frames of its own."""
    own = stack.split("\n\nCaused by:", 1)[0]
    frames = []
    for line in own.splitlines()[1:]:
        match = _V8_FRAME.match(line) or _GECKO_FRAME.match(line)
        if match:
            frames.append(
                Frame(
                    match["function"] or "",
                    match["url"],
                    int(match["line"]),
                    int(match["column"]),
                )
            )
            if len(frames) == MAX_FRAMES:
                break
    return frames


def _kept_name(function: str) -> str:
    match = _KEPT_NAME.search(function)
    return match["name"] if match else ""


def _source_line(module: str, path: str, line: int) -> str:
    try:
        with Path(file_path(f"{module}/{path}")).open(encoding="utf-8") as source:
            for number, text in enumerate(source, 1):
                if number == line:
                    return text.rstrip("\n")
    except OSError, ValueError:
        pass
    return ""


def locate(env, frames: list[Frame]) -> list[Located | None]:
    """Each frame in the addon source it was built from, or ``None``.

    A bundle frame is read through the bundle's source map, kept beside it by
    `web.esbuild.source_maps` (`external` keeps it from the public); a frame
    of a file served as is (debug assets) names its source already.
    """
    by_bundle: dict[str, list[int]] = {}
    found: list[Located | None] = [None] * len(frames)
    for index, frame in enumerate(frames):
        path = urlsplit(frame.url).path
        if _ESM_BUNDLE.match(path):
            by_bundle.setdefault(path, []).append(index)
            continue
        own = _OWN_SOURCE.search(path)
        if own:
            found[index] = Located(
                own["module"],
                own["path"],
                frame.line,
                _kept_name(frame.function),
                _source_line(own["module"], own["path"], frame.line),
            )
    for bundle, indexes in by_bundle.items():
        raw = env["ir.qweb"]._read_generated_asset(f"{bundle}.map")
        if not raw:
            continue
        source_map = SourceMap(json_loads(raw))
        positions = {i: (frames[i].line - 1, frames[i].column - 1) for i in indexes}
        originals = source_map.locate(positions.values())
        for index, position in positions.items():
            original = originals.get(position)
            own = original and _OWN_SOURCE.search(original.source)
            if own:
                found[index] = Located(
                    own["module"],
                    own["path"],
                    original.line + 1,
                    _kept_name(frames[index].function),
                    original.text or "",
                )
    return found


def _anchor(origin: Located | None, message: str) -> str:
    # The line that failed, as written: it survives edits elsewhere in the
    # file, where its number would not. Without it, the message, its data
    # (numbers, quoted values) masked.
    if origin and origin.text.strip():
        return " ".join(origin.text.split())[:300]
    return _DIGITS.sub("#", _QUOTED.sub("…", message))[:300]


def client_fingerprint(kind: str, origin: Located | None, message: str) -> str:
    module, path = (origin.module, origin.path) if origin else ("", "")
    anchor = _anchor(origin, message)
    raw = f"v{FINGERPRINT_VERSION}|client|{kind}|{module}|{path}|{anchor}"
    return hashlib.sha256(raw.encode()).hexdigest()[:20]


def read_client_error(env, stack: str) -> ClientError:
    """What the browser reported, located in our sources, with the traceback
    rewritten frame by frame to read as the sources do."""
    kind, message = split_head(stack)
    frames = parse_frames(stack)
    located = locate(env, frames)
    origin = next((place for place in located if place), None)
    lines = [stack.split("\n", 1)[0].strip()]
    for frame, place in zip(frames, located, strict=True):
        if place:
            lines.append(
                f"    at {frame.function or '<anonymous>'} "
                f"({place.module}/{place.path}:{place.line})"
            )
        else:
            lines.append(
                f"    at {frame.function or '<anonymous>'} ({frame.url}:{frame.line}:{frame.column})"
            )
    return ClientError(kind, message, origin, "\n".join(lines))
