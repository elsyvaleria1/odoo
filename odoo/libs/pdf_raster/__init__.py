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
    REFUSED = "refused"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"
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
    pages: int | None = None


@functools.cache
def available() -> bool:
    return importlib.util.find_spec("pymupdf") is not None


def render_first_page(
    content: bytes, width: int, height: int, limits: Limits = DEFAULT_LIMITS
) -> Rendering:
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
    head, _newline, png = proc.stdout.partition(b"\n")
    if (
        proc.returncode
        or not head.isascii()
        or not head.isdigit()
        or not png.startswith(_PNG)
        or len(png) > limits.output_bytes
    ):
        return Rendering(Outcome.FAILED)
    return Rendering(Outcome.RENDERED, png, int(head))
