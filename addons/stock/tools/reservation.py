import heapq
import math
import typing
from collections import defaultdict

from odoo.libs.debug_log import DebugLog
from odoo.tools import float_compare, float_is_zero, float_round

_debug = DebugLog(__name__)


class LeastPackagesPriorityQueue:
    def __init__(self) -> None:
        self.elements = []
        self._counter = 0

    def is_empty(self) -> bool:
        return not self.elements

    def put(self, item, priority):
        heapq.heappush(self.elements, (priority, self._counter, item))
        self._counter += 1

    def get(self):
        return heapq.heappop(self.elements)[2]


class LeastPackagesNode(typing.NamedTuple):
    count_remaining: float
    taken_packages: tuple
    next_index: int


LEAST_PACKAGES_MAX_EXPANSIONS = 10_000


def get_least_packages(
    qty_by_package, qty, max_expansions=LEAST_PACKAGES_MAX_EXPANSIONS
):
    size = len(qty_by_package)

    def heuristic(node):
        if node.next_index < size:
            return (
                len(node.taken_packages)
                + node.count_remaining / qty_by_package[node.next_index][1]
            )
        return len(node.taken_packages)

    def is_better_leaf(node, best):
        if best.count_remaining > 0:
            return (
                node.count_remaining <= 0 or node.count_remaining < best.count_remaining
            )
        if node.count_remaining > 0:
            return False
        return len(node.taken_packages) < len(best.taken_packages) or (
            len(node.taken_packages) == len(best.taken_packages)
            and node.count_remaining > best.count_remaining
        )

    frontier = LeastPackagesPriorityQueue()
    frontier.put(LeastPackagesNode(qty, (), 0), 0)
    best_leaf = LeastPackagesNode(qty, (), 0)
    expansions = 0

    while not frontier.is_empty():
        current = frontier.get()

        if current.count_remaining <= 0:
            return current.taken_packages
        expansions += 1
        if expansions > max_expansions:
            _debug.logic(
                "least_packages_budget_exhausted",
                packages=size,
                expansions=expansions,
                covered=best_leaf.count_remaining <= 0,
            )
            if best_leaf.count_remaining <= 0:
                return best_leaf.taken_packages
            return _take_largest_until_covered(qty_by_package, qty)

        last_count = None
        i = current.next_index
        while i < size:
            pkg = qty_by_package[i]
            i += 1
            if pkg[1] == last_count:
                continue
            last_count = pkg[1]

            count = current.count_remaining - pkg[1]
            taken = current.taken_packages + (pkg,)
            node = LeastPackagesNode(count, taken, i)

            if count < 0 or (i >= size and count != 0):
                if is_better_leaf(node, best_leaf):
                    best_leaf = node
                continue

            frontier.put(node, heuristic(node))

    return best_leaf.taken_packages


def _take_largest_until_covered(qty_by_package, qty):
    taken = []
    for pkg in sorted(qty_by_package, key=lambda pkg: pkg[1], reverse=True):
        if qty <= 0:
            break
        taken.append(pkg)
        qty -= pkg[1]
    return tuple(taken)


class RemovalStrategy(typing.NamedTuple):
    order: str | typing.Literal[False]
    sort_key: typing.Callable | None = None
    reverse: bool = False
    narrows_to_packages: bool = False
    location_sort_key: typing.Callable | None = None

    def resolve_sorted_arguments(self):
        return None if self.sort_key is None else (self.sort_key, self.reverse)


class ReservationLedger:
    __slots__ = ("_by_move", "_pending", "move_line_vals")

    def __init__(self, move_line_vals=None) -> None:
        self._pending = defaultdict(float)
        self._by_move = defaultdict(list)
        self.move_line_vals = []
        self.add_move_line_vals(move_line_vals or ())

    def add_move_line_vals(self, vals_list) -> None:
        for vals in vals_list:
            self.move_line_vals.append(vals)
            self._by_move[vals.get("move_id")].append(vals)

    def get_pending(self, quant):
        return self._pending.get(quant.id, 0.0)

    def take(self, quant, quantity):
        self._pending[quant.id] += quantity

    def get_pending_quant_ids(self) -> list:
        return [quant_id for quant_id, quantity in self._pending.items() if quantity]

    def get_total_pending(self):
        return sum(self._pending.values())

    def get_pending_move_line_vals(self, move_ids) -> list:
        return [vals for move_id in move_ids for vals in self._by_move.get(move_id, ())]


class ReservationCandidate(typing.NamedTuple):
    handle: object
    on_hand: float
    reserved: float
    key: object


def distribute_reservation(candidates, quantity, precision_rounding, whole_units=False):
    reserved = []
    if float_compare(quantity, 0, precision_rounding=precision_rounding) <= 0:
        return reserved

    negative_available = defaultdict(float)
    for cand in candidates:
        slack = cand.on_hand - cand.reserved
        if float_compare(slack, 0, precision_rounding=precision_rounding) < 0:
            negative_available[cand.key] += slack
    if _debug.logic.enabled and negative_available:
        _debug.logic(
            "distribute_reservation_negative_first", places=len(negative_available)
        )

    for cand in candidates:
        max_on_cand = cand.on_hand - cand.reserved
        if float_compare(max_on_cand, 0, precision_rounding=precision_rounding) <= 0:
            continue
        negative = negative_available[cand.key]
        if negative:
            to_absorb = min(abs(negative), max_on_cand)
            negative_available[cand.key] += to_absorb
            max_on_cand -= to_absorb
        if float_compare(max_on_cand, 0, precision_rounding=precision_rounding) <= 0:
            continue
        max_on_cand = min(max_on_cand, quantity)
        if whole_units:
            max_on_cand = float(
                math.floor(
                    float_round(max_on_cand, precision_rounding=precision_rounding)
                )
            )
            if max_on_cand <= 0:
                continue
        reserved.append((cand.handle, max_on_cand))
        quantity -= max_on_cand

        if float_is_zero(quantity, precision_rounding=precision_rounding):
            break
    _debug.logic(
        "distribute_reservation",
        candidates=len(candidates),
        whole_units=whole_units,
        taken=len(reserved),
        unserved=quantity,
    )
    return reserved


class QuantsCache:
    __slots__ = (
        "_by_product",
        "_data",
        "_empty",
        "_location_paths",
        "_lot_scope",
        "_paths_by_location",
        "_product_ids",
    )

    def __init__(
        self, empty, product_ids=(), location_paths=(), lot_scope=None
    ) -> None:
        self._data = {}
        self._by_product = defaultdict(list)
        self._empty = empty
        self._product_ids = frozenset(product_ids)
        self._location_paths = tuple(p for p in location_paths if p)
        self._lot_scope = None if lot_scope is None else frozenset(lot_scope)
        self._paths_by_location = {}

    def __getitem__(self, key):
        return self._data.get(key, self._empty)

    def __setitem__(self, key, value):
        if key not in self._data:
            self._by_product[key[0]].append(key)
        self._data[key] = value

    def set_location_path(self, location_id, parent_path) -> None:
        self._paths_by_location[location_id] = parent_path or ""

    def add(self, quant):
        location = quant.location_id
        key = (
            quant.product_id.id,
            location.id,
            quant.trace_id.id,
            quant.package_id.id,
            quant.owner_id.id,
        )
        self[key] |= quant
        self.set_location_path(location.id, location.parent_path)

    def under(
        self, product_id, location_path, trace_id=None, package_id=None, owner_id=None
    ):
        paths = self._paths_by_location
        ids = []
        for key in self._by_product.get(product_id, ()):
            _product, location, lot, package, owner = key
            if not paths.get(location, "").startswith(location_path):
                continue
            if trace_id and lot not in (trace_id, False):
                continue
            if package_id and package != package_id:
                continue
            if owner_id and owner != owner_id:
                continue
            ids.extend(self._data[key]._ids)
        return self._empty.browse(dict.fromkeys(ids))

    def is_covering(self, product_id, location_id, trace_id=None, strict=True) -> bool:
        if product_id.id not in self._product_ids:
            _debug.perf.count("quants_cache_miss_product", product=product_id.id)
            return False
        path = location_id.parent_path or ""
        if not any(path.startswith(root) for root in self._location_paths):
            _debug.perf.count("quants_cache_miss_location", location=location_id.id)
            return False
        if self._lot_scope is None:
            return True
        return trace_id.id in self._lot_scope if trace_id else strict
