import logging
import typing
from collections.abc import Iterable, Iterator
from pprint import pformat

from odoo.exceptions import CacheMiss
from odoo.libs.collections import OrderedSet
from odoo.libs.debug_log import DebugLog
from odoo.libs.iteration import PENDING, SENTINEL
from odoo.libs.sql import SQL, pg_size_pretty
from odoo.tools import Query

from ..models.field_classes import unmasked_values

if typing.TYPE_CHECKING:
    from collections.abc import MutableMapping

    from .._typing import BaseModel, Field
    from ..primitives import IdType
    from .environment import Environment
    from .transaction import Transaction
else:
    BaseModel = typing.Any
    Environment = typing.Any
    Transaction = typing.Any
    Field = typing.Any

_logger = logging.getLogger("odoo.api")
_debug = DebugLog(__name__)


class CacheInvalidError(AssertionError):
    pass


class Cache:

    __slots__ = ("transaction",)

    def __init__(self, transaction: Transaction) -> None:
        self.transaction = transaction

    @typing.override
    def __repr__(self) -> str:
        data: dict[Field[typing.Any], dict[typing.Any, typing.Any]] = {}
        core = self.transaction.core
        for field in sorted(core.iter_cached_fields(), key=str):
            dirty_ids = core.get_dirty(field) or ()
            if field in self.transaction.registry.field_depends_context:
                data[field] = {
                    key: _get_repr_entries(key_cache, dirty_ids, field)
                    for key, key_cache in core.iter_context_caches(field)
                }
            else:
                data[field] = _get_repr_entries(
                    core.get_field_data_or_none(field) or {}, dirty_ids, field
                )
        return repr(data)

    def _get_field_cache(
        self, model: BaseModel, field: Field[typing.Any]
    ) -> MutableMapping[IdType, typing.Any]:
        return field._get_cache(model.env)

    def contains(self, record: BaseModel, field: Field[typing.Any]) -> bool:
        field_cache = self._get_field_cache(record, field)
        return field_cache.get(record.id, PENDING) is not PENDING

    def get(
        self,
        record: BaseModel,
        field: Field[typing.Any],
        default: typing.Any = SENTINEL,
    ) -> typing.Any:
        value = (
            self._get_field_cache(record, field).get(record._ids[0], PENDING)
            if record._ids
            else PENDING
        )
        if value is not PENDING:
            return value
        if default is SENTINEL:
            raise CacheMiss(record, field)
        return default

    def set(
        self,
        record: BaseModel,
        field: Field[typing.Any],
        value: typing.Any,
        dirty: bool = False,
    ) -> None:
        field._update_cache(record, value, dirty=dirty)
        self._values_replaced(record, field, dirty)

    def update(
        self,
        records: BaseModel,
        field: Field[typing.Any],
        values: Iterable[typing.Any],
        dirty: bool = False,
    ) -> None:
        if dirty:
            for record, value in zip(records, values, strict=False):
                field._update_cache(record, value, dirty=True)
        else:
            field._update_cache_items(
                records.env, zip(records._ids, values, strict=False)
            )
        self._values_replaced(records, field, dirty)

    def update_raw(
        self,
        records: BaseModel,
        field: Field[typing.Any],
        values: Iterable[typing.Any],
        dirty: bool = False,
    ) -> None:
        if not dirty and (
            found := self.transaction.core.get_pending_write((field,), records._ids)
        ):
            _field, overlap = found
            _logger.warning(
                "Cache.update_raw overwrote %s on records %s, which held a "
                "pending write that is now lost. Flush those records first, or "
                "pass dirty=True to declare that this value supersedes the "
                "pending one.",
                field,
                overlap[:10],
            )
        field_cache = self._get_field_cache(records, field)
        field_cache.update(zip(records._ids, values, strict=False))
        if field.is_column and dirty:
            self.transaction.core.mark_dirty(
                field, [id_ for id_ in records._ids if id_]
            )
        self._values_replaced(records, field, dirty)

    def _values_replaced(
        self, records: BaseModel, field: Field[typing.Any], dirty: bool
    ) -> None:
        if dirty:
            records._access_inputs_written((field.name,))
        else:
            records._access_inputs_forgotten((field.name,))

    def remove(self, record: BaseModel, field: Field[typing.Any]) -> None:
        if record.id in (self.transaction.core.get_dirty(field) or ()):
            raise ValueError(
                f"Cannot remove cache entry for dirty field "
                f"{field!r} on record {record}: pending write would be lost"
            )
        try:
            field_cache = self._get_field_cache(record, field)
            del field_cache[record._ids[0]]
        except KeyError:
            pass

    def get_values(
        self, records: BaseModel, field: Field[typing.Any]
    ) -> Iterator[typing.Any]:
        field_cache = self._get_field_cache(records, field)
        for record_id in records._ids:
            value = field_cache.get(record_id, PENDING)
            if value is not PENDING:
                yield value

    def get_fields(self, record: BaseModel) -> Iterator[Field[typing.Any]]:
        for name, field in record._fields.items():
            if name != "id" and self.contains(record, field):
                yield field

    def get_records(
        self, model: BaseModel, field: Field[typing.Any], all_contexts: bool = False
    ) -> BaseModel:
        ids: Iterable[IdType]
        if all_contexts and field in model.pool.field_depends_context:
            ids = OrderedSet(self.transaction.core.get_context_cached_ids(field))
        else:
            ids = [
                id_
                for id_, value in self._get_field_cache(model, field).items()
                if value is not PENDING
            ]
        return model.browse(ids)

    def get_missing_ids(
        self, records: BaseModel, field: Field[typing.Any]
    ) -> Iterator[IdType]:
        return field._iter_cache_missing_ids(records)

    def invalidate(
        self,
        spec: Iterable[tuple[Field[typing.Any], Iterable[IdType] | None]] | None = None,
    ) -> None:
        if spec is None:
            self.transaction.invalidate_field_data()
            return
        spec = [(field, None if ids is None else tuple(ids)) for field, ids in spec]
        core = self.transaction.core
        for field, ids in spec:
            if (found := core.get_pending_write((field,), ids)) is not None:
                _field, overlap = found
                raise ValueError(
                    f"Cache.invalidate: refusing to drop {field} on records "
                    f"{overlap[:10]}; they hold a pending write that would be "
                    f"silently lost.  Flush those records first."
                )
        _debug.lifecycle(
            "recordset_cache.invalidate",
            fields=len(spec),
            whole_fields=sum(1 for _field, ids in spec if ids is None),
        )
        env = next(iter(self.transaction.envs), None)
        memo = self.transaction.access_memo
        for field, ids in spec:
            core.invalidate(field, ids)
            if env is None:
                memo.forget(self.transaction.registry, field.model_name, (field.name,))
            else:
                env[field.model_name]._access_inputs_forgotten((field.name,))

    def check(
        self, env: Environment, *, raise_on_invalid: bool = True
    ) -> list[tuple[BaseModel, Field[typing.Any], dict[str, typing.Any]]]:
        depends_context = env.registry.field_depends_context
        core = self.transaction.core
        invalids: list[tuple[BaseModel, Field[typing.Any], dict[str, typing.Any]]] = []

        def process(
            model: BaseModel, field: Field[typing.Any], field_cache: typing.Any
        ) -> None:
            dirty_ids = core.get_dirty(field) or ()
            _pending = PENDING
            ids = [
                id_
                for id_ in field_cache
                if id_ and id_ not in dirty_ids and field_cache[id_] is not _pending
            ]
            if not ids:
                return

            bin_size = field.is_binary and (
                model.env.context.get("bin_size")
                or model.env.context.get("bin_size_" + field.name)
            )
            rows: typing.Iterable[tuple[typing.Any, typing.Any]]
            if model._table_query is None:
                rows = env.backend.columns.read(model, field.name, ids).items()
                if bin_size:
                    rows = [
                        (id_, None if value is None else pg_size_pretty(len(value)))
                        for id_, value in rows
                    ]
            else:
                query = Query(env, model._table, model._table_sql)
                sql_id = SQL.identifier(model._table, "id")
                with unmasked_values():
                    sql_field = model._field_to_sql(model._table, field.name, query)
                if bin_size:
                    sql_field = SQL("pg_size_pretty(length(%s)::bigint)", sql_field)
                query.add_where(SQL("%s = ANY(%s)", sql_id, list(ids)))
                env.cr.execute(query.select(sql_id, sql_field))
                rows = env.cr.fetchall()

            for id_, value in rows:
                cached = field_cache[id_]
                if value == cached or (not value and not cached):
                    continue
                invalids.append(
                    (
                        model.browse((id_,)),
                        field,
                        {"cached": cached, "fetched": value},
                    )
                )

        checked = 0
        with _debug.perf("recordset_cache.check", cr=env.cr) as span:
            for field in list(core.iter_cached_fields()):
                if (
                    not field.store
                    or not field.column_type
                    or field.translate
                    or field.company_dependent
                ):
                    continue

                checked += 1
                model = env[field.model_name]
                if field in depends_context:
                    for context_keys, inner_cache in core.iter_context_caches(field):
                        context = dict(
                            zip(depends_context[field], context_keys, strict=True)
                        )
                        if "company" in context:
                            context["allowed_company_ids"] = [context.pop("company")]
                        process(model.with_context(context), field, inner_cache)
                elif (field_cache := core.get_field_data_or_none(field)) is not None:
                    process(model, field, field_cache)
            span.set(fields=checked, invalid=len(invalids))

        if invalids:
            _logger.warning("Invalid cache: %s", pformat(invalids))
            if raise_on_invalid:
                raise CacheInvalidError(
                    f"Cache does not match the database:\n{pformat(invalids)}"
                )
        return invalids


class Starred:
    __slots__ = ["value"]

    def __init__(self, value: typing.Any) -> None:
        self.value = value

    @typing.override
    def __repr__(self) -> str:
        return f"{self.value!r}*"


def _get_repr_entries(
    values: typing.Any, dirty_ids: typing.Any, field: Field[typing.Any]
) -> dict[typing.Any, typing.Any]:
    return {
        Starred(id_) if id_ in dirty_ids else id_: (
            "<binary>" if field.is_binary else val
        )
        for id_, val in values.items()
    }
