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
# ADD COLUMN holds its ACCESS EXCLUSIVE lock for a catalog write only, but
# while it waits for one every GPS insert queues behind it; a holder past this
# is a long report scan the next run outlasts, or this very transaction.
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
    """Qualified name of the table the foreign table reads on its server.

    ``postgres_fdw`` defaults both options to the local names, so a foreign
    table renamed locally keeps pointing at the old remote name.
    """
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
    """Run one DDL statement on the foreign server through ``dblink``.

    The foreign server name doubles as the ``dblink`` connection name, so the
    same user mapping ``postgres_fdw`` uses is reused and no password lives in
    Python. ``dblink_exec`` commits on a connection of its own: what it runs
    survives a rollback of ``cr``.

    :param str lock_timeout: how long the statement may wait for a lock on
                             the remote before it fails, naming itself
    """
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
    """Whether this transaction's ``postgres_fdw`` connection locks `target`.

    That connection keeps its remote transaction, and the locks its reads and
    writes took, until the local transaction ends; DDL sent over ``dblink``
    that needs a conflicting lock would wait on it forever. Needs
    ``postgres_fdw`` 1.2, whose connection list names the remote backend;
    an older one reports False.
    """
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
    """Run one DDL statement on the foreign server once ``env.cr`` commits.

    A rolled-back transaction (a failed upgrade, ``schema_diff``'s dry run)
    then leaves the remote database untouched, and the statement no longer
    waits on locks and snapshots this transaction's own ``postgres_fdw``
    connection holds on the remote table, which it would wait on forever.
    Queued once per statement, in order.
    """
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
    """Whether a usable index of that name exists in `target`'s schema.

    A ``CREATE INDEX CONCURRENTLY`` that failed leaves an invalid index behind,
    which ``IF NOT EXISTS`` would take for the real one: it counts as absent.
    """
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
    """Build a remote index once ``env.cr`` commits, unless a valid one exists.

    An invalid one of that name is dropped first, so `create` builds it again.

    :param str create: the ``CREATE INDEX CONCURRENTLY IF NOT EXISTS``
                       statement, sent alone: ``dblink_exec`` then runs it
                       outside a transaction block, as CONCURRENTLY needs
    """
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
    """Stored columns the model declares that the table does not have.

    :param dict existing: ``sql.get_table_columns`` output for the table
    :return: ``(column name, SQL type)`` pairs in column order
    """
    return [
        (field.name, field.column_type[1])
        for field in sorted(model._fields.values(), key=lambda f: f.column_order)
        if field.store and field.column_type and field.name not in existing
    ]


def checked_references(model) -> list[tuple[str, str, bool]]:
    """Many2one columns whose target the triggers must verify.

    :return: ``(column, referenced table, required)`` for every field named in
             the model's ``_fdw_checked_references``
    """
    refs = []
    for name in model._fdw_checked_references:
        field = model._fields[name]
        # A projected field has no column; checking NEW.<name> would fail
        # every insert.
        if not field.store:
            continue
        refs.append((name, model.env[field.comodel_name]._table, bool(field.required)))
    return refs


def trigger_statements(
    table: str,
    references: list[tuple[str, str, bool]],
    pointers: list[tuple[str, str]],
) -> list[str]:
    """DDL that stands in for the foreign keys a foreign table cannot carry.

    Three guards, all row-level and idempotent to (re)install:

    - ``BEFORE INSERT`` on the log table: every checked reference must exist
      locally. Insert-only on purpose — an ``UPDATE OF`` trigger would make
      ``postgres_fdw`` fetch and update row by row instead of shipping the
      statement (measured 3.5 s vs 0.4 s per 20k rows).
    - ``AFTER DELETE`` on the log table: pointers held by other tables are set
      to NULL, like ``ON DELETE SET NULL`` did.
    - ``BEFORE DELETE`` on each referenced table: a row with history cannot be
      deleted, like ``ON DELETE RESTRICT`` — archiving is the supported path.

    :param str table: the log table name
    :param list references: ``checked_references`` output
    :param list pointers: ``(table, column)`` pairs pointing at the log's id
    :return: SQL statements, in execution order
    """
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
    """Drop the FK constraints that used to protect the pointer columns.

    After the log table is swapped for a foreign one, a leftover constraint
    still references the renamed local table by OID, so every new pointer
    value would fail its check.

    :return: names of the constraints dropped
    """
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
    """DDL that adds the model's missing columns to the remote table.

    :param list columns: ``missing_columns`` output
    :param str target: ``remote_table`` output, the table the DDL runs on
    """
    return [
        f"ALTER TABLE {target} ADD COLUMN IF NOT EXISTS {name} {coltype}"
        for name, coltype in columns
    ]


def remote_index_ddl(model, target: str) -> list[tuple[str, str]]:
    """DDL that creates the model's indexes on the remote table.

    Both kinds the ORM builds on a local table: the model's ``models.Index``
    objects, and the ``index=`` of its stored fields, which
    ``Registry.check_indexes`` skips on a foreign table. Built concurrently,
    so GPS ingest keeps writing during the build; a failed build leaves an
    invalid index, which ``build_remote_index_after_commit`` drops and builds
    again.

    :param str target: ``remote_table`` output, the table the DDL runs on
    :return: ``(index name, CREATE INDEX statement)`` pairs
    """
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
    """Bring the remote table and the local guards in line with the model.

    Called from ``_auto_init`` instead of the ORM's own schema pass when the
    model's table is foreign. Columns are created on the remote server at
    once, since the rest of this transaction reads and writes them through
    the foreign table, which then learns them; a rollback leaves them unused
    on the remote, where ``IF NOT EXISTS`` adopts them on the next run.
    Indexes nothing in this transaction needs are created once it commits.
    The triggers are (re)installed locally.

    :raises UserError: when the server has no user mapping (a neutralized
                       copy), naming how to point it at the copy's own
                       database; when ``dblink`` is missing, or this
                       transaction already holds a lock on the remote table
                       its column DDL would wait on forever, listing the DDL
                       to apply by hand
    """
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

    # ADD COLUMN IF NOT EXISTS takes its ACCESS EXCLUSIVE lock even when the
    # column is there, as it is after a rolled-back run or one added by hand
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
                SQL(coltype),  # noqa: E8501  the ORM's own column_type
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
    # The statements carry no "%" (messages are built with ||), so SQL() takes
    # them verbatim without a parameter round-trip.
    for statement in trigger_statements(table, references, pointers):
        if _installs_existing_trigger(cr, statement):
            # a DROP/CREATE takes a lock on a table live workers read (GPS
            # ingest), and an upgrade that queues behind one deadlocks
            continue
        cr.execute(SQL(statement))


_TRIGGER_DDL = re.compile(
    r"^(?:DROP TRIGGER IF EXISTS (\w+) ON (\w+)|CREATE TRIGGER (\w+) \w+ \w+ ON (\w+) )"
)


def _installs_existing_trigger(cr, statement: str) -> bool:
    """Whether `statement` drops or creates a guard trigger that is in place.

    A guard's name spells its table, timing and function, so a trigger of
    that name on that table is already the one the statement would install;
    only the function body can change, and CREATE OR REPLACE FUNCTION
    replaces that without touching the table.
    """
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
    """Return the guard triggers the model no longer installs.

    :param str table: the log table name
    :param list references: ``checked_references`` output
    :return: ``(trigger, table it is on)`` pairs to drop
    :rtype: list
    """
    # A reference dropped from _fdw_checked_references leaves its
    # <ref>_fdw_no_delete_<table> trigger behind, still querying the log.
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
    # A renamed log table keeps its guards under the old name, and their
    # bodies still name the old tables: its insert check fails every insert
    # and its pointer guard every delete. Same for a no-delete guard on a
    # referenced table whose log table no longer exists.
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
