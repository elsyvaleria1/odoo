import ast
import itertools
import math
from typing import TYPE_CHECKING, Literal, NotRequired, TypedDict, cast

from odoo.libs.refs import split_refs

if TYPE_CHECKING:
    from collections.abc import Collection, Iterable


__all__ = ["SetDefinitions", "SetExpressionError"]
"""Only these two leave the module.  `SetExpression`, `SetDefinition`,
`UnknownId`, the EMPTY_*/UNIVERSAL_* singletons and `MAX_INTERSECTION_TERMS`
are the vocabulary `SetDefinitions` is built from, not its surface."""

MAX_INTERSECTION_TERMS = 100_000


class SetExpressionError(ValueError):
    pass


class SetDefinition(TypedDict):
    ref: str
    supersets: NotRequired[Collection[int]]
    disjoints: NotRequired[Collection[int]]


class SetDefinitions:
    __slots__ = ("__from_key", "__leaves")

    def __init__(self, definitions: dict[int, SetDefinition]) -> None:
        self.__leaves: dict[int | str, Leaf] = {}
        self.__from_key: dict[str, SetExpression] = {}

        for leaf_id, info in definitions.items():
            ref = info["ref"]
            if ref == "*":
                msg = "The set reference '*' is reserved for the universal set."
                raise ValueError(msg)
            leaf = Leaf(leaf_id, ref)
            self.__leaves[leaf_id] = leaf
            self.__leaves[ref] = leaf

        by_id: dict[LeafIdType, Leaf] = {
            leaf_id: self.__leaves[leaf_id] for leaf_id in definitions
        }
        subsets: dict[LeafIdType, set[LeafIdType]] = {
            leaf_id: leaf.subsets for leaf_id, leaf in by_id.items()
        }
        supersets: dict[LeafIdType, set[LeafIdType]] = {
            leaf_id: leaf.supersets for leaf_id, leaf in by_id.items()
        }
        for leaf_id, info in definitions.items():
            for direct_greater_id in info.get("supersets", ()):
                if direct_greater_id not in supersets:
                    raise ValueError(
                        f"set {info['ref']!r} ({leaf_id}) names a superset "
                        f"{direct_greater_id!r} that is not defined"
                    )
                smaller_ids = subsets[leaf_id]
                greater_ids = supersets[direct_greater_id]
                for smaller_id in smaller_ids:
                    supersets[smaller_id].update(greater_ids)
                for greater_id in greater_ids:
                    subsets[greater_id].update(smaller_ids)

        disjoints: dict[LeafIdType, set[LeafIdType]] = {
            leaf_id: leaf.disjoints for leaf_id, leaf in by_id.items()
        }
        for leaf_id, info in definitions.items():
            for distinct_id in info.get("disjoints", set()):
                if distinct_id not in subsets:
                    raise ValueError(
                        f"set {info['ref']!r} ({leaf_id}) names a disjoint "
                        f"{distinct_id!r} that is not defined"
                    )
                left_ids = subsets[leaf_id]
                right_ids = subsets[distinct_id]
                for left_id in left_ids:
                    disjoints[left_id].update(right_ids)
                for right_id in right_ids:
                    disjoints[right_id].update(left_ids)

    @property
    def empty(self) -> SetExpression:
        return EMPTY_UNION

    @property
    def universe(self) -> SetExpression:
        return UNIVERSAL_UNION

    def parse(self, refs: str, raise_if_not_found: bool = True) -> SetExpression:
        positives: list[Leaf] = []
        negatives: list[Leaf] = []
        for xmlid in split_refs(refs):
            if xmlid.startswith("!"):
                negatives.append(
                    ~self.__get_leaf(xmlid.removeprefix("!"), raise_if_not_found)
                )
            else:
                positives.append(self.__get_leaf(xmlid, raise_if_not_found))

        if positives:
            return SetExpression(Inter([leaf] + negatives) for leaf in positives)
        else:
            return SetExpression([Inter(negatives)])

    def from_ids(self, ids: Iterable[int], keep_subsets: bool = False) -> SetExpression:
        if keep_subsets:
            ids = set(ids)
            ids = [
                leaf_id
                for leaf_id in ids
                if not any((self.__leaves[leaf_id].subsets - {leaf_id}) & ids)
            ]
        return SetExpression(Inter([self.__leaves[leaf_id]]) for leaf_id in ids)

    def from_key(self, key: str) -> SetExpression:
        try:
            return self.__from_key[key]
        except KeyError:
            pass
        expression = self.__from_key[key] = self._parse_key(key)
        return expression

    def _parse_key(self, key: str) -> SetExpression:
        union_tuple = ast.literal_eval(key)
        return SetExpression(
            [
                Inter(
                    [
                        ~leaf if negative else leaf
                        for leaf_id, negative in inter_tuple
                        for leaf in [self.__get_leaf(leaf_id, raise_if_not_found=False)]
                    ],
                    optimal=True,
                )
                for inter_tuple in union_tuple
            ],
            optimal=True,
        )

    def get_id(self, ref: str | int) -> LeafIdType | None:
        if ref == "*":
            return UNIVERSAL_LEAF.id
        leaf = self.__leaves.get(ref)
        return None if leaf is None else leaf.id

    def get_ref(self, leaf_id: LeafIdType) -> str | None:
        leaf = self.__leaves.get(leaf_id)
        return None if leaf is None else str(leaf.ref)

    def __get_leaf(self, ref: str | int, raise_if_not_found: bool = True) -> Leaf:
        if ref == "*":
            return UNIVERSAL_LEAF
        if not raise_if_not_found and ref not in self.__leaves:
            return Leaf(UnknownId(ref), ref)
        return self.__leaves[ref]

    def get_superset_ids(self, ids: Iterable[int]) -> list[int]:
        return sorted(
            cast(
                "set[int]",
                {
                    sup_id
                    for id_ in ids
                    if id_ in self.__leaves
                    for sup_id in self.__leaves[id_].supersets
                    if sup_id != id_
                },
            )
        )

    def get_subset_ids(self, ids: Iterable[int]) -> list[int]:
        return sorted(
            cast(
                "set[int]",
                {
                    sub_id
                    for id_ in ids
                    if id_ in self.__leaves
                    for sub_id in self.__leaves[id_].subsets
                    if sub_id != id_
                },
            )
        )


class SetExpression:
    def __init__(self, inters: Iterable[Inter] = (), optimal: bool = False) -> None:
        if inters and not optimal:
            inters = self.__combine((), inters)
        self.__inters = sorted(inters, key=lambda inter: inter.key)
        self.__key = str(tuple(inter.key for inter in self.__inters))
        self.__hash = hash(self.__key)

    @property
    def key(self) -> str:
        return self.__key

    @staticmethod
    def __combine(
        inters: Iterable[Inter], inters_to_add: Iterable[Inter]
    ) -> list[Inter]:
        result = _UnionIndex(inters)

        todo = list(inters_to_add)
        while todo:
            inter_to_add = todo.pop()
            if inter_to_add.is_universal():
                return [UNIVERSAL_INTER]
            if inter_to_add.is_empty():
                continue

            for seq, inter in result.candidates(inter_to_add):
                merged = inter._union_merge(inter_to_add)
                if merged is not None:
                    result.discard(seq)
                    todo.append(merged)
                    break
            else:
                result.add(inter_to_add)

        return result.inters()

    def is_empty(self) -> bool:
        return not self.__inters

    def is_universal(self) -> bool:
        return any(item.is_universal() for item in self.__inters)

    def invert_intersect(self, factor: SetExpression) -> SetExpression | None:
        if factor == self:
            return UNIVERSAL_UNION

        # a simplification, and None already means "no simpler form": an
        # expression whose inversion exceeds the bound is kept as it is
        try:
            rfactor = ~factor
            if rfactor.is_empty() or rfactor.is_universal():
                return None
            rself = ~self
        except SetExpressionError:
            return None

        rfactor_inters = frozenset(rfactor.__inters)
        inters = [inter for inter in rself.__inters if inter not in rfactor_inters]
        if len(rself.__inters) - len(inters) != len(rfactor.__inters):
            return None

        try:
            return ~SetExpression(inters)
        except SetExpressionError:
            return None

    def __and__(self, other: SetExpression) -> SetExpression:
        if not isinstance(other, SetExpression):
            raise TypeError(f"Expected SetExpression, got {type(other).__name__}")
        if self.is_universal():
            return other
        if other.is_universal():
            return self
        if self.is_empty() or other.is_empty():
            return EMPTY_UNION
        if self == other:
            return self
        if len(self.__inters) * len(other.__inters) > MAX_INTERSECTION_TERMS:
            raise SetExpressionError(
                f"set expression intersection too large "
                f"({len(self.__inters)} x {len(other.__inters)} terms exceeds "
                f"{MAX_INTERSECTION_TERMS}); the input expression is pathological"
            )
        return SetExpression(
            self_inter & other_inter
            for self_inter in self.__inters
            for other_inter in other.__inters
        )

    def __or__(self, other: SetExpression) -> SetExpression:
        if not isinstance(other, SetExpression):
            raise TypeError(f"Expected SetExpression, got {type(other).__name__}")
        if self.is_empty():
            return other
        if other.is_empty():
            return self
        if self.is_universal() or other.is_universal():
            return UNIVERSAL_UNION
        if self == other:
            return self
        inters = self.__combine(self.__inters, other.__inters)
        return SetExpression(inters, optimal=True)

    def __invert__(self) -> SetExpression:
        if self.is_empty():
            return UNIVERSAL_UNION
        if self.is_universal():
            return EMPTY_UNION

        estimate = 1
        for inter in self.__inters:
            estimate *= max(1, len(inter.leaves))
            if estimate > MAX_INTERSECTION_TERMS:
                raise SetExpressionError(
                    f"cannot invert set expression: De Morgan expansion exceeds "
                    f"{MAX_INTERSECTION_TERMS} terms; the input is pathological"
                )

        inverses_of_inters = [
            SetExpression(Inter([~leaf]) for leaf in inter.leaves)
            for inter in self.__inters
        ]
        result = inverses_of_inters[0]
        for inverse in inverses_of_inters[1:]:
            result &= inverse

        return result

    def matches(self, user_group_ids: Iterable[int]) -> bool:
        user_group_ids = set(user_group_ids)
        if self.is_empty() or not user_group_ids:
            return False
        if self.is_universal():
            return True
        return any(inter.matches(user_group_ids) for inter in self.__inters)

    def __bool__(self) -> bool:
        raise NotImplementedError

    def __eq__(self, other: object) -> bool:
        return isinstance(other, SetExpression) and self.__key == other.__key

    def __le__(self, other: SetExpression) -> bool:
        if not isinstance(other, SetExpression):
            return False
        if self.__key == other.__key:
            return True
        if self.is_universal() or other.is_empty():
            return False
        if other.is_universal() or self.is_empty():
            return True
        return all(
            any(self_inter <= other_inter for other_inter in other.__inters)
            for self_inter in self.__inters
        )

    def __lt__(self, other: SetExpression) -> bool:
        return self != other and self.__le__(other)

    def __str__(self) -> str:
        if self.is_empty():
            return "~*"

        def leaf_to_str(leaf: Leaf) -> str:
            return f"{'~' if leaf.negative else ''}{leaf.ref!r}"

        def inter_to_str(inter: Inter, wrapped: bool = False) -> str:
            result = " & ".join(leaf_to_str(leaf) for leaf in inter.leaves) or "*"
            return f"({result})" if wrapped and len(inter.leaves) > 1 else result

        wrapped = len(self.__inters) > 1
        return " | ".join(inter_to_str(inter, wrapped) for inter in self.__inters)

    def __repr__(self) -> str:
        return repr(self.__str__())

    def __hash__(self) -> int:
        return self.__hash


class _UnionIndex:
    # The terms of a union under construction, in insertion order, indexed so that
    # merging a term looks only at the terms _union_merge can fold it into: one it
    # is <= to, one <= to it, or one over the same leaf ids. Inter a <= Inter b holds
    # only if every key of b is in a.reach(), which the maps below answer without a
    # pairwise scan. Candidates keep insertion order, so the first term that merges
    # is the one a scan of the whole union would have found.
    __slots__ = (
        "_by_ids",
        "_by_key",
        "_by_keys",
        "_by_reach",
        "_entries",
        "_indexed",
        "_next",
        "_special",
        "_widths",
    )

    def __init__(self, inters: Iterable[Inter]) -> None:
        self._entries: dict[int, Inter] = {}
        self._indexed = False
        self._next = 0
        for inter in inters:
            self.add(inter)

    def inters(self) -> list[Inter]:
        return list(self._entries.values())

    def add(self, inter: Inter) -> None:
        seq = self._next
        self._next += 1
        self._entries[seq] = inter
        if self._indexed:
            self._index(seq, inter)
        elif len(self._entries) > _SCAN_LIMIT:
            self._by_ids: dict[tuple[LeafIdType, ...], set[int]] = {}
            self._by_key: dict[LeafKey, set[int]] = {}
            self._by_keys: dict[frozenset[LeafKey], set[int]] = {}
            self._by_reach: dict[LeafKey, set[int]] = {}
            self._widths: dict[int, int] = {}
            self._special: set[int] = set()
            self._indexed = True
            for entry in self._entries.items():
                self._index(*entry)

    def _index(self, seq: int, inter: Inter) -> None:
        if inter.is_special():
            self._special.add(seq)
            return
        keys = frozenset(inter.key)
        for key in keys:
            self._by_key.setdefault(key, set()).add(seq)
        for key in inter.reach():
            self._by_reach.setdefault(key, set()).add(seq)
        self._by_keys.setdefault(keys, set()).add(seq)
        self._by_ids.setdefault(inter.ids(), set()).add(seq)
        self._widths[len(keys)] = self._widths.get(len(keys), 0) + 1

    def discard(self, seq: int) -> None:
        inter = self._entries.pop(seq)
        if not self._indexed:
            return
        if seq in self._special:
            self._special.discard(seq)
            return
        keys = frozenset(inter.key)
        for key in keys:
            self._by_key[key].discard(seq)
        for key in inter.reach():
            self._by_reach[key].discard(seq)
        self._by_keys[keys].discard(seq)
        self._by_ids[inter.ids()].discard(seq)
        self._widths[len(keys)] -= 1

    def candidates(self, inter: Inter) -> list[tuple[int, Inter]]:
        entries = self._entries
        if not self._indexed or inter.is_special():
            return list(entries.items())
        found = set(self._special)
        found.update(self._by_ids.get(inter.ids(), ()))
        found.update(self._subsuming(inter.reach()))
        reaching = [self._by_reach.get(key, set()) for key in set(inter.key)]
        found.update(set.intersection(*reaching))
        return [(seq, entries[seq]) for seq in sorted(found)]

    def _subsuming(self, reach: frozenset[LeafKey]) -> Iterable[int]:
        # the terms whose every key lies in reach: either every subset of reach of
        # a width some term has, or every term sharing a key with it, whichever the
        # index says is fewer to look at
        widths = [w for w, n in self._widths.items() if n and w <= len(reach)]
        subsets = sum(math.comb(len(reach), w) for w in widths)
        sharing = sum(len(self._by_key.get(key, ())) for key in reach)
        if subsets <= sharing:
            by_keys = self._by_keys
            return [
                seq
                for width in widths
                for keys in itertools.combinations(reach, width)
                for seq in by_keys.get(frozenset(keys), ())
            ]
        covered: dict[int, int] = {}
        for key in reach:
            for seq in self._by_key.get(key, ()):
                covered[seq] = covered.get(seq, 0) + 1
        entries = self._entries
        return [
            seq
            for seq, count in covered.items()
            if count == len(frozenset(entries[seq].key))
        ]


# below this many terms a scan costs less than consulting the index
_SCAN_LIMIT = 8


class Inter:
    __slots__ = ("_reach", "key", "leaves")

    def __init__(self, leaves: Iterable[Leaf] = (), optimal: bool = False) -> None:
        if leaves and not optimal:
            leaves = self.__combine((), leaves)
        self.leaves: list[Leaf] = sorted(leaves, key=lambda leaf: leaf.key)
        self.key: tuple[tuple[LeafIdType, bool], ...] = tuple(
            leaf.key for leaf in self.leaves
        )
        self._reach: frozenset[tuple[LeafIdType, bool]] | None = None

    def ids(self) -> tuple[LeafIdType, ...]:
        return tuple(leaf.id for leaf in self.leaves)

    def is_special(self) -> bool:
        return any(leaf.ref == "*" for leaf in self.leaves)

    def reach(self) -> frozenset[tuple[LeafIdType, bool]]:
        if self._reach is None:
            self._reach = frozenset().union(*(leaf.reach() for leaf in self.leaves))
        return self._reach

    @staticmethod
    def __combine(leaves: Iterable[Leaf], leaves_to_add: Iterable[Leaf]) -> list[Leaf]:
        result = list(leaves)
        for leaf_to_add in leaves_to_add:
            if leaf_to_add.is_universal():
                continue
            if any(leaf.isdisjoint(leaf_to_add) for leaf in result):
                return [EMPTY_LEAF]
            if any(leaf <= leaf_to_add for leaf in result):
                continue
            result = [leaf for leaf in result if not leaf_to_add <= leaf]
            result.append(leaf_to_add)
        return result

    def is_empty(self) -> bool:
        return any(item.is_empty() for item in self.leaves)

    def is_universal(self) -> bool:
        return not self.leaves

    def matches(self, user_group_ids: Collection[int]) -> bool:
        return all(leaf.matches(user_group_ids) for leaf in self.leaves)

    def _union_merge(self, other: Inter) -> Inter | None:
        if self.is_universal() or other <= self:
            return self
        if self <= other:
            return other

        if len(self.leaves) == len(other.leaves):
            opposite_index = None
            for index, self_leaf, other_leaf in zip(
                range(len(self.leaves)), self.leaves, other.leaves, strict=False
            ):
                if self_leaf.id != other_leaf.id:
                    return None
                if self_leaf.negative != other_leaf.negative:
                    if opposite_index is not None:
                        return None
                    opposite_index = index
            if opposite_index is not None:
                leaves = list(self.leaves)
                leaves.pop(opposite_index)
                return Inter(leaves, optimal=True)
        return None

    def __and__(self, other: Inter) -> Inter:
        if self.is_empty() or other.is_empty():
            return EMPTY_INTER
        if self.is_universal():
            return other
        if other.is_universal():
            return self
        leaves = self.__combine(self.leaves, other.leaves)
        return Inter(leaves, optimal=True)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Inter) and self.key == other.key

    def __le__(self, other: Inter) -> bool:
        return self.key == other.key or all(
            any(self_leaf <= other_leaf for self_leaf in self.leaves)
            for other_leaf in other.leaves
        )

    def __lt__(self, other: Inter) -> bool:
        return self != other and self <= other

    def __hash__(self) -> int:
        return hash(self.key)


class Leaf:
    __slots__ = (
        "_reach",
        "disjoints",
        "id",
        "inverse",
        "key",
        "negative",
        "ref",
        "subsets",
        "supersets",
    )

    def __init__(
        self,
        leaf_id: LeafIdType,
        ref: str | int | None = None,
        negative: bool = False,
    ) -> None:
        self.id = leaf_id
        self.ref = ref or str(leaf_id)
        self.negative = bool(negative)
        self.key: tuple[LeafIdType, bool] = (leaf_id, self.negative)

        self.subsets: set[LeafIdType] = {leaf_id}
        self.supersets: set[LeafIdType] = {leaf_id}
        self.disjoints: set[LeafIdType] = set()
        self.inverse: Leaf | None = None
        self._reach: frozenset[tuple[LeafIdType, bool]] | None = None

    def __invert__(self) -> Leaf:
        if self.inverse is None:
            self.inverse = Leaf(self.id, self.ref, negative=not self.negative)
            self.inverse.inverse = self
            self.inverse.subsets = self.subsets
            self.inverse.supersets = self.supersets
            self.inverse.disjoints = self.disjoints
        return self.inverse

    def reach(self) -> frozenset[tuple[LeafIdType, bool]]:
        # the keys of every non-special leaf this one is <= to, read off __le__:
        # subsets and supersets are one relation seen from both ends, and disjoints
        # are symmetric, so the leaves above this one are found from this one
        if self._reach is None:
            if self.negative:
                self._reach = frozenset((sub_id, True) for sub_id in self.subsets)
            else:
                self._reach = frozenset(
                    [
                        *((sup_id, False) for sup_id in self.supersets),
                        *((dis_id, True) for dis_id in self.disjoints),
                    ]
                )
        return self._reach

    def is_empty(self) -> bool:
        return self.ref == "*" and self.negative

    def is_universal(self) -> bool:
        return self.ref == "*" and not self.negative

    def isdisjoint(self, other: Leaf) -> bool:
        if self.negative:
            return other <= ~self
        elif other.negative:
            return self <= ~other
        else:
            return self.id in other.disjoints

    def matches(self, user_group_ids: Collection[int]) -> bool:
        return (
            (self.id not in user_group_ids)
            if self.negative
            else (self.id in user_group_ids)
        )

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Leaf) and self.key == other.key

    def __le__(self, other: Leaf) -> bool:
        if self.is_empty() or other.is_universal():
            return True
        elif self.is_universal() or other.is_empty():
            return False
        elif self.negative:
            return other.negative and ~other <= ~self
        elif other.negative:
            return self.id in other.disjoints
        else:
            return self.id in other.subsets

    def __lt__(self, other: Leaf) -> bool:
        return self != other and self <= other

    def __hash__(self) -> int:
        return hash(self.key)


class UnknownId(str):
    __slots__ = ()

    def __lt__(self, other: object) -> bool:
        if isinstance(other, UnknownId):
            return super().__lt__(other)
        return False

    def __gt__(self, other: object) -> bool:
        if isinstance(other, UnknownId):
            return super().__gt__(other)
        return True


type LeafIdType = int | Literal["*"] | UnknownId
type LeafKey = tuple[LeafIdType, bool]

UNIVERSAL_LEAF = Leaf("*")
EMPTY_LEAF = ~UNIVERSAL_LEAF

EMPTY_INTER = Inter([EMPTY_LEAF])
UNIVERSAL_INTER = Inter()

EMPTY_UNION = SetExpression()
UNIVERSAL_UNION = SetExpression([UNIVERSAL_INTER])
