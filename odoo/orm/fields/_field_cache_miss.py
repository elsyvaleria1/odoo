import typing
from collections.abc import Callable

from odoo.exceptions import AccessError, MissingError
from odoo.libs.debug_log import DebugLog
from odoo.libs.iteration import SENTINEL

from ._field_compute import compute_recursive_prefetch

if typing.TYPE_CHECKING:
    from .._typing import BaseModel
    from ..primitives import IdType, NewId
    from ..runtime import Environment
    from .base import Field
else:
    Environment = typing.Any
    Field = typing.Any

_debug = DebugLog(__name__)


def _run_batch_then_single(
    batch: Callable[[], None],
    single: Callable[[], None],
    recs: BaseModel,
    *,
    catching: tuple[type[BaseException], ...],
    reraise_when_single: bool = True,
) -> bool:
    try:
        batch()
        return False
    except catching as e:
        if reraise_when_single and len(recs) == 1:
            raise
        _debug.logic(
            "field.cache_miss.batch_fallback",
            records=len(recs),
            error=type(e).__name__,
        )
    single()
    return True


def missing_record_error(env: Environment, record: object) -> MissingError:
    return MissingError(
        "\n".join(
            [
                env._("Record does not exist or has been deleted."),
                env._(
                    "(Record: %(record)s, User: %(user)s)",
                    record=record,
                    user=env.uid,
                ),
            ]
        )
    )


def get_cache_miss_from_storage(
    field: Field[typing.Any], record: BaseModel, env: Environment, record_id: IdType
) -> typing.Any:
    snapshots = env.transaction.recompute_snapshots
    snapshot = snapshots.get(field) if snapshots else None
    if (
        snapshot
        and record_id in snapshot
        and env.is_protected(field, record)
        and not env.core.is_pending_in_tree(field, record_id)
    ):
        value = snapshot.pop(record_id)
        field._insert_cache(record, (value,))
        return field._get_cache(env)[record_id]
    recs = field._to_prefetch(record)
    transaction = env.transaction

    def _batch() -> None:
        if len(recs) == 1:
            recs._fetch_field(field)
            return
        outer = transaction.prefetch_batch
        transaction.prefetch_batch = (recs._get_model_name(), recs._ids)
        try:
            recs._fetch_field(field)
        finally:
            transaction.prefetch_batch = outer

    _run_batch_then_single(
        _batch,
        lambda: record._fetch_field(field),
        recs,
        catching=(AccessError,),
    )
    field_cache = field._get_cache(env)
    value = field_cache.get(record_id, SENTINEL)
    if value is SENTINEL:
        value = field._value_after_delegated_fetch(env, record_id)
    if value is SENTINEL:
        _debug.logic(
            "field.cache_miss.record_missing_after_fetch",
            model=record._name,
            field=field.name,
            record=record_id,
            prefetched=len(recs),
            su=env.su,
            uid=env.uid,
        )
        raise missing_record_error(env, record) from None
    return value


def origin_read_key(field: Field[typing.Any], env: Environment) -> object:
    if field.is_x2many or field not in env.registry.field_depends_context:
        return None
    return env.get_cache_key(field)


def get_cache_miss_from_origin(
    field: Field[typing.Any], record: BaseModel, env: Environment, record_id: IdType
) -> typing.Any:
    recs = field._to_prefetch(record)
    origin_prefetch = recs._origin._prefetch_ids
    spawn = type(recs)._spawn
    recs_env = recs.env

    origin_reads = recs_env.transaction.origin_reads

    def _batch() -> None:
        for rec in recs:
            rec_id = rec._ids[0]
            if origin_id := (rec_id or getattr(rec_id, "origin", None)):
                rec_origin = spawn(recs_env, (origin_id,), origin_prefetch)
                field._update_cache(
                    rec,
                    field.convert_to_cache(
                        field._get_origin_value(rec_origin), rec, validate=False
                    ),
                )
                if not rec_id:
                    origin_reads.note(
                        field,
                        field._get_cache(recs_env),
                        typing.cast("NewId", rec_id),
                        origin_read_key(field, recs_env),
                    )

    def _single() -> None:
        field._update_cache(
            record,
            field.convert_to_cache(
                field._get_origin_value(record._origin), record, validate=False
            ),
        )
        origin_reads.note(
            field,
            field._get_cache(env),
            typing.cast("NewId", record_id),
            origin_read_key(field, env),
        )

    _run_batch_then_single(
        _batch, _single, recs, catching=(AccessError, KeyError, MissingError)
    )
    return field._get_cache(env)[record_id]


def _get_tree_sibling_cached(
    field: Field[typing.Any], env: Environment, record_id: IdType
) -> typing.Any:
    for sibling in field.tree_siblings:
        value = sibling._get_cache(env).get(record_id, SENTINEL)
        if value is not SENTINEL:
            return value
    return SENTINEL


def _depends_on_more_than_access(field: Field[typing.Any], env: Environment) -> bool:
    depends = env._field_depends_context
    return field in depends and any(key != "access" for key in depends[field])


def get_cache_miss_by_compute(
    field: Field[typing.Any], record: BaseModel, env: Environment, record_id: IdType
) -> typing.Any:
    if env.is_protected(field, record):
        value = _get_tree_sibling_cached(field, env, record_id)
        from_sibling = value is not SENTINEL
        if not from_sibling:
            value = field._protected_value_of_other_scope(env, record_id)
        from_scope = not from_sibling and value is not SENTINEL
        _debug.logic(
            "field.cache_miss.compute_protected",
            model=field.model_name,
            field=field.name,
            record=record_id,
            from_sibling=from_sibling,
            from_scope=from_scope,
        )
        if value is SENTINEL:
            value = field.convert_to_cache(False, record, validate=False)
            if _depends_on_more_than_access(field, env):
                return value
        if not from_scope:
            field._update_cache(record, value)
    else:
        recs = field._to_prefetch(record)
        computed: list[typing.Any] = [recs]

        def batch() -> None:
            if field.recursive:
                computed[0] = compute_recursive_prefetch(field, recs, record)
            else:
                field.compute_value(recs)

        if _run_batch_then_single(
            batch,
            lambda: field.compute_value(record),
            recs,
            catching=(AccessError, MissingError),
            reraise_when_single=False,
        ):
            recs = record
        else:
            recs = computed[0]

        if field._has_cache_misses(recs):
            missing_recs_ids = tuple(field._iter_cache_missing_ids(recs))
            _debug.logic(
                "field.cache_miss.compute_unassigned",
                model=field.model_name,
                field=field.name,
                records=len(recs),
                unassigned=len(missing_recs_ids),
            )
            missing_recs = record.browse(missing_recs_ids)
            if field.readonly and not field.store:
                raise ValueError(
                    f"Compute method failed to assign {missing_recs}.{field.name}"
                )
            false_value = field.convert_to_cache(False, record, validate=False)
            field._update_cache(missing_recs, false_value)

        field_cache = field._get_cache(env)
        value = field_cache[record_id]
    return value


def get_cache_miss_by_delegation(
    field: Field[typing.Any], record: BaseModel, env: Environment
) -> typing.Any:
    def is_inherited_field(name: str) -> bool:
        candidate = record._fields[name]
        related = candidate.related
        return bool(
            candidate.inherited and related and related.split(".")[0] == field.name
        )

    parent = record.env[field._get_comodel_name()].new(
        {
            name: value
            for name, value in record._cache.items()
            if is_inherited_field(name)
        }
    )
    value = field.convert_to_cache(parent, record, validate=False)
    field._update_cache(record, value)
    if inv_recs := parent._new_records:
        for invf in env.registry.field_inverses[field]:
            invf._update_inverse(inv_recs, record)
    return value


def get_cache_miss_from_default(
    field: Field[typing.Any], record: BaseModel, env: Environment, record_id: IdType
) -> typing.Any:
    value = field.convert_to_cache(False, record, validate=False)
    field._update_cache(record, value)
    defaults = record.default_get([field.name])
    if field.name in defaults:
        value = field.convert_to_cache(defaults[field.name], record)
        field._update_cache(record, value)
    return field._get_cache(env)[record_id]


def get_cache_miss[T](
    field: Field[T], record: BaseModel, env: Environment, record_id: IdType
) -> T:
    if field.fetched_with_row and record_id and field.delegation_key_settled(env):
        source = "storage"
        value = get_cache_miss_from_storage(field, record, env, record_id)
    elif field.store and record._has_origin and not (field.compute and field.readonly):
        source = "origin"
        value = get_cache_miss_from_origin(field, record, env, record_id)
    elif field.compute:
        source = "compute"
        value = get_cache_miss_by_compute(field, record, env, record_id)
    elif field.is_delegating and not record_id:
        source = "delegation"
        value = get_cache_miss_by_delegation(field, record, env)
    else:
        source = "default"
        value = get_cache_miss_from_default(field, record, env, record_id)

    if _debug.logic.enabled:
        _debug.logic(
            "field.cache_miss",
            model=field.model_name,
            field=field.name,
            record=record_id,
            source=source,
        )
    return field.convert_to_record(value, record)
