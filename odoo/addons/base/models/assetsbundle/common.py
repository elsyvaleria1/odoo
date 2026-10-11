import logging
import re
import subprocess
from collections.abc import Callable, Sequence
from subprocess import PIPE, Popen
from typing import Literal, NotRequired, TypedDict

from lxml import etree

from odoo.libs.asset_log import get_asset_logger
from odoo.libs.debug_log import DebugLog

_logger = logging.getLogger("odoo.addons.base.models.assetsbundle")
_debug = DebugLog(__name__)

_bundle_log = get_asset_logger("bundle")


def _sourcemap_source_root(asset_url: str) -> str:
    return "/".join(".." for _ in range(len(asset_url.split("/")) - 2)) + "/"


class BundleFileSpec(TypedDict):
    url: str
    filename: str | None
    content: str
    last_modified: NotRequired[float | None]


class NativeModuleData(TypedDict):
    import_map: dict[str, str]
    preload_urls: list[str]
    bridge_import_map: dict[str, str]


class TemplatesBlock(TypedDict):
    type: Literal["templates"]
    templates: list[tuple[etree._Element, str | None, str | None]]


class ExtensionsBlock(TypedDict):
    type: Literal["extensions"]
    extensions: dict[str, list[tuple[etree._Element, str | None]]]


XMLBlock = TemplatesBlock | ExtensionsBlock


class CompileError(RuntimeError):
    pass


class AssetError(Exception):
    pass


class AssetNotFoundError(AssetError):
    pass


class XMLAssetError(AssetError):
    pass


def _run_cli_pipe(argv: Sequence[str], source: str, timeout_s: int) -> str:
    with _debug.perf("cli_pipe", tool=argv[0], source_len=len(source)) as span:
        try:
            proc = Popen(
                argv,
                stdin=PIPE,
                stdout=PIPE,
                stderr=PIPE,
                encoding="utf-8",
                errors="replace",
            )
        except OSError:
            _debug.logic("cli_pipe_failed", tool=argv[0], reason="not_executable")
            raise CompileError(f"Could not execute command {argv[0]!r}") from None
        try:
            out, err = proc.communicate(input=source, timeout=timeout_s)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            _debug.logic(
                "cli_pipe_failed", tool=argv[0], reason="timeout", timeout_s=timeout_s
            )
            raise CompileError(f"{argv[0]!r} timed out after {timeout_s}s") from None
        if proc.returncode:
            cmd_output = out + err
            if not cmd_output:
                cmd_output = f"Process exited with return code {proc.returncode}\n"
            _debug.logic(
                "cli_pipe_failed",
                tool=argv[0],
                reason="returncode",
                returncode=proc.returncode,
                stderr_len=len(err),
            )
            raise CompileError(f"{argv[0]!r}: {cmd_output}")

        span.set(returncode=proc.returncode, out_len=len(out))
        return out


_CSS_STRING_OR_COMMENT = re.compile(
    r"""/\*.*?\*/|"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'""",
    re.DOTALL,
)

_SCSS_STRING_OR_COMMENT = re.compile(
    rf"""(?:(?<=\s)|\A)//[^\n]*|{_CSS_STRING_OR_COMMENT.pattern}""",
    re.DOTALL,
)

_URL_FUNCTION = r"""url\(\s*(?:"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|[^)'"\n]*)\)"""

_SCSS_STATEMENT_SPANS = re.compile(
    rf"""{_URL_FUNCTION}|{_SCSS_STRING_OR_COMMENT.pattern}""",
    re.DOTALL,
)

_PROTECTED_SPAN = "_odoo_protected_span"


def _rewrite_css_outside_strings(
    target: re.Pattern,
    repl: Callable[[re.Match], str],
    text: str,
    tokens: re.Pattern = _CSS_STRING_OR_COMMENT,
) -> str:
    scanner = re.compile(
        f"(?P<{_PROTECTED_SPAN}>(?s:{tokens.pattern}))|{target.pattern}",
        target.flags,
    )

    def _dispatch(match: re.Match) -> str:
        span = match.group(_PROTECTED_SPAN)
        return span if span is not None else repl(match)

    return scanner.sub(_dispatch, text)
