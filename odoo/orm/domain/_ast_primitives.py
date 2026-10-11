import collections
import contextlib
import datetime
import decimal
import enum
import functools
import typing

from odoo.libs.collections import FrozenOrderedSet, OrderedSet, frozendict
from odoo.libs.debug_log import DebugLog

from .constants import SUBDOMAIN_OPERATORS

if typing.TYPE_CHECKING:
    from collections.abc import Callable

    from ..fields import Field
    from ..models import BaseModel
    from .ast import Domain, DomainCondition, DomainNary

_debug = DebugLog("odoo.orm.domain.ast")


class OptimizationLevel(enum.IntEnum):
    NONE = 0
    BASIC = enum.auto()
    DYNAMIC_VALUES = enum.auto()
    FULL = enum.auto()

    @functools.cached_property
    def next_level(self) -> OptimizationLevel:
        if self is OptimizationLevel.FULL:
            raise ValueError("FULL level is the last one")
        return OptimizationLevel(int(self) + 1)


MAX_DOMAIN_NESTING = 100


def _searches_one_value(field: Field[typing.Any]) -> bool:
    if field.is_x2many:
        return False
    if field.store:
        return True
    seq = field._related_field_seq
    return bool(field.related and seq) and all(map(_searches_one_value, seq))


def _negates_by_operator(field: Field[typing.Any]) -> bool:
    if field.related:
        return not any(
            step.is_x2many and not step.is_one2one
            for step in field._related_field_seq[:-1]
        )
    return True


def _is_comparand_equal(left: typing.Any, right: typing.Any) -> bool:
    equal: bool
    if left.__class__ in (list, tuple, set, frozenset, OrderedSet, FrozenOrderedSet):
        if len(left) != len(right):
            return False
        try:
            if set(left) != set(right):
                return False
            types = set(map(type, left))
            if len(types) == 1 and types == set(map(type, right)):
                return True
            return {(type(v), v) for v in left} == {(type(v), v) for v in right}
        except TypeError:
            equal = left == right
            return equal
    equal = left == right
    return equal


_SCALAR_CLASSES = frozenset({int, str, float, bool, type(None)})


def _freeze_comparand(value: typing.Any, path: set[int] | None = None) -> typing.Any:
    cls = value.__class__
    if cls in _SCALAR_CLASSES:
        return value
    if cls is list or cls is tuple:
        if _SCALAR_CLASSES.issuperset(map(type, value)):
            return value if cls is tuple else tuple(value)
    elif cls is OrderedSet or cls is set or cls is frozenset:
        return FrozenOrderedSet(value) if cls is OrderedSet else frozenset(value)
    if not isinstance(value, (list, tuple, set, frozenset, dict, OrderedSet)):
        return value
    if path is None:
        path = set()
    marker = id(value)
    if marker in path:
        raise ValueError("Cyclic domain operand")
    if len(path) >= MAX_DOMAIN_NESTING:
        raise ValueError("Domain nesting too deep to freeze")
    path.add(marker)
    try:
        if isinstance(value, dict):
            return frozendict(
                (key, _freeze_comparand(item, path)) for key, item in value.items()
            )
        items = (_freeze_comparand(item, path) for item in value)
        if isinstance(value, OrderedSet):
            return FrozenOrderedSet(items)
        if isinstance(value, (set, frozenset)):
            return frozenset(items)
        return tuple(items)
    finally:
        path.remove(marker)


class DomainOptimizationError(ValueError):
    pass


@contextlib.contextmanager
def _recursion_error_as_value_error() -> typing.Iterator[None]:
    try:
        yield
    except RecursionError:
        _debug.logic("domain.optimize.recursion_exhausted")
        raise ValueError(
            "Domain nesting too deep to optimize: combined n-ary and 'any' "
            "nesting exhausts the evaluation stack"
        ) from None


def _check_depth(depth: int) -> int:
    if depth > MAX_DOMAIN_NESTING:
        raise ValueError(
            f"Domain nesting too deep (>{MAX_DOMAIN_NESTING} levels); refusing "
            f"to build it to avoid a RecursionError during evaluation"
        )
    return depth


def _check_subdomain_nesting(value: object, max_depth: int) -> None:
    stack: list[tuple[object, int]] = [(value, 1)]
    while stack:
        node, depth = stack.pop()
        if depth > max_depth:
            raise ValueError(
                f"Domain nesting too deep (>{max_depth} levels); refusing to "
                f"build it to avoid a RecursionError during evaluation"
            )
        if not isinstance(node, (list, tuple)):
            continue
        child_depth = depth + 1
        stack.extend(
            (item[2], child_depth)
            for item in node
            if isinstance(item, (list, tuple))
            and len(item) == 3
            and isinstance(item[1], str)
            and item[1].lower() in SUBDOMAIN_OPERATORS
            and isinstance(item[2], (list, tuple))
        )


if typing.TYPE_CHECKING:
    ConditionOptimization = Callable[["DomainCondition", "BaseModel"], "Domain"]
    MergeOptimization = Callable[
        [type["DomainNary"], list["Domain"], "BaseModel"], list["Domain"]
    ]

    class MergeOptimizer(typing.Protocol):
        _match_operators: frozenset[str] | None

        def __call__(
            self, cls: type[DomainNary], domains: list[Domain], model: BaseModel, /
        ) -> list[Domain]: ...


_OPTIMIZATIONS_FOR: dict[OptimizationLevel, dict[str, list[ConditionOptimization]]] = {
    level: collections.defaultdict(list)
    for level in OptimizationLevel
    if level != OptimizationLevel.NONE
}
_OPTIMIZATION_KEY_KIND: dict[str, str] = {}
_MERGE_OPTIMIZATIONS: list[MergeOptimizer] = []


_CONSTANT_TIEBREAK: tuple[int, typing.Any] = (2, "")


def _get_nary_value_tiebreak(value: typing.Any) -> tuple[int, typing.Any]:
    if isinstance(value, str):
        return (0, value)
    if isinstance(value, (int, float)):
        return (1, value)
    if isinstance(value, datetime.datetime):
        return (3, value)
    if isinstance(value, datetime.date):
        return (4, value)
    if isinstance(value, decimal.Decimal):
        return (5, value)
    return _CONSTANT_TIEBREAK


def _get_nary_subtree_tiebreak(domain: Domain) -> tuple[int, typing.Any]:
    return (2, repr(list(domain)))


def _defines_the_condition(field: Field[typing.Any], su: bool) -> bool:
    search = field.search
    if not search:
        return False
    if getattr(search, "__func__", None) is not _search_related_function():
        return True
    if not su:
        return True
    target = field.related_field
    return _defines_the_condition(target, su) if target is not None else False


@functools.cache
def _search_related_function() -> typing.Any:
    from ..fields.base import Field as _Field

    return _Field._search_related
