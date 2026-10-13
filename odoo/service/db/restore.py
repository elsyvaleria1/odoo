import base64
import contextlib
import logging
import os
import shutil
import subprocess
import tempfile
import threading
import zipfile
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any, Literal, NoReturn

import odoo.api
import odoo.db
import odoo.modules.neutralize
import odoo.modules.registry
import odoo.tools
from odoo.db import BaseCursor
from odoo.libs.debug_log import DebugLog
from odoo.tools.subprocess import exec_pg_environ, get_pg_tool_path

from .._env import get_env_float, get_env_int
from ._checks import check_db_management_enabled, check_db_name
from ._dump_scanner import _PortableSqlWriter, _RestoreTarget
from .lifecycle import (
    _announce_database,
    _check_filestore_dest_free,
    _rollback_new_database,
    create_empty_database,
)
from .listing import exp_db_exist

_logger = logging.getLogger("odoo.service.db")
_debug = DebugLog(__name__)


_RESTORE_MAX_EXPANSION_RATIO = 50


_RESTORE_MIN_UNPACKED_BYTES = 100 * 1024 * 1024


_EXTRACT_CHUNK_BYTES = 1024 * 1024


_DUMP_SQL = "dump.sql"


_PSQL_RESTORE_ARGS = ("-X", "-q", "-v", "ON_ERROR_STOP=1")


def _extract_members_bounded(
    z: zipfile.ZipFile,
    members: list[str],
    dest: str,
    budget: int,
    restore_target: _RestoreTarget,
) -> int:
    dest_path = Path(dest)
    written = 0
    with _debug.perf(
        "database.restore.extracted", members=len(members), budget=budget
    ) as span:
        for member in members:
            info = z.getinfo(member)
            target = dest_path / member
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, target.open("wb") as fh:
                out = (
                    _PortableSqlWriter(fh, restore_target)
                    if member == _DUMP_SQL
                    else fh
                )
                while chunk := src.read(_EXTRACT_CHUNK_BYTES):
                    written += len(chunk)
                    if written > budget:
                        _debug.logic(
                            "database.restore.expansion_refused",
                            member=member,
                            written=written,
                            budget=budget,
                        )
                        raise _prepare_expansion_error(budget)
                    out.write(chunk)
                if isinstance(out, _PortableSqlWriter):
                    out.finish()
                    span.set(dropped=out.dropped)
        span.set(written=written)
    return written


def _prepare_expansion_error(budget: int) -> RuntimeError:
    return RuntimeError(
        f"Refusing to restore: the archive expands to more than {budget} bytes, "
        f"over {_RESTORE_MAX_EXPANSION_RATIO}x its compressed size. Raise "
        f"ODOO_RESTORE_MAX_EXPANSION_RATIO if this backup is genuinely that "
        f"compressible."
    )


def _get_source_size(dump_file: str | os.PathLike[str] | IO[bytes]) -> int:
    if isinstance(dump_file, (str, os.PathLike)):
        size = Path(dump_file).stat().st_size
        _debug.logic("database.restore.source_sized", source="path", bytes=size)
        return size
    pos = dump_file.tell()
    try:
        dump_file.seek(0, os.SEEK_END)
        size = dump_file.tell()
        _debug.logic("database.restore.source_sized", source="stream", bytes=size)
        return size
    finally:
        dump_file.seek(pos)


def _unpack_budget(dump_file: str | os.PathLike[str] | IO[bytes]) -> int:
    ratio = get_env_int(
        "ODOO_RESTORE_MAX_EXPANSION_RATIO",
        _RESTORE_MAX_EXPANSION_RATIO,
        minimum=1,
        logger=_logger,
    )
    budget: int = max(_get_source_size(dump_file) * ratio, _RESTORE_MIN_UNPACKED_BYTES)
    _debug.logic("database.restore.budget", ratio=ratio, budget=budget)
    return budget


def _get_pg_restore_total_timeout() -> float:
    return get_env_float("ODOO_PG_RESTORE_TOTAL_TIMEOUT", 3600.0, logger=_logger)


@check_db_management_enabled
def exp_restore(db_name: str, data: str, copy: bool = False) -> Literal[True]:
    _STRIP_WS = str.maketrans("", "", " \t\n\r\v\f")
    CHUNK = 8192

    data_file = tempfile.NamedTemporaryFile(delete=False)  # noqa: SIM115 -- Closed before restore reads the path; finally closes and removes it.
    try:
        with _debug.perf(
            "database.restore.decoded", db=db_name, chars=len(data)
        ) as span:
            accum = ""
            for i in range(0, len(data), CHUNK):
                accum += data[i : i + CHUNK].translate(_STRIP_WS)
                n_complete = (len(accum) // 4) * 4
                if n_complete:
                    data_file.write(base64.b64decode(accum[:n_complete]))
                    accum = accum[n_complete:]
            if accum:
                data_file.write(base64.b64decode(accum))
            span.set(bytes=data_file.tell())
        data_file.close()
        restore_db(db_name, data_file.name, copy=copy)
    finally:
        data_file.close()
        Path(data_file.name).unlink(missing_ok=True)
    return True


def _extract_zip_dump(
    dump_file: str | os.PathLike[str] | IO[bytes],
    dump_dir: str,
    restore_target: _RestoreTarget,
) -> str | None:
    with zipfile.ZipFile(dump_file, "r") as z:
        dump_dir_resolved = Path(dump_dir).resolve()
        for member in z.namelist():
            target = (dump_dir_resolved / member).resolve()
            if not target.is_relative_to(dump_dir_resolved):
                _debug.logic("database.restore.member_escapes", member=member)
                raise RuntimeError(
                    f"Refusing to restore: archive member {member!r} "
                    f"escapes the extraction directory"
                )

        if _DUMP_SQL not in z.namelist():
            _debug.logic("database.restore.no_dump_sql", members=len(z.namelist()))
            raise RuntimeError(
                "Refusing to restore: the archive contains no "
                "'dump.sql' member, so it is not an Odoo database "
                "backup."
            )

        filestore = [m for m in z.namelist() if m.startswith("filestore/")]
        _debug.pipeline(
            "database.restore.archive_listed",
            members=len(z.namelist()),
            filestore=len(filestore),
        )
        _extract_members_bounded(
            z,
            [_DUMP_SQL, *filestore],
            dump_dir,
            _unpack_budget(dump_file),
            restore_target,
        )

    return str(Path(dump_dir, "filestore")) if filestore else None


def _stream_custom_archive(
    db: str, archive: str, restore_target: _RestoreTarget, budget: int
) -> None:
    timeout = _get_pg_restore_total_timeout()
    env = exec_pg_environ()
    with (
        tempfile.TemporaryFile() as reader_err,
        tempfile.TemporaryFile() as psql_err,
        _debug.perf("database.restore.streamed", db=db, budget=budget) as span,
    ):
        reader = subprocess.Popen(
            [get_pg_tool_path("pg_restore"), "--no-owner", "--file=-", archive],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=reader_err,
        )
        psql = subprocess.Popen(
            [
                get_pg_tool_path("psql"),
                "--dbname=" + db,
                *_PSQL_RESTORE_ARGS,
                "-f",
                "-",
            ],
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=psql_err,
        )
        assert reader.stdout is not None and psql.stdin is not None
        timed_out = threading.Event()

        def _kill_on_timeout() -> None:
            timed_out.set()
            _debug.logic("database.restore.timed_out", db=db, timeout=timeout)
            reader.kill()
            psql.kill()

        timer = threading.Timer(timeout, _kill_on_timeout)
        timer.daemon = True
        timer.start()
        writer = _PortableSqlWriter(psql.stdin, restore_target)
        read = 0
        try:
            while chunk := reader.stdout.read(_EXTRACT_CHUNK_BYTES):
                read += len(chunk)
                if read > budget:
                    _debug.logic(
                        "database.restore.expansion_refused",
                        member="pg_restore",
                        written=read,
                        budget=budget,
                    )
                    raise _prepare_expansion_error(budget)
                writer.write(chunk)
            writer.finish()
            psql.stdin.close()
        except BrokenPipeError:
            _debug.logic("database.restore.psql_stopped", db=db, read=read)
        except BaseException:
            psql.kill()
            reader.kill()
            raise
        finally:
            timer.cancel()
            reader.stdout.close()
            with contextlib.suppress(BrokenPipeError):
                psql.stdin.close()
            reader_code = reader.wait()
            psql_code = psql.wait()
            span.set(read=read, dropped=writer.dropped, psql=psql_code)
        if timed_out.is_set():
            raise _prepare_timeout_error(db, timeout)
        if psql_code != 0:
            psql_err.seek(0)
            raise _prepare_psql_failure_error(
                db, psql_code, psql_err.read().decode(errors="replace")
            )
        if reader_code != 0:
            reader_err.seek(0)
            _debug.logic("database.restore.archive_unreadable", returncode=reader_code)
            raise RuntimeError(
                f"Couldn't read the archive {archive!r}:\n"
                f"{reader_err.read().decode(errors='replace').strip()}"
            )


def _prepare_timeout_error(db: str, timeout: float) -> RuntimeError:
    return RuntimeError(
        f"Restore of {db!r} exceeded {timeout:.0f}s wall-clock "
        f"timeout and was terminated.  Set "
        f"ODOO_PG_RESTORE_TOTAL_TIMEOUT for slower restores."
    )


def _prepare_psql_failure_error(db: str, returncode: int, stderr: str) -> RuntimeError:
    _logger.error("RESTORE DB %r failed:\n%s", db, stderr)
    _debug.logic("database.restore.psql_failed", db=db, returncode=returncode)
    return RuntimeError(f"Couldn't restore database {db!r}:\n{stderr.strip()}")


def _run_psql(db: str, sql_path: str) -> None:
    timeout = _get_pg_restore_total_timeout()
    try:
        with _debug.perf("database.restore.psql", db=db, timeout=timeout):
            r = subprocess.run(
                [
                    get_pg_tool_path("psql"),
                    "--dbname=" + db,
                    *_PSQL_RESTORE_ARGS,
                    "-f",
                    sql_path,
                ],
                env=exec_pg_environ(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
                timeout=timeout,
            )
    except subprocess.TimeoutExpired as e:
        _debug.logic("database.restore.timed_out", db=db, timeout=timeout)
        raise _prepare_timeout_error(db, timeout) from e
    if r.returncode != 0:
        raise _prepare_psql_failure_error(db, r.returncode, r.stderr)


def _finalize_restored_db(
    db: str, copy: bool, neutralize_database: bool, filestore_path: str | None
) -> None:
    with _debug.perf("database.restore.registry_loaded", db=db):
        registry = odoo.modules.registry.Registry.new(db, run_tests=False)
    with registry.cursor() as cr:
        env = odoo.api.Environment(cr, odoo.api.SUPERUSER_ID, {})
        if copy:
            env["ir.config_parameter"].init(force=True)
        if neutralize_database:
            odoo.modules.neutralize.neutralize_database(cr)
        _warn_unmapped_foreign_servers(cr, db)
        _debug.pipeline(
            "database.restore.finalized",
            db=db,
            copy=copy,
            neutralized=neutralize_database,
            filestore=filestore_path is not None,
        )

        if filestore_path:
            filestore_dest = env["ir.attachment"]._get_filestore()
            if Path(filestore_dest).exists():
                _debug.logic(
                    "database.restore.filestore_race", db=db, dest=filestore_dest
                )
                raise RuntimeError(
                    f"Filestore {filestore_dest!r} appeared between "
                    f"pre-flight and move (race)."
                )
            with _debug.perf("database.restore.filestore_moved", db=db):
                shutil.move(filestore_path, filestore_dest)


def _warn_unmapped_foreign_servers(cr: BaseCursor, db: str) -> None:
    cr.execute(
        "SELECT s.srvname FROM pg_foreign_server s WHERE NOT EXISTS ("
        " SELECT 1 FROM pg_user_mappings m"
        " WHERE m.srvid = s.oid AND m.usename IN (current_user, 'public')"
        ") ORDER BY 1"
    )
    servers = [row[0] for row in cr.fetchall()]
    _debug.logic("database.restore.unmapped_servers", db=db, count=len(servers))
    if servers:
        _logger.warning(
            "RESTORE DB %s: foreign server(s) %s have no user mapping for this "
            "role; a backup carries none, so create one before querying their "
            "foreign tables",
            db,
            ", ".join(servers),
        )


def _restore_into(
    db: str,
    dump_file: str | os.PathLike[str] | IO[bytes],
    dump_dir: str,
    restore_target: _RestoreTarget,
) -> str | None:
    if zipfile.is_zipfile(dump_file):
        filestore_path = _extract_zip_dump(dump_file, dump_dir, restore_target)
        _debug.logic(
            "database.restore.command",
            source="zip",
            filestore=filestore_path is not None,
        )
        _run_psql(db, str(Path(dump_dir, _DUMP_SQL)))
        return filestore_path
    if not isinstance(dump_file, (str, os.PathLike)):
        _debug.logic("database.restore.refused", reason="raw_stream")
        raise TypeError(
            "a raw (non-zip) restore needs a file path, not an open file object"
        )
    _debug.logic("database.restore.command", source="custom", filestore=False)
    _stream_custom_archive(
        db, os.fspath(dump_file), restore_target, _unpack_budget(dump_file)
    )
    return None


@check_db_management_enabled
def restore_db(
    db: str,
    dump_file: str | os.PathLike[str] | IO[bytes],
    copy: bool = False,
    neutralize_database: bool = False,
) -> None:
    if not isinstance(db, str):
        raise TypeError(f"db must be a str, got {type(db).__name__!r}")
    check_db_name(db)
    if exp_db_exist(db):
        _logger.warning("RESTORE DB: %s already exists", db)
        _debug.logic("database.restore.refused", db=db, reason="exists")
        raise RuntimeError(f"Database {db!r} already exists")

    fs_dest = odoo.tools.config.filestore(db)
    _check_filestore_dest_free(fs_dest, f"Cannot restore to {db!r}")

    _logger.info("RESTORING DB: %s", db)
    create_empty_database(db, force_unaccent=True, setup_if_exists=False)

    try:
        with odoo.db.db_connect(db).cursor() as cr:
            target = _RestoreTarget.read(cr)
        with tempfile.TemporaryDirectory() as dump_dir:
            filestore_path = _restore_into(db, dump_file, dump_dir, target)
            _finalize_restored_db(db, copy, neutralize_database, filestore_path)

        _logger.info("RESTORE DB: %s", db)
        _debug.lifecycle(
            "database.restored",
            db=db,
            copy=copy,
            neutralized=neutralize_database,
            filestore=filestore_path is not None,
        )
    except Exception:
        _debug.logic("database.restore.failed", db=db)
        _rollback_new_database(db, "RESTORE DB")
        raise
    _announce_database(db)
