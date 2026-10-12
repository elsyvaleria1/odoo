import annotationlib
import inspect
import itertools
import json
import logging
import re
import typing
from collections import defaultdict
from pathlib import Path

import odoo.upgrade
from odoo import release
from odoo.db import schema
from odoo.libs.debug_log import DebugLog
from odoo.libs.json import loads as json_loads
from odoo.libs.parse_version import parse_version
from odoo.modules.module import Manifest, adapt_version, load_script
from odoo.tools.files import file_path

if typing.TYPE_CHECKING:
    from collections.abc import Iterator

    from odoo.db import Cursor

    from .module_graph import ModuleGraph, ModuleNode
else:
    ModuleGraph = ModuleNode = typing.Any
    Cursor = typing.Any

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)


VERSION_RE = re.compile(
    r"""^
        # Optional prefix with Odoo version
        ((
            6\.1|

            # "x.0" version, with x >= 6.
            [6-9]\.0|

            # multi digits "x.0" versions
            [1-9]\d+\.0|

            # x.saas~y, where x >= 7 and x <= 10
            (7|8|9|10)\.saas~[1-9]\d*|

            # saas~x.y, where x >= 11 (any number of digits) and y between 1 and 9
            saas~(1[1-9]|[2-9]\d|[1-9]\d{2,})\.[1-9]
        )\.)?
        # After Odoo version we allow precisely 2 or 3 parts
        # note this will also allow 0.0.0 which has a special meaning
        \d+\.\d+(\.\d+)?
    $""",
    re.VERBOSE | re.ASCII,
)


MIGRATION_STAGES: tuple[str, ...] = ("pre", "post", "end")

_STAGE_PREFIXES: tuple[str, ...] = tuple(f"{stage}-" for stage in MIGRATION_STAGES)


def _warn_unstaged_scripts(directory: Path, files: list[str]) -> None:
    for path in files:
        name = Path(path).name
        if name.startswith(_STAGE_PREFIXES) or name == "__init__.py":
            continue
        _debug.logic("migration.unstaged_script", path=path)
        _logger.warning(
            "Migration script %s will never run: its name matches no stage. "
            "Rename it to one of %s (lower-case, hyphen) or move it out of %s.",
            path,
            ", ".join(f"{p}*.py" for p in _STAGE_PREFIXES),
            directory,
        )


def _convert_version(version: str) -> str:
    if version == "0.0.0":
        return version
    serie = release.major_version
    if version == serie or version.startswith(serie + "."):
        return version
    if version.count(".") > 2:
        return version
    return f"{serie}.{version}"


def _is_migration_applicable(
    version: str, installed_version: str, target_version: str
) -> bool:
    parsed_installed = parse_version(installed_version or "")
    parsed_target = parse_version(_convert_version(target_version))

    if version == "0.0.0" and parsed_installed < parsed_target:
        return True

    full_version = _convert_version(version)
    if version != full_version:
        return (
            parsed_installed[2:] < parse_version(full_version)[2:] <= parsed_target[2:]
        )

    return parsed_installed < parse_version(full_version) <= parsed_target


class ModuleOlderThanUpgradable(typing.NamedTuple):
    name: str
    installed_version: str
    oldest_upgradable_version: str


def is_older_than_upgradable(
    installed_version: str | None, oldest_upgradable_version: str
) -> bool:
    if not oldest_upgradable_version:
        return False
    return parse_version(installed_version or "") < parse_version(
        _convert_version(oldest_upgradable_version)
    )


class DatabaseOlderThanUpgradableError(RuntimeError):
    def __init__(self, db_name: str, modules: list[ModuleOlderThanUpgradable]) -> None:
        self.db_name = db_name
        self.modules = modules
        listed = "; ".join(
            f"{m.name} {m.installed_version or '(no version)'} is older than "
            f"{m.oldest_upgradable_version}"
            for m in modules
        )
        super().__init__(
            f"database {db_name!r} cannot be updated by this code: {listed}. "
            f"The migrations from those versions up to the oldest upgradable ones "
            f"were deleted from this checkout, so an upgrade would skip them "
            f"without error. Upgrade the database first with a checkout that "
            f"still ships them (one from before the deletion), to at least the "
            f"versions named, then run this again. Nothing was changed."
        )


def _read_installed_versions(cr: Cursor) -> list[tuple[str, str | None]]:
    if schema.column_exists(cr, "ir_module_module", "db_version"):
        cr.execute(
            "SELECT name, db_version FROM ir_module_module"
            " WHERE state IN ('installed', 'to upgrade') ORDER BY name"
        )
    else:
        cr.execute(
            "SELECT name, latest_version FROM ir_module_module"
            " WHERE state IN ('installed', 'to upgrade') ORDER BY name"
        )
    return cr.fetchall()


def get_base_ahead_of_database(cr: Cursor) -> tuple[str, str] | None:
    installed = dict(_read_installed_versions(cr)).get("base")
    manifest = Manifest.for_addon("base", display_warning=False)
    if not installed or not manifest or not manifest.get("version"):
        return None
    code = adapt_version(manifest["version"])
    if parse_version(code) > parse_version(installed):
        return installed, code
    return None


def get_modules_older_than_upgradable(cr: Cursor) -> list[ModuleOlderThanUpgradable]:
    too_old = []
    for name, installed_version in _read_installed_versions(cr):
        manifest = Manifest.for_addon(name, display_warning=False)
        oldest = manifest["oldest_upgradable_version"] if manifest else ""
        if is_older_than_upgradable(installed_version, oldest):
            too_old.append(
                ModuleOlderThanUpgradable(name, installed_version or "", oldest)
            )
    _debug.logic(
        "migration.oldest_upgradable_checked",
        db=cr.dbname,
        too_old=[m.name for m in too_old],
    )
    return too_old


def _iter_upgrade_paths(pkg: str) -> Iterator[str]:
    for path in odoo.upgrade.__path__:
        upgrade_path = Path(path, pkg)
        if upgrade_path.exists():
            yield str(upgrade_path)


def _is_upgrade_version_dir(path: str, version: str) -> bool:
    full_path = Path(path, version)
    if not full_path.is_dir():
        return False
    if version == "tests":
        return False
    if not VERSION_RE.match(version):
        _debug.logic("migration.invalid_version_dir", path=str(full_path))
        _logger.warning("Invalid version for upgrade script %r", str(full_path))
        return False
    return True


def _get_scripts_by_version(path: str) -> dict[str, list[str]]:
    if not path:
        return {}
    p = Path(path)
    by_version = {
        entry.name: [str(f) for f in (p / entry.name).glob("*.py")]
        for entry in p.iterdir()
        if _is_upgrade_version_dir(path, entry.name)
    }
    for version, files in by_version.items():
        _warn_unstaged_scripts(p / version, files)
    _debug.perf.count(
        "migration.scripts_indexed",
        path=path,
        versions=len(by_version),
        scripts=sum(len(files) for files in by_version.values()),
    )
    return by_version


def _get_addon_path(path: str) -> str:
    try:
        return file_path(path)
    except FileNotFoundError:
        return ""


PENDING_END_MIGRATIONS_KEY = "base.pending_end_migrations"


def read_pending_end_migrations(cr: Cursor) -> dict[str, str]:
    if not schema.table_exists(cr, "ir_config_parameter"):
        return {}
    cr.execute(
        "SELECT value FROM ir_config_parameter WHERE key = %s",
        [PENDING_END_MIGRATIONS_KEY],
    )
    row = cr.fetchone()
    return json_loads(row[0]) if row and row[0] else {}


def _write_pending_end_migrations(cr: Cursor, pending: dict[str, str]) -> None:
    if not pending:
        cr.execute(
            "DELETE FROM ir_config_parameter WHERE key = %s",
            [PENDING_END_MIGRATIONS_KEY],
        )
        return
    cr.execute(
        "INSERT INTO ir_config_parameter "
        "(key, value, create_uid, write_uid, create_date, write_date) "
        "VALUES (%s, %s, 1, 1, now() AT TIME ZONE 'UTC', now() AT TIME ZONE 'UTC') "
        "ON CONFLICT (key) DO UPDATE "
        "SET value = EXCLUDED.value, write_date = EXCLUDED.write_date",
        [PENDING_END_MIGRATIONS_KEY, json.dumps(pending, sort_keys=True)],
    )


class MigrationManager:
    migrations: dict[str, dict[str, dict[str, list[str]]]]
    pending_end: dict[str, str]

    def __init__(
        self,
        cr: Cursor,
        graph: ModuleGraph,
        pending_end: dict[str, str] | None = None,
    ) -> None:
        self.cr = cr
        self.graph = graph
        self.migrations = {}
        self.pending_end = dict(pending_end or {})
        self.index_migration_scripts()

    def _is_migration_required(self, pkg: ModuleNode, stage: str | None = None) -> bool:
        if pkg.load_state == "to upgrade":
            return True
        return stage in (None, "end") and pkg.name in self.pending_end

    def _get_installed_version(self, pkg: ModuleNode, stage: str) -> str:
        if stage == "end" and pkg.name in self.pending_end:
            return self.pending_end[pkg.name]
        return pkg.load_version or ""

    def record_pending_end_migrations(self, pkg: ModuleNode) -> None:
        if pkg.load_state != "to upgrade" or pkg.name in self.pending_end:
            return
        if not self._has_applicable_scripts(pkg, "end"):
            return
        self.pending_end[pkg.name] = pkg.load_version or ""
        _write_pending_end_migrations(self.cr, self.pending_end)
        _debug.lifecycle(
            "migration.end_pending",
            module=pkg.name,
            installed=pkg.load_version,
        )

    def clear_pending_end_migrations(self, names: typing.Iterable[str]) -> None:
        cleared = self.pending_end.keys() & set(names)
        if not cleared:
            return
        for name in cleared:
            del self.pending_end[name]
        _write_pending_end_migrations(self.cr, self.pending_end)
        _debug.lifecycle("migration.end_cleared", modules=len(cleared))

    def _has_applicable_scripts(self, pkg: ModuleNode, stage: str) -> bool:
        sources = self.migrations.get(pkg.name, {})
        installed_version = self._get_installed_version(pkg, stage)
        target_version = pkg.manifest["version"]
        return any(
            Path(f).name.startswith(f"{stage}-")
            and _is_migration_applicable(version, installed_version, target_version)
            for by_version in sources.values()
            for version, files in by_version.items()
            for f in files
        )

    def index_migration_scripts(self) -> None:
        with _debug.perf(
            "migration.index", graph=len(self.graph), indexed=len(self.migrations)
        ) as span:
            added = 0
            for pkg in self.graph:
                if pkg.name in self.migrations:
                    continue
                if not self._is_migration_required(pkg):
                    continue

                added += 1
                self.migrations[pkg.name] = {
                    "module": _get_scripts_by_version(
                        _get_addon_path(pkg.name + "/migrations")
                    ),
                    "module_upgrades": _get_scripts_by_version(
                        _get_addon_path(pkg.name + "/upgrades")
                    ),
                }

                scripts = defaultdict(list)
                for p in _iter_upgrade_paths(pkg.name):
                    for v, s in _get_scripts_by_version(p).items():
                        scripts[v].extend(s)
                self.migrations[pkg.name]["upgrade"] = scripts
                _debug.lifecycle(
                    "migration.module_indexed",
                    module=pkg.name,
                    installed=getattr(pkg, "load_version", None),
                    target=getattr(pkg, "manifest", {}).get("version"),
                    versions=len(
                        {
                            version
                            for source in self.migrations[pkg.name].values()
                            for version in source
                        }
                    ),
                )
            span.set(added=added)

    def migrate_module(
        self,
        pkg: ModuleNode,
        stage: typing.Literal["pre", "post", "end"],
    ) -> None:
        if stage not in MIGRATION_STAGES:
            raise ValueError(f"invalid migration stage {stage!r}")
        stageformat = {
            "pre": "[>%s]",
            "post": "[%s>]",
            "end": "[$%s]",
        }
        if not self._is_migration_required(pkg, stage):
            return

        def _get_migration_versions(pkg: ModuleNode, stage: str) -> list[str]:
            versions = sorted(
                {
                    ver
                    for lv in self.migrations[pkg.name].values()
                    for ver, lf in lv.items()
                    if lf
                },
                key=lambda k: parse_version(_convert_version(k)),
            )
            if "0.0.0" in versions:
                versions.remove("0.0.0")
                if stage == "pre":
                    versions.insert(0, "0.0.0")
                else:
                    versions.append("0.0.0")
            return versions

        def _get_migration_files(
            pkg: ModuleNode, version: str, stage: str
        ) -> list[str]:
            m = self.migrations[pkg.name]

            return sorted(
                (
                    f
                    for k in m
                    for f in m[k].get(version, [])
                    if Path(f).name.startswith(f"{stage}-")
                ),
                key=lambda f: (Path(f).name, f),
            )

        installed_version = self._get_installed_version(pkg, stage)
        target_version = pkg.manifest["version"]

        versions = _get_migration_versions(pkg, stage)
        _debug.logic(
            "migration.versions",
            module=pkg.name,
            stage=stage,
            installed=installed_version,
            target=target_version,
            versions=len(versions),
            applicable=sum(
                1
                for version in versions
                if _is_migration_applicable(version, installed_version, target_version)
            ),
        )
        scripts_run = 0
        for version in versions:
            if not _is_migration_applicable(version, installed_version, target_version):
                continue
            files = _get_migration_files(pkg, version, stage)
            _debug.logic(
                "migration.version_applicable",
                module=pkg.name,
                stage=stage,
                version=version,
                scripts=len(files),
            )
            for pyfile in files:
                scripts_run += 1
                run_migration_script(
                    self.cr,
                    installed_version,
                    pyfile,
                    pkg.name,
                    stage,
                    stageformat[stage] % version,
                )
        _debug.lifecycle(
            "migration.stage_done", module=pkg.name, stage=stage, scripts=scripts_run
        )


VALID_MIGRATE_PARAMS = list(
    itertools.product(
        ["cr", "_cr"],
        ["version", "_version"],
    )
)


def run_migration_script(
    cr: Cursor,
    installed_version: str,
    pyfile: str,
    addon: str,
    stage: str,
    version: str | None = None,
) -> None:
    version = version or installed_version
    p = Path(pyfile)
    if p.suffix.lower() != ".py":
        _debug.logic("migration.script_skipped", module=addon, script=pyfile)
        _logger.warning(
            "module %s: migration script %s skipped: not a .py file",
            addon,
            pyfile,
        )
        return
    _debug.pipeline(
        "migration.script",
        module=addon,
        stage=stage,
        script=p.name,
        version=version,
        installed=installed_version,
    )
    try:
        mod = load_script(pyfile, p.stem)
    except ImportError as e:
        _debug.logic(
            "migration.script_failed",
            module=addon,
            script=p.name,
            reason="import",
            error=type(e).__name__,
        )
        raise ImportError(
            f"module {addon}: Unable to load {stage}-migration file {pyfile}"
        ) from e

    if not hasattr(mod, "migrate"):
        _debug.logic(
            "migration.script_failed", module=addon, script=p.name, reason="no_migrate"
        )
        raise AttributeError(
            f"module {addon}: Each {stage}-migration file must have a"
            f' "migrate(cr, installed_version)" function, not found in {pyfile}'
        )

    try:
        sig = inspect.signature(
            mod.migrate, annotation_format=annotationlib.Format.FORWARDREF
        )
    except TypeError as e:
        raise TypeError(
            f"module {addon}: `migrate` needs to be a function, got {mod.migrate!r}"
        ) from e

    if not (
        tuple(sig.parameters.keys()) in VALID_MIGRATE_PARAMS
        and all(
            param.kind in (param.POSITIONAL_ONLY, param.POSITIONAL_OR_KEYWORD)
            for param in sig.parameters.values()
        )
    ):
        _debug.logic(
            "migration.script_failed",
            module=addon,
            script=p.name,
            reason="signature",
            signature=str(sig),
        )
        raise TypeError(
            f"module {addon}: `migrate`'s signature should be `(cr, version)`,"
            f" {mod.migrate} is {sig}"
        )

    _logger.info("module %s: Running migration %s %s", addon, version, mod.__name__)
    with _debug.perf(
        "migration.script", cr=cr, module=addon, stage=stage, script=p.name
    ):
        mod.migrate(cr, installed_version)
