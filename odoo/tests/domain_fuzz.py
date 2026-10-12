from __future__ import annotations

import dataclasses
import os
import random
import typing
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass, field
from datetime import date, datetime

from odoo.fields import Command
from odoo.libs.debug_log import DebugLog
from odoo.orm.model_test_env import InMemoryCursor

if typing.TYPE_CHECKING:
    from odoo.orm.fields import Properties
    from odoo.orm.models import BaseModel
    from odoo.orm.runtime.environment import Environment

_debug = DebugLog(__name__)

ROUNDS_VARIABLE = "ODOO_DOMAIN_FUZZ_ROUNDS"
SEED_VARIABLE = "ODOO_DOMAIN_FUZZ_SEED"
DEPTH_VARIABLE = "ODOO_DOMAIN_FUZZ_DEPTH"

_MAGIC_FIELDS = frozenset(
    ("create_uid", "create_date", "write_uid", "write_date", "parent_path")
)

PRINCIPALS = "res.users"
LANGS = ("en_US", "fr_FR")
TIMEZONES = ("UTC", "America/Mexico_City", "Asia/Tokyo", "Pacific/Kiritimati")
_PARTS = (
    "year_number",
    "quarter_number",
    "month_number",
    "iso_week_number",
    "day_of_year",
    "day_of_month",
    "day_of_week",
    "hour_number",
)


@dataclass(frozen=True, order=True)
class Ref:
    model: str
    index: int

    @typing.override
    def __repr__(self) -> str:
        return f"{self.model.rsplit('.', 1)[-1]}#{self.index}"


ME = Ref(PRINCIPALS, 0)
OTHER = Ref(PRINCIPALS, 1)


class _UserId:
    @typing.override
    def __repr__(self) -> str:
        return "user.id"


USER = _UserId()


@dataclass(frozen=True)
class Translated:
    en_US: str
    fr_FR: str

    @typing.override
    def __repr__(self) -> str:
        return f"{{en_US: {self.en_US!r}, fr_FR: {self.fr_FR!r}}}"


@dataclass(frozen=True)
class Raised:
    error: str

    @typing.override
    def __repr__(self) -> str:
        return f"raised {self.error}"


ABSTAINED = Raised("abstained")
Outcome = frozenset[Ref] | Raised
Row = dict[str, typing.Any]
Dataset = dict[str, list[Row | None]]


@dataclass(frozen=True)
class FieldSpec:
    name: str
    type: str
    comodel: str | None
    required: bool
    size: int | None
    selection: tuple[str, ...]
    writable: bool
    unique: bool
    hierarchical: bool
    source: tuple[str, str] | None
    translate: bool = False
    container: str | None = None
    part: str | None = None


@dataclass(frozen=True)
class Container:
    name: str
    link: str
    definition: str


@dataclass(frozen=True)
class ModelSpec:
    name: str
    fields: tuple[FieldSpec, ...]
    containers: tuple[Container, ...] = ()
    definitions: tuple[str, ...] = ()

    def writable(self) -> list[FieldSpec]:
        return [spec for spec in self.fields if spec.writable]

    @property
    def hierarchical(self) -> bool:
        return any(spec.hierarchical for spec in self.fields)

    def get(self, fname: str) -> FieldSpec:
        return next(spec for spec in self.fields if spec.name == fname)

    def find(self, fname: str) -> FieldSpec | None:
        return next((spec for spec in self.fields if spec.name == fname), None)


@dataclass(frozen=True)
class Schema:
    models: Mapping[str, ModelSpec]
    creation_order: tuple[str, ...]

    def resolve(self, model: str, path: str) -> tuple[list[str], str, FieldSpec]:
        names = path.split(".")
        owner = model
        for index in range(len(names)):
            spec = self.models[owner].find(".".join(names[index:]))
            if spec is not None:
                return names[:index], owner, spec
            owner = typing.cast("str", self.models[owner].get(names[index]).comodel)
        raise KeyError(path)

    def reached(self, model: str, path: str) -> set[str]:
        steps, owner, spec = self.resolve(model, path)
        found = set()
        current = model
        for step in steps:
            current = typing.cast("str", self.models[current].get(step).comodel)
            found.add(current)
        if spec.comodel:
            found.add(spec.comodel)
        return found | {owner} if steps else found


def build_schema(env: Environment, model_names: Sequence[str]) -> Schema:
    specs = {}
    for model_name in model_names:
        model = env[model_name]
        parent_name = (
            model._parent_name if model._parent_name in model._fields else None
        )
        found = []
        containers = []
        definitions = []
        for fname, fld in model._fields.items():
            if fld.type == "properties_definition":
                definitions.append(fname)
                continue
            if fld.type == "properties":
                path = typing.cast("Properties", fld).definition
                assert path, f"{fld} names no definition"
                link, definition = path.split(".")
                containers.append(Container(fname, link, definition))
                found += _property_specs(fname)
                continue
            if fname in _MAGIC_FIELDS or not fld._description_searchable:
                continue
            comodel = getattr(fld, "comodel_name", None)
            if comodel and comodel not in model_names and comodel != PRINCIPALS:
                continue
            selection: tuple[str, ...] = ()
            choices = getattr(fld, "selection", None)
            if fld.type == "selection" and isinstance(choices, list):
                selection = tuple(key for key, _label in choices)
            found.append(
                FieldSpec(
                    name=fname,
                    type=fld.type,
                    comodel=comodel,
                    required=bool(fld.required),
                    size=getattr(fld, "size", None),
                    selection=selection,
                    writable=bool(
                        fld.store
                        and not fld.compute
                        and not fld.related
                        and fname != "id"
                        and fld.type not in ("one2many", "one2one")
                    ),
                    unique=fld.index == "unique",
                    hierarchical=fname == parent_name,
                    source=_source_of(model_name, fname, fld),
                    translate=bool(getattr(fld, "translate", False)),
                )
            )
            if fld.type in ("date", "datetime"):
                found += _part_specs(fname)
        specs[model_name] = ModelSpec(
            model_name, tuple(found), tuple(containers), tuple(definitions)
        )
    return Schema(specs, _creation_order(specs))


def _part_specs(fname: str, container: str | None = None) -> list[FieldSpec]:
    return [
        FieldSpec(
            name=f"{fname}.{part}",
            type="part",
            comodel=None,
            required=False,
            size=None,
            selection=(),
            writable=False,
            unique=False,
            hierarchical=False,
            source=None,
            container=container,
            part=part,
        )
        for part in _PARTS
    ]


def _property_specs(container: str) -> list[FieldSpec]:
    found = []
    for definition in PROPERTY_POOL:
        ptype = definition["type"]
        name = f"{container}.{definition['name']}"
        choices = definition.get("selection") or definition.get("tags") or ()
        found.append(
            FieldSpec(
                name=name,
                type=f"property_{ptype}",
                comodel=definition.get("comodel"),
                required=False,
                size=None,
                selection=tuple(choice[0] for choice in choices),
                writable=False,
                unique=False,
                hierarchical=False,
                source=None,
                container=container,
            )
        )
        if ptype in ("date", "datetime"):
            found += _part_specs(name, container)
    return found


def _source_of(model_name: str, fname: str, fld: typing.Any) -> tuple[str, str] | None:
    if fld.related and (seq := fld._related_field_seq):
        target = seq[-1]
        return target.model_name, target.name
    if fld.store and not fld.compute and fname != "id":
        return model_name, fname
    return None


def _creation_order(specs: Mapping[str, ModelSpec]) -> tuple[str, ...]:
    order: list[str] = []

    def visit(name: str, path: tuple[str, ...]) -> None:
        if name in order or name in path:
            return
        for spec in specs[name].writable():
            comodel = spec.comodel
            if (
                spec.type == "many2one"
                and comodel is not None
                and comodel in specs
                and comodel != name
            ):
                visit(comodel, (*path, name))
        order.append(name)

    for name in specs:
        visit(name, ())
    return tuple(order)


_CHARS = (
    "a",
    "",
    "aB",
    "abcdef",
    "A",
    "ab",
    "abc",
    "b",
    "ba",
    "a_c",
    "a%c",
    "%",
    "_",
    "zz",
    "é",
    "É",
    " a",
    "ABCDEFGH",
)
_INTEGERS = (0, 1, 7, -1, 2, 8, 2147483647, -2147483648)
_FLOATS = (0.0, 1.0, 2.25, -0.5, 0.5, 7.0, 1e9)
_DATES = (date(2025, 12, 31), date(2026, 1, 1), date(2026, 1, 31), date(2026, 2, 28))
_DATETIMES = (
    datetime(2025, 12, 31, 23, 59, 59),
    datetime(2026, 1, 1, 0, 0, 0),
    datetime(2026, 1, 1, 23, 59, 59),
    datetime(2026, 1, 31, 12, 0, 0),
)
_LIKE_PATTERNS = (
    "a",
    "A",
    "b",
    "%",
    "_",
    "a%",
    "%c",
    "a_c",
    "",
    "é",
    "ab%",
    "\\%",
    "1",
    "0",
    "-%",
    "2026%",
    "%01%",
    "%.%",
    "tr%",
)
_REGEXES = ("a", "^a", "b$", ".", "^$", "^[ab]+$", "A", "^0$", "1", "^-", "^2026-01")
_PATTERN_OPERATORS = ("like", "not like", "ilike", "not ilike", "=like", "=~", "not =~")
MISSING = -1
_FOREIGN: dict[str, tuple[typing.Any, ...]] = {
    "integer": ("7", 7.5, "-1"),
    "float": (7, "2.25", "0"),
    "char": (7, 0),
    "text": (7,),
    "date": ("2026-01-01", "2026-01-31", datetime(2026, 1, 1, 12, 0, 0)),
    "datetime": ("2026-01-01", "2026-01-01 00:00:00", date(2026, 1, 1)),
    "property_date": ("2026-01-01", "2026-01-31"),
    "property_datetime": ("2026-01-01 00:00:00", date(2026, 1, 1)),
    "property_integer": (7.0, "7"),
}


_PART_VALUES = (0, 1, 2, 3, 4, 5, 6, 12, 23, 31, 52, 53, 365, 2025, 2026)
PROPERTY_POOL: tuple[dict[str, typing.Any], ...] = (
    {"name": "size", "type": "integer"},
    {"name": "ratio", "type": "float"},
    {"name": "label", "type": "char"},
    {"name": "flag", "type": "boolean"},
    {"name": "kind", "type": "selection", "selection": [["s1", "S1"], ["s2", "S2"]]},
    {"name": "due", "type": "date"},
    {"name": "stamp", "type": "datetime"},
    {"name": "tag", "type": "many2one", "comodel": "test_orm.domain.tag"},
    {
        "name": "marks",
        "type": "tags",
        "tags": [["t1", "T1", 1], ["t2", "T2", 2], ["t3", "T3", 3]],
    },
)


def _scalars(spec: FieldSpec) -> tuple[typing.Any, ...]:
    match spec.type.removeprefix("property_"):
        case "char" | "text":
            return _CHARS
        case "integer":
            return _INTEGERS
        case "float":
            return _FLOATS
        case "boolean":
            return (True, False)
        case "date":
            return _DATES
        case "datetime":
            return _DATETIMES
        case "selection" | "tags":
            return spec.selection
        case "part":
            return _PART_VALUES
    raise ValueError(f"no value pool for {spec.type} field {spec.name}")


def generate_dataset(
    schema: Schema, rng: random.Random, sizes: Mapping[str, int]
) -> Dataset:
    dataset: Dataset = {}
    for model_name in schema.creation_order:
        count = sizes.get(model_name, 0)
        rows: list[Row | None] = []
        model = schema.models[model_name]
        taken: dict[str, set[Ref]] = {}
        for index in range(count):
            row: Row = {}
            for spec in model.writable():
                value = _row_value(spec, dataset, model_name, index, rng, taken)
                if value is not _UNSET:
                    row[spec.name] = value
            for fname in model.definitions:
                if rng.random() < 0.85:
                    row[fname] = _definition(rng)
            for container in model.containers:
                values = _property_values(rng, dataset, row, container)
                if values is not None:
                    row[container.name] = values
            rows.append(row)
        dataset[model_name] = rows
    return dataset


_UNSET = object()


def _definition(rng: random.Random) -> list[dict[str, typing.Any]]:
    chosen = [item for item in PROPERTY_POOL if rng.random() < 0.7]
    rng.shuffle(chosen)
    return [dict(item, string=item["name"].title()) for item in chosen]


def _property_values(
    rng: random.Random, dataset: Dataset, row: Row, container: Container
) -> dict[str, typing.Any] | None:
    holder = row.get(container.link)
    if not isinstance(holder, Ref) or rng.random() < 0.15:
        return None
    holder_row = dataset[holder.model][holder.index] or {}
    values: dict[str, typing.Any] = {}
    for definition in holder_row.get(container.definition) or ():
        if rng.random() < 0.25:
            continue
        values[definition["name"]] = _property_value(rng, dataset, definition)
    return values


def _property_value(
    rng: random.Random, dataset: Dataset, definition: dict[str, typing.Any]
) -> typing.Any:
    match definition["type"]:
        case "integer":
            return rng.choice(_INTEGERS[:5])
        case "float":
            return rng.choice(_FLOATS[:5])
        case "char":
            return rng.choice((*_CHARS[:6], False))
        case "boolean":
            return rng.random() < 0.5
        case "selection":
            return rng.choice(
                (*(key for key, _label in definition["selection"]), False)
            )
        case "date":
            return rng.choice((*_DATES, False))
        case "datetime":
            return rng.choice((*_DATETIMES, False))
        case "many2one":
            refs = _refs(dataset, definition["comodel"])
            return rng.choice(refs) if refs and rng.random() < 0.8 else False
        case "tags":
            keys = [key for key, _label, _color in definition["tags"]]
            return rng.sample(keys, rng.randint(0, len(keys)))
    raise ValueError(definition)


def _refs(dataset: Dataset, model_name: str, below: int | None = None) -> list[Ref]:
    if model_name == PRINCIPALS:
        return [ME, OTHER]
    rows = dataset.get(model_name, ())
    limit = len(rows) if below is None else below
    return [Ref(model_name, i) for i in range(limit) if rows[i] is not None]


def _row_value(
    spec: FieldSpec,
    dataset: Dataset,
    model_name: str,
    index: int,
    rng: random.Random,
    taken: dict[str, set[Ref]],
) -> typing.Any:
    if spec.type == "many2one":
        assert spec.comodel
        candidates = (
            [Ref(model_name, i) for i in range(index)]
            if spec.comodel == model_name
            else _refs(dataset, spec.comodel)
        )
        if spec.unique:
            candidates = [
                ref for ref in candidates if ref not in taken.get(spec.name, ())
            ]
        if not candidates or (not spec.required and rng.random() < 0.3):
            return _UNSET if spec.required else None
        ref = rng.choice(candidates)
        taken.setdefault(spec.name, set()).add(ref)
        return ref
    if spec.type == "many2many":
        assert spec.comodel
        candidates = _refs(dataset, spec.comodel)
        return sorted(rng.sample(candidates, rng.randint(0, min(3, len(candidates)))))
    if rng.random() < 0.15:
        return _UNSET
    if spec.type in ("char", "text") and rng.random() < 0.1:
        return False
    pool = _scalars(spec)
    if spec.translate and rng.random() < 0.6:
        english = rng.choice([text for text in pool[:6] if text])
        return Translated(english, rng.choice(pool[:8]))
    if rng.random() < 0.8:
        pool = pool[:4]
    return rng.choice(pool)


@dataclass(frozen=True)
class Leaf:
    path: str
    operator: str
    value: typing.Any


@dataclass(frozen=True)
class Not:
    child: Node


@dataclass(frozen=True)
class Nary:
    operator: str
    children: tuple[Node, ...]


@dataclass(frozen=True)
class SubDomain:
    model: str
    node: Node


Node = Leaf | Not | Nary


_SCALAR_OPERATORS = {
    "char": (
        "=",
        "!=",
        "in",
        "not in",
        "like",
        "not like",
        "ilike",
        "not ilike",
        "=like",
        "not =like",
        "=ilike",
        "not =ilike",
        "<",
        "<=",
        ">",
        ">=",
        "=~",
        "not =~",
        "=?",
    ),
    "integer": ("=", "!=", "<", "<=", ">", ">=", "in", "not in", "=?"),
    "boolean": ("=", "!=", "in", "not in"),
    "selection": ("=", "!=", "in", "not in", "<", ">="),
}
_SCALAR_OPERATORS["text"] = _SCALAR_OPERATORS["char"]
_SCALAR_OPERATORS["float"] = _SCALAR_OPERATORS["integer"]
_SCALAR_OPERATORS["date"] = _SCALAR_OPERATORS["integer"]
_SCALAR_OPERATORS["datetime"] = _SCALAR_OPERATORS["integer"]
_SCALAR_OPERATORS["part"] = ("=", "!=", "<", "<=", ">", ">=", "in", "not in")
_SCALAR_OPERATORS["property_integer"] = _SCALAR_OPERATORS["part"]
_SCALAR_OPERATORS["property_float"] = _SCALAR_OPERATORS["part"]
_SCALAR_OPERATORS["property_date"] = _SCALAR_OPERATORS["part"]
_SCALAR_OPERATORS["property_datetime"] = _SCALAR_OPERATORS["part"]
_SCALAR_OPERATORS["property_char"] = (
    "=",
    "!=",
    "in",
    "not in",
    "like",
    "not like",
    "ilike",
    "not ilike",
    "=like",
    "=ilike",
    "<",
    ">=",
)
_SCALAR_OPERATORS["property_boolean"] = ("=", "!=", "in", "not in")
_SCALAR_OPERATORS["property_selection"] = ("=", "!=", "in", "not in")
_SCALAR_OPERATORS["property_tags"] = ("=", "!=", "in", "not in")
_PROPERTY_RELATIONAL_OPERATORS = ("=", "!=", "in", "not in", "any", "not any")
_RELATIONAL_OPERATORS = (
    "=",
    "!=",
    "in",
    "not in",
    "any",
    "not any",
    "ilike",
    "not ilike",
)
_HIERARCHY_OPERATORS = ("child_of", "parent_of")
_SET_OPERATORS = ("=", "!=", "in", "not in")


class DomainGenerator:
    def __init__(
        self,
        schema: Schema,
        dataset: Dataset,
        rng: random.Random,
        *,
        accepts: Callable[[str, str, str], bool] | None = None,
        merges: bool = False,
    ) -> None:
        self.schema = schema
        self.dataset = dataset
        self.rng = rng
        self.accepts = accepts or (lambda model, path, operator: True)
        self.merges = merges

    def node(self, model: str, depth: int = 3) -> Node:
        roll = self.rng.random()
        if self.merges:
            group = self._siblings(model, depth, self.rng.choice((2, 2, 3)))
            return Not(group) if roll < 0.2 else group
        if depth > 0 and roll < 0.4:
            return self._nary(model, depth)
        if depth > 0 and roll < 0.5:
            return Not(self.node(model, depth - 1))
        return self.leaf(model, depth)

    def _nary(self, model: str, depth: int) -> Nary:
        count = self.rng.choice((2, 2, 2, 3))
        if self.rng.random() < 0.5:
            return self._siblings(model, depth, count)
        children = tuple(self.node(model, depth - 1) for _index in range(count))
        return Nary(self.rng.choice("&|"), children)

    def _siblings(self, model: str, depth: int, count: int) -> Nary:
        rng = self.rng
        first = self.leaf(model, depth - 1)
        children: list[Node] = [first]
        for _index in range(count - 1):
            roll = rng.random()
            operator = (
                first.operator
                if roll < 0.5
                else rng.choice(_SET_OPERATORS)
                if roll < 0.8
                else None
            )
            sibling = self.leaf_on(model, first.path, depth - 1, operator)
            children.append(sibling or self.leaf(model, depth - 1))
        return Nary(rng.choice("&|"), tuple(children))

    def leaf(self, model: str, depth: int) -> Leaf:
        for _attempt in range(50):
            leaf = self._leaf(model, depth)
            if leaf is not None:
                return leaf
        return Leaf("id", "!=", False)

    def leaf_on(
        self, model: str, path: str, depth: int, operator: str | None = None
    ) -> Leaf | None:
        steps, owner, spec = self.schema.resolve(model, path)
        for _attempt in range(10):
            leaf = self._condition(owner, spec, depth, operator)
            if leaf is not None and leaf.operator not in _HIERARCHY_OPERATORS:
                leaf = Leaf(".".join((*steps, leaf.path)), leaf.operator, leaf.value)
                if self.accepts(model, leaf.path, leaf.operator):
                    return leaf
        return None

    def _leaf(self, model: str, depth: int) -> Leaf | None:
        rng = self.rng
        fields = self.schema.models[model].fields
        weights = [
            3 if spec.source and spec.source[0] != model else 1 for spec in fields
        ]
        spec = rng.choices(fields, weights)[0]
        leaf: Leaf | None
        if (
            spec.comodel is not None
            and spec.comodel in self.schema.models
            and not spec.container
            and depth > 0
            and rng.random() < 0.25
        ):
            sub = self._leaf(spec.comodel, depth - 1)
            if sub is None or sub.operator in _HIERARCHY_OPERATORS:
                return None
            leaf = Leaf(f"{spec.name}.{sub.path}", sub.operator, sub.value)
        else:
            leaf = self._condition(model, spec, depth)
        if leaf is None or not self.accepts(model, leaf.path, leaf.operator):
            return None
        return leaf

    def _condition(
        self, model: str, spec: FieldSpec, depth: int, operator: str | None = None
    ) -> Leaf | None:
        rng = self.rng
        chosen = operator

        def choose(operators: Sequence[str]) -> str:
            if chosen is not None and chosen in operators:
                return chosen
            return rng.choice(operators)

        if spec.name == "id":
            operators: tuple[str, ...] = ("=", "!=", "in", "not in", "<", ">=")
            if self.schema.models[model].hierarchical:
                operators = (*operators, *_HIERARCHY_OPERATORS)
            operator = choose(operators)
            return Leaf("id", operator, self._ids(model, operator))
        if spec.name == "display_name":
            operator = choose(_SCALAR_OPERATORS["char"][:12])
            return Leaf(spec.name, operator, self._scalar_value(spec, operator))
        if spec.type == "property_many2one":
            assert spec.comodel
            operator = choose(_PROPERTY_RELATIONAL_OPERATORS)
            if operator in ("any", "not any"):
                if depth <= 0:
                    return None
                return Leaf(
                    spec.name,
                    operator,
                    SubDomain(spec.comodel, self.node(spec.comodel, min(depth - 1, 1))),
                )
            return Leaf(spec.name, operator, self._ids(spec.comodel, operator))
        if spec.comodel:
            operators = _RELATIONAL_OPERATORS
            if spec.type == "many2one":
                operators = (*operators, "<", ">=")
            comodel = self.schema.models.get(spec.comodel)
            if comodel is not None and comodel.hierarchical:
                operators = (*operators, *_HIERARCHY_OPERATORS)
            if comodel is None:
                operators = tuple(
                    op for op in operators if op not in ("any", "not any")
                )
            operator = choose(operators)
            if operator in ("any", "not any"):
                if depth <= 0:
                    return None
                subnode = self.node(spec.comodel, min(depth - 1, 2))
                return Leaf(
                    spec.name,
                    operator,
                    SubDomain(
                        spec.comodel, self._naming_every_active(spec.comodel, subnode)
                    ),
                )
            if operator in ("ilike", "not ilike"):
                return Leaf(spec.name, operator, rng.choice(_LIKE_PATTERNS))
            return Leaf(spec.name, operator, self._ids(spec.comodel, operator))
        operator = choose(_SCALAR_OPERATORS[spec.type])
        if (
            spec.type in ("integer", "float", "boolean", "date", "datetime")
            and rng.random() < 0.1
            and not chosen
        ):
            operator = rng.choice(_PATTERN_OPERATORS)
        return Leaf(spec.name, operator, self._scalar_value(spec, operator))

    def _naming_every_active(self, model: str, node: Node) -> Node:
        rng = self.rng
        names = {spec.name for spec in self.schema.models[model].fields}
        if "active" not in names or rng.random() >= 0.4:
            return node
        every = rng.choice(
            (
                Leaf("active", "in", (True, False)),
                Nary("|", (Leaf("active", "=", True), Leaf("active", "=", False))),
                Leaf("active", "not in", ()),
            )
        )
        return Nary("&", (every, node)) if rng.random() < 0.7 else every

    def _ids(self, model: str, operator: str) -> typing.Any:
        rng = self.rng
        refs: list[Ref | str] = list(_refs(self.dataset, model))
        if rng.random() < 0.05:
            refs = [*refs, Ref(model, MISSING)]
        if operator in ("=", "!=", "in", "not in", *_HIERARCHY_OPERATORS) and (
            rng.random() < 0.05
        ):
            refs = [*refs, rng.choice(("a", "ab", "zz", "é"))]
        if operator in ("in", "not in"):
            chosen: list[typing.Any] = rng.sample(
                refs, rng.randint(0, min(3, len(refs)))
            )
            if rng.random() < 0.4:
                chosen.append(False)
            return tuple(chosen)
        if not refs or (operator in ("=", "!=") and rng.random() < 0.25):
            return False
        return rng.choice(refs)

    def _scalar_value(self, spec: FieldSpec, operator: str) -> typing.Any:
        rng = self.rng
        if operator in ("in", "not in"):
            values = [self._comparand(spec) for _ in range(rng.randint(0, 3))]
            if rng.random() < 0.4:
                values.append(rng.choice((False, None)))
            return tuple(values)
        if operator.endswith("like"):
            return rng.choice(_LIKE_PATTERNS)
        if operator.endswith("=~"):
            return rng.choice(_REGEXES)
        if rng.random() < 0.12:
            return rng.choice((False, False, None))
        return self._comparand(spec)

    def _comparand(self, spec: FieldSpec) -> typing.Any:
        rng = self.rng
        held = self._held_values(spec)
        if held and rng.random() < 0.7:
            return rng.choice(held)
        foreign = _FOREIGN.get(spec.type)
        if foreign and rng.random() < 0.05:
            return rng.choice(foreign)
        if spec.type in ("char", "text") and spec.size and rng.random() < 0.5:
            return rng.choice(("abcdefg", "ABCDEFGH", "abcdef", "ABCDE"))
        if spec.type == "integer" and rng.random() < 0.2:
            return rng.choice((3, -2, 100))
        return rng.choice(_scalars(spec))

    def _held_values(self, spec: FieldSpec) -> list[typing.Any]:
        if spec.container and not spec.part:
            key = spec.name.split(".", 1)[1]
            held = []
            for rows in self.dataset.values():
                for row in rows:
                    value = (row or {}).get(spec.container)
                    if isinstance(value, dict) and value.get(key) not in (None, False):
                        item = value[key]
                        held += item if isinstance(item, list) else [item]
            return held
        if spec.source is None:
            return []
        model_name, fname = spec.source
        held = []
        for row in self.dataset.get(model_name, ()):
            value = (row or {}).get(fname)
            if isinstance(value, Translated):
                held += [text for text in (value.en_US, value.fr_FR) if text]
            elif value not in (None, False):
                held.append(value)
        return held


def to_list(node: Node, resolve: Callable[[Ref], typing.Any]) -> list[typing.Any]:
    if isinstance(node, Nary):
        children = [to_list(child, resolve) for child in node.children]
        return [node.operator] * (len(children) - 1) + [
            term for child in children for term in child
        ]
    if isinstance(node, Not):
        return ["!", *to_list(node.child, resolve)]
    return [(node.path, node.operator, _resolve_value(node.value, resolve))]


def _resolve_value(
    value: typing.Any, resolve: Callable[[Ref], typing.Any]
) -> typing.Any:
    if isinstance(value, Ref):
        return resolve(value)
    if isinstance(value, SubDomain):
        return to_list(value.node, resolve)
    if isinstance(value, tuple):
        return [_resolve_value(item, resolve) for item in value]
    return value


def leaves(node: Node) -> Iterator[Leaf]:
    if isinstance(node, Leaf):
        yield node
    elif isinstance(node, Not):
        yield from leaves(node.child)
    else:
        for child in node.children:
            yield from leaves(child)


def referenced(node: Node) -> set[Ref]:
    found: set[Ref] = set()

    def walk(value: typing.Any) -> None:
        if isinstance(value, Ref):
            found.add(value)
        elif isinstance(value, SubDomain):
            found.update(referenced(value.node))
        elif isinstance(value, tuple):
            for item in value:
                walk(item)

    for leaf in leaves(node):
        walk(leaf.value)
    return found


_EXPECTED_ERRORS = (
    ValueError,
    TypeError,
    KeyError,
    AssertionError,
    NotImplementedError,
)


def _reading(read: Callable[[], Sequence[int]], loaded: Loaded, model: str) -> Outcome:
    cr = loaded.env.cr
    isolated = nullcontext() if isinstance(cr, InMemoryCursor) else cr.savepoint(False)
    try:
        with isolated:
            return loaded.outcome(model, read())
    except _EXPECTED_ERRORS as error:
        return Raised(type(error).__name__)
    except Exception as error:
        if type(error).__module__.startswith(("psycopg", "odoo.exceptions")):
            return Raised(type(error).__name__)
        raise


@dataclass(frozen=True)
class Rule:
    model: str
    kind: str
    node: Node

    def text(self, resolve: Callable[[Ref], typing.Any]) -> str:
        return repr(to_list(self.node, resolve))


@dataclass(frozen=True)
class Viewpoint:
    lang: str = "en_US"
    tz: str | None = None
    rules: tuple[Rule, ...] | None = None

    def render(self, resolve: Callable[[Ref], typing.Any]) -> str:
        head = f"lang {self.lang}, tz {self.tz or 'unset'}"
        if self.rules is None:
            return f"{head}, as the superuser"
        texts = [
            f"\n    {rule.kind} on {rule.model}: {rule.text(resolve)}"
            for rule in self.rules
        ]
        return f"{head}, as a user holding{''.join(texts) or ' every record'}"


_RULE_TYPES = frozenset(
    ("char", "text", "integer", "float", "boolean", "selection", "many2one")
) | frozenset(("one2many", "many2many", "one2one"))


def draw_viewpoint(
    schema: Schema,
    dataset: Dataset,
    rng: random.Random,
    *,
    rules: bool,
    root: str,
) -> Viewpoint:
    lang = rng.choice(LANGS)
    tz = rng.choice((None, *TIMEZONES))
    if not rules:
        return Viewpoint(lang, tz)

    def accepts(model: str, path: str, operator: str) -> bool:
        _steps, _owner, spec = schema.resolve(model, path)
        return spec.type in _RULE_TYPES and not spec.container

    generator = DomainGenerator(schema, dataset, rng, accepts=accepts)
    drawn: list[Rule] = []
    if rng.random() < 0.85:
        drawn += [
            Rule(root, "permission", _rule_node(generator, root, rng))
            for _index in range(rng.choice((1, 1, 2)))
        ]
    if rng.random() < 0.3:
        drawn.append(Rule(root, "guard", _rule_node(generator, root, rng)))
    others = [name for name in schema.models if name != root]
    if rng.random() < 0.35:
        model = rng.choice(others)
        kind = rng.choice(("permission", "guard"))
        drawn.append(Rule(model, kind, generator.node(model, 1)))
    return Viewpoint(lang, tz, tuple(drawn))


def _rule_node(generator: DomainGenerator, model: str, rng: random.Random) -> Node:
    if "user_id" in {spec.name for spec in generator.schema.models[model].fields}:
        roll = rng.random()
        if roll < 0.2:
            return Leaf("user_id", "=", USER)
        if roll < 0.3:
            return Nary("|", (Leaf("user_id", "=", USER), generator.node(model, 1)))
    return generator.node(model, 1)


class Loaded:
    def __init__(
        self,
        env: Environment,
        schema: Schema,
        dataset: Dataset,
        *,
        active_test: bool = False,
        viewpoint: Viewpoint | None = None,
    ) -> None:
        viewpoint = viewpoint or Viewpoint()
        self.viewpoint = viewpoint
        self.active_test = active_test
        self.schema = schema
        self.env = env(context={**env.context, "active_test": False, "lang": "en_US"})
        self.ids: dict[Ref, int] = {}
        self._create_principals()
        for model_name in schema.creation_order:
            self._create(schema.models[model_name], dataset.get(model_name, []))
        self._translate(dataset)
        self.applied: tuple[Rule, ...] = ()
        if viewpoint.rules is not None:
            self.applied = self._grant(viewpoint.rules)
        self.env.flush_all()
        self.env.invalidate_all()
        context = {
            **env.context,
            "active_test": active_test,
            "lang": viewpoint.lang,
            **({"tz": viewpoint.tz} if viewpoint.tz else {}),
        }
        self.sudo_env = env(context=context)
        self.env = self.sudo_env
        if viewpoint.rules is not None:
            self.env = env(user=self.ids[ME], su=False, context=context)
        self.refs = {(ref.model, id_): ref for ref, id_ in self.ids.items()}
        self.readable = {
            model_name: self.env[model_name]
            .with_context(active_test=False)
            .search([])
            ._ids
            for model_name in schema.models
        }

    @property
    def as_user(self) -> bool:
        return self.viewpoint.rules is not None

    def _create_principals(self) -> None:
        users = self.env["res.users"].create(
            [
                {"name": "domain fuzz evaluator", "login": "domain_fuzz_evaluator"},
                {"name": "domain fuzz other", "login": "domain_fuzz_other"},
            ]
        )
        self.ids[ME], self.ids[OTHER] = users.ids

    def _create(self, model: ModelSpec, rows: Sequence[Row | None]) -> None:
        Model = self.env[model.name]
        self_referencing = any(spec.comodel == model.name for spec in model.writable())
        containers = {container.name for container in model.containers}
        pending: list[tuple[int, dict[str, typing.Any]]] = []
        for index, row in enumerate(rows):
            if row is None:
                continue
            vals = {
                fname: value
                if fname in model.definitions
                else self._properties(value)
                if fname in containers
                else self._column(value)
                for fname, value in row.items()
            }
            pending.append((index, vals))
            if self_referencing:
                self._create_batch(Model, pending)
                pending = []
        self._create_batch(Model, pending)

    def _create_batch(
        self, Model: BaseModel, pending: list[tuple[int, dict[str, typing.Any]]]
    ) -> None:
        if not pending:
            return
        records = Model.create([vals for _index, vals in pending])
        for (index, _vals), id_ in zip(pending, records._ids, strict=True):
            self.ids[Ref(Model._get_model_name(), index)] = id_

    def _translate(self, dataset: Dataset) -> None:
        for model_name, rows in dataset.items():
            for index, row in enumerate(rows):
                for fname, value in (row or {}).items():
                    if isinstance(value, Translated):
                        record = self.env[model_name].browse(
                            self.ids[Ref(model_name, index)]
                        )
                        record.with_context(lang="fr_FR")[fname] = value.fr_FR

    def _column(self, value: typing.Any) -> typing.Any:
        if isinstance(value, Ref):
            return self.ids[value]
        if isinstance(value, Translated):
            return value.en_US
        if value is None:
            return False
        if isinstance(value, list):
            return [Command.set([self.ids[ref] for ref in value])]
        return value

    def _properties(self, values: dict[str, typing.Any]) -> dict[str, typing.Any]:
        return {
            name: self.ids[value] if isinstance(value, Ref) else value
            for name, value in values.items()
        }

    def _grant(self, rules: Sequence[Rule]) -> tuple[Rule, ...]:
        env = self.env
        access = env["ir.access"]
        access.search([("model_id.model", "in", list(self.schema.models))]).write(
            {"active": False}
        )
        group = env["res.groups"].create({"name": "domain fuzz readers"})
        internal = env.ref("base.group_user", raise_if_not_found=False)
        env["res.users"].browse(self.ids[ME]).write(
            {
                "group_ids": [
                    Command.link(group.id),
                    *([Command.link(internal.id)] if internal else []),
                ]
            }
        )

        def row(model_name: str, kind: str, domain: str | bool) -> bool:
            values = {
                "name": f"domain fuzz {kind} on {model_name}",
                "model_id": env["ir.model"]._get(model_name).id,
                "group_id": group.id,
                "kind": kind,
                "operation": "r",
                "domain": domain,
                **({"guard_scope": "members"} if kind == "guard" else {}),
            }
            try:
                with env.cr.savepoint():
                    access.create(values)
                    env.flush_all()
            except Exception as error:
                if type(error).__module__.startswith(("psycopg", "odoo.exceptions")):
                    return False
                if isinstance(error, _EXPECTED_ERRORS):
                    return False
                raise
            return True

        applied = [
            rule
            for rule in rules
            if row(rule.model, rule.kind, rule.text(self._rule_value))
        ]
        permitted = {rule.model for rule in applied if rule.kind == "permission"}
        for model_name in (*self.schema.models, PRINCIPALS, "res.partner"):
            if model_name not in permitted:
                row(model_name, "permission", False)
        return tuple(applied)

    def _rule_value(self, ref: Ref) -> typing.Any:
        return self.resolve(ref)

    def resolve(self, ref: Ref) -> int:
        if ref.index == MISSING:
            return 2**31 - 2
        return self.ids[ref]

    def domain(self, node: Node) -> list[typing.Any]:
        return to_list(node, self.resolve)

    def outcome(self, model: str, ids: Sequence[int]) -> frozenset[Ref]:
        return frozenset(self.refs[model, id_] for id_ in ids)

    def every_id(self, model: str) -> list[int]:
        return [id_ for ref, id_ in self.ids.items() if ref.model == model]

    def all_ids(self, model: str) -> list[int]:
        if self.as_user:
            return list(self.readable[model])
        return self.every_id(model)

    def universe(self, model: str) -> frozenset[Ref]:
        return self.outcome(model, self.all_ids(model))

    def keeps_active_only(self, model: str, node: Node) -> bool:
        active_name = self.env[model]._active_name
        return bool(
            self.active_test
            and active_name
            and not any(
                not isinstance(leaf.value, SubDomain) and leaf.path == active_name
                for leaf in leaves(node)
            )
        )

    def active(self, model: str) -> frozenset[Ref]:
        records = self.env[model].browse(self.all_ids(model))
        return self.outcome(model, records.filtered(records._active_name or "id").ids)

    def search(self, model: str, domain: list[typing.Any]) -> Outcome:
        return _reading(lambda: self.env[model].search(domain).ids, self, model)

    def search_as_superuser(self, model: str, domain: list[typing.Any]) -> Outcome:
        return _reading(lambda: self.sudo_env[model].search(domain).ids, self, model)

    def search_every_record(self, model: str, domain: list[typing.Any]) -> Outcome:
        Model = self.env[model]
        if self.active_test and Model._active_name:
            domain = ["&", (Model._active_name, "in", [True, False]), *domain]
        return self.search(model, domain)

    def relating(
        self, model: str, fname: str, corefs: frozenset[Ref]
    ) -> frozenset[Ref]:
        coids = {self.ids[ref] for ref in corefs}
        ids = self.all_ids(model)
        records = self.env[model].with_context(active_test=False).browse(ids)
        return self.outcome(
            model,
            [
                id_
                for id_, record in zip(ids, records, strict=True)
                if not coids.isdisjoint(record[fname]._ids)
            ],
        )

    def filtered(
        self, model: str, domain: list[typing.Any], *, active_only: bool
    ) -> Outcome:
        records = self.env[model].browse(self.all_ids(model))
        if not records:
            return ABSTAINED

        def read() -> Sequence[int]:
            matched = records.filtered_domain(domain)
            if active_only:
                matched = matched.filtered(records._active_name or "id")
            return matched.ids

        outcome = _reading(read, self, model)
        if self.as_user and outcome == Raised("AccessError"):
            return ABSTAINED
        return outcome

    def reached(self, model: str, node: Node) -> set[str] | None:
        found: set[str] = set()
        for leaf in leaves(node):
            _steps, _owner, spec = self.schema.resolve(model, leaf.path)
            found |= self.schema.reached(model, leaf.path)
            if spec.name == "display_name" or leaf.operator in _HIERARCHY_OPERATORS:
                return None
            if (spec.comodel or spec.name == "id") and (
                leaf.operator.endswith("ilike")
                or isinstance(leaf.value, str)
                or (
                    isinstance(leaf.value, tuple)
                    and any(isinstance(item, str) for item in leaf.value)
                )
            ):
                return None
            if isinstance(leaf.value, SubDomain):
                below = self.reached(leaf.value.model, leaf.value.node)
                if below is None:
                    return None
                found |= below | {leaf.value.model}
        return found


def composed(
    node: Node, universe: frozenset[Ref], leaf_outcome: Callable[[Leaf], Outcome]
) -> Outcome:
    if isinstance(node, Leaf):
        outcome = leaf_outcome(node)
        return ABSTAINED if isinstance(outcome, Raised) else outcome
    if isinstance(node, Not):
        inner = composed(node.child, universe, leaf_outcome)
        return ABSTAINED if isinstance(inner, Raised) else universe - inner
    results = [composed(child, universe, leaf_outcome) for child in node.children]
    if any(isinstance(result, Raised) for result in results):
        return ABSTAINED
    sets = typing.cast("list[frozenset[Ref]]", results)
    if node.operator == "&":
        return frozenset.intersection(*sets)
    return frozenset.union(*sets)


Evaluate = Callable[[str, Node], dict[str, Outcome]]


def _related_any_chain(
    loaded: Loaded, model: str, related: str, value: SubDomain
) -> Node | None:
    *hops, last = related.split(".")
    owners = [model]
    for hop in hops:
        comodel = loaded.env[owners[-1]]._fields[hop].comodel_name
        if comodel is None:
            return None
        owners.append(comodel)
    node: Node = Leaf(last, "any", value)
    for hop, owner in zip(reversed(hops), reversed(owners[1:]), strict=True):
        node = Leaf(hop, "any", SubDomain(owner, node))
    return node


def evaluators(loaded: Loaded, *, prefix: str = "") -> Evaluate:
    leaf_cache: dict[tuple[str, str], Outcome] = {}
    ruled = {rule.model for rule in loaded.applied}

    def any_outcome(model: str, leaf: Leaf) -> Outcome | None:
        value = leaf.value
        if not isinstance(value, SubDomain) or leaf.operator not in ("any", "not any"):
            return None
        field = loaded.env[model]._fields.get(leaf.path)
        if field is None:
            return None
        if not field.store:
            if not field.related or loaded.as_user:
                return None
            node = _related_any_chain(loaded, model, field.related, value)
            if node is None:
                return None
            chained = algebra(model, node)
            if isinstance(chained, Raised) or leaf.operator == "any":
                return chained
            return loaded.universe(model) - chained
        matched = algebra(value.model, value.node)
        if isinstance(matched, Raised):
            return matched
        if field.type != "many2one" and loaded.keeps_active_only(
            value.model, value.node
        ):
            matched &= loaded.active(value.model)
        found = loaded.relating(model, leaf.path, matched)
        return found if leaf.operator == "any" else loaded.universe(model) - found

    def algebra(model: str, node: Node) -> Outcome:
        def leaf_outcome(leaf: Leaf) -> Outcome:
            key = (model, repr(leaf))
            if key not in leaf_cache:
                outcome = any_outcome(model, leaf)
                if outcome is None:
                    outcome = loaded.search_every_record(model, loaded.domain(leaf))
                leaf_cache[key] = outcome
            return leaf_cache[key]

        return composed(node, loaded.universe(model), leaf_outcome)

    def evaluate(model: str, node: Node) -> dict[str, Outcome]:
        domain = loaded.domain(node)
        active_only = loaded.keeps_active_only(model, node)
        outcome = algebra(model, node)
        if active_only and isinstance(outcome, frozenset):
            outcome &= loaded.active(model)
        outcomes = {
            f"{prefix}search": loaded.search(model, domain),
            f"{prefix}filtered_domain": loaded.filtered(
                model, domain, active_only=active_only
            ),
            f"{prefix}composed": outcome,
        }
        if loaded.as_user:
            reached = loaded.reached(model, node)
            if reached is not None and not reached & ruled:
                found = loaded.search_as_superuser(model, domain)
                if isinstance(found, frozenset):
                    found &= loaded.universe(model)
                outcomes[f"{prefix}superuser search"] = found
        return outcomes

    return evaluate


World = Callable[[Dataset, Viewpoint], AbstractContextManager[tuple[Evaluate, Loaded]]]


def disagreement(outcomes: Mapping[str, Outcome]) -> tuple[str, str] | None:
    erring_alone = any(outcome is ABSTAINED for outcome in outcomes.values())
    names = list(outcomes)
    for i, first in enumerate(names):
        for second in names[i + 1 :]:
            left, right = outcomes[first], outcomes[second]
            if erring_alone and isinstance(left, Raised) != isinstance(right, Raised):
                continue
            if not _agree(left, right):
                return first, second
    return None


def _agree(left: Outcome, right: Outcome) -> bool:
    if left is ABSTAINED or right is ABSTAINED:
        return True
    if isinstance(left, Raised) or isinstance(right, Raised):
        return isinstance(left, Raised) and isinstance(right, Raised)
    return left == right


@dataclass
class Finding:
    seed: int
    model: str
    node: Node
    dataset: Dataset
    outcomes: dict[str, Outcome]
    pair: tuple[str, str]
    viewpoint: Viewpoint = field(default_factory=Viewpoint)
    shrunk: bool = False
    attempts: int = 0

    def render(self) -> str:
        lines = [
            f"seed {self.seed}: {self.pair[0]} != {self.pair[1]}"
            + (f" (shrunk in {self.attempts} attempts)" if self.shrunk else ""),
            f"  domain on {self.model}: {to_list(self.node, lambda ref: ref)!r}",
            f"  evaluated in {self.viewpoint.render(lambda ref: ref)}",
        ]
        for name, outcome in self.outcomes.items():
            shown = sorted(outcome) if isinstance(outcome, frozenset) else outcome
            lines.append(f"  {name}: {shown!r}")
        lines.append("  data:")
        for model_name, rows in self.dataset.items():
            for index, row in enumerate(rows):
                if row is not None:
                    lines.append(f"    {Ref(model_name, index)!r}: {row!r}")
        return "\n".join(lines)


@dataclass
class Campaign:
    schema: Schema
    roots: Sequence[str]
    world: World
    sizes: Callable[[random.Random], Mapping[str, int]]
    domains_per_seed: int = 100
    depth: int = field(default_factory=lambda: int(os.environ.get(DEPTH_VARIABLE) or 3))
    shrink_budget: int = 400
    max_shrunk: int = 6
    accepts: Callable[[str, str, str], bool] | None = None
    merges: bool = False
    viewpoints: Callable[[Schema, Dataset, random.Random], Viewpoint] | None = None
    checked: int = 0
    findings: list[Finding] = field(default_factory=list)

    def run(self, seeds: Sequence[int]) -> list[Finding]:
        for seed in seeds:
            self._run_seed(seed)
        shrunk: dict[str, Finding] = {}
        for finding in self.findings:
            if len(shrunk) >= self.max_shrunk:
                break
            minimal = self.shrink(finding)
            key = f"{minimal.model} {to_list(minimal.node, lambda ref: ref)!r}"
            shrunk.setdefault(key, minimal)
        _debug.logic(
            "domain_fuzz.campaign_done",
            roots=len(self.roots),
            seeds=len(seeds),
            checked=self.checked,
            findings=len(self.findings),
        )
        return list(shrunk.values())

    def describe(self, shrunk: Sequence[Finding]) -> str:
        cases = "\n\n".join(finding.render() for finding in shrunk)
        return (
            f"{len(self.findings)} of {self.checked} domains disagree; "
            f"minimal cases:\n{cases}"
        )

    def _run_seed(self, seed: int) -> None:
        rng = random.Random(seed)
        dataset = generate_dataset(self.schema, rng, self.sizes(rng))
        generator = DomainGenerator(
            self.schema, dataset, rng, accepts=self.accepts, merges=self.merges
        )
        roots = [root for root in self.roots if _refs(dataset, root)]
        viewpoint = (
            self.viewpoints(self.schema, dataset, rng)
            if self.viewpoints
            else Viewpoint()
        )
        with self.world(dataset, viewpoint) as (evaluate, _loaded):
            for _index in range(self.domains_per_seed):
                model = rng.choice(roots)
                node = generator.node(model, self.depth)
                outcomes = evaluate(model, node)
                self.checked += 1
                if (pair := disagreement(outcomes)) is not None:
                    self.findings.append(
                        Finding(seed, model, node, dataset, outcomes, pair, viewpoint)
                    )

    def _fails(
        self,
        model: str,
        node: Node,
        dataset: Dataset,
        pair: tuple[str, str],
        viewpoint: Viewpoint,
    ) -> dict[str, Outcome] | None:
        with self.world(dataset, viewpoint) as (evaluate, _loaded):
            outcomes = evaluate(model, node)
        if pair[0] not in outcomes or pair[1] not in outcomes:
            return None
        if not _agree(outcomes[pair[0]], outcomes[pair[1]]):
            return outcomes
        return None

    def shrink(self, finding: Finding) -> Finding:
        model, pair = finding.model, finding.pair
        node, dataset, outcomes = finding.node, finding.dataset, finding.outcomes
        viewpoint = finding.viewpoint
        attempts = 0
        progress = True
        while progress and attempts < self.shrink_budget:
            progress = False
            for candidate in _smaller_nodes(node):
                attempts += 1
                found = self._fails(model, candidate, dataset, pair, viewpoint)
                if found is not None:
                    node, outcomes, progress = candidate, found, True
                    break
                if attempts >= self.shrink_budget:
                    break
            if progress:
                continue
            for simpler in _simpler_viewpoints(viewpoint):
                attempts += 1
                found = self._fails(model, node, dataset, pair, simpler)
                if found is not None:
                    viewpoint, outcomes, progress = simpler, found, True
                    break
            if progress:
                continue
            keep = referenced(node)
            for rule in viewpoint.rules or ():
                keep |= referenced(rule.node)
            for smaller in _smaller_datasets(self.schema, dataset, keep, model):
                attempts += 1
                found = self._fails(model, node, smaller, pair, viewpoint)
                if found is not None:
                    dataset, outcomes, progress = smaller, found, True
                    break
                if attempts >= self.shrink_budget:
                    break
        return Finding(
            finding.seed,
            model,
            node,
            dataset,
            outcomes,
            pair,
            viewpoint,
            True,
            attempts,
        )


def _simpler_viewpoints(viewpoint: Viewpoint) -> Iterator[Viewpoint]:
    rules = viewpoint.rules
    for index in range(len(rules or ())):
        assert rules is not None
        yield dataclasses.replace(viewpoint, rules=rules[:index] + rules[index + 1 :])
    if viewpoint.tz is not None:
        yield dataclasses.replace(viewpoint, tz=None)
    if viewpoint.lang != "en_US":
        yield dataclasses.replace(viewpoint, lang="en_US")


def _smaller_nodes(node: Node) -> Iterator[Node]:
    if isinstance(node, Not):
        yield node.child
        for child in _smaller_nodes(node.child):
            yield Not(child)
    elif isinstance(node, Nary):
        yield from node.children
        if len(node.children) > 2:
            for i in range(len(node.children)):
                yield Nary(node.operator, node.children[:i] + node.children[i + 1 :])
        for i, child in enumerate(node.children):
            for smaller in _smaller_nodes(child):
                yield Nary(
                    node.operator,
                    node.children[:i] + (smaller,) + node.children[i + 1 :],
                )
    else:
        value = node.value
        if isinstance(value, SubDomain):
            for smaller in _smaller_nodes(value.node):
                yield Leaf(node.path, node.operator, SubDomain(value.model, smaller))
        elif isinstance(value, tuple):
            for i in range(len(value)):
                yield Leaf(node.path, node.operator, value[:i] + value[i + 1 :])


def _smaller_datasets(
    schema: Schema, dataset: Dataset, keep: set[Ref], root: str
) -> Iterator[Dataset]:
    for model_name in reversed(list(dataset)):
        for index, row in enumerate(dataset[model_name]):
            if row is not None and Ref(model_name, index) not in keep:
                smaller = _without(schema, dataset, Ref(model_name, index))
                if any(row is not None for row in smaller[root]):
                    yield smaller
    for model_name, rows in dataset.items():
        model = schema.models[model_name]
        for index, row in enumerate(rows):
            for fname, value in (row or {}).items():
                spec = model.find(fname)
                if spec is not None and spec.required:
                    continue
                if isinstance(value, Translated):
                    yield _with_value(dataset, model_name, index, fname, value.en_US)
                if isinstance(value, dict) and value:
                    for key in value:
                        rest = {k: v for k, v in value.items() if k != key}
                        yield _with_value(dataset, model_name, index, fname, rest)
                if isinstance(value, list) and len(value) > 1:
                    for i in range(len(value)):
                        yield _with_value(
                            dataset,
                            model_name,
                            index,
                            fname,
                            value[:i] + value[i + 1 :],
                        )
                else:
                    yield _with_value(dataset, model_name, index, fname, _UNSET)


def _with_value(
    dataset: Dataset, model_name: str, index: int, fname: str, value: typing.Any
) -> Dataset:
    rows = list(dataset[model_name])
    row = dict(typing.cast("Row", rows[index]))
    if value is _UNSET:
        del row[fname]
    else:
        row[fname] = value
    rows[index] = row
    return {**dataset, model_name: rows}


def _without(schema: Schema, dataset: Dataset, gone: Ref) -> Dataset:
    removed = {gone}
    changed = True
    while changed:
        changed = False
        for model_name, rows in dataset.items():
            model = schema.models[model_name]
            for index, row in enumerate(rows):
                ref = Ref(model_name, index)
                if row is None or ref in removed:
                    continue
                if any(
                    value in removed and model.get(fname).required
                    for fname, value in row.items()
                    if isinstance(value, Ref)
                ):
                    removed.add(ref)
                    changed = True
    result: Dataset = {}
    for model_name, rows in dataset.items():
        kept: list[Row | None] = []
        for index, row in enumerate(rows):
            if row is None or Ref(model_name, index) in removed:
                kept.append(None)
                continue
            new_row: Row = {}
            for fname, value in row.items():
                if isinstance(value, Ref) and value in removed:
                    continue
                if isinstance(value, list):
                    value = [
                        item
                        for item in value
                        if not (isinstance(item, Ref) and item in removed)
                    ]
                elif isinstance(value, dict):
                    value = {
                        k: v
                        for k, v in value.items()
                        if not (isinstance(v, Ref) and v in removed)
                    }
                new_row[fname] = value
            kept.append(new_row)
        result[model_name] = kept
    return result


def seeds_from_environment(default: Sequence[int]) -> list[int]:
    rounds = os.environ.get(ROUNDS_VARIABLE)
    if not rounds:
        return list(default)
    start = int(os.environ.get(SEED_VARIABLE, "0"))
    return list(range(start, start + int(rounds)))


def item_sizes(rng: random.Random) -> dict[str, int]:
    items = rng.randint(4, 10)
    return {
        "test_orm.domain.partner": 3,
        "test_orm.domain.tag": 3,
        "test_orm.domain.item": items,
        "test_orm.domain.line": rng.randint(items // 2, 3 * items),
        "test_orm.domain.detail": rng.randint(0, items),
    }


ITEM_MODELS = (
    "test_orm.domain.partner",
    "test_orm.domain.tag",
    "test_orm.domain.item",
    "test_orm.domain.line",
    "test_orm.domain.detail",
)
ITEM_ROOTS = (
    "test_orm.domain.item",
    "test_orm.domain.item",
    "test_orm.domain.item",
    "test_orm.domain.line",
    "test_orm.domain.detail",
    "test_orm.domain.partner",
    "test_orm.domain.tag",
)
