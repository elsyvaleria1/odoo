import itertools
import logging
import re
import typing
from collections import defaultdict
from collections.abc import Collection, Iterable, Sequence
from itertools import batched

from odoo.exceptions import MissingError
from odoo.libs.collections import OrderedSet
from odoo.libs.debug_log import DebugLog
from odoo.libs.iteration import PENDING, SENTINEL

from ... import decorators as api
from ...components.recompute import RecomputeScheduler
from ...domain import Domain, ids_selected_without_query
from ...fields._field_cache_miss import origin_read_key
from ...helpers import (
    get_all_company_ids,
    get_fields_by_name,
    get_or_create_class_memo,
)
from ...primitives import NewId
from ...profiling import _OrmProfile
from ..table_objects import Constraint
from ._model_stubs import _ModelStubs

_orm_cache = logging.getLogger("odoo.orm.cache")
_orm_compute = logging.getLogger("odoo.orm.compute")
_debug = DebugLog(__name__)

_SQL_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

if typing.TYPE_CHECKING:
    from ..._typing import BaseModel, IdType
    from ...fields.base import Field
    from ...runtime import TriggerTree
    from ...runtime.origin_reads import OriginReads

    type ToValidate = dict[Field[typing.Any], OrderedSet[int]]


def _filtered_referencing(
    records: BaseModel, fname: str, ids: Collection[typing.Any]
) -> BaseModel:
    return records.filtered(lambda r: not set(r[fname]._ids).isdisjoint(ids))


def _fires_constraints(env: typing.Any, field: Field[typing.Any]) -> bool:
    if field.store or not field.related:
        return False
    names = env.registry[field.model_name].__dict__.get(
        "_constrained_projection_names__"
    )
    if names is None:
        names = env[field.model_name]._constrained_projection_names
    return field.name in names


def _tree_column(field: Field[typing.Any]) -> bool:
    return (
        field.is_many2one
        and field.model_name == field.comodel_name
        and bool(field.store)
        and bool(field.column_type)
        and not field.compute
        and not field.company_dependent
    )


class _TreeEdges:
    # One trigger walk's view of the self-referencing many2ones it crosses. A
    # recursive field re-enters the walk once per level of its tree, and each
    # level looked its neighbours up again: a search for the children, a fetch
    # of the parent. Once a re-entry crosses a column a second time, the rest
    # of the tree is read in one statement; a walk that does not recurse keeps
    # its one lookup per crossing.
    __slots__ = ("_children", "_crossed", "_parents")

    def __init__(self) -> None:
        self._children: dict[Field[typing.Any], dict[int, list[int]]] = {}
        self._parents: dict[Field[typing.Any], dict[int, int | None]] = {}
        self._crossed: set[tuple[Field[typing.Any], bool]] = set()

    def follow(
        self, records: BaseModel, field: Field[typing.Any], recursive: bool
    ) -> BaseModel | None:
        if field.comodel_name != records._name or field.model_name != records._name:
            return None
        if records._table_query:
            return None
        downward = field.is_many2one
        column = field if downward else _inverse_column(records, field)
        if column is None or not _tree_column(column):
            return None
        if not all(type(id_) is int for id_ in records._ids):
            return None
        ids = typing.cast("Sequence[int]", records._ids)
        if downward:
            children = self._known_children(records, column, ids)
        else:
            children = self._known_parents(records, column, ids)
        if children is not None:
            return records.browse(children)
        key = (column, downward)
        if not recursive or key not in self._crossed:
            self._crossed.add(key)
            return None
        if downward and _one2many_cached(records, column, ids):
            # the walk's own lookup reads the cache: no statement to save
            return None
        if downward:
            return records.browse(self._read_descendants(records, column, ids))
        return records.browse(self._read_ancestors(records, column, ids))

    def remember(
        self, records: BaseModel, field: Field[typing.Any], found: BaseModel
    ) -> None:
        # a lookup of one record's children answers the re-entry of the
        # recursive field from that same record
        if len(records._ids) != 1 or not field.is_many2one:
            return
        (id_,) = records._ids
        if type(id_) is not int or not _tree_column(field):
            return
        if field.comodel_name != records._name or field.model_name != records._name:
            return
        if all(type(child) is int for child in found._ids):
            self._children.setdefault(field, {}).setdefault(
                id_, sorted(typing.cast("Sequence[int]", found._ids))
            )

    def _known_children(
        self, records: BaseModel, column: Field[typing.Any], ids: Sequence[int]
    ) -> list[int] | None:
        memo = self._children.get(column)
        if not memo:
            return None
        if records.env.core.get_dirty(column):
            # the rows no longer hold the tree the cache does
            _debug.logic(
                "recompute.tree_edges_dropped",
                model=records._name,
                field=column.name,
                known=len(memo),
            )
            memo.clear()
            return None
        if not all(id_ in memo for id_ in ids):
            return None
        return sorted({child for id_ in ids for child in memo[id_]})

    def _read_descendants(
        self, records: BaseModel, column: Field[typing.Any], ids: Sequence[int]
    ) -> list[int]:
        memo = self._children.setdefault(column, {})
        missing = [id_ for id_ in ids if id_ not in memo]
        edges = records.env.backend.descendant_edges(records, column.name, missing)
        fresh = set(missing)
        fresh.update(child for child, _parent in edges if child not in memo)
        for id_ in fresh:
            memo[id_] = []
        for child, parent in edges:
            if parent in fresh:
                memo[parent].append(child)
        inverse = _inverse_column(records, column)
        if inverse is not None and inverse.is_x2many and not inverse.compute:
            self._cache_one2many(records, inverse, memo, fresh)
        _debug.logic(
            "recompute.tree_descendants_read",
            model=records._name,
            field=column.name,
            roots=len(missing),
            descendants=len(edges),
            one2many=inverse.name if inverse is not None else None,
        )
        return sorted({child for id_ in ids for child in memo[id_]})

    def _cache_one2many(
        self,
        records: BaseModel,
        inverse: Field[typing.Any],
        memo: dict[int, list[int]],
        fresh: set[int],
    ) -> None:
        # the level reads left the one2many cached, and what reads it next
        # (the recompute, the caller, the next walk) found it there. The
        # column was flushed before the tree was read, so a record without
        # children holds none; the others are read once, in their order.
        cache = inverse._get_cache(records.env)
        empty = [id_ for id_ in fresh if not memo[id_] and id_ not in cache]
        if empty:
            inverse._update_cache(records.browse(empty), ())
        parents = sorted(id_ for id_ in fresh if memo[id_])
        if parents:
            records.browse(parents).fetch([inverse.name])

    def _known_parents(
        self, records: BaseModel, column: Field[typing.Any], ids: Sequence[int]
    ) -> list[int] | None:
        return _parents_from(
            column._get_cache(records.env), self._parents.get(column, {}), ids
        )

    def _read_ancestors(
        self, records: BaseModel, column: Field[typing.Any], ids: Sequence[int]
    ) -> list[int]:
        cache = column._get_cache(records.env)
        memo = self._parents.setdefault(column, {})
        missing = [id_ for id_ in ids if id_ not in cache and id_ not in memo]
        # read without flushing the column: the cached values override the rows
        rows = records.env.backend.ancestors(records, column.name, missing, flush=False)
        for id_, parent in rows:
            memo.setdefault(id_, parent)
        for id_ in missing:
            memo.setdefault(id_, None)
        _debug.logic(
            "recompute.tree_ancestors_read",
            model=records._name,
            field=column.name,
            records=len(missing),
            ancestors=len(rows),
        )
        return _parents_from(cache, memo, ids) or []


def _parents_from(
    cache: typing.Mapping[typing.Any, typing.Any],
    memo: dict[int, int | None],
    ids: Sequence[int],
) -> list[int] | None:
    # a cached value wins over the row, as it does in a fetch
    parents: OrderedSet[int] = OrderedSet()
    for id_ in ids:
        parent = cache.get(id_, SENTINEL)
        if parent is SENTINEL:
            if id_ not in memo:
                return None
            parent = memo[id_]
        if parent:
            parents.add(parent)
    return list(parents)


def _company_dependent_referrers(
    model: BaseModel, field: Field[typing.Any], ids: list[int]
) -> list[int]:
    # a company-dependent value is one per company: the records naming these
    # in any company depend on them, not only those naming them in the
    # writer's, whose search alone would leave the others' dependents stale
    referrers: OrderedSet[int] = OrderedSet()
    company_ids = get_all_company_ids(model.env)
    for company_id in company_ids:
        scoped = model.sudo().with_company(company_id)
        referrers.update(scoped.search([(field.name, "in", ids)], order="id")._ids)
    _debug.logic(
        "recompute.company_dependent_referrers",
        model=model._name,
        field=field.name,
        companies=len(company_ids),
        records=len(referrers),
    )
    return sorted(referrers)


def _one2many_cached(
    records: BaseModel, column: Field[typing.Any], ids: Sequence[int]
) -> bool:
    inverse = _inverse_column(records, column)
    if inverse is None or not inverse.is_x2many:
        return False
    cache = inverse._get_cache(records.env)
    return all(id_ in cache for id_ in ids)


def _inverse_column(
    records: BaseModel, field: Field[typing.Any]
) -> Field[typing.Any] | None:
    for invf in records.pool.field_inverses[field]:
        if not (invf.is_x2many and invf.domain):
            return invf
    return None


class RecomputeMixin(_ModelStubs):
    __slots__ = ()

    @api.private
    def modified(
        self,
        fnames: Collection[str],
        create: bool = False,
        before: bool = False,
    ) -> None:
        if not self or not fnames:
            return

        if origin_reads := self.env.transaction.origin_reads:
            self._modified_origin_reads(origin_reads, fnames, before)

        # a created row is in no sibling's cache yet, and the before phase of
        # a write is followed by its after phase, which drops what the
        # siblings cached once the new values are in place
        if not (create or before):
            self._invalidate_inheritance_tree(fnames)

        core = self.env.core

        if before:
            scheduler = core.new_scheduler()
            self._modified_trigger_loop(fnames, False, scheduler)

            _debug.pipeline(
                "recompute.modified_before",
                model=self._name,
                records=len(self),
                fields_to_recompute=len(scheduler.to_recompute),
            )
            for field, ids in scheduler.to_recompute.items():
                records = self.env[field.model_name].browse(ids)
                self.env.add_to_compute(field, records)
        else:
            scheduler = core.new_scheduler(inline=True)
            _debug.pipeline(
                "recompute.modified",
                model=self._name,
                records=len(self),
                fields=len(fnames),
                create=create,
            )
            to_validate: ToValidate = {}
            self._modified_trigger_loop(fnames, create, scheduler, to_validate)
            being_created = set(self._ids) if create else ()
            transaction = self.env.transaction
            for field, validated_ids in to_validate.items():
                records = (
                    self.env[field.model_name]
                    .browse(
                        id_
                        for id_ in validated_ids
                        if not (field.model_name == self._name and id_ in being_created)
                        and not transaction.is_being_created(field.model_name, id_)
                    )
                    .exists()
                )
                _debug.pipeline(
                    "recompute.projection_constraints",
                    model=field.model_name,
                    field=field.name,
                    records=len(records),
                )
                records._check_fields([field.name])

    def _modified_origin_reads(
        self, origin_reads: OriginReads, fnames: Collection[str], before: bool
    ) -> None:
        # a draft's own assignment is no longer what it read from its origin;
        # a saved record's change drops what its drafts read of it, and what
        # the drafts of the records a many2one names, before the write and
        # after it, read of their x2many; then the drafts' dependents are told.
        # Before the write the records a many2one names are only noted: a
        # draft's dependents told then would read its origin as it still is
        ids = self._ids
        real = [id_ for id_ in ids if id_]
        if len(real) < len(ids):
            env = self.env
            origin_reads.forget_assigned(
                self._name,
                [typing.cast("NewId", id_) for id_ in ids if not id_],
                fnames,
                lambda field: origin_read_key(field, env),
            )
        if not real:
            return
        env = self.env
        evicted: dict[Field[typing.Any], OrderedSet[NewId]] = defaultdict(OrderedSet)
        changes: list[tuple[str, list[int], Collection[str]]] = []
        for fname in fnames:
            field = self._fields.get(fname)
            if field is None or not field.is_many2one:
                continue
            inverses = [f for f in self.pool.field_inverses[field] if f.is_x2many]
            if not inverses:
                continue
            # the value it names is read when not cached: before the write it
            # is the record losing these, whose drafts must read again. A row
            # already deleted holds only what the cache has of it
            rows = self.browse(real).sudo().with_context(active_test=False)
            try:
                named = rows[fname]._ids
            except MissingError:
                cache = field._get_cache(env)
                named = tuple(cache.get(id_) for id_ in real)
            co_ids = [co_id for co_id in named if isinstance(co_id, int)]
            changes.extend((invf.model_name, co_ids, (invf.name,)) for invf in inverses)
        if before:
            origin_reads.defer(changes)
            return
        changes += [(self._name, real, fnames), *origin_reads.take_deferred()]
        for model_name, model_ids, names in changes:
            for field, drafts in origin_reads.evict(
                env.core, model_name, model_ids, names
            ).items():
                evicted[field].update(drafts)
        origin_reads.telling += 1
        try:
            for field, draft_ids in evicted.items():
                env[field.model_name].browse(draft_ids).modified([field.name])
        finally:
            origin_reads.telling -= 1

    def _invalidate_inheritance_tree(self, fnames: Collection[str]) -> None:
        tree = self.env._table_inheritance_tree(self._name)
        if not tree:
            return
        _debug.pipeline(
            "recompute.invalidate_inheritance_tree",
            model=self._name,
            siblings=len(tree),
            records=len(self),
            fields=len(fnames),
        )
        for model_name in tree:
            other = self.env[model_name]
            names = [name for name in fnames if name in other._fields]
            if names:
                # only the sibling's own dirty values: flushing the tree from
                # here would write the very values being modified
                sibling = other.browse(self._ids)
                sibling._flush_recordset_own(get_fields_by_name(sibling, names))
                sibling._invalidate_cache(names, sibling._ids)

    def _modified_before(self, fnames: Collection[str]) -> None:
        return self.modified(fnames, before=True)

    def _modified_traverse(
        self,
        todo: list[Iterable[tuple[Field[typing.Any], BaseModel, bool]]],
        scheduler: RecomputeScheduler,
        debug: bool,
        to_validate: ToValidate | None,
        edges: _TreeEdges,
    ) -> tuple[int, int]:
        _mark_count = 0
        _invalidate_count = 0
        env = self.env
        for field, records, entry_create in itertools.chain.from_iterable(todo):
            if to_validate is not None and _fires_constraints(env, field):
                to_validate.setdefault(field, OrderedSet()).update(
                    id_ for id_ in records._ids if id_
                )
            cached_ids = None
            if field.recursive and not field.is_stored_computed:
                cached_ids = field._get_all_cache_ids(env).keys()

            recursive_ids = scheduler.schedule_recompute(
                field,
                OrderedSet(records._ids),
                cached_ids=cached_ids,
            )

            if scheduler.to_invalidate:
                for inv_field, inv_ids in scheduler.to_invalidate:
                    inv_field._invalidate_cache(env, inv_ids)
                scheduler.to_invalidate.clear()

            if recursive_ids:
                todo.append(
                    records.browse(recursive_ids)._modified(
                        [field], entry_create, edges, recursive=True
                    )
                )

            if debug:
                n = len(recursive_ids) if recursive_ids else len(records)
                if field.is_stored_computed:
                    _mark_count += n
                else:
                    _invalidate_count += n
        return _mark_count, _invalidate_count

    def _modified_trigger_loop(
        self,
        fnames: Collection[str],
        create: bool,
        scheduler: RecomputeScheduler,
        to_validate: ToValidate | None = None,
    ) -> None:
        self._modified_trigger_walk(fnames, create, scheduler, to_validate)
        if create:
            return
        # a created root row is no subtype's row, but an existing one may be:
        # the subtype reads the root's column through its own field, which
        # holds the triggers of the subtype's dependents
        for members, names in self._modified_tree_members(fnames):
            members._modified_trigger_walk(names, False, scheduler, to_validate)

    def _modified_tree_members(
        self, fnames: Collection[str]
    ) -> list[tuple[BaseModel, list[str]]]:
        root = self._table_inheritance_root
        if not root or self._table != root:
            return []
        triggers = self.pool._get_field_triggers()
        found: list[tuple[BaseModel, list[str]]] = []
        ids: list[IdType] | None = None
        for model_name in self.env._table_inheritance_tree(self._name):
            model = self.env[model_name]
            if model._table == root:
                continue
            fields = model._fields
            names = [
                fname
                for fname in fnames
                if (field := fields.get(fname)) is not None and field in triggers
            ]
            if not names or not model._select_trigger_tree(
                [fields[fname] for fname in names]
            ):
                continue
            if ids is None:
                ids = [id_ for id_ in self._ids if id_]
            if not ids:
                return found
            members = model.browse(ids).exists()
            _debug.logic(
                "recompute.tree_members",
                model=self._name,
                member=model_name,
                records=len(ids),
                members=len(members),
                fields=len(names),
            )
            if members:
                found.append((members, names))
        return found

    def _modified_trigger_walk(
        self,
        fnames: Collection[str],
        create: bool,
        scheduler: RecomputeScheduler,
        to_validate: ToValidate | None = None,
    ) -> None:
        prof = _OrmProfile(_orm_compute)
        _fnames_list: typing.Any = ()
        _mark_count = 0
        _invalidate_count = 0
        if prof.debug:
            _fnames_list = (
                list(fnames) if not isinstance(fnames, (list, dict)) else fnames
            )

        _field_triggers = self.pool._get_field_triggers()
        _fields = self._fields
        fields = [_fields[fname] for fname in fnames]
        if not any(f in _field_triggers for f in fields):
            _debug.logic(
                "recompute.no_triggers",
                model=self._name,
                records=len(self),
                fields=len(fields),
                create=create,
            )
            prof.stop()
            prof.report(
                _orm_compute,
                "modified %s: %d fields on %d records (create=%s, no triggers)",
                self._name,
                len(_fnames_list),
                len(self),
                create,
            )
            if prof.timed and self.env.transaction.observers:
                self.env.transaction.observe_timing(
                    "modified", self._name, len(self), prof.elapsed
                )
            return

        edges = _TreeEdges()
        todo = [self._modified(fields, create, edges)]
        prof.mark("tree")

        _mark_count, _invalidate_count = self._modified_traverse(
            todo, scheduler, prof.debug, to_validate, edges
        )

        _debug.pipeline(
            "recompute.triggers_traversed",
            model=self._name,
            records=len(self),
            fields=len(fields),
            create=create,
            chains=len(todo),
            to_recompute=len(scheduler.to_recompute),
        )
        prof.stop("traverse")
        prof.report(
            _orm_compute,
            "modified %s: %d fields on %d records (create=%s, marked=%d, invalidated=%d)",
            self._name,
            len(_fnames_list),
            len(self),
            create,
            _mark_count,
            _invalidate_count,
        )
        if prof.timed and self.env.transaction.observers:
            self.env.transaction.observe_timing(
                "modified", self._name, len(self), prof.elapsed
            )

    def _modified(
        self,
        fields: list[Field[typing.Any]],
        create: bool,
        edges: _TreeEdges,
        recursive: bool = False,
    ) -> Iterable[tuple[Field[typing.Any], BaseModel, bool]]:
        # this model's records for its own fields, and a dependent model's
        # where the trigger walks into one

        tree = self._select_trigger_tree(fields)
        if not tree:
            return ()

        env = self.env
        if len(tree):
            records = self.with_env(env._derive(su=True, active_test=False))
        else:
            records = self
        return records._modified_triggers(
            tree, edges=edges, create=create, recursive=recursive
        )

    def _select_trigger_tree(
        self, fields: list[Field[typing.Any]]
    ) -> TriggerTree[Field[typing.Any]]:
        env = self.env
        core = env.core

        def static(field: Field[typing.Any]) -> bool:
            return field.is_stored_computed or _fires_constraints(env, field)

        def cached(field: Field[typing.Any]) -> bool:
            if field._is_context_dependent(env):
                return core.has_any_context_cached(field)
            return core.has_any_cached(field)

        def select(field: Field[typing.Any]) -> bool:
            return static(field) or cached(field)

        return self.pool.get_trigger_tree(
            fields, select=select, static=static, cached=cached
        )

    def _modified_triggers(
        self,
        tree: TriggerTree[Field[typing.Any]],
        *,
        edges: _TreeEdges,
        create: bool = False,
        recursive: bool = False,
    ) -> Iterable[tuple[Field[typing.Any], BaseModel, bool]]:
        # the walk descends into the dependent models, so what comes out of it
        # is this model's records only for the fields of the tree's own root
        if not self:
            return

        own = typing.cast("BaseModel", self)
        for field in tree.root:
            yield field, own, create

        for field, subtree in tree.items():
            if create and (field.is_many2one or field.is_many2one_reference):
                continue

            model = self.env[field.model_name]
            if self._invalidates_from_cache(field, subtree):
                yield from self._modified_cache_only(field, subtree)
                continue
            followed = edges.follow(own, field, recursive)
            if followed is not None:
                yield from followed._modified_triggers(
                    subtree, edges=edges, recursive=recursive
                )
                continue
            for invf in model.pool.field_inverses[field]:
                if not (invf.is_x2many and invf.domain):
                    if invf.is_many2one_reference:
                        model_field = invf.model_field
                        assert model_field is not None
                        rec_ids: OrderedSet[int] = OrderedSet()
                        for rec in self:
                            try:
                                if rec[model_field] == field.model_name:
                                    rec_ids.add(rec[invf.name])
                            except MissingError:
                                continue
                        records = model.browse(rec_ids)
                    else:
                        try:
                            records = self[invf.name]
                        except MissingError:
                            _debug.logic(
                                "recompute.inverse_missing_records",
                                model=self._name,
                                field=invf.name,
                                records=len(self),
                            )
                            records = self.exists()[invf.name]

                    if field.model_name == records._name:
                        if not any(self._ids):
                            records = records.browse(
                                it and NewId(it) for it in records._ids
                            )
                        break
            else:
                self_ids = self._ids
                real_ids = [id_ for id_ in self_ids if id_]
                records = model.browse()
                _debug.logic(
                    "recompute.trigger_search_fallback",
                    model=self._name,
                    via=f"{field.model_name}.{field.name}",
                    records=len(real_ids),
                )
                if real_ids and field.company_dependent:
                    records = model.browse(
                        _company_dependent_referrers(model, field, real_ids)
                    )
                elif real_ids:
                    domain = Domain(field.name, "in", real_ids).optimize_full(model)
                    ids = ids_selected_without_query(domain)
                    if ids is None:
                        records = model.search(domain, order="id")
                    else:
                        records = model.browse(sorted(ids))
                if len(real_ids) != len(self_ids):
                    field_cache = field._get_cache(model.env)
                    cache_records = model.browse(field_cache)
                    new_ids = set(self_ids)
                    records |= _filtered_referencing(cache_records, field.name, new_ids)

            edges.remember(own, field, records)
            yield from records._modified_triggers(
                subtree, edges=edges, recursive=recursive
            )

    def _invalidates_from_cache(
        self, field: Field[typing.Any], subtree: TriggerTree[Field[typing.Any]]
    ) -> bool:
        if len(subtree) or field.is_many2one_reference:
            return False
        if any(
            f.is_stored_computed or f.recursive or _fires_constraints(self.env, f)
            for f in subtree.root
        ):
            return False
        inverses = self.env[field.model_name].pool.field_inverses[field]
        return any(invf.is_x2many and not invf.domain for invf in inverses)

    def _modified_cache_only(
        self, field: Field[typing.Any], subtree: TriggerTree[Field[typing.Any]]
    ) -> Iterable[tuple[Field[typing.Any], BaseModel, bool]]:
        # the records yielded are the *dependent* field's, not this model's
        env = self.env
        model = env[field.model_name]
        self_ids = set(self._ids)
        back = field._get_cache(env)
        if field.is_many2one:

            def points_back(value: typing.Any) -> bool:
                return value in self_ids
        else:
            # a paired x2many caches a tuple of ids, never a bare id
            def points_back(value: typing.Any) -> bool:
                return not self_ids.isdisjoint(value)

        for dependent in subtree.root:
            ids = [
                id_
                for id_ in dependent._get_all_cache_ids(env)
                if id_ not in back or points_back(back[id_])
            ]
            _debug.logic(
                "recompute.invalidated_from_cache",
                model=self._name,
                via=f"{field.model_name}.{field.name}",
                field=dependent.name,
                records=len(ids),
            )
            if ids:
                yield dependent, model.browse(ids), False

    @classmethod
    def _get_stored_computed_fields(cls) -> tuple[Field[typing.Any], ...]:
        return get_or_create_class_memo(
            cls,
            "_stored_computed_fields__",
            lambda: tuple(f for f in cls._fields.values() if f.is_stored_computed),
        )

    @classmethod
    def _get_check_coupled_fields(
        cls,
    ) -> dict[Field[typing.Any], tuple[Field[typing.Any], ...]]:
        def get_check_coupled_fields_uncached() -> dict[
            Field[typing.Any], tuple[Field[typing.Any], ...]
        ]:
            columns = {
                name: field
                for name, field in cls._fields.items()
                if field.store and field.column_type
            }
            coupled: dict[Field[typing.Any], set[Field[typing.Any]]] = defaultdict(set)
            for table_object in cls._table_objects.values():
                if not isinstance(table_object, Constraint):
                    continue
                definition = table_object.get_definition(cls.pool)
                if not definition.lstrip().upper().startswith("CHECK"):
                    continue
                group = {
                    columns[token]
                    for token in _SQL_IDENTIFIER.findall(definition)
                    if token in columns
                }
                for field in group:
                    coupled[field].update(
                        other
                        for other in group
                        if other is not field and other.is_stored_computed
                    )
            return {field: tuple(others) for field, others in coupled.items() if others}

        return get_or_create_class_memo(
            cls, "_check_coupled_fields__", get_check_coupled_fields_uncached
        )

    def _recompute_check_coupled_fields(self) -> None:
        coupled = self._get_check_coupled_fields()
        core = self.env.core
        if not coupled or not core.has_pending():
            return
        for _pass in range(len(coupled) + 1):
            progressed = False
            for field, partners in coupled.items():
                dirty = core.get_dirty(field)
                if not dirty:
                    continue
                for partner in partners:
                    pending = core.get_pending_ids(partner)
                    if ids := [id_ for id_ in dirty if id_ in pending]:
                        _debug.logic(
                            "recompute.flush_check_coupled",
                            model=self._name,
                            dirty=field.name,
                            recomputed=partner.name,
                            records=len(ids),
                        )
                        self._recompute_field(partner, ids)
                        progressed = True
            if not progressed:
                return

    def _recompute_model(self, fnames: Collection[str] | None = None) -> None:
        self._recompute_fields(self._resolve_recompute_fields(fnames), None)

    def _recompute_recordset(self, fnames: Collection[str] | None = None) -> None:
        self._recompute_fields(self._resolve_recompute_fields(fnames), self._ids)

    def _resolve_recompute_fields(
        self, fnames: Collection[str] | None
    ) -> Collection[Field[typing.Any]]:
        if fnames is None:
            return self._get_stored_computed_fields()
        return get_fields_by_name(self, fnames)

    def _recompute_fields(
        self, fields: Collection[Field[typing.Any]], ids: Sequence[IdType] | None
    ) -> None:
        if not self.env.core.has_pending():
            return
        for field in fields:
            if field.is_stored_computed:
                self._recompute_field(field, ids)

    def _recompute_field(
        self, field: Field[typing.Any], ids: Sequence[IdType] | None = None
    ) -> None:
        ids_to_compute = self.env.core.get_pending_ids(field)
        scoped = ids is not None  # debuglog
        # not rebound: the pending set is passed through rather than copied
        selected: Collection[IdType] = (
            ids_to_compute
            if ids is None
            else [id_ for id_ in ids if id_ in ids_to_compute]
        )
        if not selected:
            return

        prof = _OrmProfile(_orm_compute)

        # NewIds included: a new record's stored compute is scheduled like
        # any other, and dropping it here leaves it pending forever -- so a
        # write to one field of a compute group survives until something
        # reads a sibling, which recomputes the group over the write.
        # `_expand_ids` already batches new and real ids apart.
        records = self.browse(tuple(selected))
        if _debug.pipeline.enabled:
            _debug.pipeline(
                "recompute.field",
                model=field.model_name,
                field=field.name,
                records=len(records),
                pending=len(ids_to_compute),
                scoped=scoped,
            )
        field.recompute(records)

        prof.stop()
        prof.report(
            _orm_compute,
            "recompute_field %s.%s: %d records",
            field.model_name,
            field.name,
            len(records),
        )
        if prof.timed and self.env.transaction.observers:
            self.env.transaction.observe_timing(
                "recompute", field.model_name, len(records), prof.elapsed
            )

    @api.private
    def flush_model(self, fnames: Collection[str] | None = None) -> None:
        self._flush_model_own(fnames)
        if self._table_inheritance_root:
            self._flush_table_inheritance_siblings(fnames)

    def _flush_model_own(self, fnames: Collection[str] | None) -> None:
        fields = self._resolve_recompute_fields(fnames)
        core = self.env.core
        if fnames is not None and not core.has_pending() and not core.is_any_dirty():
            return

        prof = _OrmProfile(_orm_cache)

        self._recompute_fields(fields, None)
        prof.mark("recompute")
        if fnames is None or any(map(core.has_dirty_field, fields)):
            _debug.pipeline(
                "recompute.flush_model",
                model=self._name,
                fields=None if fnames is None else len(fields),
            )
            self._flush()

        prof.stop("flush")
        prof.report(_orm_cache, "flush_model %s", self._name)

    def _flush_table_inheritance_siblings(
        self, fnames: Collection[str] | None, ids: Sequence[IdType] | None = None
    ) -> None:
        for name in self.env._table_inheritance_tree(self._name):
            sibling = self.env[name]
            if fnames is None:
                sibling._flush_model_own(None)
                continue
            shared = [fname for fname in fnames if fname in sibling._fields]
            if not shared:
                continue
            if ids is None:
                sibling._flush_model_own(shared)
            else:
                # a fetch of these rows: the sibling's dirty values of the read
                # columns must reach the table, its pending computes stay pending
                sibling._flush_if_dirty([sibling._fields[fname] for fname in shared])

    @api.private
    def flush_recordset(self, fnames: Collection[str] | None = None) -> None:
        named_fields = None if fnames is None else get_fields_by_name(self, fnames)
        if not self:
            return
        self._flush_recordset_own(named_fields)
        if not self._table_inheritance_root:
            return
        # the rows are the siblings' rows too: what one of them holds dirty on
        # them is what a raw query after this flush would miss
        for name in self.env._table_inheritance_tree(self._name):
            sibling = self.env[name].browse(self._ids)
            if named_fields is None:
                sibling._flush_recordset_own(None)
                continue
            shared = [
                sibling._fields[field.name]
                for field in named_fields
                if field.name in sibling._fields
            ]
            if shared:
                sibling._flush_recordset_own(shared)

    def _flush_recordset_own(
        self, named_fields: list[Field[typing.Any]] | None
    ) -> None:
        core = self.env.core
        if (
            named_fields is not None
            and not core.has_pending()
            and not core.is_any_dirty()
        ):
            return
        self._recompute_fields(
            self._get_stored_computed_fields()
            if named_fields is None
            else named_fields,
            self._ids,
        )
        fields: Collection[Field[typing.Any]] = (
            self._fields.values() if named_fields is None else named_fields
        )
        ids = self._ids
        if len(ids) == 1:
            id_ = ids[0]
            dirty = any(id_ in (core.get_dirty(field) or ()) for field in fields)
        else:
            id_set = set(ids)
            dirty = not all(
                id_set.isdisjoint(core.get_dirty(field) or ()) for field in fields
            )
        if dirty:
            _debug.pipeline(
                "recompute.flush_recordset",
                model=self._name,
                records=len(ids),
                fields=None if named_fields is None else len(named_fields),
            )
            self._flush()

    def _flush_if_dirty(self, fields: Collection[Field[typing.Any]]) -> None:
        # a SELECT about to read these columns: a dirty value among them must
        # reach the table first, and nothing is recomputed on the way
        core = self.env.core
        if any(core.get_dirty(field) for field in fields):
            self._flush()

    def _flush(self) -> None:
        core = self.env.core
        self._recompute_check_coupled_fields()
        dirty_field_ids = core.pop_dirty_for_model(self._name)
        if not dirty_field_ids:
            return

        prof = _OrmProfile(_orm_cache)

        model = self
        env = self.env
        cls = type(model)

        id_to_fields: dict[IdType, list[Field[typing.Any]]] = defaultdict(list)
        for field, ids in dirty_field_ids.items():
            for id_ in ids:
                id_to_fields[id_].append(field)

        dirty_ids = list(id_to_fields)
        prof.mark("collect")

        _debug.pipeline(
            "recompute.flush",
            model=self._name,
            fields=len(dirty_field_ids),
            records=len(dirty_ids),
        )
        _batch_count = 0
        BATCH_SIZE = 1000
        with env.cr.pipeline():
            for some_ids in batched(dirty_ids, BATCH_SIZE, strict=False):
                if prof.debug:
                    _batch_count += 1
                vals_list = []
                _new = object.__new__
                try:
                    for id_ in some_ids:
                        record = _new(cls)
                        record.env = env
                        record._ids = (id_,)
                        record._prefetch_ids = some_ids
                        vals = {}
                        for f in id_to_fields[id_]:
                            col_val = f.get_column_update(record)
                            if col_val is not PENDING:
                                vals[f.name] = col_val
                            elif core.is_pending(f, id_):
                                _debug.logic(
                                    "recompute.flush_deferred_pending",
                                    model=self._name,
                                    field=f.name,
                                    record=id_,
                                )
                                core.mark_dirty(f, (id_,))
                            else:
                                _debug.logic(
                                    "recompute.flush_pending_unscheduled",
                                    model=self._name,
                                    field=f.name,
                                    record=id_,
                                )
                                raise RuntimeError(
                                    f"Cannot flush {f}: the cached value is "
                                    f"PENDING on {self._name}({id_}) but the "
                                    f"field is not scheduled for recomputation, "
                                    f"so the value can never materialize"
                                )
                        vals_list.append(vals)
                except KeyError as e:
                    raise RuntimeError(
                        f"Could not find all values of {self._name}({id_}) to flush them\n"
                        f"    Context: {env.context}\n"
                        f"    Cache: {env.cache!r}"
                    ) from e
                model.browse(some_ids)._write_multi(vals_list)

        prof.stop("update")
        prof.report(
            _orm_cache,
            "_flush %s: %d fields, %d records, %d batches",
            self._name,
            len(dirty_field_ids),
            len(dirty_ids),
            _batch_count,
        )
        if prof.timed and self.env.transaction.observers:
            self.env.transaction.observe_timing(
                "flush", self._name, len(dirty_ids), prof.elapsed
            )
