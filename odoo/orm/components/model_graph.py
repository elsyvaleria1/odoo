import logging
import threading
from collections import defaultdict
from typing import TYPE_CHECKING, Any

from odoo.libs._trigger_trees import TriggerGraph
from odoo.libs.accel import get_trigger_trees as _get_trigger_trees
from odoo.libs.collections import Collector
from odoo.libs.debug_log import DebugLog
from odoo.libs.iteration.sorting import strongly_connected_components
from odoo.libs.lru import LRU

if TYPE_CHECKING:
    from collections.abc import Callable, Collection, Iterator

    from odoo.libs._trigger_trees import Bucket, Meta, Node

    from ._protocols import FieldLike

    type Triggers[F] = defaultdict[F, dict[tuple[F, ...], list[F]]]


_Collector = Collector

_debug = DebugLog(__name__)
_logger = logging.getLogger(__name__)

_TREE_NODE_BUDGET = 20_000


def _measure(node: Node) -> tuple[int, int]:
    nodes, depth = 1, 0
    for _label, child in node[1]:
        child_nodes, child_depth = _measure(child)
        nodes += child_nodes
        depth = max(depth, child_depth + 1)
    return nodes, depth


def _get_stored_compute_adjacency[F: FieldLike](
    triggers: Triggers[F],
) -> dict[F, set[F]]:
    all_targets: set[F] = set()
    for dep_field, paths in triggers.items():
        for targets in paths.values():
            for target in targets:
                if target.store and target.compute:
                    all_targets.add(target)
                    if dep_field.store and dep_field.compute:
                        all_targets.add(dep_field)

    adjacency: dict[F, set[F]] = {field: set() for field in all_targets}
    for dep_field, paths in triggers.items():
        if dep_field not in all_targets:
            continue
        dep_adjacency = adjacency[dep_field]
        for targets in paths.values():
            for target in targets:
                if target in all_targets and target is not dep_field:
                    dep_adjacency.add(target)
    return adjacency


def _condense_components[F](
    adjacency: dict[F, set[F]], sccs: list[list[F]]
) -> tuple[dict[F, int], list[set[int]], list[int]]:
    component_of: dict[F, int] = {}
    for component_index, component in enumerate(sccs):
        for field in component:
            component_of[field] = component_index
    component_adjacency: list[set[int]] = [set() for _ in sccs]
    component_in_degree: list[int] = [0] * len(sccs)
    for field, dependents in adjacency.items():
        source = component_of[field]
        source_adjacency = component_adjacency[source]
        for dependent in dependents:
            sink = component_of[dependent]
            if sink != source and sink not in source_adjacency:
                source_adjacency.add(sink)
                component_in_degree[sink] += 1
    return component_of, component_adjacency, component_in_degree


class TriggerTree[F = Any](dict[F, "TriggerTree[F]"]):
    __slots__ = ("root",)
    root: tuple[F, ...]

    def __init__(self, root: Collection[F] = (), *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.root = tuple(root)

    def __bool__(self) -> bool:
        return bool(self.root or len(self))

    def __repr__(self) -> str:
        return f"TriggerTree(root={self.root!r}, {super().__repr__()})"

    def iter_depth_first(self) -> Iterator[TriggerTree[F]]:
        yield self
        for subtree in self.values():
            yield from subtree.iter_depth_first()

    @classmethod
    def merge(
        cls, trees: list[TriggerTree[F]], select: Callable[[F], bool] = bool
    ) -> TriggerTree[F]:
        if len(trees) == 1:
            return trees[0]._filtered(select)

        root_fields: list[F] = []
        subtrees_to_merge: dict[F, list[TriggerTree[F]]] = defaultdict(list)

        for tree in trees:
            root_fields.extend(tree.root)
            for label, subtree in tree.items():
                subtrees_to_merge[label].append(subtree)

        seen: set[F] = set()
        unique_root: list[F] = []
        for field in root_fields:
            if field not in seen:
                seen.add(field)
                unique_root.append(field)

        result = cls([field for field in unique_root if select(field)])
        for label, subtrees in subtrees_to_merge.items():
            subtree = cls.merge(subtrees, select)
            if subtree:
                result[label] = subtree

        return result

    def nodes(self) -> list[F]:
        seen: dict[F, None] = {}
        stack = [self]
        while stack:
            tree = stack.pop()
            seen.update(dict.fromkeys(tree.root))
            stack.extend(tree.values())
        return list(seen)

    def _filtered(self, select: Callable[[F], bool]) -> TriggerTree[F]:
        root = self.root
        filtered_root = [f for f in root if select(f)]
        children_changed = False
        filtered_children: list[tuple[F, TriggerTree[F]]] = []
        for label, subtree in self.items():
            filtered_sub = subtree._filtered(select)
            if filtered_sub is not subtree:
                children_changed = True
            if filtered_sub:
                filtered_children.append((label, filtered_sub))
        if len(filtered_root) == len(root) and not children_changed:
            return self
        result = TriggerTree(filtered_root)
        for label, filtered_sub in filtered_children:
            result[label] = filtered_sub
        return result


class _TriggerIndex[F: FieldLike]:
    __slots__ = ("field_ids", "fields", "graph", "meta", "payload")

    def __init__(
        self, triggers: Triggers[F], fact_of: Callable[[F], Any] | None = None
    ) -> None:
        self.field_ids: dict[F, int] = {}
        self.fields: list[F] = []
        self.payload: list[tuple[int, list[Bucket]]] = [
            (
                self._get_or_create_field_id(dep),
                [
                    (
                        [self._get_or_create_field_id(f) for f in path],
                        [self._get_or_create_field_id(t) for t in targets],
                    )
                    for path, targets in buckets.items()
                ],
            )
            for dep, buckets in triggers.items()
        ]
        strings: dict[Any, int] = {}
        facts: dict[Any, int] = {}
        self.meta: list[Meta] = [
            (
                getattr(field, "is_many2one", False),
                getattr(field, "is_one2many", False),
                strings.setdefault(getattr(field, "name", None), len(strings)),
                strings.setdefault(getattr(field, "inverse_name", None), len(strings)),
                strings.setdefault(getattr(field, "model_name", None), len(strings)),
                strings.setdefault(getattr(field, "comodel_name", None), len(strings)),
                facts.setdefault(fact_of(field) if fact_of else field, len(facts)),
            )
            for field in self.fields
        ]
        self.graph: TriggerGraph | None = None

    def _get_or_create_field_id(self, field: F) -> int:
        field_id = self.field_ids.get(field)
        if field_id is None:
            field_id = self.field_ids[field] = len(self.fields)
            self.fields.append(field)
        return field_id

    def get_tree(self, field: F) -> TriggerTree[F]:
        graph = self.graph
        if graph is None:
            graph = self.graph = TriggerGraph(dict(self.payload), self.meta)
        return self._wrap(graph.tree(self.field_ids[field]))

    def get_trees(self, fields: list[F] | None) -> dict[F, TriggerTree[F]]:
        wanted = None if fields is None else [self.field_ids[f] for f in fields]
        if _debug.perf.enabled:
            return self._get_trees_one_by_one(wanted)
        return {
            self.fields[field_id]: self._wrap(node)
            for field_id, node in _get_trigger_trees(self.payload, self.meta, wanted)
        }

    def _get_trees_one_by_one(
        self, wanted: list[int] | None
    ) -> dict[F, TriggerTree[F]]:
        if wanted is None:
            wanted = [field_id for field_id, _buckets in self.payload]
        trees: dict[F, TriggerTree[F]] = {}
        for field_id in wanted:
            field = self.fields[field_id]
            _debug.pipeline("model_graph.tree_building", field=field)
            with _debug.perf("model_graph.tree_built", field=field) as span:
                [(_, node)] = _get_trigger_trees(self.payload, self.meta, [field_id])
                nodes, depth = _measure(node)
                span.set(nodes=nodes, depth=depth)
            if nodes > _TREE_NODE_BUDGET:
                _logger.warning(
                    "trigger tree of %s holds %d nodes (depth %d), over the budget "
                    "of %d; a dependency cycle through a path is the usual cause",
                    field,
                    nodes,
                    depth,
                    _TREE_NODE_BUDGET,
                )
            trees[field] = self._wrap(node)
        return trees

    def _wrap(self, node: Node) -> TriggerTree[F]:
        root, children = node
        fields = self.fields
        tree = TriggerTree([fields[i] for i in root])
        for label, child in children:
            tree[fields[label]] = self._wrap(child)
        return tree


class _TriggerState[F: FieldLike]:
    __slots__ = (
        "dynamic_nodes",
        "fact_of",
        "filtered",
        "index",
        "merged",
        "modifying_relations",
        "path_fields",
        "recompute_order",
        "recursive_paths",
        "reverse_triggers",
        "trees",
        "triggers",
    )

    def __init__(
        self, triggers: Triggers[F], fact_of: Callable[[F], Any] | None = None
    ) -> None:
        self.triggers = triggers
        self.fact_of = fact_of
        self.index: _TriggerIndex[F] | None = None
        self.trees: dict[F, TriggerTree[F]] = {}
        self.merged: LRU[tuple[F, ...], TriggerTree[F]] = LRU(_MERGED_CACHE_MAX)
        self.dynamic_nodes: LRU[tuple[F, ...], tuple[F, ...]] = LRU(_MERGED_CACHE_MAX)
        self.filtered: LRU[tuple[tuple[F, ...], tuple[bool, ...]], TriggerTree[F]] = (
            LRU(_MERGED_CACHE_MAX)
        )
        self.modifying_relations: dict[F, bool] = {}
        self.path_fields: frozenset[F] | None = None
        self.recompute_order: dict[F, int] | None = None
        self.recursive_paths: dict[F, tuple[tuple[F, ...], ...] | None] = {}
        self.reverse_triggers: dict[F, list[tuple[F, tuple[F, ...]]]] | None = None

    def get_index(self) -> _TriggerIndex[F]:
        index = self.index
        if index is None:
            index = self.index = _TriggerIndex(self.triggers, self.fact_of)
        return index

    def get_path_fields(self) -> frozenset[F]:
        path_fields = self.path_fields
        if path_fields is None:
            path_fields = self.path_fields = frozenset(
                field
                for paths in self.triggers.values()
                for path in paths
                for field in path
            )
        return path_fields

    def get_reverse_triggers(self) -> dict[F, list[tuple[F, tuple[F, ...]]]]:
        reverse = self.reverse_triggers
        if reverse is None:
            reverse = defaultdict(list)
            for dep_field, paths in self.triggers.items():
                for key, targets in paths.items():
                    for target in targets:
                        reverse[target].append((dep_field, key))
            self.reverse_triggers = reverse
        return reverse

    def fact(self, field: F) -> Any:
        return self.fact_of(field) if self.fact_of is not None else field


_MERGED_CACHE_MAX = 512


def _get_empty_triggers[F = Any]() -> Triggers[F]:
    return defaultdict(lambda: defaultdict(list))


class ModelGraph[F: FieldLike = Any]:
    __slots__ = (
        "_computed",
        "_depends",
        "_depends_context",
        "_epoch",
        "_invalidation_depth",
        "_inverses",
        "_publish_lock",
        "_state",
    )

    def __init__(self) -> None:
        self._inverses: _Collector[F, F] = _Collector()
        self._depends: _Collector[F, str] = _Collector()
        self._depends_context: _Collector[F, str] = _Collector()
        self._computed: dict[F, list[F]] = {}
        self._state: _TriggerState[F] = _TriggerState(_get_empty_triggers())
        self._epoch: int = 0
        self._invalidation_depth: int = 0
        self._publish_lock = threading.Lock()

    def set_triggers(
        self,
        triggers: Triggers[F],
        *,
        epoch: int | None = None,
        fact_of: Callable[[F], Any] | None = None,
    ) -> bool:
        state = _TriggerState(triggers, fact_of)
        with self._publish_lock:
            if epoch is not None and (self._invalidation_depth or epoch != self._epoch):
                _debug.logic(
                    "model_graph.set_triggers.rejected",
                    epoch=epoch,
                    current_epoch=self._epoch,
                    depth=self._invalidation_depth,
                )
                return False
            self._state = state
        _debug.lifecycle(
            "model_graph.triggers_published",
            epoch=self._epoch,
            fields=len(triggers),
        )
        return True

    @property
    def trigger_epoch(self) -> int:
        return self._epoch

    def begin_invalidation(self) -> None:
        with self._publish_lock:
            self._epoch += 1
            self._invalidation_depth += 1
            depth = self._invalidation_depth
        _debug.lifecycle(
            "model_graph.invalidation_begin", epoch=self._epoch, depth=depth
        )

    def end_invalidation(self) -> None:
        with self._publish_lock:
            self._epoch += 1
            self._invalidation_depth = max(self._invalidation_depth - 1, 0)
            depth = self._invalidation_depth
        _debug.lifecycle("model_graph.invalidation_end", epoch=self._epoch, depth=depth)

    def reset_field_metadata(self) -> None:
        self._inverses.clear()
        self._depends.clear()
        self._depends_context.clear()
        self._computed.clear()

    def clear_caches(self) -> None:
        _debug.lifecycle("model_graph.caches_cleared", epoch=self._epoch)
        with self._publish_lock:
            self._state = _TriggerState(self._state.triggers, self._state.fact_of)

    def discard_fields(self, fields: Collection[F]) -> None:
        discarded = set(fields)
        for f in discarded:
            self._depends.pop(f, None)
            self._depends_context.pop(f, None)
            self._computed.pop(f, None)

        self._inverses.discard_keys_and_values(fields)

        old_triggers = self._state.triggers
        new_triggers: Triggers[F] = _get_empty_triggers()
        for dep, buckets in old_triggers.items():
            if dep in discarded:
                continue
            for path, targets in buckets.items():
                kept = [t for t in targets if t not in discarded]
                if kept:
                    new_triggers[dep][path] = kept

        _debug.lifecycle(
            "model_graph.fields_discarded",
            fields=len(discarded),
            triggers_before=len(old_triggers),
            triggers_after=len(new_triggers),
        )
        with self._publish_lock:
            self._state = _TriggerState(new_triggers, self._state.fact_of)

    def get_trigger_tree(
        self,
        fields: list[F],
        select: Callable[[F], bool] = bool,
        static: Callable[[F], bool] | None = None,
        cached: Callable[[F], bool] | None = None,
    ) -> TriggerTree[F]:
        state = self._state
        triggers = state.triggers
        key = tuple(field for field in fields if field in triggers)
        if not key:
            return TriggerTree()
        structure = state.merged.get(key)
        if structure is None:
            trees = [self._get_field_trigger_tree(state, field) for field in key]
            structure = TriggerTree.merge(trees, bool)
            _debug.perf.count(
                "model_graph.trigger_tree_merged",
                fields=len(fields),
                trees=len(trees),
                cached=len(state.merged),
            )
            state.merged[key] = structure
        if static is None:
            return structure._filtered(select)
        dynamic = state.dynamic_nodes.get(key)
        if dynamic is None:
            dynamic = state.dynamic_nodes[key] = tuple(
                node for node in structure.nodes() if not static(node)
            )
        keep = cached or select
        filtered_key = (key, tuple(keep(node) for node in dynamic))
        filtered = state.filtered.get(filtered_key)
        if filtered is None:
            filtered = state.filtered[filtered_key] = structure._filtered(select)
        return filtered

    def _get_field_trigger_tree(
        self, state: _TriggerState[F], field: F
    ) -> TriggerTree[F]:
        try:
            return state.trees[field]
        except KeyError:
            pass

        if field not in state.triggers:
            return TriggerTree()

        tree = state.trees[field] = state.get_index().get_tree(field)
        return tree

    @staticmethod
    def _add_missing_trees[G: FieldLike](state: _TriggerState[G]) -> None:
        missing = [field for field in state.triggers if field not in state.trees]
        if missing:
            with _debug.perf("model_graph.trees_built", missing=len(missing)):
                state.trees.update(state.get_index().get_trees(missing))

    def get_dependent_fields(self, field: F) -> Iterator[F]:
        return self._get_dependent_fields(self._state, field)

    def _get_dependent_fields(self, state: _TriggerState[F], field: F) -> Iterator[F]:
        if field not in state.triggers:
            return
        for tree in self._get_field_trigger_tree(state, field).iter_depth_first():
            yield from tree.root

    def is_modifying_relations(self, field: F) -> bool:
        return self._is_modifying_relations(self._state, field)

    def _is_modifying_relations(self, state: _TriggerState[F], field: F) -> bool:
        if field not in state.triggers:
            return False

        try:
            return state.modifying_relations[field]
        except KeyError:
            pass

        path_fields = state.get_path_fields()
        result = self._modifies_relations(field, path_fields) or any(
            self._modifies_relations(dep, path_fields)
            for dep in self._get_dependent_fields(state, field)
        )
        state.modifying_relations[field] = result
        return result

    def _modifies_relations(self, field: F, path_fields: frozenset[F]) -> bool:
        return bool(self._inverses.get(field, ())) or field in path_fields

    def get_recursive_paths(
        self, field: F, group: Collection[F]
    ) -> tuple[tuple[F, ...], ...] | None:
        state = self._state
        try:
            return state.recursive_paths[field]
        except KeyError:
            pass
        paths = self._get_recursive_paths(state, field, group)
        state.recursive_paths[field] = paths
        return paths

    def _get_recursive_paths(
        self, state: _TriggerState[F], field: F, group: Collection[F]
    ) -> tuple[tuple[F, ...], ...] | None:
        facts = {state.fact(member) for member in group}
        dependents = {
            dependent
            for member in group
            for dependent in self._get_dependent_fields(state, member)
            if state.fact(dependent) not in facts
        }
        paths: dict[tuple[F, ...], None] = {}
        for dep_field, key in state.get_reverse_triggers().get(field, ()):
            steps = (*reversed(key), dep_field)
            for index, step in enumerate(steps):
                if state.fact(step) in facts:
                    if not index:
                        continue
                    prefix = steps[:index]
                    if any(
                        link.compute or state.fact(link) in facts for link in prefix
                    ):
                        _debug.logic(
                            "model_graph.recursive_paths.computed_link",
                            field=str(field),
                            path=[link.name for link in steps],
                        )
                        return None
                    paths[prefix] = None
                elif step in dependents:
                    _debug.logic(
                        "model_graph.recursive_paths.dependent_on_path",
                        field=str(field),
                        path=[link.name for link in steps],
                        dependent=str(step),
                    )
                    return None
        return tuple(paths)

    @property
    def recompute_order(self) -> dict[F, int]:
        state = self._state
        order = state.recompute_order
        if order is None:
            with _debug.perf(
                "model_graph.recompute_order", triggers=len(state.triggers)
            ) as span:
                order = state.recompute_order = self._get_recompute_order(
                    state.triggers
                )
                span.set(fields=len(order))
        return order

    @staticmethod
    def _get_recompute_order[G: FieldLike](
        triggers: Triggers[G],
    ) -> dict[G, int]:
        adjacency = _get_stored_compute_adjacency(triggers)
        sccs = strongly_connected_components(adjacency)
        _, component_adjacency, component_in_degree = _condense_components(
            adjacency, sccs
        )

        queue: list[int] = [
            index for index, degree in enumerate(component_in_degree) if degree == 0
        ]
        order: dict[G, int] = {}
        priority = 0
        while queue:
            next_queue: list[int] = []
            for index in queue:
                for field in sccs[index]:
                    order[field] = priority
                for sink in component_adjacency[index]:
                    component_in_degree[sink] -= 1
                    if component_in_degree[sink] == 0:
                        next_queue.append(sink)
            queue = next_queue
            priority += 1

        return order

    def freeze(self) -> None:
        state = self._state
        with _debug.perf("model_graph.freeze", fields=len(state.triggers)) as span:
            self._add_missing_trees(state)
            for field in state.triggers:
                self._is_modifying_relations(state, field)
            if state.recompute_order is None:
                state.recompute_order = self._get_recompute_order(state.triggers)
            span.set(trees=len(state.trees), ordered=len(state.recompute_order or ()))

    def set_inverses(self, inverses: _Collector[F, F]) -> None:
        self._inverses = inverses

    def set_computed(self, computed: dict[F, list[F]]) -> None:
        self._computed = computed

    @property
    def published_triggers(self) -> Triggers[F]:
        return self._state.triggers

    @property
    def field_inverses(self) -> _Collector[F, F]:
        return self._inverses

    @property
    def field_depends(self) -> _Collector[F, str]:
        return self._depends

    @property
    def field_depends_context(self) -> _Collector[F, str]:
        return self._depends_context

    @property
    def field_computed(self) -> dict[F, list[F]]:
        return self._computed
