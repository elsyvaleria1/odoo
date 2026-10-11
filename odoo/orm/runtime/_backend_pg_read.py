from __future__ import annotations

import logging
import typing

from odoo.libs.collections import OrderedSet
from odoo.libs.debug_log import DebugLog
from odoo.libs.sql import SQL
from odoo.tools import Query

from ..models.field_classes import unmasked_values
from ..profiling import _OrmProfile

if typing.TYPE_CHECKING:
    from .._typing import ModelLike
    from ..domain import Domain
    from ..fields import Field
    from ..models.base import BaseModel

_debug = DebugLog("odoo.orm.runtime.backend")


_orm_read = logging.getLogger("odoo.orm.read")


def _prepare_postgres_search_query(
    model: BaseModel,
    domain: Domain,
    offset: int,
    limit: int | None,
    order: str | None,
    *,
    check_access: bool = True,
    prof: typing.Any = None,
) -> Query:
    if prof is None:
        prof = _OrmProfile(_orm_read)
    query = Query(model.env, model._table, model._table_sql)
    if not domain.is_true():
        query.add_where(domain._to_sql(model, model._table, query))
    prof.mark("domain")

    if check_access:
        model_sudo = model.sudo().with_context(active_test=False)
        sec_domain = model.env.registry.access_policy.record_domain(
            model.env, model._get_model_name(), "read"
        )
        sec_domain = sec_domain.optimize_full(model_sudo)
        if sec_domain.is_false():
            _debug.logic(
                "backend.search.rules_deny_all", model=model._name, uid=model.env.uid
            )
            return model.browse()._as_query()
        if not sec_domain.is_true():
            _debug.logic(
                "backend.search.rules_applied", model=model._name, uid=model.env.uid
            )
            query.add_where(sec_domain._to_sql(model_sudo, model._table, query))
    prof.mark("rules")

    if order:
        query.order = _total_order(model, order, model._order_to_sql(order, query))

    if limit is not None and limit is not False:
        query.limit = 1 if limit is True else limit
    if offset is not None and offset is not False:
        query.offset = 1 if offset is True else offset

    prof.stop("query")
    prof.report(_orm_read, "_search %s", model._name)
    return query


def _total_order(model: ModelLike, order: str, order_sql: SQL) -> SQL:
    id_sql = SQL.identifier(model._table, "id")
    if not order_sql:
        return id_sql
    if any(part.split()[:1] == ["id"] for part in order.split(",")):
        return order_sql
    return SQL("%s, %s", order_sql, id_sql)


def _get_fetch_term(model: ModelLike, field: Field[typing.Any], query: Query) -> SQL:
    if field.translate:
        return _get_translated_fetch_term(model, field, query)
    term = field._fetch_term
    if term is not None:
        model._check_field_access(field, "read")
        return term
    column = model._field_to_sql(model._table, field.name, query)
    sql = column.with_to_flush(f for f in column.to_flush if f != field)
    if (
        not sql.params
        and not sql.to_flush
        and sql.code == f'"{model._table}"."{field.name}"'
    ):
        field._fetch_term = sql
        if tuple(column.to_flush) == (field,):
            field._column_term = column
    return sql


def _get_translated_fetch_term(
    model: ModelLike, field: Field[typing.Any], query: Query
) -> SQL:
    if model.env.context.get("prefetch_langs"):
        return model._field_to_sql(model._table, field.name, query)
    langs = field.get_translation_fallback_langs(model.env)
    terms = field._fetch_terms_by_langs
    term = terms.get(langs) if terms is not None else None
    if term is not None:
        model._check_field_access(field, "read")
        return term
    sql = model._field_to_sql(model._table, field.name, query)
    column = f'"{model._table}"."{field.name}"->>%s'
    expected = (
        column if len(langs) == 1 else f"COALESCE({', '.join([column] * len(langs))})"
    )
    if sql.params == langs and sql.code == expected and tuple(sql.to_flush) == (field,):
        if terms is None:
            terms = field._fetch_terms_by_langs = {}
        terms[langs] = sql
    return sql


class _PostgresReadMixin:
    __slots__ = ()

    def fetch(
        self,
        model: ModelLike,
        query: Query,
        column_fields: typing.Iterable[Field[typing.Any]],
        other_fields: typing.Iterable[Field[typing.Any]],
    ) -> ModelLike:
        prof = _OrmProfile(_orm_read)
        env = model.env
        context = env.context
        column_fields = OrderedSet(column_fields)
        other_fields = OrderedSet(other_fields)

        if column_fields:
            sql_terms = [SQL.identifier(model._table, "id")]
            with unmasked_values():
                for field in column_fields:
                    if field.is_binary and (
                        context.get("bin_size") or context.get("bin_size_" + field.name)
                    ):
                        sql = SQL(
                            "pg_size_pretty(length(%s)::bigint)",
                            model._field_to_sql(model._table, field.name, query),
                        )
                    else:
                        sql = _get_fetch_term(model, field, query)
                    sql_terms.append(sql)

            select = query.statement(*sql_terms)
            if model._ids:
                filtering = {
                    *query.where_clause.to_flush,
                    *query.from_clause.to_flush,
                }
                fetched_columns = set(column_fields) - filtering
                model._flush_if_dirty(
                    [f for f in select.to_flush if f in fetched_columns]
                )
                select = select.with_to_flush(
                    [f for f in select.to_flush if f not in fetched_columns]
                )
            rows = env.execute_query(select)
            prof.mark("sql")

            if not rows:
                _debug.logic(
                    "backend.fetch.no_rows",
                    model=model._name,
                    columns=len(column_fields),
                )
                return model.browse()

            column_values = zip(*rows, strict=False)
            ids = next(column_values)
            fetched = model.browse(ids)

            core = env.core
            for field, values in zip(column_fields, column_values, strict=True):
                if field.is_stored_computed:
                    field._clear_dead_pending(fetched)
                    members = (field, *field.tree_siblings)
                    if any(core.has_pending_field(member) for member in members):
                        keep = [
                            i
                            for i, id_ in enumerate(fetched._ids)
                            if not core.is_pending_in_tree(field, id_)
                        ]
                        if len(keep) != len(fetched):
                            field._insert_cache(
                                fetched.browse([fetched._ids[i] for i in keep]),
                                [values[i] for i in keep],
                            )
                            snapshots = env.transaction.recompute_snapshots
                            if snapshots is not None:
                                snapshot = snapshots.setdefault(field, {})
                                kept = set(keep)
                                for i, id_ in enumerate(fetched._ids):
                                    if i not in kept:
                                        snapshot.setdefault(id_, values[i])
                            continue
                field._insert_cache(fetched, values)
            prof.mark("cache")
        else:
            _debug.logic(
                "backend.fetch.no_columns",
                model=model._name,
                other=len(other_fields),
            )
            fetched = model.browse(query)
            prof.mark("sql")
            prof.mark("cache")

        if fetched:
            for field in other_fields:
                field.read(typing.cast("BaseModel", fetched))

        prof.stop("other")
        prof.report(
            _orm_read,
            "_fetch_query %s: %d col + %d other fields -> %d rows",
            model._name,
            len(column_fields),
            len(other_fields),
            len(fetched),
        )

        return fetched

    def search(
        self,
        model: ModelLike,
        domain: Domain,
        offset: int,
        limit: int | None,
        order: str | None,
        *,
        check_access: bool = True,
        prof: typing.Any = None,
    ) -> Query:
        return _prepare_postgres_search_query(
            typing.cast("BaseModel", model),
            domain,
            offset,
            limit,
            order,
            check_access=check_access,
            prof=prof,
        )

    def search_raw(
        self,
        model: ModelLike,
        domain: Domain,
        offset: int,
        limit: int | None,
        order: str | None,
        *,
        check_access: bool = True,
    ) -> Query | None:
        return None

    def as_query(self, model: ModelLike, ordered: bool = True) -> Query:
        query = Query(model.env, model._table, model._table_sql)
        query.set_result_ids(model._ids, ordered)
        return query

    def read_group_rows(
        self,
        model: ModelLike,
        select: SQL,
        *,
        domain: Domain,
        query: Query,
        groupby: typing.Sequence[str],
        aggregates: typing.Sequence[str],
        having: typing.Any,
        order: str | None,
        limit: int | None,
        offset: int,
    ) -> list[tuple[typing.Any, ...]]:
        return model.env.execute_query(select)

    def read_grouping_sets_rows(
        self,
        model: ModelLike,
        select: SQL,
        *,
        domain: Domain,
        query: Query,
        grouping_sets: typing.Sequence[typing.Sequence[str]],
        groupby_terms: typing.Mapping[str, SQL],
        aggregates: typing.Sequence[str],
        order: str | None,
    ) -> list[tuple[typing.Any, ...]]:
        return model.env.execute_query(select)

    def get_existing_ids(self, model: ModelLike, ids: typing.Iterable[int]) -> set[int]:
        ids = list(ids)
        query = Query(model.env, model._table, model._table_sql)
        query.add_where(SQL("%s = ANY(%s)", SQL.identifier(model._table, "id"), ids))
        existing = {id_ for [id_] in model.env.execute_query(query.select())}
        _debug.perf.count(
            "backend.existing_ids",
            model=model._name,
            requested=len(ids),
            existing=len(existing),
        )
        return existing

    def has_rows_beyond(self, model: ModelLike, count: int) -> bool:
        cr = model.env.cr
        cr.execute(
            SQL(
                "SELECT 1 FROM %s OFFSET %s LIMIT 1",
                SQL.identifier(model._table),
                count,
            )
        )
        return cr.fetchone() is not None
