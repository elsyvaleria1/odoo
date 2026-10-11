import hashlib
import logging

import psycopg

from odoo import models
from odoo.exceptions import UserError
from odoo.libs.sql import SQL

_PENDING_REBUILDS = "mixin_report_sql.pending_materialized_view_rebuilds"

_logger = logging.getLogger(__name__)

_MV_COMMENT_PREFIX = "odoo-mv:v1:"

_RELKIND_LABELS = {"v": "view", "m": "materialized view", "r": "table"}

_MAX_IDENTIFIER = 63


_TRANSIENT_REFRESH_ERRORS = (
    psycopg.errors.SerializationFailure,
    psycopg.errors.LockNotAvailable,
    psycopg.errors.DeadlockDetected,
    psycopg.errors.QueryCanceled,
)


class MixinMaterializedView(models.AbstractModel):

    _name = "mixin.materialized.view"
    _description = "Materialized View Mixin"

    _materialized = True

    _relation_index_field = "id"

    _relation_kind = "m"

    _relation_rebuild_when_empty = True

    _refresh_statement_timeout = "30min"


    def _query(self) -> SQL:
        inherited = getattr(super(), "_query", None)
        if inherited is not None:
            return inherited()
        raise NotImplementedError(
            f"{self._name}: inherit 'mixin.sql.report' for the registry pattern, "
            "or override _query() to return a non-empty SQL object."
        )


    def _relation_exists(self, table) -> bool:
        self.env.cr.execute(
            SQL(
                "SELECT 1 FROM pg_class "
                "WHERE relname = %s "
                "AND relkind = %s "
                "AND relnamespace = current_schema::regnamespace",
                table,
                self._relation_kind,
            )
        )
        return bool(self.env.cr.fetchone())

    def _is_populated(self, table) -> bool:
        self.env.cr.execute(
            SQL(
                "SELECT relispopulated FROM pg_class "
                "WHERE relname = %s "
                "AND relkind = 'm' "
                "AND relnamespace = current_schema::regnamespace",
                table,
            )
        )
        row = self.env.cr.fetchone()
        return bool(row and row[0])

    def _relkind(self, table):
        self.env.cr.execute(
            SQL(
                "SELECT relkind FROM pg_class "
                "WHERE relname = %s "
                "AND relnamespace = current_schema::regnamespace",
                table,
            )
        )
        row = self.env.cr.fetchone()
        return row[0] if row else None

    def _dependent_relations(self, table) -> list:
        self.env.cr.execute(
            SQL(
                """
            SELECT DISTINCT c2.relname, c2.relkind
            FROM pg_depend d
            JOIN pg_class c1 ON d.refobjid = c1.oid
            JOIN pg_rewrite r ON d.objid = r.oid
            JOIN pg_class c2 ON r.ev_class = c2.oid
            WHERE c1.relname = %s
              AND c1.relnamespace = current_schema::regnamespace
              AND c2.relname != c1.relname
            """,
                table,
            )
        )
        return list(self.env.cr.fetchall())


    def refresh(self, force_rebuild=False) -> bool:
        if not self._refresh_try_lock():
            _logger.warning(
                "Refresh of %s skipped: another transaction is refreshing it",
                self._table,
            )
            return False
        try:
            with self.env.cr.savepoint(flush=False):
                if self._refresh_statement_timeout:
                    self.env.cr.execute(
                        SQL(
                            "SELECT set_config('statement_timeout', %s, true)",
                            self._refresh_statement_timeout,
                        )
                    )
                if force_rebuild or self._relation_definition_changed():
                    self._create_relation()
                else:
                    self._refresh_contents()
        except _TRANSIENT_REFRESH_ERRORS as exc:
            _logger.warning(
                "Transient refresh failure on %s: %s. Cron will retry.",
                self._table,
                exc,
            )
            return False
        self.invalidate_model()
        return True

    def _refresh_try_lock(self) -> bool:
        self.env.cr.execute(
            SQL("SELECT pg_try_advisory_xact_lock(hashtext(%s))", self._table)
        )
        return bool(self.env.cr.fetchone()[0])

    def _refresh_contents(self) -> None:
        table_name = SQL.identifier(self._table)
        if self._is_populated(self._table):
            _logger.info("Refreshing %s (CONCURRENTLY)", self._table)
            self.env.cr.execute(
                SQL("REFRESH MATERIALIZED VIEW CONCURRENTLY %s", table_name),
            )
        else:
            _logger.info("Refreshing %s (blocking, first refresh)", self._table)
            self.env.cr.execute(SQL("REFRESH MATERIALIZED VIEW %s", table_name))

    def _cron_refresh_materialized_view(self) -> bool:
        return self.refresh()


    def init(self) -> None:
        if self._abstract:
            return
        self._relation_prepare_schema()
        with_data = self.env.context.get("with_data", True)
        if not self._relation_exists(self._table):
            self._create_relation(with_data=with_data)
            return
        if not self.pool.loaded:
            self.pool.loading.state(_PENDING_REBUILDS, dict)[self._name] = with_data
            return
        self._sync_existing_relation(with_data)

    def _register_hook(self) -> None:
        super()._register_hook()
        if self._abstract or self.pool.ready:
            return
        pending = self.pool.loading.state(_PENDING_REBUILDS, dict)
        if self._name not in pending:
            return
        self._sync_existing_relation(pending.pop(self._name))

    def _sync_existing_relation(self, with_data=True) -> None:
        if self._is_relation_rebuild_needed(with_data=with_data):
            self._create_relation(with_data=with_data)
        else:
            self._relation_create_indexes()

    def _relation_prepare_schema(self) -> None:
        pass

    def _relation_index_cols(self, index_field=None) -> list:
        if index_field is None:
            index_field = self._relation_index_field
        return [index_field] if isinstance(index_field, str) else list(index_field)

    def _relation_index_name(self, suffix) -> str:
        name = f"{self._table}__{suffix}"
        if len(name.encode()) <= _MAX_IDENTIFIER:
            return name
        digest = hashlib.sha256(name.encode()).hexdigest()[:8]
        keep = _MAX_IDENTIFIER - len(digest) - 1
        return f"{name.encode()[:keep].decode(errors='ignore')}_{digest}"

    def _relation_extra_indexes(self) -> list:
        return []

    def _relation_definition_hash(self, query_sql: SQL, index_cols: list) -> str:
        payload = "\x00".join(
            (query_sql.code, repr(query_sql.params), ",".join(index_cols))
        )
        digest = hashlib.sha256(payload.encode()).hexdigest()
        return f"{_MV_COMMENT_PREFIX}{digest}"

    def _relation_stored_comment(self):
        self.env.cr.execute(
            SQL(
                "SELECT obj_description(c.oid, 'pg_class') FROM pg_class c "
                "WHERE c.relname = %s AND c.relkind = %s "
                "AND c.relnamespace = current_schema::regnamespace",
                self._table,
                self._relation_kind,
            )
        )
        row = self.env.cr.fetchone()
        return row[0] if row else None

    def _relation_definition_changed(self) -> bool:
        if self._relkind(self._table) != self._relation_kind:
            return True
        return self._relation_stored_comment() != self._relation_definition_hash(
            self._query(), self._relation_index_cols()
        )

    def _is_relation_rebuild_needed(self, with_data=True) -> bool:
        if self._relation_definition_changed():
            return True
        if not (with_data and self._relation_rebuild_when_empty):
            return False
        return not self._is_populated(self._table)

    def _relation_create_sql(self, table_name, query_sql, with_data) -> SQL:
        if with_data:
            return SQL("CREATE MATERIALIZED VIEW %s AS %s", table_name, query_sql)
        return SQL(
            "CREATE MATERIALIZED VIEW %s AS %s WITH NO DATA", table_name, query_sql
        )

    def _relation_comment_sql(self, table_name, digest) -> SQL:
        return SQL("COMMENT ON MATERIALIZED VIEW %s IS %s", table_name, digest)

    def _create_relation(self, with_data=True, index_field=None):
        self._check_orm_reads_this_relation()
        index_cols = self._relation_index_cols(index_field)
        if not index_cols:
            raise ValueError(
                f"{self._name}: index_field must name at least one column "
                "for the unique index REFRESH ... CONCURRENTLY requires."
            )

        query_sql = self._query()
        if not isinstance(query_sql, SQL) or not query_sql:
            raise TypeError(
                f"{self._name}._query() must return a non-empty SQL object, "
                f"got {type(query_sql).__name__}: {query_sql!r}",
            )

        self._relation_prepare_schema()
        self._drop_existing_relation()

        table_name = SQL.identifier(self._table)
        _logger.info(
            "Creating %s %s %s DATA",
            _RELKIND_LABELS.get(self._relation_kind, self._relation_kind),
            self._table,
            "WITH" if with_data else "WITH NO",
        )
        self.env.cr.execute(self._relation_create_sql(table_name, query_sql, with_data))
        if not with_data and self._relation_kind == "m":
            _logger.warning(
                "%s was created WITH NO DATA — SELECT on it raises "
                "ObjectNotInPrerequisiteState until the first refresh().",
                self._table,
            )

        self._relation_create_indexes(index_cols)

        self.env.cr.execute(
            self._relation_comment_sql(
                table_name, self._relation_definition_hash(query_sql, index_cols)
            )
        )

    def _check_orm_reads_this_relation(self) -> None:
        if not self._table_query:
            return
        raise UserError(
            self.env._(
                "Model '%(model)s' sets _table_query, so the ORM inlines its "
                "query as a subquery and would never read the %(kind)s this "
                "mixin builds at '%(table)s'. Override _query() instead, or "
                "inherit 'mixin.sql.report'.",
                model=self._name,
                kind=_RELKIND_LABELS.get(self._relation_kind, self._relation_kind),
                table=self._table,
            )
        )

    def _relation_create_indexes(self, index_cols=None) -> None:
        if index_cols is None:
            index_cols = self._relation_index_cols()
        table_name = SQL.identifier(self._table)

        unique_name = self._relation_index_name("_".join(index_cols) + "_uidx")
        _logger.info(
            "Creating unique index %s on %s(%s)",
            unique_name,
            self._table,
            ", ".join(index_cols),
        )
        self.env.cr.execute(
            SQL(
                "CREATE UNIQUE INDEX IF NOT EXISTS %s ON %s (%s)",
                SQL.identifier(unique_name),
                table_name,
                SQL(", ").join(SQL.identifier(col) for col in index_cols),
            )
        )

        if index_cols[0] != "id":
            self.env.cr.execute(
                SQL(
                    "CREATE INDEX IF NOT EXISTS %s ON %s (%s)",
                    SQL.identifier(self._relation_index_name("id_idx")),
                    table_name,
                    SQL.identifier("id"),
                )
            )

        for suffix, columns in self._relation_extra_indexes():
            self.env.cr.execute(
                SQL(
                    "CREATE INDEX IF NOT EXISTS %s ON %s (%s)",
                    SQL.identifier(self._relation_index_name(suffix)),
                    table_name,
                    SQL(", ").join(SQL.identifier(col) for col in columns),
                )
            )

        legacy_name = f"id_{self._table}"
        if legacy_name != unique_name:
            self.env.cr.execute(
                SQL("DROP INDEX IF EXISTS %s", SQL.identifier(legacy_name))
            )

    def _drop_existing_relation(self) -> None:
        kind = self._relkind(self._table)
        if kind is None:
            return
        droppable = {"v", "m", self._relation_kind}
        if kind not in droppable:
            raise UserError(
                self.env._(
                    "Cannot (re)create '%(table)s': the name is taken by a "
                    "relation of kind '%(kind)s', which this model does not own "
                    "(it owns '%(owned)s'). Drop or rename it manually before "
                    "upgrading the module.",
                    table=self._table,
                    kind=kind,
                    owned=self._relation_kind,
                )
            )

        dependents = self._dependent_relations(self._table)
        if dependents:
            _logger.warning(
                "Dropping %s %s will CASCADE %d dependent relation(s): %s",
                _RELKIND_LABELS.get(kind, kind),
                self._table,
                len(dependents),
                [f"{name} (kind={relkind})" for name, relkind in dependents],
            )

        _logger.info(
            "Dropping %s at %s (relkind %r) to recreate it as %r",
            _RELKIND_LABELS.get(kind, kind),
            self._table,
            kind,
            self._relation_kind,
        )
        table_name = SQL.identifier(self._table)
        if kind == "v":
            self.env.cr.execute(SQL("DROP VIEW IF EXISTS %s CASCADE", table_name))
        elif kind == "m":
            self.env.cr.execute(
                SQL("DROP MATERIALIZED VIEW IF EXISTS %s CASCADE", table_name),
            )
        else:
            self.env.cr.execute(SQL("DROP TABLE IF EXISTS %s CASCADE", table_name))
