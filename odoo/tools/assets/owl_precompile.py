import functools
import json
import logging
import shutil
import subprocess
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, NamedTuple

import odoo
from odoo.libs.asset_log import get_asset_logger, log_event
from odoo.libs.hashing import cache_hash
from odoo.libs.json import loads as json_loads
from odoo.modules.module import get_module_path
from odoo.tools.json import json_default

_precompile_log = get_asset_logger("owl_precompile")

_SCRIPT = Path(__file__).parent / "js" / "owl_precompile.mjs"

_WEB_COMPILER_FILES = (
    "lib/owl/owl.es.js",
    "lib/owl/owl.runtime.es.js",
    "src/core/templates.js",
    "src/core/template_inheritance.js",
    "src/core/translation.js",
    "src/core/utils/format/strings.js",
    "src/env.js",
)
_NODE_COMPILER_FILES = (
    _SCRIPT,
    _SCRIPT.with_name("owl_precompile_hooks.mjs"),
)
_NODE_PACKAGES = ("acorn", "jsdom", "xpath")

_fingerprints: dict[tuple, str] = {}


class PrecompiledTemplates(NamedTuple):
    script: str
    compiled: int
    inline: int
    failures: dict[str, str]
    elapsed_ms: int


class InlineSource(NamedTuple):
    url: str
    content: str


def _odoo_root() -> Path:
    return Path(odoo.__path__[0]).parent


def web_static_path() -> Path | None:
    web = get_module_path("web", display_warning=False)
    return Path(web) / "static" if web else None


@functools.cache
def precompiler_missing() -> tuple[str, ...]:
    node_modules = _odoo_root() / "node_modules"
    missing = [] if shutil.which("node") else ["node"]
    if not web_static_path():
        missing.append("the web addon")
    missing.extend(
        f"node_modules/{package}"
        for package in _NODE_PACKAGES
        if not (node_modules / package).is_dir()
    )
    if missing:
        log_event(
            _precompile_log,
            logging.WARNING,
            "unavailable",
            missing=",".join(missing),
            fix=f"npm ci in {_odoo_root()}, then restart",
            effect="templates compile in the browser and pages keep unsafe-eval",
        )
    return tuple(missing)


def precompiler_available() -> bool:
    return not precompiler_missing()


def compiler_fingerprint(web_static: Path) -> str:
    files = [web_static / name for name in _WEB_COMPILER_FILES]
    files += _NODE_COMPILER_FILES
    files += [
        _odoo_root() / "node_modules" / package / "package.json"
        for package in _NODE_PACKAGES
    ]
    stats: list[tuple[str, int | None, int | None]] = []
    for path in files:
        try:
            info = path.stat()
        except OSError:
            stats.append((str(path), None, None))
        else:
            stats.append((str(path), info.st_mtime_ns, info.st_size))
    key = tuple(stats)
    if key not in _fingerprints:
        digest = b"".join(
            path.read_bytes() if size is not None else b"-"
            for path, (_, _, size) in zip(files, stats, strict=True)
        )
        _fingerprints[key] = cache_hash(digest)[:16]
    return _fingerprints[key]


def precompile_templates(
    registrations: str,
    translations: Mapping[str, Any],
    *,
    web_static: Path,
    label: str,
    sources: Sequence[InlineSource] = (),
    page_registrations: Sequence[str] = (),
    dev: bool = False,
    timeout_s: int = 120,
) -> PrecompiledTemplates | None:
    node = shutil.which("node")
    if not node:
        log_event(_precompile_log, logging.WARNING, "no_node", bundle=label)
        return None
    request = json.dumps(
        {
            "web_static": str(web_static),
            "registrations": registrations,
            "page_registrations": list(page_registrations),
            "modules": translations,
            "sources": [source._asdict() for source in sources],
            "dev": dev,
        },
        default=json_default,
    )
    started = time.monotonic()
    try:
        result = subprocess.run(
            [node, str(_SCRIPT)],
            input=request,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout_s,
            cwd=_odoo_root(),
            check=False,
        )
    except subprocess.TimeoutExpired:
        log_event(
            _precompile_log,
            logging.WARNING,
            "timeout",
            bundle=label,
            timeout_s=timeout_s,
        )
        return None
    except OSError as error:
        log_event(
            _precompile_log, logging.WARNING, "spawn_failed", bundle=label, error=error
        )
        return None
    if result.returncode != 0:
        log_event(
            _precompile_log,
            logging.WARNING,
            "failed",
            bundle=label,
            exit=result.returncode,
        )
        _precompile_log.warning(
            "template precompiler stderr for %s:\n%s", label, result.stderr[-4000:]
        )
        return None
    try:
        output = json_loads(result.stdout)
    except ValueError:
        log_event(_precompile_log, logging.WARNING, "unreadable_output", bundle=label)
        return None
    precompiled = PrecompiledTemplates(
        script=output["script"],
        compiled=output["compiled"],
        inline=output["inline"],
        failures=output["failures"],
        elapsed_ms=output["elapsed_ms"],
    )
    log_event(
        _precompile_log,
        logging.INFO,
        "compiled",
        bundle=label,
        templates=precompiled.compiled,
        inline=precompiled.inline,
        dev=dev,
        failed=len(precompiled.failures),
        compile_ms=precompiled.elapsed_ms,
        elapsed=f"{time.monotonic() - started:.3f}",
    )
    for name, reason in precompiled.failures.items():
        _precompile_log.info("template %s left to the browser: %s", name, reason)
    return precompiled
