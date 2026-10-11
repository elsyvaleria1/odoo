"""What one step of a run may read of the others, and how code names them.

Not a model. `make_step_key` derives a step's key, `collect_references` reads
which keys a piece of code names without running it, and `StepView` /
`StepScope` are the read-only objects a code step or an edge expression is
handed. vision.md Phase 5 carries the design.
"""

import ast
import copy
import keyword
import re
import unicodedata
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from itertools import pairwise
from typing import Any

SCOPE_NAME = "steps"
PREVIOUS_NAME = "previous"

RESERVED_KEYS = frozenset({"get", "items", "keys", "values"})
STEP_KEY_RE = re.compile(r"^[a-z_][a-z0-9_]*$")
STEP_KEY_MAX = 64


def is_valid_step_key(key: str) -> bool:
    return bool(
        key
        and len(key) <= STEP_KEY_MAX
        and STEP_KEY_RE.match(key)
        and "__" not in key
        and not keyword.iskeyword(key)
        and key not in RESERVED_KEYS
    )


def make_step_key(name: str, taken: set[str]) -> str:
    ascii_name = (
        unicodedata.normalize("NFKD", name or "")
        .encode("ascii", "ignore")
        .decode()
        .lower()
    )
    base = re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", ascii_name)).strip("_")
    base = base[: STEP_KEY_MAX - 4] or "step"
    if base[0].isdigit():
        base = f"step_{base}"
    if keyword.iskeyword(base) or base in RESERVED_KEYS:
        base = f"{base}_step"
    key, suffix = base, 2
    while key in taken:
        key = f"{base}_{suffix}"
        suffix += 1
    return key


@dataclass
class References:
    keys: set[str] = field(default_factory=set)
    uses_previous: bool = False
    dynamic: bool = False

    def to_json(self) -> dict[str, Any]:
        return {
            "keys": sorted(self.keys),
            "uses_previous": self.uses_previous,
            "dynamic": self.dynamic,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any] | None) -> References:
        data = data or {}
        return cls(
            keys=set(data.get("keys") or ()),
            uses_previous=bool(data.get("uses_previous")),
            dynamic=bool(data.get("dynamic")),
        )


def collect_references(source: str | None, mode: str = "exec") -> References:
    refs = References()
    if not source or not source.strip():
        return refs
    try:
        tree = ast.parse(source, mode=mode)
    except SyntaxError:
        return refs
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == PREVIOUS_NAME:
            refs.uses_previous = True
        elif isinstance(node, ast.Attribute) and _is_scope(node.value):
            if node.attr == "get":
                continue
            refs.keys.add(node.attr)
        elif isinstance(node, ast.Subscript) and _is_scope(node.value):
            _add_literal(refs, node.slice)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and _is_scope(node.func.value)
            and node.args
        ):
            _add_literal(refs, node.args[0])
        elif isinstance(node, ast.Compare):
            operands = [node.left, *node.comparators]
            for op, (left, right) in zip(node.ops, pairwise(operands), strict=True):
                if isinstance(op, (ast.In, ast.NotIn)) and _is_scope(right):
                    _add_literal(refs, left)
    return refs


def _is_scope(node: ast.AST) -> bool:
    return isinstance(node, ast.Name) and node.id == SCOPE_NAME


def _add_literal(refs: References, node: ast.AST) -> None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        refs.keys.add(node.value)
    else:
        refs.dynamic = True


class StepReferenceError(LookupError):
    pass


class StepView:
    """One step of a run as another step sees it: read-only, output copied."""

    __slots__ = ("input", "key", "name", "output", "record", "state", "summary")

    def __init__(self, line) -> None:
        self.key = line.action_id.step_key
        self.name = line.name
        self.state = line.state
        self.summary = line.output_summary or ""
        self.output = copy.deepcopy(line.output or {})
        self.record = line.created_record_ref or None
        self.input = {name: line.input_values[name] for name in line.input_values}

    def __repr__(self) -> str:
        return f"<step {self.key} ({self.state})>"


class StepScope(Mapping):
    """Steps by key, with a refusal that names what was in reach."""

    __slots__ = ("_owner", "_views")

    def __init__(self, views: dict[str, StepView], owner: str) -> None:
        self._views = views
        self._owner = owner

    def _missing(self, key: str) -> str:
        reachable = ", ".join(sorted(self._views)) or "none"
        return (
            f"No step '{key}' is upstream of '{self._owner}'; "
            f"the steps it can read are: {reachable}"
        )

    def __getitem__(self, key: str) -> StepView:
        try:
            return self._views[key]
        except KeyError:
            raise StepReferenceError(self._missing(key)) from None

    def __getattr__(self, key: str) -> StepView:
        try:
            return self._views[key]
        except KeyError:
            raise AttributeError(self._missing(key)) from None

    def __iter__(self) -> Iterator[str]:
        return iter(self._views)

    def __len__(self) -> int:
        return len(self._views)

    def __repr__(self) -> str:
        return f"<steps {', '.join(self._views)}>"


class NoPrevious:
    """`previous` of a step that has no single predecessor: falsy, and any
    read of it explains which steps to name instead."""

    __slots__ = ("_message",)

    def __init__(self, message: str) -> None:
        self._message = message

    def __bool__(self) -> bool:
        return False

    def __getattr__(self, name: str) -> Any:
        raise AttributeError(self._message)

    def __repr__(self) -> str:
        return "<no previous step>"
