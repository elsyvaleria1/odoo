import dataclasses
import enum
import functools
import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path

__all__ = [
    "DEFAULT_LIMITS",
    "Limits",
    "Outcome",
    "Rendering",
    "available",
    "render_first_page",
]

_CHILD = Path(__file__).with_name("_child.py")
_PNG = b"\x89PNG\r\n\x1a\n"


class Outcome(enum.StrEnum):
    RENDERED = "rendered"
    # the PDF holds no page to show: encrypted, or empty
    REFUSED = "refused"
    # the renderer itself is missing: says nothing about this PDF
    UNAVAILABLE = "unavailable"
    # malformed, or past a limit of its own: CPU, memory, output
    FAILED = "failed"
    # past the wall limit, which a loaded machine reaches with any PDF: says
    # nothing about this one
    TIMED_OUT = "timed_out"


@dataclasses.dataclass(frozen=True)
class Limits:
    cpu_seconds: int = 10
    memory_bytes: int = 1024 * 1024 * 1024
    wall_seconds: float = 30.0
    output_bytes: int = 8 * 1024 * 1024


DEFAULT_LIMITS = Limits()


@dataclasses.dataclass(frozen=True)
class Rendering:
    outcome: Outcome
    png: bytes = b""


@functools.cache
def available() -> bool:
    # asked without importing: MuPDF is AGPL-or-commercial, offered and not
    # imposed, and never loaded into the process that asks
    return importlib.util.find_spec("pymupdf") is not None


def render_first_page(
    content: bytes, width: int, height: int, limits: Limits = DEFAULT_LIMITS
) -> Rendering:
    # an untrusted PDF is parsed in a child of its own: no database, no
    # credentials, no network handle, its own CPU and memory caps, and a crash
    # or a hang that costs that child alone
    if not available():
        return Rendering(Outcome.UNAVAILABLE)
    try:
        proc = subprocess.run(
            [
                sys.executable,
                "-I",
                str(_CHILD),
                str(width),
                str(height),
                str(limits.cpu_seconds),
                str(limits.memory_bytes),
            ],
            input=content,
            capture_output=True,
            timeout=limits.wall_seconds,
            env={"PATH": os.defpath},
            cwd=tempfile.gettempdir(),
            close_fds=True,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return Rendering(Outcome.TIMED_OUT)
    if proc.returncode == 3:
        return Rendering(Outcome.UNAVAILABLE)
    if proc.returncode == 2:
        return Rendering(Outcome.REFUSED)
    png = proc.stdout
    if proc.returncode or not png.startswith(_PNG) or len(png) > limits.output_bytes:
        return Rendering(Outcome.FAILED)
    return Rendering(Outcome.RENDERED, png)
