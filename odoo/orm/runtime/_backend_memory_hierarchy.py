from __future__ import annotations

import typing
from collections import defaultdict

from odoo.libs.collections import OrderedSet
from odoo.libs.debug_log import DebugLog
from odoo.tools import Query

from ..domain import Domain

if typing.TYPE_CHECKING:
    from .._typing import ModelLike
    from ..components.storage import DictBackend

_debug = DebugLog("odoo.orm.runtime._backend_memory")


class _InMemoryHierarchyMixin:
    __slots__ = ()

    if typing.TYPE_CHECKING:
        storage: DictBackend

        def as_query(self, model: ModelLike, ordered: bool = True) -> Query: ...

        def _iter_m2m_rows(
            self, relation: str
        ) -> typing.Iterator[tuple[int, dict[str, typing.Any]]]: ...

    def ancestors(
        self,
        model: ModelLike,
        parent_field: str,
        ids: typing.Collection[int],
        *,
        flush: bool = True,
    ) -> list[tuple[int, int | None]]:
        if flush:
            model.flush_model([parent_field])
        rows: dict[int, int | None] = {}
        frontier = list(ids)
        while frontier:
            next_frontier = []
            for id_ in frontier:
                if id_ in rows:
                    continue
                row = self.storage.get_row(model._table, id_)
                if row is None:
                    continue
                parent_id = row.get(parent_field) or None
                rows[id_] = parent_id
                if parent_id and parent_id not in rows:
                    next_frontier.append(parent_id)
            frontier = next_frontier
        return list(rows.items())

    def descendant_edges(
        self, model: ModelLike, parent_field: str, ids: typing.Collection[int]
    ) -> list[tuple[int, int]]:
        unfiltered = model.sudo().with_context(active_test=False)
        edges: list[tuple[int, int]] = []
        seen: set[int] = set()
        frontier = list(ids)
        while frontier:
            next_frontier = []
            for child in unfiltered._search(
                Domain(parent_field, "in", frontier)
            ).get_result_ids():
                if child in seen:
                    continue
                seen.add(child)
                row = self.storage.get_row(model._table, child) or {}
                edges.append((child, typing.cast("int", row.get(parent_field))))
                next_frontier.append(child)
            frontier = next_frontier
        return edges

    def descendants(
        self,
        model: ModelLike,
        parent_field: str,
        root_ids: typing.Collection[int],
        *,
        domain: Domain,
        step_domain: Domain,
        same_columns: typing.Sequence[str] = (),
    ) -> Query:
        # the closure reads the columns: a pending write has to reach them
        model.flush_model([parent_field, *same_columns])
        table = model._table

        def matching(condition: Domain) -> set[int] | None:
            # _single_table_where: a TRUE domain adds no WHERE at all, so
            # neither the active test nor the record rules a search adds
            if condition.is_true():
                return None
            return set(model._search(condition).get_result_ids())

        base = matching(domain)
        step = matching(domain & step_domain)
        rows = self.storage.get_rows(table, self.storage.get_table_ids(table))
        children_of: defaultdict[int, list[int]] = defaultdict(list)
        for row_id, row in rows.items():
            parent_id = row.get(parent_field)
            if parent_id is not None and (step is None or row_id in step):
                children_of[parent_id].append(row_id)

        def same_key(row_id: int) -> tuple[str, ...]:
            # COALESCE(col::text, '') on the SQL side: only NULL collapses
            # to '', a stored 0 or false compares as its text
            row = rows[row_id]
            key = []
            for column in same_columns:
                value = row.get(column)
                if value is None:
                    key.append("")
                elif value is True or value is False:
                    key.append("true" if value else "false")
                else:
                    key.append(str(value))
            return tuple(key)

        found: OrderedSet[int] = OrderedSet(
            id_ for id_ in root_ids if id_ in rows and (base is None or id_ in base)
        )
        frontier = list(found)
        while frontier:
            next_frontier = []
            for parent_id in frontier:
                parent_key = same_key(parent_id)
                for child_id in children_of.get(parent_id, ()):
                    if child_id not in found and same_key(child_id) == parent_key:
                        found.add(child_id)
                        next_frontier.append(child_id)
            frontier = next_frontier
        return self.as_query(model.browse(list(found)), ordered=False)

    def has_cycle(
        self,
        model: ModelLike,
        relation: str,
        column1: str,
        column2: str,
        ids: typing.Collection[int],
    ) -> bool:
        # the reachability CTE over the relation rows: a source that reaches
        # itself closes a cycle
        edges: defaultdict[int, set[int]] = defaultdict(set)
        for _row_id, row in self._iter_m2m_rows(relation):
            source, destination = row.get(column1), row.get(column2)
            if source is not None and destination is not None:
                edges[source].add(destination)
        for source in ids:
            seen: set[int] = set()
            frontier = set(edges.get(source, ()))
            while frontier:
                if source in frontier:
                    return True
                seen.update(frontier)
                frontier = {
                    destination
                    for node in frontier
                    for destination in edges.get(node, ())
                    if destination not in seen
                }
        return False

    def set_parent_paths(
        self, model: ModelLike, ids: typing.Sequence[int]
    ) -> list[tuple[int, str]]:
        table, parent_column = model._table, model._parent_name
        updated: list[tuple[int, str]] = []
        orphans: list[int] = []
        for id_ in ids:
            row = self.storage.get_row(table, id_)
            if row is None:
                continue
            if not row.get(parent_column):
                updated.append((id_, f"{id_}/"))
            elif prefix := self._stored_parent_path(table, row[parent_column]):
                updated.append((id_, f"{prefix}{id_}/"))
            else:
                orphans.append(id_)
        self.storage.update_rows(
            table, [(id_, {"parent_path": path}) for id_, path in updated]
        )
        if orphans:
            updated.extend(self._rebuild_parent_paths(model, orphans).items())
        return updated

    def _stored_parent_path(self, table: str, id_: int) -> str | None:
        return (self.storage.get_row(table, id_) or {}).get("parent_path") or None

    def records_with_parent_changed(
        self, model: ModelLike, parent_to_ids: dict[typing.Any, list[int]]
    ) -> list[int]:
        table, parent_column = model._table, model._parent_name
        changed: list[int] = []
        for parent_id, ids in parent_to_ids.items():
            for id_ in ids:
                row = self.storage.get_row(table, id_)
                if row is None:
                    continue
                stored = row.get(parent_column) or None
                if (stored != parent_id) if parent_id else (stored is not None):
                    changed.append(id_)
        return sorted(changed)

    def move_parent_paths(
        self, model: ModelLike, ids: typing.Sequence[int], prefix: str
    ) -> dict[int, str]:
        table, parent_column = model._table, model._parent_name
        located: dict[int, str] = {}
        unlocated: list[int] = []
        for node_id in ids:
            node = self.storage.get_row(table, node_id)
            if node is None:
                continue
            node_path = node.get("parent_path")
            parent_id = node.get(parent_column)
            if not node_path or (
                parent_id and not self._stored_parent_path(table, parent_id)
            ):
                unlocated.append(node_id)
            else:
                located[node_id] = node_path
        moved: dict[int, str] = {}
        for child_id in self.storage.get_table_ids(table):
            child = self.storage.get_row(table, child_id)
            child_path = (child or {}).get("parent_path") or ""
            owners = [
                (node_path, node_id)
                for node_id, node_path in located.items()
                if child_path.startswith(node_path)
            ]
            if owners:
                node_path, node_id = max(owners, key=lambda owner: len(owner[0]))
                cut = len(node_path) - len(f"{node_id}/")
                moved[child_id] = f"{prefix}{child_path[cut:]}"
        self.storage.update_rows(
            table, [(id_, {"parent_path": path}) for id_, path in moved.items()]
        )
        if unlocated:
            moved.update(self._rebuild_parent_paths(model, unlocated))
        return moved

    def _rebuild_parent_paths(self, model: ModelLike, ids: list[int]) -> dict[int, str]:
        table, parent_column = model._table, model._parent_name
        children: dict[int, list[int]] = defaultdict(list)
        for id_ in self.storage.get_table_ids(table):
            row = self.storage.get_row(table, id_) or {}
            if row.get(parent_column):
                children[row[parent_column]].append(id_)

        rebuilt: dict[int, str] = {}

        def healed_path(id_: int) -> str:
            chain: list[int] = []
            current: int | None = id_
            base = ""
            while current:
                if current in rebuilt:
                    base = rebuilt[current]
                    break
                row = self.storage.get_row(table, current)
                if row is None:
                    break
                if row.get("parent_path"):
                    base = row["parent_path"]
                    break
                if current in chain:
                    return ""
                chain.append(current)
                current = row.get(parent_column)
            for ancestor in reversed(chain):
                base = rebuilt[ancestor] = f"{base}{ancestor}/"
            return base

        for node_id in ids:
            node = self.storage.get_row(table, node_id)
            if node is None:
                continue
            parent_id = node.get(parent_column)
            stack = [
                (node_id, f"{healed_path(parent_id) if parent_id else ''}{node_id}/")
            ]
            while stack:
                id_, path = stack.pop()
                rebuilt[id_] = path
                stack.extend(
                    (child_id, f"{path}{child_id}/")
                    for child_id in children[id_]
                    if f"/{child_id}/" not in f"/{path}"
                )
        self.storage.update_rows(
            table, [(id_, {"parent_path": path}) for id_, path in rebuilt.items()]
        )
        _debug.logic(
            "backend.parent_path.rebuilt",
            model=model._name,
            nodes=len(ids),
            rows=len(rebuilt),
        )
        return rebuilt
