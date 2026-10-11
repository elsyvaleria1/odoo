"""Schema management for a log table that lives in another database.

A data-log table may be a ``postgres_fdw`` foreign table pointing at a
dedicated database. The ORM then cannot manage its schema (``ALTER FOREIGN
TABLE`` does not create indexes or constraints) and Postgres cannot enforce
the foreign keys that tie the log to ``device_device`` and ``res_company``.
This module replaces both: it mirrors the model's columns and indexes onto the
remote table through ``dblink``, and installs row triggers on the local side
that do what the foreign keys used to do.
"""

import logging
import re

import psycopg

from odoo.db import schema as sql
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL, get_index_name

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)

_REMOTE_DDL_AFTER_COMMIT = "device.fdw.remote_ddl_after_commit"
REMOTE_COLUMN_LOCK_TIMEOUT = "10s"


def is_foreign(cr, table: str) -> bool:
    return sql.get_table_kind(cr, table) == sql.TableKind.Foreign


def foreign_server(cr, table: str) -> str | None:
    cr.execute(
        SQL(
            """
            SELECT s.srvname
              FROM pg_foreign_table ft
              JOIN pg_class c ON c.oid = ft.ftrelid
              JOIN pg_foreign_server s ON s.oid = ft.ftserver
             WHERE c.relname = %s
               AND c.relnamespace = current_schema::regnamespace
            """,
            table,
        )
    )
    row = cr.fetchone()
    return row[0] if row else None


def remote_table(cr, table: str) -> str:
    cr.execute(
        SQL(
            """
            SELECT ft.ftoptions
              FROM pg_foreign_table ft
              JOIN pg_class c ON c.oid = ft.ftrelid
             WHERE c.relname = %s
               AND c.relnamespace = current_schema::regnamespace
            """,
            table,
        )
    )
    row = cr.fetchone()
    return qualified_remote_name(table, row[0] if row else None)


def qualified_remote_name(table: str, options: list[str] | None) -> str:
    opts = dict(option.split("=", 1) for option in options or ())
    return f"{opts.get('schema_name', 'public')}.{opts.get('table_name', table)}"


def dblink_available(cr) -> bool:
    cr.execute("SELECT 1 FROM pg_extension WHERE extname = 'dblink'")
    return bool(cr.fetchone())


def user_mapping_exists(cr, server: str) -> bool:
    cr.execute(
        SQL(
            "SELECT 1 FROM pg_user_mappings"
            " WHERE srvname = %s AND usename IN (current_user, 'public')",
            server,
        )
    )
    return bool(cr.fetchone())


def remote_exec(
    cr, server: str, statement: str, *, lock_timeout: str | None = None
) -> None:
    sent = statement
    if lock_timeout:
        sent = f"SET lock_timeout = '{lock_timeout}'; {statement}"
    try:
        cr.execute(SQL("SELECT dblink_exec(%s, %s)", server, sent))
    except psycopg.errors.LockNotAvailable as exc:
        _debug.logic("device.fdw.remote_lock_timeout", server=server)
        exc.add_note(
            f"FDW {server}: waited {lock_timeout} for a lock on the remote and "
            f"gave up: {statement}"
        )
        raise


def remote_column_names(cr, server: str, target: str) -> set[str]:
    cr.execute(
        SQL(
            "SELECT * FROM dblink(%s, %s) AS t(name text)",
            server,
            "SELECT attname FROM pg_attribute"
            f" WHERE attrelid = to_regclass('{target}')"
            " AND attnum > 0 AND NOT attisdropped",
        )
    )
    return {name for (name,) in cr.fetchall()}


def holds_remote_lock(cr, server: str, target: str) -> bool:
    cr.execute(
        "SELECT to_regprocedure('postgres_fdw_get_connections(boolean)') IS NOT NULL"
    )
    if not cr.fetchone()[0]:
        _debug.logic("device.fdw.connection_list_unavailable", server=server)
        return False
    cr.execute(
        SQL(
            "SELECT remote_backend_pid FROM postgres_fdw_get_connections()"
            " WHERE server_name = %s AND used_in_xact AND remote_backend_pid IS NOT NULL",
            server,
        )
    )
    pids = [pid for (pid,) in cr.fetchall()]
    if not pids:
        return False
    cr.execute(
        SQL(
            "SELECT * FROM dblink(%s, %s) AS t(n int)",
            server,
            f"SELECT 1 FROM pg_locks WHERE pid IN ({', '.join(map(str, pids))})"
            f" AND relation = to_regclass('{target}') LIMIT 1",
        )
    )
    return bool(cr.fetchone())


def remote_exec_after_commit(env, server: str, statement: str) -> None:
    postcommit = env.cr.postcommit
    queue = postcommit.data.get(_REMOTE_DDL_AFTER_COMMIT)
    if queue is None:
        queue = postcommit.data.setdefault_list(_REMOTE_DDL_AFTER_COMMIT)
        postcommit.add(_run_remote_ddl(env.registry, queue))
    if (server, statement) in queue:
        _debug.logic("device.fdw.remote_ddl_already_queued", server=server)
        return
    queue.append((server, statement))


def _run_remote_ddl(registry, queue):
    def run() -> None:
        with registry.cursor() as cr:
            for server, statement in queue:
                _logger.info("FDW %s: %s", server, statement)
                try:
                    with cr.savepoint():
                        remote_exec(cr, server, statement)
                except Exception:
                    _logger.exception(
                        "FDW %s: the local transaction committed but this remote "
                        "DDL failed; run it on the remote database: %s",
                        server,
                        statement,
                    )

    return run


def remote_index_exists(cr, server: str, target: str, indexname: str) -> bool:
    cr.execute(
        SQL(
            "SELECT * FROM dblink(%s, %s) AS t(n int)",
            server,
            valid_index_query(target, indexname),
        )
    )
    return bool(cr.fetchone())


def valid_index_query(target: str, indexname: str) -> str:
    schema = target.split(".", 1)[0]
    return (
        "SELECT 1 FROM pg_index i"
        " JOIN pg_class c ON c.oid = i.indexrelid"
        " JOIN pg_namespace n ON n.oid = c.relnamespace"
        f" WHERE c.relname = '{indexname}' AND n.nspname = '{schema}'"
        " AND i.indisvalid"
    )


def build_remote_index_after_commit(
    env, server: str, target: str, indexname: str, create: str
) -> None:
    if remote_index_exists(env.cr, server, target, indexname):
        return
    schema = target.split(".", 1)[0]
    _logger.info(
        "FDW %s: index %s on %s, once this transaction commits",
        server,
        indexname,
        target,
    )
    remote_exec_after_commit(
        env, server, f"DROP INDEX CONCURRENTLY IF EXISTS {schema}.{indexname}"
    )
    remote_exec_after_commit(env, server, create)


def missing_columns(model, existing: dict) -> list[tuple[str, str]]:
    return [
        (field.name, field.column_type[1])
        for field in sorted(model._fields.values(), key=lambda f: f.column_order)
        if field.store and field.column_type and field.name not in existing
    ]


def checked_references(model) -> list[tuple[str, str, bool]]:
    refs = []
    for name in model._fdw_checked_references:
        field = model._fields[name]
        if not field.store:
            continue
        refs.append((name, model.env[field.comodel_name]._table, bool(field.required)))
    return refs


def trigger_statements(
    table: str,
    references: list[tuple[str, str, bool]],
    pointers: list[tuple[str, str]],
) -> list[str]:
    stmts = []

    checks = []
    for column, ref_table, _required in references:
        checks.append(
            f"IF NEW.{column} IS NOT NULL AND NOT EXISTS "
            f"(SELECT 1 FROM {ref_table} WHERE id = NEW.{column}) THEN\n"
            f"    RAISE EXCEPTION USING ERRCODE = 'foreign_key_violation', "
            f"MESSAGE = '{table}.{column}=' || NEW.{column} "
            f"|| ' does not exist in {ref_table}';\n"
            f"  END IF;"
        )
    if checks:
        fn = f"{table}_fdw_fk_check"
        body = "\n  ".join(checks)
        stmts.append(
            f"CREATE OR REPLACE FUNCTION {fn}() RETURNS trigger LANGUAGE plpgsql AS $$\n"
            f"BEGIN\n  {body}\n  RETURN NEW;\nEND $$"
        )
        stmts.append(f"DROP TRIGGER IF EXISTS trg_{fn} ON {table}")
        stmts.append(
            f"CREATE TRIGGER trg_{fn} BEFORE INSERT ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION {fn}()"
        )

    if pointers:
        fn = f"{table}_fdw_unlink_pointer"
        body = "\n  ".join(
            f"UPDATE {ptr_table} SET {ptr_column} = NULL WHERE {ptr_column} = OLD.id;"
            for ptr_table, ptr_column in pointers
        )
        stmts.append(
            f"CREATE OR REPLACE FUNCTION {fn}() RETURNS trigger LANGUAGE plpgsql AS $$\n"
            f"BEGIN\n  {body}\n  RETURN OLD;\nEND $$"
        )
        stmts.append(f"DROP TRIGGER IF EXISTS trg_{fn} ON {table}")
        stmts.append(
            f"CREATE TRIGGER trg_{fn} AFTER DELETE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION {fn}()"
        )

    for column, ref_table, _required in references:
        fn = f"{ref_table}_fdw_no_delete_{table}"
        stmts.append(
            f"CREATE OR REPLACE FUNCTION {fn}() RETURNS trigger LANGUAGE plpgsql AS $$\n"
            f"BEGIN\n"
            f"  IF EXISTS (SELECT 1 FROM {table} WHERE {column} = OLD.id LIMIT 1) THEN\n"
            f"    RAISE EXCEPTION USING ERRCODE = 'foreign_key_violation', "
            f"MESSAGE = '{ref_table} ' || OLD.id "
            f"|| ' still has rows in {table}; archive it instead';\n"
            f"  END IF;\n"
            f"  RETURN OLD;\nEND $$"
        )
        stmts.append(f"DROP TRIGGER IF EXISTS trg_{fn} ON {ref_table}")
        stmts.append(
            f"CREATE TRIGGER trg_{fn} BEFORE DELETE ON {ref_table} "
            f"FOR EACH ROW EXECUTE FUNCTION {fn}()"
        )
    return stmts


def drop_pointer_foreign_keys(cr, pointers: list[tuple[str, str]]) -> list[str]:
    dropped = []
    for ptr_table, ptr_column in pointers:
        cr.execute(
            SQL(
                """
                SELECT con.conname
                  FROM pg_constraint con
                  JOIN pg_attribute att
                    ON att.attrelid = con.conrelid AND att.attnum = ANY(con.conkey)
                 WHERE con.contype = 'f'
                   AND con.conrelid = %s::regclass
                   AND att.attname = %s
                """,
                ptr_table,
                ptr_column,
            )
        )
        for (conname,) in cr.fetchall():
            sql.drop_constraint(cr, ptr_table, conname)
            dropped.append(conname)
    return dropped


def remote_column_ddl(columns: list[tuple[str, str]], target: str) -> list[str]:
    return [
        f"ALTER TABLE {target} ADD COLUMN IF NOT EXISTS {name} {coltype}"
        for name, coltype in columns
    ]


def remote_index_ddl(model, target: str) -> list[tuple[str, str]]:
    ddl = []
    for obj in model._table_objects.values():
        clause = getattr(obj, "_get_definition_clause", None)
        if clause is None:
            continue
        definition = clause(model.pool)
        if not definition:
            continue
        indexname = obj.get_full_name(model)
        unique = "UNIQUE " if getattr(obj, "unique", False) else ""
        create = (
            f"CREATE {unique}INDEX CONCURRENTLY IF NOT EXISTS {indexname} ON {target}"
        )
        ddl.append((indexname, f"{create} {definition}"))
    for field in sorted(model._fields.values(), key=lambda f: f.column_order):
        index = field.index
        if not (field.store and field.column_type and index) or field.translate:
            continue
        if index == "trigram" and not model.pool.has_trigram:
            continue
        expression, method, where = model.pool._get_index_expression(field, index)
        indexname = get_index_name(model._table, field.name)
        unique = "UNIQUE " if index == "unique" else ""
        predicate = f" WHERE {where}" if where else ""
        create = (
            f"CREATE {unique}INDEX CONCURRENTLY IF NOT EXISTS {indexname} ON {target}"
        )
        ddl.append((indexname, f"{create} USING {method} ({expression}){predicate}"))
    return ddl


def sync_foreign_schema(model) -> None:
    cr = model.env.cr
    table = model._table
    server = foreign_server(cr, table)
    if not user_mapping_exists(cr, server):
        _debug.logic("device.fdw.server_unmapped", server=server, table=table)
        raise UserError(
            model.env._(
                "%(model)s is backed by foreign table %(table)s on server "
                "%(server)s, which has no user mapping for this role: a "
                "neutralized copy does not reach its source's databases. Point "
                "the server at this copy's own database, then map the role:\n"
                "ALTER SERVER %(server)s OPTIONS (SET host '<host>', "
                "SET port '<port>', SET dbname '<database>');\n"
                "CREATE USER MAPPING FOR CURRENT_USER SERVER %(server)s "
                "OPTIONS (user '<role>', password '<password>');",
                model=model._name,
                table=repr(table),
                server=server,
            )
        )
    existing = sql.get_table_columns(cr, table)
    columns = missing_columns(model, existing)
    target = remote_table(cr, table)
    column_ddl = remote_column_ddl(columns, target)
    index_ddl = remote_index_ddl(model, target)
    remote_ddl = column_ddl + [create for _name, create in index_ddl]

    if remote_ddl and not dblink_available(cr):
        raise UserError(
            model.env._(
                "%(model)s is backed by foreign table %(table)s but the dblink "
                "extension is not installed, so its schema cannot be synchronised. "
                "Install dblink or run this on the remote database:\n%(ddl)s",
                model=model._name,
                table=repr(table),
                ddl=";\n".join(remote_ddl),
            )
        )

    if columns:
        present = remote_column_names(cr, server, target)
        column_ddl = remote_column_ddl(
            [(name, coltype) for name, coltype in columns if name not in present],
            target,
        )
    if column_ddl and holds_remote_lock(cr, server, target):
        _debug.logic("device.fdw.column_ddl_self_wait", server=server, table=table)
        raise UserError(
            model.env._(
                "%(model)s needs new columns on %(target)s, but this "
                "transaction already read or wrote that table through server "
                "%(server)s, which keeps its lock until the transaction ends: "
                "adding them from inside it would wait forever. Run this on "
                "the remote database, then run again:\n%(ddl)s",
                model=model._name,
                target=target,
                server=server,
                ddl=";\n".join(column_ddl),
            )
        )
    for ddl in column_ddl:
        _logger.info("FDW %s: %s", server, ddl)
        remote_exec(cr, server, ddl, lock_timeout=REMOTE_COLUMN_LOCK_TIMEOUT)
    for indexname, create in index_ddl:
        build_remote_index_after_commit(model.env, server, target, indexname, create)
    for name, coltype in columns:
        cr.execute(
            SQL(
                "ALTER FOREIGN TABLE %s ADD COLUMN %s %s",
                SQL.identifier(table),
                SQL.identifier(name),
                SQL(coltype),  # noqa: E8501 -- the ORM's own column_type
            )
        )

    pointers = list(model._fdw_pointer_columns)
    for conname in drop_pointer_foreign_keys(cr, pointers):
        _logger.info("FDW %s: dropped pointer constraint %s", table, conname)
    references = checked_references(model)
    for trigger, on_table in stale_guard_triggers(cr, table, references):
        _logger.info("FDW %s: dropped stale guard %s on %s", table, trigger, on_table)
        cr.execute(
            SQL(
                "DROP TRIGGER IF EXISTS %s ON %s",
                SQL.identifier(trigger),
                SQL.identifier(on_table),
            )
        )
    for statement in trigger_statements(table, references, pointers):
        if _installs_existing_trigger(cr, statement):
            continue
        cr.execute(SQL(statement))


_TRIGGER_DDL = re.compile(
    r"^(?:DROP TRIGGER IF EXISTS (\w+) ON (\w+)|CREATE TRIGGER (\w+) \w+ \w+ ON (\w+) )"
)


def _installs_existing_trigger(cr, statement: str) -> bool:
    match = _TRIGGER_DDL.match(statement)
    if not match:
        return False
    name = match.group(1) or match.group(3)
    on_table = match.group(2) or match.group(4)
    cr.execute(
        SQL(
            "SELECT 1 FROM pg_trigger WHERE tgname = %s AND tgrelid = to_regclass(%s)",
            name,
            on_table,
        )
    )
    return bool(cr.fetchone())


def stale_guard_triggers(cr, table: str, references) -> list[tuple[str, str]]:
    wanted = {
        f"trg_{ref_table}_fdw_no_delete_{table}" for _c, ref_table, _r in references
    }
    cr.execute(
        SQL(
            "SELECT t.tgname, c.relname FROM pg_trigger t"
            " JOIN pg_class c ON c.oid = t.tgrelid"
            " WHERE NOT t.tgisinternal AND t.tgname LIKE %s",
            f"trg\\_%\\_fdw\\_no\\_delete\\_{table}",
        )
    )
    stale = [(name, rel) for name, rel in cr.fetchall() if name not in wanted]
    cr.execute(
        SQL(
            "SELECT t.tgname, c.relname FROM pg_trigger t"
            " JOIN pg_class c ON c.oid = t.tgrelid"
            " WHERE NOT t.tgisinternal AND c.relname = %s"
            " AND (t.tgname LIKE %s OR t.tgname LIKE %s)"
            " AND t.tgname NOT IN %s",
            table,
            "trg\\_%\\_fdw\\_fk\\_check",
            "trg\\_%\\_fdw\\_unlink\\_pointer",
            (f"trg_{table}_fdw_fk_check", f"trg_{table}_fdw_unlink_pointer"),
        )
    )
    stale.extend((name, rel) for name, rel in cr.fetchall())
    cr.execute(
        SQL(
            "SELECT t.tgname, c.relname FROM pg_trigger t"
            " JOIN pg_class c ON c.oid = t.tgrelid"
            " WHERE NOT t.tgisinternal AND t.tgname LIKE %s"
            " AND to_regclass(split_part(t.tgname, '_fdw_no_delete_', 2)) IS NULL",
            "trg\\_%\\_fdw\\_no\\_delete\\_%",
        )
    )
    stale.extend((name, rel) for name, rel in cr.fetchall() if (name, rel) not in stale)
    return stale
