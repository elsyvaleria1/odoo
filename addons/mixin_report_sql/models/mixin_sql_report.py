from itertools import starmap

from odoo import models
from odoo.libs.sql import SQL


class MixinSqlReport(models.AbstractModel):
    """Registry-driven SQL construction for ``_auto = False`` analytical reports."""

    _name = "mixin.sql.report"
    _description = "SQL Report Construction Helper"
    _auto = False


    def _query(self) -> SQL:
        cte = self._with_cte()
        clauses = (
            self._get_where_clause(),
            self._get_group_by_clause(),
            self._get_having_clause(),
            self._get_order_by_clause(),
        )

        parts = []
        if cte:
            parts.append(SQL("WITH %s", cte))
        parts.extend([self._get_select_clause(), self._get_from_clause()])
        parts.extend(clause for clause in clauses if clause)
        return SQL("\n").join(parts)

    @property
    def _table_query(self):
        if getattr(self, "_materialized", False):
            return None
        return self._query()


    def _with_cte(self) -> SQL:
        return SQL.EMPTY

    def _get_select_clause(self) -> SQL:
        fields = self._get_fields_select()
        if not fields:
            raise NotImplementedError(
                f"{self._name}: override _get_fields_select() to return a "
                "non-empty {field_name: sql_expression} mapping."
            )
        field_parts = []
        for field_name, expression in fields.items():
            self._check_percent_escaping(expression, f"select[{field_name!r}]")
            field_parts.append(
                SQL("%s AS %s", SQL(expression), SQL.identifier(field_name)),
            )
        return SQL("SELECT\n    %s", SQL(",\n    ").join(field_parts))

    def _get_from_clause(self) -> SQL:
        tables = self._get_from_tables()
        if not tables:
            raise NotImplementedError(
                f"{self._name}: override _get_from_tables() to return a "
                "non-empty list of (table, alias, join_type, on_condition) tuples."
            )
        from_parts = list(starmap(self._prepare_from_entry, tables))
        return SQL("FROM\n    %s", SQL("\n    ").join(from_parts))

    def _prepare_from_entry(self, table_name, alias, join_type, on_condition) -> SQL:
        if isinstance(table_name, SQL):
            table_sql = table_name
        else:
            self._check_percent_escaping(table_name, "from-table")
            table_sql = SQL(table_name)
            if alias:
                self._check_percent_escaping(alias, "from-alias")
                table_sql = SQL("%s %s", table_sql, SQL(alias))
        if join_type is None:
            return table_sql
        if not on_condition:
            return SQL("%s %s", SQL(join_type), table_sql)
        self._check_percent_escaping(on_condition, f"from-join[{alias!r}]")
        return SQL("%s %s ON %s", SQL(join_type), table_sql, SQL(on_condition))

    def _get_where_clause(self) -> SQL:
        return self._get_conditions_clause(
            SQL("WHERE"), self._get_where_conditions(), "where"
        )

    def _get_having_clause(self) -> SQL:
        return self._get_conditions_clause(
            SQL("HAVING"), self._get_having_conditions(), "having"
        )

    def _get_conditions_clause(self, keyword_sql, conditions, location) -> SQL:
        if not conditions:
            return SQL.EMPTY
        condition_parts = []
        for cond in conditions:
            if isinstance(cond, SQL):
                condition_parts.append(cond)
            else:
                self._check_percent_escaping(cond, location)
                condition_parts.append(SQL(cond))
        return SQL(
            "%s\n    %s",
            keyword_sql,
            SQL("\n    AND ").join(condition_parts),
        )

    def _get_group_by_clause(self) -> SQL:
        return self._get_field_clause(
            SQL("GROUP BY"), self._get_fields_group_by(), "group_by"
        )

    def _get_order_by_clause(self) -> SQL:
        return self._get_field_clause(
            SQL("ORDER BY"), self._get_fields_order_by(), "order_by"
        )

    def _get_field_clause(self, keyword_sql, fields, location) -> SQL:
        if not fields:
            return SQL.EMPTY
        field_parts = []
        for field in fields:
            self._check_percent_escaping(field, location)
            field_parts.append(SQL(field))
        return SQL(
            "%s\n    %s",
            keyword_sql,
            SQL(",\n    ").join(field_parts),
        )


    def _get_fields_select(self) -> dict:
        return {}

    def _get_from_tables(self) -> list:
        return []

    def _get_where_conditions(self) -> list:
        return []

    def _get_fields_group_by(self) -> list:
        return []

    def _get_having_conditions(self) -> list:
        return []

    def _get_fields_order_by(self) -> list:
        return []


    @staticmethod
    def _check_percent_escaping(expr, location) -> None:
        if not isinstance(expr, str) or "%" not in expr:
            return
        if "%" in expr.replace("%%", ""):
            raise ValueError(
                f"mixin.sql.report: un-escaped '%' in {location}: {expr!r}. "
                "Use '%%' for literal percent (e.g. LIKE '%%x%%')."
            )
