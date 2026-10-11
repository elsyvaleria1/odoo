import logging

from odoo import models
from odoo.db import get_or_create_row
from odoo.libs.sql import SQL

_logger = logging.getLogger(__name__)


class MixinRollingReport(models.AbstractModel):
    """A report whose oldest rows never change, refreshed one window at a time."""

    _name = "mixin.rolling.report"
    _inherit = ["mixin.materialized.view"]
    _description = "Rolling-Window Report Mixin"

    _relation_kind = "r"

    _relation_rebuild_when_empty = False

    _rolling_key_field = "date"

    _rolling_window_days = 3


    def _rolling_cutoff_sql(self) -> SQL:
        return SQL("(current_date - %s::int)", self._rolling_window_days)

    def _rolling_scope(self) -> SQL:
        raise NotImplementedError(
            f"{self._name}: override _rolling_scope() to narrow the scan to "
            "the window, seed rows included."
        )

    def _rolling_scope_sql(self) -> SQL:
        return self.env.context.get("rolling_scope") or SQL.EMPTY

    def _rolling_query(self) -> SQL:
        return self.with_context(rolling_scope=self._rolling_scope())._query()

    def _rolling_columns(self) -> list:
        registry_fields = getattr(self, "_get_fields_select", None)
        if registry_fields is None:
            raise NotImplementedError(
                f"{self._name}: a rolling report needs a column list for its "
                "INSERT ... SELECT. Inherit 'mixin.sql.report' (list it FIRST "
                "in _inherit) or override _rolling_columns()."
            )
        return list(registry_fields())

    def _create_relation(self, with_data=True, index_field=None):
        self._rolling_columns()
        return super()._create_relation(with_data=with_data, index_field=index_field)


    def refresh(self, force_rebuild=False) -> bool:
        stale = self._rolling_pop_stale()
        if stale:
            _logger.info(
                "%s was marked stale — rebuilding every period, not just the window",
                self._table,
            )
        if not self._relation_exists(self._table):
            return super().refresh(force_rebuild=True)
        return super().refresh(
            force_rebuild=force_rebuild or stale or not self._is_populated(self._table)
        )

    def _refresh_contents(self) -> None:
        table = SQL.identifier(self._table)
        key = SQL.identifier(self._rolling_key_field)
        cutoff = self._rolling_cutoff_sql()

        self.env.cr.execute(SQL("DELETE FROM %s WHERE %s >= %s", table, key, cutoff))
        deleted = self.env.cr.rowcount

        columns = SQL(", ").join(
            SQL.identifier(name) for name in self._rolling_columns()
        )
        self.env.cr.execute(
            SQL(
                "INSERT INTO %s (%s) SELECT %s FROM (%s) AS rolling WHERE %s >= %s",
                table,
                columns,
                columns,
                self._rolling_query(),
                key,
                cutoff,
            )
        )
        _logger.info(
            "Rolling refresh of %s: %d row(s) replaced by %d over the last %d day(s)",
            self._table,
            deleted,
            self.env.cr.rowcount,
            self._rolling_window_days,
        )


    def _rolling_mark_stale(self) -> None:
        states = self.env["report.rolling.state"].sudo()
        state = states.search_fetch([("model", "=", self._name)], ["stale"], limit=1)
        if not state:
            state, _created = get_or_create_row(
                self.env.cr,
                lambda: states.create({"model": self._name, "stale": True}),
                lambda: states.search([("model", "=", self._name)], limit=1),
                conflict=f"report.rolling.state {self._name!r}",
            )
        if not state.stale:
            state.stale = True
        _logger.info(
            "%s marked stale; the next refresh will rebuild in full", self._name
        )

    def _rolling_pop_stale(self) -> bool:
        state = (
            self.env["report.rolling.state"]
            .sudo()
            .search_fetch(
                [("model", "=", self._name), ("stale", "=", True)], ["stale"], limit=1
            )
        )
        if not state:
            return False
        state.stale = False
        return True


    def _is_populated(self, table) -> bool:
        self.env.cr.execute(
            SQL("SELECT EXISTS (SELECT 1 FROM %s)", SQL.identifier(table))
        )
        return bool(self.env.cr.fetchone()[0])

    def _relation_create_sql(self, table_name, query_sql, with_data) -> SQL:
        if with_data:
            return SQL("CREATE TABLE %s AS %s", table_name, query_sql)
        return SQL("CREATE TABLE %s AS %s WITH NO DATA", table_name, query_sql)

    def _relation_comment_sql(self, table_name, digest) -> SQL:
        return SQL("COMMENT ON TABLE %s IS %s", table_name, digest)

    def _relation_extra_indexes(self) -> list:
        return [
            *super()._relation_extra_indexes(),
            (f"{self._rolling_key_field}_idx", [self._rolling_key_field]),
        ]
