import functools
import hashlib
import importlib.metadata
import logging
from pathlib import Path

import odoo.tools
from odoo.libs.debug_log import DebugLog
from odoo.libs.json import loads as json_loads

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)


def _tools_dir() -> Path | None:
    tools_file = getattr(odoo.tools, "__file__", None)
    if not tools_file:
        return None
    return Path(tools_file).resolve().parent


def pipeline_sources() -> tuple[Path, ...]:
    tools_dir = _tools_dir()
    if tools_dir is None:
        _debug.logic("pipeline_sources_unknown", reason="no_file")
        return ()
    base_dir = tools_dir.parent / "addons" / "base"
    return (
        base_dir / "models" / "assetsbundle",
        tools_dir / "assets",
        tools_dir / "sass_embedded.py",
        base_dir / "data" / "rtlcss.json",
    )


OUTPUT_AFFECTING_NPM_TOOLS = ("sass-embedded", "rtlcss", "esbuild")
OUTPUT_AFFECTING_PY_TOOLS = ("rjsmin",)


@functools.cache
def toolchain_versions() -> str:
    root = _repo_root()
    if root is None:
        _debug.logic("toolchain_versions_unknown", reason="no_root")
        return "unknown"
    lock_versions: dict[str, str] = {}
    try:
        packages = json_loads((root / "package-lock.json").read_text())["packages"]
    except OSError, ValueError, KeyError, TypeError:
        packages = {}
        _debug.logic("toolchain_lock_unreadable")
    for name in OUTPUT_AFFECTING_NPM_TOOLS:
        entry = packages.get(f"node_modules/{name}")
        if isinstance(entry, dict) and entry.get("version"):
            lock_versions[name] = entry["version"]

    parts = []
    for name in OUTPUT_AFFECTING_NPM_TOOLS:
        version = None
        try:
            installed = json_loads(
                (root / "node_modules" / name / "package.json").read_text()
            )
            version = installed.get("version")
        except OSError, ValueError, AttributeError:
            version = None
        parts.append(f"{name}@{version or lock_versions.get(name) or 'absent'}")
    for name in OUTPUT_AFFECTING_PY_TOOLS:
        try:
            version = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            version = None
        parts.append(f"{name}@{version or 'absent'}")
    _debug.logic("toolchain_versions", versions=";".join(parts))
    return ";".join(parts)


def _repo_root() -> Path | None:
    tools_dir = _tools_dir()
    return None if tools_dir is None else tools_dir.parent.parent


@functools.cache
def pipeline_fingerprint() -> str:
    with _debug.perf("pipeline_fingerprint") as span:
        digest = hashlib.sha256()
        digest.update(toolchain_versions().encode())
        digest.update(b"\x00")
        files: list[Path] = []
        for source in pipeline_sources():
            if source.is_dir():
                files.extend(source.glob("*.py"))
                files.extend(source.glob("js/*.mjs"))
            elif source.is_file():
                files.append(source)
            else:
                _logger.warning(
                    "Asset pipeline source %s does not exist; changes to it will "
                    "not invalidate cached bundles.",
                    source,
                )
                _debug.logic("pipeline_source_missing", source=source.name)
        try:
            for path in sorted(files):
                digest.update(path.name.encode())
                digest.update(path.read_bytes())
        except OSError:
            from odoo import release

            _logger.warning(
                "Could not read the asset pipeline sources to fingerprint them; "
                "falling back to the release version. A pipeline change that does "
                "not touch any asset file will not invalidate cached bundles."
            )
            _debug.logic("pipeline_fingerprint_fallback", reason="unreadable_source")
            return release.version
        if not files:
            from odoo import release

            _debug.logic("pipeline_fingerprint_fallback", reason="no_sources")
            return release.version
        span.set(files=len(files))
        return digest.hexdigest()
