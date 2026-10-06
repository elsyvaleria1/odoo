__all__ = ["merge_sequences", "strongly_connected_components", "topological_sort"]

from collections import defaultdict
from typing import TYPE_CHECKING, cast

from .sentinel import SENTINEL, Sentinel

if TYPE_CHECKING:
    from collections.abc import Collection, Iterable, Iterator, Mapping


def topological_sort[T](
    elems: Mapping[T, Collection[T]], *, strict: bool = True
) -> list[T]:
    result: list[T] = []
    visited: set[T] = set()
    path: set[T] = set()

    for root in elems:
        if root in visited:
            continue
        visited.add(root)
        path.add(root)
        stack: list[tuple[T, Iterator[T]]] = [(root, iter(elems[root]))]
        while stack:
            node, deps = stack[-1]
            for dep in deps:
                if dep == node:
                    continue
                if dep in path:
                    if strict:
                        raise ValueError(
                            f"topological_sort: cyclic dependency involving {dep!r}"
                        )
                    continue
                if dep in visited:
                    continue
                visited.add(dep)
                if dep in elems:
                    path.add(dep)
                    stack.append((dep, iter(elems[dep])))
                    break
            else:
                stack.pop()
                path.discard(node)
                result.append(node)

    return result


def merge_sequences[T](*iterables: Iterable[T]) -> list[T]:
    deps: defaultdict[T, list[T]] = defaultdict(list)
    for iterable in iterables:
        prev: T | Sentinel = SENTINEL
        for item in iterable:
            if prev is SENTINEL:
                deps[item]
            else:
                deps[item].append(cast("T", prev))
            prev = item
    return topological_sort(deps, strict=False)


def strongly_connected_components[T](graph: Mapping[T, Iterable[T]]) -> list[list[T]]:
    # Tarjan's algorithm, iterative so a deep chain does not recurse. Every
    # successor must be a key of graph. Components come in completion order (a
    # component before any that reaches it), each listing its members in the
    # order the stack pops them, its root last.
    index_of: dict[T, int] = {}
    lowlink: dict[T, int] = {}
    on_stack: set[T] = set()
    stack: list[T] = []
    components: list[list[T]] = []

    for root, root_successors in graph.items():
        if root in index_of:
            continue
        index_of[root] = lowlink[root] = len(index_of)
        stack.append(root)
        on_stack.add(root)
        work: list[tuple[T, Iterator[T]]] = [(root, iter(root_successors))]
        while work:
            node, successors = work[-1]
            for successor in successors:
                if successor not in index_of:
                    index_of[successor] = lowlink[successor] = len(index_of)
                    stack.append(successor)
                    on_stack.add(successor)
                    work.append((successor, iter(graph[successor])))
                    break
                if successor in on_stack and index_of[successor] < lowlink[node]:
                    lowlink[node] = index_of[successor]
            else:
                work.pop()
                if work:
                    parent = work[-1][0]
                    lowlink[parent] = min(lowlink[parent], lowlink[node])
                if lowlink[node] == index_of[node]:
                    component: list[T] = []
                    while True:
                        member = stack.pop()
                        on_stack.discard(member)
                        component.append(member)
                        if member is node:
                            break
                    components.append(component)
    return components
