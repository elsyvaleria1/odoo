import contextlib
import logging
import re
import sys
import typing
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from odoo.db import BaseCursor, Cursor
from odoo.libs.debug_log import DebugLog
from odoo.libs.worker_thread import working_on_database
from odoo.service.settings import ServerSettings
from odoo.service.settings import current as current_settings

from . import DatabaseCommand

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)

_DDL = re.compile(r"^\s*(ALTER|CREATE|DROP|COMMENT ON|TRUNCATE)\b", re.IGNORECASE)
_META_DML = re.compile(
    r"^\s*(INSERT INTO|UPDATE|DELETE FROM)\s+\"?(ir_[a-z_]+|res_groups|res_users)\"?",
    re.IGNORECASE,
)


class _Recorder:
    def __init__(self) -> None:
        self.ddl: list[str] = []
        self.meta: Counter[str] = Counter()
        self.migrations: list[tuple[str, str, str]] = []

    def record(self, query: typing.Any) -> None:
        code = query if isinstance(query, str) else getattr(query, "code", None)
        if not isinstance(code, str):
            return
        text = " ".join(code.split())
        if _DDL.match(text):
            self.ddl.append(text)
        elif match := _META_DML.match(text):
            self.meta[f"{match.group(1).upper()} {match.group(2)}"] += 1

    def record_migration(
        self, installed_version: str, pyfile: str, addon: str, version: str | None
    ) -> None:
        self.migrations.append((addon, version or installed_version, Path(pyfile).stem))


class SchemaDiff(DatabaseCommand):
    name = "schema_diff"
    description = """
        Print the DDL and migrations an install or upgrade would commit, from a rolled-back run

        -u, -i and --reinit are the server's options and mean what they mean to it.
    """

    def __init__(self) -> None:
        super().__init__()
        self.add_config_arguments(self.parser)
        self.parser.add_argument(
            "--all",
            dest="show_all",
            action="store_true",
            help="print every DDL statement; the default folds identical shapes",
        )

    def run(self, cmdargs: list[str]) -> None:
        parsed_args, unknown = self.parse_args(cmdargs)
        db_name = self.bootstrap_config(parsed_args, extra_args=unknown)
        settings = current_settings()
        if not settings.update_module:
            self.parser.error("name at least one module with -u, -i or --reinit")
        with working_on_database(db_name):
            self._preview(db_name, settings, show_all=parsed_args.show_all)

    def _preview(
        self, db_name: str, settings: ServerSettings, *, show_all: bool
    ) -> None:
        from odoo.modules import migration
        from odoo.modules.registry import Registry

        recorder = _Recorder()
        run_migration_script = migration.run_migration_script

        def recording_migration(
            cr: Cursor,
            installed_version: str,
            pyfile: str,
            addon: str,
            stage: str,
            version: str | None = None,
        ) -> None:
            recorder.record_migration(installed_version, pyfile, addon, version)
            run_migration_script(cr, installed_version, pyfile, addon, stage, version)

        registry = Registry(db_name)
        error: BaseException | None = None
        try:
            with registry.cursor() as real:
                opened = [0]
                real_execute = real.execute

                def dry_commit() -> None:
                    real.flush()
                    real.commit_count += 1
                    real.clear()
                    real.prerollback.clear()
                    real.postrollback.clear()
                    real.postcommit.clear()

                def recording_execute(
                    query: typing.Any, *args: typing.Any, **kw: typing.Any
                ) -> None:
                    recorder.record(query)
                    return real_execute(query, *args, **kw)

                def open_dry(
                    self: typing.Any, readonly: bool = False, **kwargs: typing.Any
                ) -> BaseCursor:
                    opened[0] += 1
                    return real

                for name, callback in (
                    ("commit", dry_commit),
                    ("rollback", lambda: None),
                    ("close", lambda: None),
                    ("execute", recording_execute),
                ):
                    setattr(real, name, callback)
                with contextlib.ExitStack() as stack:
                    stack.enter_context(patch.object(Registry, "cursor", open_dry))
                    stack.enter_context(
                        patch.object(
                            migration, "run_migration_script", recording_migration
                        )
                    )
                    for name, value in (
                        ("setup_signaling", lambda self: None),
                        ("check_signaling", lambda self: self),
                        ("signal_changes", lambda self: None),
                    ):
                        stack.enter_context(patch.object(Registry, name, value))
                    try:
                        Registry.new(
                            db_name,
                            update_module=True,
                            upgrade_modules=settings.update,
                            install_modules=settings.init,
                            reinit_modules=settings.reinit,
                            run_tests=False,
                        )
                    except Exception as exc:
                        error = exc
                    finally:
                        for name in ("commit", "rollback", "close", "execute"):
                            vars(real).pop(name, None)
                        real.rollback()
        finally:
            Registry.remove(db_name)

        self._report(recorder, error, show_all=show_all)
        if error is not None:
            _logger.error("the upgrade would fail: %s", error, exc_info=error)
            sys.exit(1)

    @staticmethod
    def _report(
        recorder: _Recorder, error: BaseException | None, *, show_all: bool
    ) -> None:
        out = sys.stdout
        print(f"migrations that would run: {len(recorder.migrations)}", file=out)
        for module, version, script in recorder.migrations:
            print(f"  {module} {version} {script}", file=out)
        print(f"DDL statements that would run: {len(recorder.ddl)}", file=out)
        if show_all:
            for statement in recorder.ddl:
                print(f"  {statement}", file=out)
        else:
            shapes = Counter(_shape(statement) for statement in recorder.ddl)
            for shape, count in sorted(shapes.items()):
                print(f"  {count:5d}  {shape}", file=out)
        print("rows the catalog models would change:", file=out)
        for key, count in sorted(recorder.meta.items()):
            print(f"  {count:5d}  {key}", file=out)
        if error is not None:
            print(f"STOPPED: {type(error).__name__}: {error}", file=out)
        _debug.lifecycle(
            "cli.schema_diff.done",
            ddl=len(recorder.ddl),
            migrations=len(recorder.migrations),
            failed=error is not None,
        )


def _shape(statement: str) -> str:
    shape = re.sub(r"'[^']*'", "'…'", statement)
    shape = re.sub(r"; COMMENT ON [^;]*", "", shape)
    shape = re.sub(r"\bIS %s\b", "IS …", shape)
    return shape[:200]
