import contextlib
import fcntl
import hashlib
import logging
import os
import re
import shutil
import stat
import subprocess
import tempfile
import time
from collections.abc import Callable, Collection, Iterable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import NamedTuple, Protocol

import odoo
from odoo.libs.asset_log import get_asset_logger, log_event
from odoo.libs.debug_log import DebugLog
from odoo.libs.json import scriptsafe as json
from odoo.modules.module import MODULE_NAME_RE, Manifest
from odoo.tools import config
from odoo.tools.assets import esbuild_process, esbuild_stubs
from odoo.tools.assets.constants import OWL_COMPILER_SPECIFIER, OWL_FULL_BUILD_URL
from odoo.tools.assets.nodes import CLASSIC_SCRIPT_BANNER

_esbuild_log = get_asset_logger("esbuild")
_debug = DebugLog(__name__)

EXTERNAL_SPECIFIER_PREFIX = "@odoo/"


class EntryAsset(Protocol):
    @property
    def module_path(self) -> str: ...

    @property
    def url(self) -> str | None: ...

    @property
    def _filename(self) -> str | None: ...

    @property
    def raw_content(self) -> str: ...

    @property
    def parsed_header(self) -> re.Match[str] | None: ...


def module_specifiers(asset: EntryAsset) -> tuple[str, ...]:
    names = [asset.module_path]
    if (asset.url or "").endswith("/index.js"):
        names.append(asset.module_path + "/index")
    header = getattr(asset, "parsed_header", None)
    if header and header["alias"]:
        names.append(header["alias"])
    return tuple(names)


def _write_resolution_root(root_dir: Path, roots: Mapping[str, Path]) -> Path:
    root_dir.mkdir(mode=0o700)
    for spec, path in roots.items():
        (root_dir / spec).symlink_to(path, target_is_directory=True)
    return root_dir


def _holds_exactly(root_dir: Path, roots: Mapping[str, Path]) -> bool:
    if root_dir.is_symlink() or not root_dir.is_dir():
        return False
    try:
        entries = {entry.name: entry for entry in root_dir.iterdir()}
        return entries.keys() == roots.keys() and all(
            entry.is_symlink() and entry.readlink() == roots[name]
            for name, entry in entries.items()
        )
    except OSError:
        return False


def _create_private_dir(base: Path) -> None:
    base.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = base.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
    ):
        raise PermissionError(f"{base} is not a directory only its owner can write")


@contextlib.contextmanager
def _root_lock(base: Path, name: str) -> Iterator[None]:
    fd = os.open(
        base / f"{name}.lock",
        os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC,
        0o600,
    )
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def _dangles(root_dir: Path) -> bool:
    try:
        links = [entry for entry in root_dir.iterdir() if entry.is_symlink()]
    except OSError:
        return False
    return bool(links) and not any(link.exists() for link in links)


def _prune_dangling_roots(base: Path, keep: str) -> int:
    pruned = 0
    for root_dir in base.iterdir():
        name = root_dir.name
        if name == keep or root_dir.is_symlink() or not root_dir.is_dir():
            continue
        if not _dangles(root_dir):
            continue
        lock = base / f"{name}.lock"
        try:
            fd = os.open(lock, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
        except FileNotFoundError:
            fd = None
        except OSError:
            continue
        try:
            if fd is not None:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    continue
            shutil.rmtree(root_dir, ignore_errors=True)
            with contextlib.suppress(OSError):
                lock.unlink()
            pruned += 1
        finally:
            if fd is not None:
                os.close(fd)
    _debug.lifecycle("esbuild.resolution_roots_pruned", base=str(base), pruned=pruned)
    return pruned


def _shared_resolution_root(base: Path, name: str, roots: Mapping[str, Path]) -> Path:
    root_dir = base / name
    if _holds_exactly(root_dir, roots):
        return root_dir
    with _root_lock(base, name):
        if _holds_exactly(root_dir, roots):
            return root_dir
        _prune_dangling_roots(base, keep=name)
        staging = _write_resolution_root(
            Path(tempfile.mkdtemp(prefix=f"{name}-", dir=base)) / "roots", roots
        )
        try:
            if _holds_exactly(root_dir, roots):
                _debug.logic(
                    "esbuild.resolution_root_published_meanwhile", root=str(root_dir)
                )
                return root_dir
            if root_dir.is_symlink() or root_dir.exists():
                _debug.logic("esbuild.resolution_root_replaced", root=str(root_dir))
                stale = Path(tempfile.mkdtemp(prefix=f"{name}-stale-", dir=base))
                with contextlib.suppress(OSError):
                    root_dir.rename(stale / "roots")
                shutil.rmtree(stale, ignore_errors=True)
            with contextlib.suppress(OSError):
                staging.rename(root_dir)
        finally:
            shutil.rmtree(staging.parent, ignore_errors=True)
    if not _holds_exactly(root_dir, roots):
        raise OSError(f"{root_dir} does not hold exactly the addon roots")
    return root_dir


class EsbuildResult(NamedTuple):
    code: str
    metafile: str | None
    sourcemap: str | None
    source_key: str | None = None
    prebuilt: bool = False
    variant: str = ""


class EsbuildGroupResult(NamedTuple):
    files: dict[str, str]
    metafile: str | None


def _esbuild_argv(
    esbuild: str,
    *,
    target: str,
    out_path: str | None,
    metafile_path: str,
    external_specifier_flags: list[str],
    external_flags: list[str],
    sourcemap_flags: list[str],
    alias_flags: list[str],
    extra_flags: Sequence[str] = (),
    entry_points: Sequence[str] = (),
    out_dir: str | None = None,
) -> list[str]:
    output_flags = (
        [f"--outfile={out_path}"]
        if out_path
        else [
            f"--outdir={out_dir}",
            "--splitting",
            "--entry-names=[name].esm",
            "--chunk-names=chunk-[hash].esm",
        ]
    )
    return [
        esbuild,
        "--bundle",
        "--format=esm",
        "--minify",
        "--keep-names",
        *external_specifier_flags,
        *external_flags,
        f"--target={target}",
        "--resolve-extensions=.js,.mjs,.json",
        "--tsconfig-raw={}",
        *output_flags,
        f"--metafile={metafile_path}",
        *sourcemap_flags,
        *alias_flags,
        *extra_flags,
        *entry_points,
    ]


_ALIASABLE_SPECIFIER_RE = re.compile(r"@?[\w.-]+(?:/[\w.-]+)*")


def classic_script(
    code: str,
    static_externals: Sequence[str],
    *,
    label: str,
    target: str,
    timeout_s: int,
) -> str | None:
    esbuild = _get_esbuild_path()
    unaliasable = [
        spec for spec in static_externals if not _ALIASABLE_SPECIFIER_RE.fullmatch(spec)
    ]
    if not esbuild or unaliasable:
        log_event(
            _esbuild_log,
            logging.INFO,
            "classic_declined",
            bundle=label,
            reason="unaliasable_external" if unaliasable else "no_binary",
            externals=",".join(unaliasable),
        )
        return None
    t0 = time.monotonic()
    tmp_dir = tempfile.mkdtemp(prefix=f"odoo-esbuild-classic-{label}-")
    try:
        tmp = Path(tmp_dir)
        (tmp / "bundle.esm.js").write_text(code, encoding="utf-8")
        alias_flags = []
        for index, spec in enumerate(static_externals):
            stub = f"external{index}.cjs"
            (tmp / stub).write_text(
                f"module.exports = odoo.loader.external({json.dumps(spec)});\n",
                encoding="utf-8",
            )
            alias_flags.append(f"--alias:{spec}=./{stub}")
        result = subprocess.run(
            [
                esbuild,
                "bundle.esm.js",
                "--bundle",
                "--format=iife",
                "--minify",
                f"--target={target}",
                "--packages=external",
                "--external:/web/static/lib/*",
                f"--banner:js={CLASSIC_SCRIPT_BANNER}",
                "--log-override:empty-import-meta=silent",
                "--log-level=error",
                *alias_flags,
                "--metafile=bundle.classic.json",
                "--outfile=bundle.classic.js",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout_s,
            cwd=tmp_dir,
            check=False,
        )
        if result.returncode != 0:
            log_event(
                _esbuild_log,
                logging.WARNING,
                "classic_failed",
                bundle=label,
                exit=result.returncode,
                err=result.stderr[:500],
            )
            return None
        classic = (tmp / "bundle.classic.js").read_text(encoding="utf-8")
        unprovided = sorted(
            {
                imported["path"]
                for output in json.loads(
                    (tmp / "bundle.classic.json").read_text(encoding="utf-8")
                )["outputs"].values()
                for imported in output.get("imports", ())
                if imported.get("external") and imported["kind"] != "dynamic-import"
            }
        )
        if unprovided:
            log_event(
                _esbuild_log,
                logging.WARNING,
                "classic_declined",
                bundle=label,
                reason="unprovided_import",
                externals=",".join(unprovided),
            )
            return None
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        log_event(
            _esbuild_log,
            logging.WARNING,
            "classic_failed",
            bundle=label,
            err=type(exc).__name__,
        )
        return None
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    log_event(
        _esbuild_log,
        logging.INFO,
        "classic",
        bundle=label,
        externals=len(static_externals),
        chars=len(classic),
        elapsed=f"{time.monotonic() - t0:.3f}",
    )
    return classic


_ESBUILD_PATH: str | None = None


def _get_esbuild_path() -> str | None:
    global _ESBUILD_PATH  # noqa: PLW0603 -- Updates process-wide state shared by callers of this module.
    if _ESBUILD_PATH is not None:
        return _ESBUILD_PATH
    odoo_root = Path(odoo.__path__[0]).parent
    _ESBUILD_PATH = shutil.which(
        "esbuild", path=str(odoo_root / "node_modules" / ".bin")
    ) or shutil.which("esbuild")
    return _ESBUILD_PATH


_ESBUILD_VERSIONS: dict[str, str] = {}


def get_esbuild_version() -> str:
    esbuild = _get_esbuild_path()
    if esbuild is None:
        return ""
    version = _ESBUILD_VERSIONS.get(esbuild)
    if version is None:
        try:
            version = subprocess.run(
                [esbuild, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                check=True,
            ).stdout.strip()
        except OSError, subprocess.SubprocessError:
            _debug.lifecycle("esbuild.version_probe_failed", path=esbuild)
            return ""
        _ESBUILD_VERSIONS[esbuild] = version
        _debug.lifecycle("esbuild.version_probed", path=esbuild, version=version)
    return version


def minify_js(
    source: str,
    *,
    label: str = "<asset>",
    timeout_s: int = 60,
    keep_names: bool = False,
) -> str | None:
    esbuild_bin = _get_esbuild_path()
    if not esbuild_bin:
        log_event(_esbuild_log, logging.WARNING, "minify_no_binary", asset=label)
        return None
    argv = [
        esbuild_bin,
        "--minify",
        *(["--keep-names"] if keep_names else []),
        "--loader=js",
        f"--target={EsbuildCompiler._ESBUILD_TARGET}",
        "--charset=utf8",
        "--legal-comments=inline",
        "--log-level=error",
    ]
    t0 = time.monotonic()
    try:
        result = subprocess.run(
            argv,
            input=source,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired:
        log_event(
            _esbuild_log,
            logging.WARNING,
            "minify_timeout",
            asset=label,
            timeout_s=timeout_s,
        )
        return None
    if result.returncode != 0:
        log_event(
            _esbuild_log,
            logging.WARNING,
            "minify_failed",
            asset=label,
            exit=result.returncode,
        )
        _esbuild_log.warning("esbuild minify stderr for %s:\n%s", label, result.stderr)
        return None
    log_event(
        _esbuild_log,
        logging.DEBUG,
        "minify",
        asset=label,
        in_kb=f"{len(source) / 1024:.0f}",
        out_kb=f"{len(result.stdout) / 1024:.0f}",
        elapsed=f"{time.monotonic() - t0:.3f}",
    )
    return result.stdout.strip()


class EsbuildCompiler:
    def __init__(
        self,
        name: str,
        native_modules: Iterable[EntryAsset],
        javascripts: Iterable[EntryAsset] = (),
        *,
        import_map_included: bool = False,
        skip_legacy_test_imports: bool = False,
        standalone: bool = False,
        addon_flags_provider: Callable[[Path], tuple[list[str], list[str]]]
        | None = None,
        exported_specs: Collection[str] | None = None,
        registered_reach: Mapping[str, str] | None = None,
    ) -> None:
        self.name = name
        self.native_modules = list(native_modules)
        self.javascripts = list(javascripts)
        self._import_map_included = import_map_included
        self._skip_legacy_test_imports = skip_legacy_test_imports
        self._standalone = standalone
        self._exported_specs = (
            None if exported_specs is None else frozenset(exported_specs)
        )
        self._registered_reach = dict(registered_reach or {})
        self._addon_flags_provider = (
            addon_flags_provider or self._get_esbuild_addon_flags
        )
        self._mirror_roots: dict[str, Path] = {}
        self._resolution_roots: dict[str, Path] = {}
        self._preserves_symlinks = False
        self._absolute_entry_paths = False

    _esbuild_addon_scan_cache: (
        tuple[tuple[Path, tuple[Path, ...]], list[str], list[str]] | None
    ) = None

    @classmethod
    def invalidate_addon_scan_cache(cls) -> None:
        _debug.lifecycle(
            "esbuild.addon_scan_invalidated",
            cached=cls._esbuild_addon_scan_cache is not None,
        )
        cls._esbuild_addon_scan_cache = None

    @classmethod
    def resolves_specifier(cls, spec: str) -> bool:
        from odoo.tools.assets.esm_registry import external_bare_specifiers

        return spec.startswith(EXTERNAL_SPECIFIER_PREFIX) or spec in (
            external_bare_specifiers()
        )

    @classmethod
    def _get_esbuild_addon_flags(cls, odoo_root: Path) -> tuple[list[str], list[str]]:
        from odoo.addons import __path__ as _addon_paths

        addon_paths = tuple(Path(path).absolute() for path in _addon_paths)
        cache_key = (odoo_root.absolute(), addon_paths)
        cached = cls._esbuild_addon_scan_cache
        if cached and cached[0] == cache_key:
            return list(cached[1]), list(cached[2])

        alias_flags: list[str] = []
        test_external_flags: list[str] = []
        seen_addons: set[str] = set()
        for addon_dir in addon_paths:
            if not addon_dir.is_dir():
                continue
            for entry in addon_dir.iterdir():
                name = entry.name
                if name in seen_addons or not entry.is_dir():
                    continue
                if not (MODULE_NAME_RE.match(name) and Manifest._from_path(str(entry))):
                    continue
                seen_addons.add(name)
                static_src = entry / "static" / "src"
                if static_src.is_dir():
                    rel = os.path.relpath(static_src, odoo_root)
                    alias_flags.append(f"--alias:@{name}=./{rel}")
                if (entry / "static" / "tests").is_dir():
                    test_external_flags.append(f"--external:@{name}/../tests/*")
                    rel_tests = os.path.relpath(
                        entry / "static" / "tests",
                        odoo_root,
                    )
                    test_external_flags.append(f"--external:./{rel_tests}/*")

        cls._esbuild_addon_scan_cache = (cache_key, alias_flags, test_external_flags)
        log_event(
            _esbuild_log,
            logging.DEBUG,
            "addon_scan_cached",
            aliases=len(alias_flags),
            test_externals=len(test_external_flags),
        )
        return list(alias_flags), list(test_external_flags)

    _ESBUILD_TIMEOUT_S: int = 30
    _ESBUILD_TARGET: str = "chrome154,firefox157,safari27"
    _ESBUILD_TARGET_TOKEN_RE = re.compile(r"[a-z]+\d*(?:\.\d+)*")
    _ESBUILD_SOURCE_MAPS: str = ""
    _ESBUILD_SOURCE_MAP_MODES: frozenset[str] = frozenset(
        {
            "",
            "linked",
            "external",
            "inline",
        }
    )

    def _esbuild_skip_reason(self) -> str | None:
        if not self.native_modules:
            return "no_native_modules"
        if self._import_map_included:
            return "import_map_included"
        return None

    def _esbuild_external_flags(
        self, odoo_root: Path, alias_flags: list[str]
    ) -> tuple[list[str], list[str]]:
        from odoo.tools.assets.esm_registry import external_bare_specifiers

        if self._standalone:
            alias_flags += self._standalone_alias_flags(
                odoo_root,
                {
                    flag.partition("=")[0].removeprefix("--alias:")
                    for flag in alias_flags
                },
            )
            return [], alias_flags
        return [
            f"--external:{EXTERNAL_SPECIFIER_PREFIX}*",
            "--external:/web/static/lib/*",
            *(f"--external:{spec}" for spec in sorted(external_bare_specifiers())),
        ], alias_flags

    def compile(
        self,
        timeout_s: int | None = None,
        target: str | None = None,
        source_maps: str | None = None,
        dynamic_child_specs: frozenset[str] | None = None,
        secondary_parent_stubs: dict[str, str] | None = None,
    ) -> EsbuildResult:
        timeout_s, target, source_maps = self._esbuild_resolve_opts(
            timeout_s, target, source_maps
        )
        if reason := self._esbuild_skip_reason():
            log_event(
                _esbuild_log, logging.DEBUG, "skip", bundle=self.name, reason=reason
            )
            return EsbuildResult("", None, None)

        _t0 = time.monotonic()

        odoo_root = Path(odoo.__path__[0]).parent
        esbuild = _get_esbuild_path()
        if not esbuild:
            raise FileNotFoundError(
                "esbuild is required for native ESM bundling. "
                "Run 'npm install' in the Odoo root directory."
            )

        tmp_dir = tempfile.mkdtemp(prefix=f"odoo-esbuild-{self.name}-")
        try:
            with _debug.perf(
                "esbuild.compile_prepared",
                bundle=self.name,
                modules=len(self.native_modules),
                standalone=self._standalone,
                dynamic_children=len(dynamic_child_specs or ()),
                parent_stubs=len(secondary_parent_stubs or {}),
            ) as span:
                alias_flags, external_flags = self._esbuild_flags(
                    odoo_root, dynamic_child_specs
                )

                out_path = str(Path(tmp_dir) / "bundle.out.js")
                metafile_path = str(Path(tmp_dir) / "bundle.meta.json")

                self._mirror_roots = {}
                addon_flags = list(alias_flags)
                argv_aliases, node_path = self._addon_resolution_root(
                    alias_flags, odoo_root, tmp_dir
                )
                moved = set(alias_flags) - set(argv_aliases)
                if secondary_parent_stubs:
                    alias_flags, self._mirror_roots = esbuild_stubs.mirror_aliases(
                        self.native_modules,
                        list(alias_flags),
                        secondary_parent_stubs,
                        tmp_dir,
                        odoo_root,
                    )
                self._preserves_symlinks = bool(self._mirror_roots)
                alias_flags = self._file_aliases_through_root(
                    [flag for flag in alias_flags if flag not in moved],
                    addon_flags,
                    node_path,
                    odoo_root,
                )

                entry_modules = [
                    asset
                    for asset in self.native_modules
                    if asset.module_path not in (secondary_parent_stubs or {})
                ]
                entry_lines = self._esbuild_entry_lines(
                    odoo_root, modules=entry_modules
                )
                entry_text = "\n".join(entry_lines)
                entry_bytes = len(entry_text.encode("utf-8"))
                span.set(
                    aliases=len(alias_flags),
                    externals=len(external_flags),
                    moved=len(moved),
                    entries=len(entry_lines),
                    node_path=node_path is not None,
                )

            esbuild_process.log_invoke(
                self.name,
                entry_lines,
                entry_bytes,
                alias_flags,
                external_flags,
                tmp_dir,
            )
            sourcemap_flags = [f"--sourcemap={source_maps}"] if source_maps else []
            sourcemap_path = f"{out_path}.map"
            external_specifier_flags, alias_flags = self._esbuild_external_flags(
                odoo_root, alias_flags
            )
            argv = _esbuild_argv(
                esbuild,
                target=target,
                out_path=out_path,
                metafile_path=metafile_path,
                external_specifier_flags=external_specifier_flags,
                external_flags=external_flags,
                sourcemap_flags=sourcemap_flags,
                alias_flags=alias_flags,
                extra_flags=["--preserve-symlinks"] if self._preserves_symlinks else [],
            )
            esbuild_process.run_esbuild(
                self.name, argv, timeout_s, entry_text, _t0, node_path=node_path
            )
            code, metafile, sourcemap = esbuild_process.postprocess_output(
                self.name,
                len(self.native_modules),
                out_path,
                metafile_path,
                sourcemap_path,
                source_maps,
                entry_bytes,
                _t0,
            )
            return EsbuildResult(code, metafile, sourcemap)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def _esbuild_entry_files(
        self, entries: dict[str, list[EntryAsset]], entry_dir: Path, odoo_root: Path
    ) -> dict[str, str]:
        entry_texts = {}
        for name, modules in entries.items():
            if not modules:
                continue
            text = "\n".join(self._esbuild_entry_lines(odoo_root, modules, name))
            entry_file = entry_dir / f"{name}.js"
            entry_file.write_text(text, encoding="utf-8")
            entry_texts[str(entry_file)] = text
        return entry_texts

    def compile_group(
        self,
        entries: dict[str, list[EntryAsset]],
        *,
        timeout_s: int | None = None,
        target: str | None = None,
        source_maps: str | None = None,
        secondary_parent_stubs: dict[str, str] | None = None,
    ) -> EsbuildGroupResult:
        timeout_s, target, source_maps = self._esbuild_resolve_opts(
            timeout_s, target, source_maps
        )
        if not any(entries.values()):
            _debug.logic("esbuild.group_empty", bundle=self.name, groups=len(entries))
            return EsbuildGroupResult({}, None)
        _t0 = time.monotonic()
        _debug.pipeline(
            "esbuild.compile_group",
            bundle=self.name,
            groups=len(entries),
            modules=sum(len(m) for m in entries.values()),
            parent_stubs=len(secondary_parent_stubs or {}),
        )
        odoo_root = Path(odoo.__path__[0]).parent
        esbuild = _get_esbuild_path()
        if not esbuild:
            raise FileNotFoundError(
                "esbuild is required for native ESM bundling. "
                "Run 'npm install' in the Odoo root directory."
            )
        alias_flags, external_flags = self._esbuild_flags(odoo_root, None)
        tmp_dir = tempfile.mkdtemp(prefix=f"odoo-esbuild-{self.name}-")
        try:
            out_dir = Path(tmp_dir) / "out"
            entry_dir = Path(tmp_dir) / "entries"
            entry_dir.mkdir()
            metafile_path = str(Path(tmp_dir) / "group.meta.json")
            self._mirror_roots = {}
            self._preserves_symlinks = True
            self._absolute_entry_paths = True
            addon_flags = list(alias_flags)
            argv_aliases, node_path = self._addon_resolution_root(
                alias_flags, odoo_root, tmp_dir
            )
            moved = set(alias_flags) - set(argv_aliases)
            mirrored_flags, self._mirror_roots = esbuild_stubs.mirror_aliases(
                self.native_modules,
                list(alias_flags),
                secondary_parent_stubs or {},
                tmp_dir,
                odoo_root,
            )
            alias_flags = self._file_aliases_through_root(
                [flag for flag in mirrored_flags if flag not in moved],
                addon_flags,
                node_path,
                odoo_root,
            )
            entry_texts = self._esbuild_entry_files(entries, entry_dir, odoo_root)
            entry_points = list(entry_texts)
            entry_bytes = sum(
                len(text.encode("utf-8")) for text in entry_texts.values()
            )
            external_specifier_flags, alias_flags = self._esbuild_external_flags(
                odoo_root, alias_flags
            )
            argv = _esbuild_argv(
                esbuild,
                target=target,
                out_path=None,
                metafile_path=metafile_path,
                external_specifier_flags=external_specifier_flags,
                external_flags=external_flags,
                sourcemap_flags=([f"--sourcemap={source_maps}"] if source_maps else []),
                alias_flags=alias_flags,
                extra_flags=["--preserve-symlinks"],
                entry_points=entry_points,
                out_dir=str(out_dir),
            )
            esbuild_process.log_invoke(
                self.name,
                entry_points,
                entry_bytes,
                alias_flags,
                external_flags,
                tmp_dir,
            )
            esbuild_process.run_esbuild(
                self.name,
                argv,
                timeout_s,
                "",
                _t0,
                node_path=node_path,
                entry_dump="".join(
                    f"// {Path(path).name}\n{text}\n"
                    for path, text in entry_texts.items()
                ),
            )
            files, metafile = esbuild_process.get_group_output(
                self.name,
                out_dir,
                metafile_path,
                len(entry_points),
                sum(len(m) for m in entries.values()),
                _t0,
            )
            return EsbuildGroupResult(files, metafile)
        finally:
            self._absolute_entry_paths = False
            self._preserves_symlinks = False
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def _esbuild_resolve_opts(
        self,
        timeout_s: int | None,
        target: str | None,
        source_maps: str | None,
    ) -> tuple[int, str, str]:
        if timeout_s is None:
            timeout_s = self._ESBUILD_TIMEOUT_S
        if target is None:
            target = self._ESBUILD_TARGET
        elif not all(
            self._ESBUILD_TARGET_TOKEN_RE.fullmatch(token.strip())
            for token in target.split(",")
        ):
            log_event(
                _esbuild_log,
                logging.WARNING,
                "target_invalid",
                bundle=self.name,
                target=target,
                fallback=self._ESBUILD_TARGET,
            )
            target = self._ESBUILD_TARGET
        if source_maps is None:
            source_maps = self._ESBUILD_SOURCE_MAPS
        if source_maps not in self._ESBUILD_SOURCE_MAP_MODES:
            log_event(
                _esbuild_log,
                logging.WARNING,
                "source_maps_unknown_mode",
                bundle=self.name,
                mode=source_maps,
                valid=sorted(m for m in self._ESBUILD_SOURCE_MAP_MODES if m),
            )
            source_maps = ""
        return timeout_s, target, source_maps

    def _reached_module_path(self, url: str, odoo_root: Path) -> str | None:
        from odoo.tools.files import file_path

        rel = url.lstrip("/")
        for candidate in (rel, rel.removesuffix(".js") + "/index.js"):
            try:
                path = file_path(candidate)
            except ValueError, FileNotFoundError:
                continue
            return self._mirrored_path(candidate) or (
                "./" + os.path.relpath(path, odoo_root)
            )
        return None

    def _mirrored_path(self, url: str) -> str | None:
        addon, _, rest = url.lstrip("/").partition("/static/")
        if not rest:
            return None
        mirror = self._mirror_roots.get(addon)
        if mirror is not None:
            return str(mirror.parent / rest)
        root = self._resolution_roots.get(addon) if self._preserves_symlinks else None
        if root is None or not rest.startswith("src/"):
            return None
        return str(root / rest.removeprefix("src/"))

    def _standalone_alias_flags(
        self, odoo_root: Path, already_aliased: set[str]
    ) -> list[str]:
        from odoo.tools.assets.esm_registry import external_libs
        from odoo.tools.files import file_path

        flags = []
        for spec, url in sorted(external_libs().items()):
            if spec in already_aliased or spec == OWL_COMPILER_SPECIFIER:
                continue
            if spec == "@odoo/owl":
                url = OWL_FULL_BUILD_URL
            try:
                path = file_path(url.lstrip("/"))
            except ValueError, FileNotFoundError:
                continue
            flags.append(f"--alias:{spec}=./{os.path.relpath(path, odoo_root)}")
        return flags

    def _imports_owl(self) -> bool:
        return any(
            "@odoo/owl" in (asset.raw_content or "") for asset in self.native_modules
        )

    def _entry_path(self, asset: EntryAsset, odoo_root: Path) -> str:
        url = asset.url or ""
        mirrored = self._mirrored_path(url)
        if mirrored is not None:
            return mirrored
        if self._absolute_entry_paths:
            return str(
                Path(asset._filename) if asset._filename else odoo_root / f"addons{url}"
            )
        if asset._filename:
            return "./" + os.path.relpath(asset._filename, odoo_root)
        return f"./addons{url}"

    def _esbuild_entry_lines(
        self,
        odoo_root: Path,
        modules: list[EntryAsset] | None = None,
        bundle: str | None = None,
    ) -> list[str]:
        entry_lines = []
        register_entries = []
        registered_specs: set[str] = set()
        if not self._standalone or self._imports_owl():
            registered_specs.add("@odoo/owl")
            entry_lines.append('import * as __owl from "@odoo/owl";')
            register_entries.append('  "@odoo/owl": __owl')
        _skip_legacy_test_imports = self._skip_legacy_test_imports
        modules = self.native_modules if modules is None else modules
        exported = self._exported_specs
        for i, asset in enumerate(modules):
            if _skip_legacy_test_imports and "/static/tests/" in (asset.url or ""):
                continue
            path = self._entry_path(asset, odoo_root)
            names = module_specifiers(asset)
            if exported is not None and exported.isdisjoint(names):
                entry_lines.append(f"import {json.dumps(path)};")
                continue
            entry_lines.append(f"import * as __m{i} from {json.dumps(path)};")
            for name in names:
                register_entries.append(f"  {json.dumps(name)}: __m{i}")
                registered_specs.add(name)
        for i, (spec, url) in enumerate(sorted(self._registered_reach.items())):
            if spec in registered_specs:
                continue
            reached = self._reached_module_path(url, odoo_root)
            if reached is None:
                continue
            entry_lines.append(f"import * as __r{i} from {json.dumps(reached)};")
            register_entries.append(f"  {json.dumps(spec)}: __r{i}")
            registered_specs.add(spec)

        if self._standalone:
            entry_lines.append("if (globalThis.odoo?.loader?.registerNativeModules) {")
        entry_lines.append("odoo.loader.registerNativeModules({")
        entry_lines.append(",\n".join(register_entries))
        entry_lines.append(f"}}, {json.dumps(bundle or self.name)});")
        from odoo.tools.assets.esm_registry import external_lib_aliases

        for ext_name, int_name in external_lib_aliases().items():
            if int_name in registered_specs:
                entry_lines.append(
                    f"odoo.loader.registerNativeModules({{{json.dumps(ext_name)}:"
                    f"odoo.loader.modules.get({json.dumps(int_name)})}});"
                )
        if self._standalone:
            entry_lines.append("}")
        return entry_lines

    def _esbuild_flags(
        self,
        odoo_root: Path,
        dynamic_child_specs: frozenset[str] | None,
    ) -> tuple[list[str], list[str]]:
        alias_flags, test_external_flags = self._addon_flags_provider(odoo_root)
        bundle_test_addons: set[str] = set()
        for asset in self.native_modules:
            url = (asset.url or "").lstrip("/")
            parts = url.split("/")
            if len(parts) >= 3 and parts[1] == "static" and parts[2] == "tests":
                bundle_test_addons.add(parts[0])
        if not self._reaches_test_files(bundle_test_addons):
            test_external_flags = []
        if bundle_test_addons:
            test_external_flags = [
                flag
                for flag in test_external_flags
                if not any(
                    f"--external:@{name}/../tests/" in flag
                    or f"/{name}/static/tests/" in flag
                    for name in bundle_test_addons
                )
            ]
        dynamic_external_flags: list[str] = []
        if dynamic_child_specs:
            dynamic_external_flags.extend(
                f"--external:{spec}" for spec in sorted(dynamic_child_specs)
            )

        for js_asset in self.javascripts + self.native_modules:
            header = js_asset.parsed_header
            if header and header["alias"] and header["alias"].startswith("@odoo/"):
                if js_asset._filename:
                    alias_path = os.path.relpath(js_asset._filename, odoo_root)
                else:
                    alias_path = f"addons{js_asset.url}"
                alias_flags.append(f"--alias:{header['alias']}=./{alias_path}")
        return alias_flags, test_external_flags + dynamic_external_flags

    def _reaches_test_files(self, bundle_test_addons: set[str]) -> bool:
        if self._skip_legacy_test_imports or bundle_test_addons:
            return True
        return any(
            "/../tests/" in (asset.raw_content or "") for asset in self.native_modules
        )

    _PARENT_DIR_SPECIFIER_RE = re.compile(r'["\'](@[\w.-]+)/\.\./')

    def _addons_reached_through_parent_dirs(self) -> set[str]:
        return {
            match.group(1)
            for asset in (*self.native_modules, *self.javascripts)
            for match in self._PARENT_DIR_SPECIFIER_RE.finditer(asset.raw_content or "")
        }

    @staticmethod
    def _file_aliases_through_root(
        alias_flags: list[str],
        addon_flags: list[str],
        node_path: str | None,
        odoo_root: Path,
    ) -> list[str]:
        def parse(flag: str) -> tuple[str, str]:
            spec, _, target = flag.removeprefix("--alias:").partition("=")
            return spec, target

        def addon_dir(target: str) -> Path:
            if target.startswith("./"):
                return odoo_root / target.removeprefix("./")
            return Path(target)

        real_roots = {
            spec: addon_dir(target)
            for spec, target in map(parse, addon_flags)
            if spec.startswith("@") and "/" not in spec
        }
        resolved = {
            spec: addon_dir(target)
            for spec, target in map(parse, alias_flags)
            if spec.startswith("@") and "/" not in spec
        }
        if node_path is not None:
            for spec in real_roots.keys() - resolved.keys():
                resolved[spec] = Path(node_path) / spec
        routed = []
        for flag in alias_flags:
            spec, target = parse(flag)
            if spec.startswith(EXTERNAL_SPECIFIER_PREFIX) and target.startswith("./"):
                path = addon_dir(target)
                for addon_spec, real_root in real_roots.items():
                    if addon_spec in resolved and path.is_relative_to(real_root):
                        rel = path.relative_to(real_root)
                        flag = f"--alias:{spec}={resolved[addon_spec] / rel}"
                        break
            routed.append(flag)
        return routed

    def _addon_resolution_root(
        self, alias_flags: list[str], odoo_root: Path, private_dir: str
    ) -> tuple[list[str], str | None]:
        roots: dict[str, Path] = {}
        kept: list[str] = []
        keep_aliased = self._addons_reached_through_parent_dirs()
        self._resolution_roots = {}
        for flag in alias_flags:
            spec, _, target = flag.removeprefix("--alias:").partition("=")
            if (
                spec.startswith("@")
                and "/" not in spec
                and target.startswith("./")
                and target.endswith("/static/src")
            ):
                roots[spec] = odoo_root / target.removeprefix("./")
                if spec in keep_aliased:
                    kept.append(flag)
            else:
                kept.append(flag)
        if not roots:
            return kept, None
        digest = hashlib.sha1(
            "\n".join(f"{spec}={path}" for spec, path in sorted(roots.items())).encode()
        ).hexdigest()[:12]
        base = Path(config["data_dir"]) / "esbuild-roots"
        try:
            _create_private_dir(base)
            root_dir = _shared_resolution_root(base, digest, roots)
        except OSError as exc:
            root_dir = _write_resolution_root(Path(private_dir) / "roots", roots)
            _debug.logic(
                "esbuild.resolution_root_private",
                bundle=self.name,
                base=str(base),
                error=type(exc).__name__,
            )
        self._resolution_roots = {
            spec.removeprefix("@"): Path(root_dir) / spec
            for spec in roots
            if spec not in keep_aliased
        }
        return kept, str(root_dir)
