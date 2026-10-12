import itertools
import logging
import typing
from collections.abc import Callable, Collection, Iterable, Iterator

from odoo.exceptions import AccessError, MissingError
from odoo.libs.debug_log import DebugLog
from odoo.libs.iteration import SENTINEL

from .._recordset import is_recordset
from ..primitives import PREFETCH_MAX
from ..profiling import _OrmProfile

if typing.TYPE_CHECKING:
    from .._typing import ModelLike
    from ..primitives import IdType
    from .base import Field
else:
    Field = typing.Any
    ModelLike = typing.Any

_orm_compute = logging.getLogger("odoo.orm.compute")
_debug = DebugLog(__name__)


def call_hook(
    needle: str | Callable[..., typing.Any] | None,
    records: ModelLike,
    *args: object,
) -> typing.Any:
    if not is_recordset(records):
        msg = "Hook dispatch requires a subject recordset"
        raise TypeError(msg)
    if isinstance(needle, str):
        method = getattr(records, needle)
        call_args: tuple[object, ...] = args
    elif callable(needle):
        method = needle
        call_args = (records, *args)
    else:
        msg = "Hook dispatch requires a callable or method name"
        raise TypeError(msg)

    name = getattr(method, "__name__", "")
    if name.startswith("__"):
        msg = (
            f"Hook dispatch refuses {name!r}: a dunder cannot be a compute, "
            f"inverse, search or group_expand target"
        )
        raise TypeError(msg)
    return method(*call_args)


def _expand_ids(id0: IdType, ids: Iterable[IdType]) -> Iterator[IdType]:
    yield id0
    seen = {id0}
    kind = bool(id0)
    for id_ in ids:
        if id_ not in seen and bool(id_) == kind:
            yield id_
            seen.add(id_)


def recompute(field: Field[typing.Any], records: ModelLike) -> None:
    to_compute_ids = records.env.core.get_pending_ids(field)
    if not to_compute_ids:
        return

    prof = _OrmProfile(_orm_compute)
    if prof.debug:
        _pending_before = len(to_compute_ids)

        def _count() -> int:
            remaining = records.env.core.get_pending_ids(field)
            return _pending_before - len(remaining or ())

    def apply_except_missing(
        func: typing.Callable[[typing.Any], None], records: typing.Any
    ) -> None:
        try:
            func(records)
            return
        except MissingError:
            pass

        existing = records.exists()
        missing = records - existing
        _debug.logic(
            "field.recompute.missing_records",
            model=field.model_name,
            field=field.name,
            records=len(records),
            missing=len(missing),
        )
        if existing:
            func(existing)
        for f in records._get_stored_computed_fields():
            records.env.remove_to_compute(f, missing)

    if field.recursive:
        _recompute_recursive(field, records, to_compute_ids, apply_except_missing)
    else:
        _recompute_batched(field, records, to_compute_ids, apply_except_missing)

    prof.stop()
    prof.report(
        _orm_compute,
        "recompute %s.%s: %d records (recursive=%s)",
        field.model_name,
        field.name,
        _count() if prof.debug else 0,
        field.recursive,
    )


def _iter_recursive_reads(
    prefix: tuple[Field[typing.Any], ...], probe: ModelLike, through_parent: bool
) -> Iterator[tuple[IdType, IdType]]:
    first = prefix[0]
    if len(prefix) == 1 and first.is_many2one:
        for record in probe:
            for target in record[first.name]._ids:
                yield record.id, target
        return
    inverse = (
        probe._fields.get(first.inverse_name)
        if through_parent
        and len(prefix) == 1
        and first.is_one2many
        and first.inverse_name is not None
        else None
    )
    if (
        inverse is not None
        and inverse.is_many2one
        and not inverse.compute
        and first.comodel_name == probe._name
    ):
        for record in probe:
            for parent_id in record[inverse.name]._ids:
                yield parent_id, record.id
        return
    dotted = ".".join(step.name for step in prefix)
    for record in probe:
        for target in record.mapped(dotted)._ids:
            yield record.id, target


def _sort_levels(
    ids: list[IdType], reads: dict[IdType, set[IdType]], blocked: set[IdType]
) -> tuple[list[list[IdType]], list[IdType]]:
    position = {id_: index for index, id_ in enumerate(ids)}
    waiting = {id_: len(reads[id_]) + (id_ in blocked) for id_ in ids}
    readers: dict[IdType, list[IdType]] = {}
    for reader, targets in reads.items():
        for target in targets:
            readers.setdefault(target, []).append(reader)
    levels: list[list[IdType]] = []
    level = [id_ for id_ in ids if not waiting[id_]]
    while level:
        levels.append(level)
        released = []
        for target in level:
            for reader in readers.get(target, ()):
                waiting[reader] -= 1
                if not waiting[reader]:
                    released.append(reader)
        level = sorted(released, key=position.__getitem__)
    return levels, [id_ for id_ in ids if waiting[id_]]


def _get_unfinished_ids(
    field: Field[typing.Any], records: ModelLike, ids: Iterable[IdType]
) -> set[IdType]:
    if field.store:
        pending = records.env.core.get_pending_ids(field)
        return {id_ for id_ in ids if id_ in pending}
    reading = records.sudo() if field.compute_sudo else records
    return set(field._iter_cache_missing_ids(reading.browse(ids)))


def _ancestor_chains(
    paths: tuple[tuple[Field[typing.Any], ...], ...],
    probe: ModelLike,
    outside: dict[IdType, set[IdType]],
) -> dict[IdType, list[IdType]] | None:
    if not probe._parent_store or len(paths) != 1:
        return None
    parent = probe._fields[probe._parent_name]
    if paths[0] != (parent,):
        return None
    stored_paths = probe._fields["parent_path"]._get_cache(probe.env)
    parents = parent._get_cache(probe.env)
    chains: dict[IdType, list[IdType]] = {}
    for target, readers in outside.items():
        stored = stored_paths.get(next(iter(readers)))
        if not stored:
            return None
        lineage = [int(part) for part in stored.split("/") if part]
        if len(lineage) < 2 or lineage[-2] != target:
            return None
        above: list[IdType] = list(lineage[-3::-1])
        for child, ancestor in zip([target, *above], [*above, None], strict=True):
            cached = parents.get(child, SENTINEL)
            if cached is not SENTINEL and (cached or None) != ancestor:
                return None
        chains[target] = above
    return chains


def _read_up_the_chains(
    field: Field[typing.Any],
    records: ModelLike,
    chains: dict[IdType, list[IdType]],
    outside: dict[IdType, set[IdType]],
    reads: dict[IdType, set[IdType]],
    blocked: set[IdType],
) -> None:
    held = records.env.core.get_protected_ids(field)
    unfinished = _get_unfinished_ids(
        field,
        records,
        {id_ for chain in chains.values() for id_ in chain} | set(chains),
    )
    for target, readers in outside.items():
        if target not in unfinished:
            continue
        reached: set[IdType] = set()
        reaches_held = False
        for ancestor in chains[target]:
            if ancestor in reads:
                reached.add(ancestor)
                break
            if ancestor in held:
                reaches_held = True
                break
            if ancestor not in unfinished:
                break
        for reader in readers:
            reads[reader] |= reached
            if reaches_held:
                blocked.add(reader)


def _read_through_unfinished(
    field: Field[typing.Any],
    records: ModelLike,
    paths: tuple[tuple[Field[typing.Any], ...], ...],
    probe: ModelLike,
    outside: dict[IdType, set[IdType]],
    reads: dict[IdType, set[IdType]],
    blocked: set[IdType],
) -> None:
    chains = _ancestor_chains(paths, probe, outside)
    if chains is not None:
        _read_up_the_chains(field, records, chains, outside, reads, blocked)
        return
    held = records.env.core.get_protected_ids(field)
    unfinished = _get_unfinished_ids(field, records, outside)
    edges: dict[IdType, set[IdType]] = {}
    frontier = list(unfinished)
    while frontier:
        step = probe.browse(frontier)
        found: set[IdType] = set()
        for prefix in paths:
            for reader, target in _iter_recursive_reads(prefix, step, False):
                if reader == target:
                    continue
                edges.setdefault(reader, set()).add(target)
                if (
                    target not in reads
                    and target not in held
                    and target not in unfinished
                ):
                    found.add(target)
        fresh = _get_unfinished_ids(field, records, found)
        unfinished |= fresh
        frontier = list(fresh)

    for target, readers in outside.items():
        if target not in unfinished:
            continue
        reached: set[IdType] = set()
        reaches_held = False
        visited = {target}
        stack = [target]
        while stack:
            for next_id in edges.get(stack.pop(), ()):
                if next_id in reads:
                    reached.add(next_id)
                elif next_id in held:
                    reaches_held = True
                elif next_id in unfinished and next_id not in visited:
                    visited.add(next_id)
                    stack.append(next_id)
        for reader in readers:
            reads[reader] |= reached
            if reaches_held:
                blocked.add(reader)


def get_recursive_levels(
    field: Field[typing.Any], records: ModelLike
) -> tuple[list[list[IdType]], list[IdType]] | None:
    paths = records.pool.get_recursive_paths(field)
    if paths is None:
        return None
    ids = list(dict.fromkeys(records._ids))
    if not paths or len(ids) < 2:
        return [ids], []

    held = records.env.core.get_protected_ids(field)
    reads: dict[IdType, set[IdType]] = {id_: set() for id_ in ids}
    blocked: set[IdType] = set()
    outside: dict[IdType, set[IdType]] = {}
    probe = records.browse(ids).sudo().with_context(active_test=False)
    through_parent = (
        not held
        and field.store
        and all(id_ in reads for id_ in records.env.core.get_pending_ids(field))
    )
    for prefix in paths:
        for reader, target in _iter_recursive_reads(prefix, probe, through_parent):
            if reader == target or reader not in reads:
                continue
            if target in reads:
                reads[reader].add(target)
            elif target in held:
                blocked.add(reader)
            else:
                outside.setdefault(target, set()).add(reader)
    if outside:
        _read_through_unfinished(field, records, paths, probe, outside, reads, blocked)

    levels, leftover = _sort_levels(ids, reads, blocked)
    _debug.logic(
        "field.recursive_levels",
        model=field.model_name,
        field=field.name,
        records=len(ids),
        levels=len(levels),
        leftover=len(leftover),
        held=len(blocked),
    )
    return levels, leftover


def _recompute_recursive(
    field: Field[typing.Any],
    records: ModelLike,
    to_compute_ids: Collection[IdType],
    apply_except_missing: Callable[[Callable[[typing.Any], None], typing.Any], None],
) -> None:
    computed_ids: list[IdType] = []
    core = records.env.core

    def compute_single(record: typing.Any) -> None:
        if record.id in core.get_pending_ids(field):
            field.compute_value(record, validate=False)
            computed_ids.append(record.id)

    def compute_batch(batch: typing.Any) -> None:
        pending = core.get_pending_ids(field)
        batch = batch.browse(id_ for id_ in batch._ids if id_ in pending).with_prefetch(
            batch._prefetch_ids
        )
        if len(batch) > 1:
            try:
                field.compute_value(batch, validate=False)
            except AccessError:
                _debug.logic(
                    "field.recompute.recursive_level_access_error",
                    model=field.model_name,
                    field=field.name,
                    batch=len(batch),
                )
            else:
                computed_ids.extend(batch._ids)
                return
        for record in batch:
            compute_single(record)

    def recursive_compute(records: typing.Any) -> None:
        pending = core.get_pending_ids(field)
        records = records.browse(id_ for id_ in records._ids if id_ in pending)
        ordered = get_recursive_levels(field, records)
        if ordered is None:
            for record in records:
                compute_single(record)
            return
        levels, leftover = ordered
        for level in levels:
            for index in range(0, len(level), PREFETCH_MAX):
                chunk = level[index : index + PREFETCH_MAX]
                compute_batch(records.browse(chunk).with_prefetch(records._ids))
        for id_ in leftover:
            compute_single(records.browse(id_))

    record_ids = records._ids
    expanded = (
        len(record_ids) == 1
        and record_ids[0] in to_compute_ids
        and not core.has_any_protected()
    )
    if expanded:
        records = records.browse(
            itertools.islice(_expand_ids(record_ids[0], to_compute_ids), PREFETCH_MAX)
        )
        _debug.logic(
            "field.recompute.recursive_expanded",
            model=field.model_name,
            field=field.name,
            pending=len(to_compute_ids),
            batch=len(records),
        )

    transaction = records.env.transaction
    owns_snapshots = transaction.recompute_snapshots is None
    if owns_snapshots:
        transaction.recompute_snapshots = {}
    try:
        apply_except_missing(recursive_compute, records)
    except AccessError:
        if not (expanded and record_ids[0] in computed_ids):
            raise
        _debug.logic(
            "field.recompute.recursive_access_error_swallowed",
            model=field.model_name,
            field=field.name,
            computed=len(computed_ids),
        )
    finally:
        if owns_snapshots:
            transaction.recompute_snapshots = None
    if computed_ids:
        records.browse(computed_ids)._check_computed(field)


def compute_recursive_prefetch(
    field: Field[typing.Any], records: ModelLike, record: ModelLike
) -> ModelLike:
    held = records.env.core.get_protected_ids(field)
    if held:
        records = records.browse(
            id_ for id_ in records._ids if id_ == record.id or id_ not in held
        )
    ordered = get_recursive_levels(field, records) if len(records) > 1 else None
    if ordered is None:
        field.compute_value(record)
        return record
    levels, leftover = ordered
    if record.id in leftover:
        field.compute_value(record)
        return record
    computed: list[IdType] = []
    for level in levels:
        batch = records.browse(
            field._iter_cache_missing_ids(records.browse(level))
        ).with_prefetch(records._ids)
        if batch:
            field.compute_value(batch)
            computed.extend(batch._ids)
        if record.id in level:
            break
    return records.browse(computed)


def _get_ids_mid_compute(field: Field[typing.Any], records: ModelLike) -> set[IdType]:
    core = records.env.core
    if not core.has_any_protected():
        return set()
    model_fields = records._fields
    held: set[IdType] = set()
    for path in records.pool.field_depends.get(field, ()):
        dependency = model_fields.get(path.split(".", 1)[0])
        if dependency is not None:
            held.update(core.get_protected_ids(dependency))
    return held


def _recompute_batched(
    field: Field[typing.Any],
    records: ModelLike,
    to_compute_ids: Collection[IdType],
    apply_except_missing: Callable[[Callable[[typing.Any], None], typing.Any], None],
) -> None:
    held = {
        id_ for id_ in _get_ids_mid_compute(field, records) if id_ in to_compute_ids
    }
    if held:
        _debug.logic(
            "field.recompute.expansion_held_back",
            model=field.model_name,
            field=field.name,
            held=len(held),
        )
    for record in records:
        if record.id in to_compute_ids:
            ids = _expand_ids(record.id, to_compute_ids)
            if held:
                ids = (id_ for id_ in ids if id_ == record.id or id_ not in held)
            recs = record.browse(itertools.islice(ids, PREFETCH_MAX))
            try:
                apply_except_missing(field.compute_value, recs)
                continue
            except AccessError:
                pass
            _debug.logic(
                "field.recompute.batch_access_error_single",
                model=field.model_name,
                field=field.name,
                batch=len(recs),
            )
            field.compute_value(record)


def compute_value(
    field: Field[typing.Any], records: ModelLike, validate: bool = True
) -> None:
    prof = _OrmProfile(_orm_compute)

    env = records.env
    if field.compute_sudo:
        records = records.sudo()
    fields = records.pool.field_computed[field]

    for computed in fields:
        if computed.store:
            env.remove_to_compute(computed, records)

    if _debug.pipeline.enabled:
        _debug.pipeline(
            "field.compute_value",
            model=field.model_name,
            field=field.name,
            records=len(records),
            computed_together=len(fields),
            sudo=bool(field.compute_sudo),
            validate=validate,
        )
    sudo_assigned = [
        (computed, computed._superuser_slot_snapshot(records.env, records._ids))
        for computed in fields
    ]
    try:
        with records.env.protecting(fields, records):
            records._compute_field_value(field, validate=validate)
        for computed, before in sudo_assigned:
            computed._adopt_superuser_assignments(records.env, before)
    except Exception as e:
        _debug.logic(
            "field.compute.failed_rescheduled",
            model=field.model_name,
            field=field.name,
            records=len(records),
            error=type(e).__name__,
        )
        for computed in fields:
            if computed.store:
                env.add_to_compute(computed, records)
        raise

    prof.stop()
    prof.report(
        _orm_compute,
        "compute_value %s.%s: %d records (sudo=%s)",
        field.model_name,
        field.name,
        len(records),
        field.compute_sudo,
    )


def apply_inverse(field: Field[typing.Any], records: ModelLike) -> None:
    prof = _OrmProfile(_orm_compute)

    _debug.pipeline(
        "field.apply_inverse",
        model=field.model_name,
        field=field.name,
        records=len(records),
    )
    call_hook(field.inverse, records)

    prof.stop()
    prof.report(
        _orm_compute,
        "apply_inverse %s.%s: %d records",
        field.model_name,
        field.name,
        len(records),
    )
