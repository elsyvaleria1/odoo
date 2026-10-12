import functools
import typing
from collections import deque
from collections.abc import Callable, Hashable, Iterable, Iterator, Mapping
from operator import attrgetter

from odoo.libs.collections import OrderedSet
from odoo.libs.debug_log import DebugLog
from odoo.models import BaseModel

from ..fields import Field
from ..models.anchors import (
    Anchor,
    anchor_path_error,
    collect_anchors,
    infer_company_variant,
)
from ..models.field_classes import (
    FIELD_CLASS_HOOKS,
    field_access_classes,
    model_field_classes,
)
from ..models.mixins.access import AccessMixin
from ..models.verbs import Verb, collect_verbs
from ._registry_stubs import _RegistryStubs

if typing.TYPE_CHECKING:
    from .environment import Environment
else:
    Environment = typing.Any

_debug = DebugLog(__name__)

_CASCADE_PATH_MAX_MODELS = 4


def index_model_names_by_inheritance_root(
    models: Mapping[str, type[BaseModel]],
) -> dict[str, tuple[str, ...]]:
    by_root: dict[str, list[str]] = {}
    for name, model_cls in models.items():
        root = model_cls._table_inheritance_root
        if root and not model_cls._abstract:
            by_root.setdefault(root, []).append(name)
    return {root: tuple(names) for root, names in by_root.items()}


class _RegistryModelsMixin(_RegistryStubs):
    __slots__ = ()

    models: dict[str, type[BaseModel]]
    if typing.TYPE_CHECKING:

        @property
        def fields_by_comodel(self) -> dict[str, tuple[Field[typing.Any], ...]]: ...

    def _init_models_container(self) -> None:
        self.models = {}

    def __len__(self) -> int:
        return len(self.models)

    def __iter__(self) -> Iterator[str]:
        return iter(self.models)

    def __getitem__(self, model_name: str) -> type[BaseModel]:
        return self.models[model_name]

    def __setitem__(self, model_name: str, model: type[BaseModel]) -> None:
        self.models[model_name] = model

    def __delitem__(self, model_name: str) -> None:
        del self.models[model_name]
        _debug.lifecycle("registry.model_removed", model=model_name)
        for Model in self.models.values():
            Model._inherit_children.discard(model_name)

    @functools.cached_property
    def models_by_table(self) -> dict[str, type[BaseModel]]:
        by_table: dict[str, type[BaseModel]] = {}
        for model_cls in self.models.values():
            table = getattr(model_cls, "_table", None)
            if not table:
                continue
            incumbent = by_table.get(table)
            if incumbent is None or model_cls._name in self._get_ancestors(incumbent):
                by_table[table] = model_cls
        _debug.perf.count(
            "registry.models_by_table_built",
            models=len(self.models),
            tables=len(by_table),
        )
        return by_table

    @functools.cached_property
    def model_verbs(self) -> dict[str, dict[str, Verb]]:
        return {
            name: verbs
            for name, model_cls in self.models.items()
            if not model_cls._abstract and (verbs := collect_verbs(model_cls))
        }

    def bind_field_access_classes(self, env: Environment) -> None:
        bound = 0
        defaults = {name: vars(AccessMixin)[name] for name in FIELD_CLASS_HOOKS}
        for name, model_cls in self.models.items():
            said = model_field_classes(env[name], defaults)
            binder = functools.partial(field_access_classes, said)
            for field in model_cls._fields.values():
                field._access_binder = binder
                field.access_classes = binder(field)
                bound += field.access_classes is not None
        _debug.pipeline("registry.field_access_classes_bound", fields=bound)

    @functools.cached_property
    def model_anchors(self) -> dict[str, dict[str, Anchor]]:
        result: dict[str, dict[str, Anchor]] = {}
        errors = []
        for name, model_cls in self.models.items():
            anchors = collect_anchors(model_cls)
            for key, anchor in list(anchors.items()):
                if error := anchor_path_error(model_cls, key, anchor, self.models):
                    if model_cls._abstract:
                        del anchors[key]
                        continue
                    errors.append(f"{name}: anchor {key!r} ({anchor.path}): {error}")
                    continue
                anchors[key] = infer_company_variant(model_cls, anchor, self.models)
            if anchors:
                result[name] = anchors
        if errors:
            raise TypeError("Invalid access anchors:\n" + "\n".join(errors))
        return result

    @functools.cached_property
    def moving_anchor_fields(self) -> dict[str, dict[str, frozenset[str]]]:
        result: dict[str, dict[str, frozenset[str]]] = {}
        for name, anchors in self.model_anchors.items():
            fields = self.models[name]._fields
            moving: dict[str, frozenset[str]] = {}
            for anchor in anchors.values():
                if anchor.kind == "creator" or anchor.path == "id":
                    continue
                fname = anchor.path.split(".", 1)[0]
                field = fields.get(fname)
                triggers = {fname}
                if field is not None and field.compute:
                    triggers.update(
                        dep.split(".", 1)[0]
                        for dep in self.field_depends.get(field, ())
                    )
                moving[fname] = frozenset(triggers)
            if moving:
                result[name] = moving
        return result

    @functools.cached_property
    def verb_transitions(self) -> dict[str, dict[str, tuple[tuple[str, Verb], ...]]]:
        transitions: dict[str, dict[str, list[tuple[str, Verb]]]] = {}
        for model_name, verbs in self.model_verbs.items():
            for name, verb in verbs.items():
                if verb.transition is not None:
                    transitions.setdefault(model_name, {}).setdefault(
                        verb.transition[0], []
                    ).append((name, verb))
        return {
            model_name: {fname: tuple(pairs) for fname, pairs in fields.items()}
            for model_name, fields in transitions.items()
        }

    @functools.cached_property
    @typing.override
    def model_names_by_inheritance_root(self) -> dict[str, tuple[str, ...]]:
        return index_model_names_by_inheritance_root(self.models)

    @functools.cached_property
    def cascades_into_inheritance_trees(self) -> dict[str, tuple[tuple[str, str], ...]]:
        referrers: dict[str, list[tuple[str, str]]] = {}
        for root_table, names in self.model_names_by_inheritance_root.items():
            root_fields: Mapping[str, Field[typing.Any]] = next(
                (
                    self.models[name]._fields
                    for name in names
                    if self.models[name]._table == root_table
                ),
                {},
            )
            for name in names:
                model_cls = self.models[name]
                for field in model_cls._fields.values():
                    if (
                        field.is_many2one
                        and field.store
                        and field.column_type
                        and field.ondelete == "cascade"
                        and field.comodel_name
                        and (
                            model_cls._table == root_table
                            or field.name not in root_fields
                        )
                    ):
                        referrers.setdefault(field.comodel_name, []).append(
                            (name, field.name)
                        )
        self._extend_cascades_through_plain_models(referrers)
        return {comodel: tuple(sorted(pairs)) for comodel, pairs in referrers.items()}

    def _extend_cascades_through_plain_models(
        self, referrers: dict[str, list[tuple[str, str]]]
    ) -> None:
        in_trees = {
            name
            for names in self.model_names_by_inheritance_root.values()
            for name in names
        }
        frontier: list[tuple[str, str, str, tuple[str, ...]]] = [
            (comodel, leaf, path, (comodel,))
            for comodel, pairs in referrers.items()
            for leaf, path in pairs
        ]
        while frontier:
            comodel, leaf, path, trail = frontier.pop()
            model_cls = self.models.get(comodel)
            if (
                model_cls is None
                or comodel in in_trees
                or model_cls._abstract
                or len(trail) > _CASCADE_PATH_MAX_MODELS
            ):
                continue
            for field in model_cls._fields.values():
                if (
                    field.is_many2one
                    and field.store
                    and field.column_type
                    and field.ondelete == "cascade"
                    and field.comodel_name
                    and field.comodel_name not in trail
                ):
                    longer = f"{path}.{field.name}"
                    referrers.setdefault(field.comodel_name, []).append((leaf, longer))
                    frontier.append(
                        (field.comodel_name, leaf, longer, (*trail, field.comodel_name))
                    )

    @functools.cached_property
    def _prefetch_fields_by_model(
        self,
    ) -> dict[tuple[str, typing.Any], tuple[Field[typing.Any], ...]]:
        return {}

    def prefetch_fields(
        self, model_name: str, prefetch: typing.Any = True
    ) -> tuple[Field[typing.Any], ...]:
        key = (model_name, prefetch)
        try:
            return self._prefetch_fields_by_model[key]
        except KeyError:
            fields = tuple(
                field
                for field in self.models[model_name]._fields.values()
                if field.prefetch == prefetch
            )
            self._prefetch_fields_by_model[key] = fields
            return fields

    def _get_fields_memos(self) -> dict[Hashable, typing.Any]:
        by_comodel = self.fields_by_comodel
        memo = vars(self).get("_fields_memos")
        if memo is None or memo[0] is not by_comodel:
            memo = (by_comodel, {})
            vars(self)["_fields_memos"] = memo
        return memo[1]

    def get_or_create_fields_memo[T](
        self, key: Hashable, factory: Callable[[], T]
    ) -> T:
        memos = self._get_fields_memos()
        try:
            memo: T = memos[key]
            return memo
        except KeyError:
            value = memos[key] = factory()
            return value

    def discard_class_memo(self, key: str) -> None:
        for model_cls in self.models.values():
            if memos := model_cls.__dict__.get("_class_memos__"):
                memos.pop(key, None)

    def stored_x2many_fields_into(
        self, comodel_name: str
    ) -> tuple[Field[typing.Any], ...]:
        memos = self._get_fields_memos()
        key = ("stored_x2many_into", comodel_name)
        try:
            memo: tuple[Field[typing.Any], ...] = memos[key]
            return memo
        except KeyError:
            fields = memos[key] = tuple(
                field
                for field in self.fields_by_comodel.get(comodel_name, ())
                if field.is_x2many and field.store
            )
            return fields

    @functools.cached_property
    def _depends_flush_fields_by_model(
        self,
    ) -> dict[str, tuple[Field[typing.Any], ...]]:
        return {}

    def depends_flush_fields(self, model: BaseModel) -> tuple[Field[typing.Any], ...]:
        try:
            return self._depends_flush_fields_by_model[model._get_model_name()]
        except KeyError:
            seen, closure = model._get_depends_closure()
            fields = tuple(closure)
            self._depends_flush_fields_by_model[model._get_model_name()] = fields
            _debug.logic(
                "registry.depends_flush_fields_built",
                model=model._name,
                models=len(seen),
                fields=len(fields),
            )
            return fields

    @functools.cached_property
    def _paths_in_database(self) -> set[tuple[str, str]]:
        return set()

    def _get_ancestors(self, model_cls: type[BaseModel]) -> set[str]:
        seen: set[str] = set()
        queue = deque(getattr(model_cls, "_inherit", ()) or ())
        while queue:
            name = queue.popleft()
            if name in seen:
                continue
            seen.add(name)
            parent = self.models.get(name)
            if parent is not None:
                queue.extend(getattr(parent, "_inherit", ()) or ())
        return seen

    def get_descendants(
        self,
        model_names: Iterable[str],
        *kinds: typing.Literal["_inherit", "_inherits"],
    ) -> OrderedSet[str]:
        if not all(kind in ("_inherit", "_inherits") for kind in kinds):
            raise ValueError(
                f"descendants: kinds must be '_inherit'/'_inherits', got {kinds!r}"
            )
        funcs = [attrgetter(kind + "_children") for kind in kinds]

        models: OrderedSet[str] = OrderedSet()
        queue = deque(model_names)
        while queue:
            model = self.models.get(queue.popleft())
            if model is None or model._name in models:
                continue
            models.add(model._get_model_name())
            for func in funcs:
                queue.extend(func(model))
        return models
