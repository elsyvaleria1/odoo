from __future__ import annotations

from collections.abc import Iterable
from hashlib import blake2b

from .node import Node


def _short_hash(parts: Iterable[str]) -> str:
    digest = blake2b(digest_size=6)
    for part in parts:
        digest.update(part.encode("utf-8"))
        digest.update(b"\x1f")
    return digest.hexdigest()


def identify(root: Node) -> dict[str, Node]:
    nodes: list[tuple[Node, Node | None]] = []
    stack: list[tuple[Node, Node | None]] = [(root, None)]
    while stack:
        node, parent = stack.pop()
        nodes.append((node, parent))
        stack.extend((child, node) for child in reversed(node.children))

    counts: dict[str, int] = {}
    for node, _parent in nodes:
        counts[node.kind] = counts.get(node.kind, 0) + 1

    ids: dict[str, Node] = {}
    taken: dict[str, int] = {}

    def claim(base: str, node: Node) -> str:
        n = taken.get(base, 0) + 1
        taken[base] = n
        node_id = base if n == 1 else f"{base}#{n}"
        ids[node_id] = node
        return node_id

    for node, _parent in nodes:
        if node.attrs.get("id"):
            node.id = claim(node.attrs["id"], node)

    for node, parent in nodes:
        if node.attrs.get("id"):
            continue
        if node.attrs.get("name"):
            node.id = claim(f"{node.kind}:{node.attrs['name']}", node)
        elif counts[node.kind] == 1:
            node.id = claim(node.kind, node)
        else:
            digest = _short_hash(
                [
                    parent.id or "" if parent is not None else "",
                    node.kind,
                    *(f"{key}={value}" for key, value in sorted(node.attrs.items())),
                ]
            )
            node.id = claim(f"{node.kind}@{digest}", node)
    return ids
