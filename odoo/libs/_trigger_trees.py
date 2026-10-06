from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence

from .iteration.sorting import strongly_connected_components

__all__ = ["TriggerGraph", "get_trigger_trees"]

Bucket = tuple[Sequence[int], Sequence[int]]
# (is_many2one, is_one2many, name, inverse_name, model_name, comodel_name, fact):
# `fact` is the stored column a field stands for. Every model of a table-
# inheritance tree keeps its own Field for one column, so the walk closes a
# cycle on the fact, or a self-dependency shared by n siblings costs n! paths.
Meta = tuple[bool, bool, int, int, int, int, int]
Node = tuple[list[int], list[tuple[int, "Node"]]]


def _is_inverse_pair(meta: Sequence[Meta], f1: int, f2: int) -> bool:
    a_m2o, _, a_name, _, a_model, a_comodel, _ = meta[f1]
    _, b_o2m, _, b_inverse, b_model, b_comodel, _ = meta[f2]
    return (
        a_m2o
        and b_o2m
        and b_inverse == a_name
        and a_model == b_comodel
        and a_comodel == b_model
    )


def _components(
    triggers: Mapping[int, Sequence[Bucket]], meta: Sequence[Meta]
) -> dict[int, int]:
    successors: dict[int, list[int]] = {}
    for dep, buckets in triggers.items():
        out = successors.setdefault(meta[dep][6], [])
        for _path, targets in buckets:
            out.extend(meta[t][6] for t in targets if t in triggers)
    return {
        member: component[-1]
        for component in strongly_connected_components(successors)
        for member in component
    }


class _Frame:
    __slots__ = ("buckets", "component", "fact", "node", "prefix", "targets")

    def __init__(
        self, prefix: int, fact: int, component: int, buckets: Iterator[Bucket]
    ) -> None:
        self.prefix = prefix
        self.fact = fact
        self.component = component
        self.buckets = buckets
        self.node = prefix
        self.targets: Iterator[int] = iter(())


class TriggerGraph:
    __slots__ = ("_component", "_meta", "_triggers")

    def __init__(
        self, triggers: Mapping[int, Sequence[Bucket]], meta: Sequence[Meta]
    ) -> None:
        self._triggers = triggers
        self._meta = meta
        self._component = _components(triggers, meta)

    def tree(self, field: int) -> Node:
        triggers = self._triggers
        root: Node = ([], [])
        if field not in triggers:
            return root
        meta = self._meta
        component = self._component
        nodes: list[Node] = [root]
        parents = [0]
        labels = [-1]
        child_of: dict[tuple[int, int], int] = {}
        listed: set[tuple[int, int]] = set()
        seen: set[int] = set()
        active: dict[int, int] = {}
        expanded: set[tuple[int, int]] = set()

        def enter(field: int, prefix: int) -> _Frame:
            fact = meta[field][6]
            seen.add(fact)
            comp = component[fact]
            active[comp] = active.get(comp, 0) + 1
            return _Frame(prefix, fact, comp, iter(triggers[field]))

        def descend(node: int, path: Sequence[int]) -> int:
            start = 0
            while (
                node
                and start < len(path)
                and _is_inverse_pair(meta, labels[node], path[start])
            ):
                node = parents[node]
                start += 1
            for label in path[start:]:
                child = child_of.get((node, label))
                if child is None:
                    child = child_of[node, label] = len(nodes)
                    entry: Node = ([], [])
                    nodes[node][1].append((label, entry))
                    nodes.append(entry)
                    parents.append(node)
                    labels.append(label)
                node = child
            return node

        stack = [enter(field, 0)]
        while stack:
            frame = stack[-1]
            for target in frame.targets:
                fact = meta[target][6]
                if fact in seen or target not in triggers:
                    continue
                # With no frame of its component on the stack, nothing the
                # walk below `target` reaches is on the stack either, so its
                # result depends on (target, node) alone and is already in.
                if not active.get(component[fact]):
                    key = (target, frame.node)
                    if key in expanded:
                        continue
                    expanded.add(key)
                stack.append(enter(target, frame.node))
                break
            else:
                bucket = next(frame.buckets, None)
                if bucket is not None:
                    path, targets = bucket
                    node = frame.node = descend(frame.prefix, path)
                    roots = nodes[node][0]
                    for target in targets:
                        if (node, target) not in listed:
                            listed.add((node, target))
                            roots.append(target)
                    frame.targets = iter(targets)
                    continue
                stack.pop()
                seen.discard(frame.fact)
                active[frame.component] -= 1
        return root


def get_trigger_trees(
    triggers: Sequence[tuple[int, Sequence[Bucket]]],
    meta: Sequence[Meta],
    fields: Sequence[int] | None = None,
) -> list[tuple[int, Node]]:
    ids = range(len(meta))
    for dep, buckets in triggers:
        if dep not in ids or any(
            f not in ids for path, targets in buckets for f in (*path, *targets)
        ):
            raise IndexError("get_trigger_trees: a field id is out of range of `meta`")
    by_field = dict(triggers)
    if fields is None:
        fields = list(by_field)
    elif any(f not in ids for f in fields):
        raise IndexError("get_trigger_trees: a field id is out of range of `meta`")
    graph = TriggerGraph(by_field, meta)
    return [(field, graph.tree(field)) for field in fields]
