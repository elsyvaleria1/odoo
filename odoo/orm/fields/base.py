import builtins
import collections
import functools
import itertools
import logging
import typing
from collections.abc import (
    Callable,
    Collection,
    Iterable,
    Iterator,
    Mapping,
    MutableMapping,
    Sequence,
)
from operator import attrgetter

from odoo.libs.accel import batch_cache_get as _batch_cache_get
from odoo.libs.accel import to_prefetch_ids as _to_prefetch_ids
from odoo.libs.collections import ReadonlyDict, frozendict
from odoo.libs.debug_log import DebugLog
from odoo.libs.func import reset_cached_properties
from odoo.libs.iteration import PENDING, SENTINEL, Sentinel

from .._recordset import get_base_model, is_model_class
from ..primitives import PREFETCH_MAX, NewId
from . import (
    _field_cache_miss as _cache_miss,
)
from . import (
    _field_compute as _compute,
)
from . import (
    _field_ddl as _ddl,
)
from . import (
    _field_related as _related,
)
from . import (
    _field_setup as _setup,
)
from ._field_compute import call_hook
from ._field_convert import _FieldConvertMixin
from ._field_description import _FieldDescriptionMixin
from ._field_metadata import _FieldMetadataMixin
from ._field_setup import COMPANY_DEPENDENT_FIELDS, resolve_mro
from ._field_sql import _FieldSqlMixin

if typing.TYPE_CHECKING:
    from types import NotImplementedType

    from .._typing import (
        BaseModel,
        ContextType,
        DomainType,
        ModelClass,
        ModelLike,
        ModelType,
        Self,
    )
    from ..models.field_classes import FieldAccessClasses
    from ..primitives import IdType
    from ..runtime import Environment, Registry

    M = typing.TypeVar("M", bound=BaseModel)


__all__ = ["COMPANY_DEPENDENT_FIELDS", "Field", "call_hook", "resolve_mro"]

_NO_ARGS: Mapping[str, typing.Any] = ReadonlyDict({})


def _get_recordset_like(records: BaseModel, ids: Iterable[IdType]) -> BaseModel:
    rs = object.__new__(records.__class__)
    rs.env = records.env
    rs._ids = tuple(ids)
    rs._prefetch_ids = records._prefetch_ids
    return rs


_logger = logging.getLogger("odoo.fields")

BOOLEAN_ATTRIBUTES = (
    "store",
    "precompute",
    "copy",
    "recursive",
    "compute_sudo",
    "related_sudo",
    "required",
    "readonly",
    "export_string_translation",
)
_debug = DebugLog(__name__)


def _prepare_fast_get(
    cache_to_record: Callable[[Field[typing.Any], typing.Any, BaseModel], typing.Any]
    | None = None,
    guarded_cache_to_record: (
        Callable[[Field[typing.Any], typing.Any, BaseModel], typing.Any] | None
    ) = None,
) -> Callable[..., typing.Any]:
    _PENDING = PENDING
    guarded_to_record = guarded_cache_to_record or cache_to_record

    def __get__(
        self: Field[typing.Any], record: BaseModel | None, owner: type | None = None
    ) -> typing.Any:
        if record is None:
            return self
        if self._get_guarded:
            if self.access_classes is not None:
                self.check_read_access(record)
            ids = record._ids
            if len(ids) != 1:
                return self._get_not_singleton(record, owner)
            if self.is_stored_computed:
                self.recompute_where_scheduled(record)
            to_record = guarded_to_record
        else:
            ids = record._ids
            if len(ids) != 1:
                return self._get_not_singleton(record, owner)
            to_record = cache_to_record
        env = record.env
        try:
            value = env.__dict__["_field_cache_memo"][self][ids[0]]
        except KeyError:
            pass
        else:
            if value is not _PENDING:
                if to_record is None:
                    return self.convert_to_record(value, record)
                return to_record(self, value, record)
        return self._get_uncached(record, env, ids[0])

    return __get__


def _none_is_false(
    field: Field[typing.Any], value: typing.Any, record: BaseModel
) -> typing.Any:
    return False if value is None else value


def _prepare_inline_get(
    falsy: typing.Any,
    guarded_cache_to_record: (
        Callable[[Field[typing.Any], typing.Any, BaseModel], typing.Any] | None
    ) = None,
) -> Callable[..., typing.Any]:
    _PENDING = PENDING

    if falsy is False:
        guarded_get = _prepare_fast_get(
            _none_is_false, guarded_cache_to_record or _none_is_false
        )

        def __get__(
            self: Field[typing.Any], record: BaseModel | None, owner: type | None = None
        ) -> typing.Any:
            if record is None or self._get_guarded:
                return guarded_get(self, record, owner)
            ids = record._ids
            if len(ids) != 1:
                return self._get_not_singleton(record, owner)
            env = record.env
            try:
                value = env.__dict__["_field_cache_memo"][self][ids[0]]
            except KeyError:
                return self._get_uncached(record, env, ids[0])
            if value is _PENDING:
                return self._get_uncached(record, env, ids[0])
            return False if value is None else value

        return __get__

    def falsy_is(
        field: Field[typing.Any], value: typing.Any, record: BaseModel
    ) -> typing.Any:
        return value or falsy

    guarded_numeric_get = _prepare_fast_get(
        falsy_is, guarded_cache_to_record or falsy_is
    )

    def numeric_get(
        self: Field[typing.Any], record: BaseModel | None, owner: type | None = None
    ) -> typing.Any:
        if record is None or self._get_guarded:
            return guarded_numeric_get(self, record, owner)
        ids = record._ids
        if len(ids) != 1:
            return self._get_not_singleton(record, owner)
        env = record.env
        try:
            value = env.__dict__["_field_cache_memo"][self][ids[0]]
        except KeyError:
            return self._get_uncached(record, env, ids[0])
        if value is _PENDING:
            return self._get_uncached(record, env, ids[0])
        return value or falsy

    return numeric_get


_global_seq = itertools.count()


class Field[T](
    _FieldDescriptionMixin,
    _FieldConvertMixin[T],
    _FieldSqlMixin,
    _FieldMetadataMixin,
):
    type: str

    relational: bool = False
    is_text: bool = False
    falsy_value: T | None = None

    is_x2many: bool = False

    is_temporal: bool = False

    is_many2one: bool = False
    is_one2one: bool = False

    cache_is_record_value: bool = False

    cache_truthiness_matches: bool = False

    cache_is_orderable: bool = False

    cache_is_read_value: bool = False

    column_value_is_cache: bool = False

    is_one2many: bool = False

    is_many2many: bool = False

    is_many2one_reference: bool = False

    is_boolean: bool = False

    is_integer: bool = False

    is_monetary: bool = False

    is_date: bool = False

    is_datetime: bool = False

    is_html: bool = False

    is_binary: bool = False

    is_properties: bool = False

    @property
    def is_delegating(self) -> bool:
        return False

    @property
    def is_attachment_backed(self) -> bool:
        return False

    write_sequence: int = 0

    _args__: Mapping[str, typing.Any] = _NO_ARGS
    _module: str | None = None
    _modules: tuple[str, ...] = ()
    _setup_done = True
    _sequence: int
    _base_fields__: tuple[Self, ...] = ()
    _extra_keys__: tuple[str, ...] = ()
    _reuse_key__: tuple[object, ...] | None = None
    _direct: bool = False
    _toplevel: bool = False

    inherited: bool = False
    joins_delegation: bool = False
    tree_siblings: tuple[Field[typing.Any], ...] = ()
    inherited_field: typing.Any = None

    comodel_name: str | None = None
    context: ContextType = frozendict({})

    delegate: bool = False

    attachment: bool = False

    index: str | None = None
    manual: bool = False
    copy: bool = True
    _depends: Collection[str] | None = None
    _depends_context: Collection[str] | None = None
    recursive: bool = False
    compute: str | Callable[[BaseModel], None] | None = None
    compute_sudo: bool = False
    precompute: bool = False
    inverse: str | Callable[[BaseModel], None] | None = None
    search: str | Callable[[BaseModel, str, typing.Any], DomainType] | None = None
    related: str | None = None
    default: Callable[[ModelLike], T] | T | None = None
    default_literal: typing.Any = None

    string: str | None = None
    export_string_translation: bool = True
    help: str | None = None
    readonly: bool = False
    required: bool = False
    classification: str | None = None
    write_classification: str | None = None
    discloses: str | None = None
    _access_binder: Callable[[Field[typing.Any]], FieldAccessClasses | None] | None = (
        None
    )

    @property  # type: ignore[explicit-override]  # mypy cannot mark a settable property override
    @typing.override
    def groups(self) -> str | None:
        return self.__dict__.get("groups")

    @groups.setter
    def groups(self, value: str | None) -> None:
        self.__dict__["groups"] = value
        self._rebind_access_classes()

    @groups.deleter
    def groups(self) -> None:
        self.__dict__.pop("groups", None)
        self._rebind_access_classes()

    @property  # type: ignore[explicit-override]  # mypy cannot mark a settable property override
    @typing.override
    def write_groups(self) -> str | Callable[[BaseModel], bool] | None:
        return self.__dict__.get("write_groups")

    @write_groups.setter
    def write_groups(self, value: str | Callable[[BaseModel], bool] | None) -> None:
        self.__dict__["write_groups"] = value
        self._rebind_access_classes()

    @write_groups.deleter
    def write_groups(self) -> None:
        self.__dict__.pop("write_groups", None)
        self._rebind_access_classes()

    @property  # type: ignore[explicit-override]  # mypy cannot mark a settable property override
    @typing.override
    def access_classes(self) -> FieldAccessClasses | None:
        return self.__dict__.get("access_classes")

    @access_classes.setter
    def access_classes(self, value: FieldAccessClasses | None) -> None:
        self.__dict__["access_classes"] = value
        self._refresh_get_guarded()

    @access_classes.deleter
    def access_classes(self) -> None:
        self.__dict__.pop("access_classes", None)
        self._refresh_get_guarded()

    _get_guarded: bool = True

    def _refresh_get_guarded(self) -> None:
        self._get_guarded = (
            not self._setup_done
            or self.access_classes is not None
            or self.is_stored_computed
            or callable(self.translate)
        )

    def _rebind_access_classes(self) -> None:
        binder = self.__dict__.get("_access_binder")
        if binder is not None:
            self.access_classes = binder(self)

    change_default = False

    related_field: typing.Any = None
    _related_names: tuple[str, ...] = ()
    _related_field_seq: tuple[Field[typing.Any], ...] = ()
    aggregator: str | None = None
    group_expand: (
        str | Callable[[ModelLike, typing.Any, DomainType], typing.Any] | None
    ) = None
    group_by_field: str | None = None
    order_by_field: str | None = None
    group_by_sql: str | None = None
    order_by_sql: str | None = None
    value_sql: str | None = None
    falsy_value_label: str | None = None
    prefetch: bool | str = True

    default_export_compatible: bool = False
    exportable: bool = True

    _by_type__: dict[str, builtins.type[Field[typing.Any]]] = {}
    _register_type: typing.ClassVar[bool] = True

    def __init__(self, string: str | Sentinel = SENTINEL, **kwargs: typing.Any) -> None:
        for key in BOOLEAN_ATTRIBUTES:
            value = kwargs.get(key, SENTINEL)
            if value is not SENTINEL and not isinstance(value, bool):
                raise TypeError(
                    f"{type(self).__name__}({key}={value!r}): {key} takes a bool"
                )
        kwargs["string"] = string
        self._sequence = next(_global_seq)
        self._args__ = ReadonlyDict(
            {key: val for key, val in kwargs.items() if val is not SENTINEL}
        )

    def _get_comodel_name(self) -> str:
        """Return the relation target once field setup has supplied it."""
        if self.comodel_name is None:
            raise TypeError(f"{self} has no comodel_name")
        return self.comodel_name

    @typing.override
    def __str__(self) -> str:
        if not self.name:
            return f"<{__name__}.{type(self).__name__}>"
        return f"{self.model_name}.{self.name}"

    @typing.override
    def __repr__(self) -> str:
        if not self.name:
            return repr(f"<{__name__}.{type(self).__name__}>")
        return repr(f"{self.model_name}.{self.name}")

    @typing.override
    def __init_subclass__(cls) -> None:
        super().__init_subclass__()
        if not hasattr(cls, "type"):
            return

        if cls.type and cls._register_type:
            taken = cls._by_type__.get(cls.type)
            if (
                taken is not None
                and "type" in cls.__dict__
                and not issubclass(cls, taken)
            ):
                raise TypeError(
                    f"field type {cls.type!r} is already registered by "
                    f"{taken.__module__}.{taken.__qualname__}; {cls.__module__}."
                    f"{cls.__qualname__} cannot claim it too. Set "
                    f"`_register_type = False` on the class that should not be "
                    f"reachable through Field._by_type__."
                )
            if taken is None:
                cls._by_type__[cls.type] = cls
                _debug.lifecycle(
                    "field.type_registered",
                    type=cls.type,
                    field_class=f"{cls.__module__}.{cls.__qualname__}",
                )

        related: list[tuple[str, str]] = []
        described: list[tuple[str, str]] = []
        for attr in dir(cls):
            if attr.startswith("_related_"):
                related.append((attr.removeprefix("_related_"), attr))
            elif attr.startswith("_description_"):
                described.append((attr.removeprefix("_description_"), attr))
        cls.related_attrs = tuple(related)
        cls.description_attrs = tuple(described)
        cls.description_props = dict(described)

    def __set_name__(self, owner: ModelClass, name: str) -> None:
        assert get_base_model() is None or is_model_class(owner)
        # Unregistered framework prototypes have no model name yet; registry
        # setup clones/binds these declarations before exposing model fields.
        self.model_name = owner._name  # type: ignore[assignment]
        self.name = name
        if getattr(owner, "pool", None) is None:
            self._module = owner._module
            owner._field_definitions.append(self)

        if not self._args__.get("related"):
            self._direct = True
        if self._direct or self._toplevel:
            self._setup_attrs__(owner, name)
            if self._toplevel:
                self.__dict__.pop("_args__", None)
                if not self.related:
                    self.__dict__.pop("_base_fields__", None)

    def _get_attrs(self, model_class: ModelClass, name: str) -> dict[str, typing.Any]:
        return _setup.get_attrs(self, model_class, name)

    def _setup_attrs__(self, model_class: ModelClass, name: str) -> None:
        attrs = self._get_attrs(model_class, name)

        extra_keys = tuple(key for key in attrs if not hasattr(self, key))
        if extra_keys:
            attrs["_extra_keys__"] = extra_keys

        self.__dict__.update(attrs)

        if not self.column_type or not self.fetched_with_row or self.manual:
            self.prefetch = False
        if _debug.logic.enabled and extra_keys:
            _debug.logic(
                "field.setup.extra_keys",
                model=self.model_name,
                field=name,
                type=self.type,
                extra_keys=list(extra_keys),
            )

        if not self.string and not self.related:
            self.string = (
                (name[:-4] if name.endswith("_ids") else name.removesuffix("_id"))
                .replace("_", " ")
                .title()
            )

        if self.default is not None and not callable(self.default):
            value = self.default
            self.default_literal = value
            self.default = lambda model: value
        else:
            self.default_literal = None

    def reset_setup(self) -> None:
        self._setup_done = False
        self._get_guarded = True

    def setup(self, model: BaseModel) -> None:
        if not self._setup_done:
            for key in self._extra_keys__:
                if not model._is_valid_field_parameter(self, key):
                    _debug.logic(
                        "field.setup.unknown_parameter",
                        model=self.model_name,
                        field=self.name,
                        parameter=key,
                    )
                    _logger.warning(
                        "Field %s: unknown parameter %r, if this is an actual"
                        " parameter you may want to override the method"
                        " _is_valid_field_parameter on the relevant model in order to"
                        " allow it",
                        self,
                        key,
                    )
            if self.related:
                self.setup_related(model)
            else:
                self.setup_nonrelated(model)
            self._check_stand_in_fields(model)

            self._setup_done = True
            reset_cached_properties(self)
            self._refresh_get_guarded()

    def setup_nonrelated(self, model: BaseModel) -> None:
        pass

    def _check_stand_in_fields(self, model: BaseModel) -> None:
        self._check_sql_hooks(model)
        for attribute in ("group_by_field", "order_by_field"):
            target_name = getattr(self, attribute)
            if target_name is None:
                continue
            target = model._fields.get(target_name)
            if target is None or target is self:
                raise ValueError(
                    f"Field {self}: {attribute}={target_name!r} names no other field "
                    f"of {model._name}"
                )
            if attribute == "group_by_field" and (
                target.comodel_name != self.comodel_name
                if self.relational
                else target.type != self.type
            ):
                raise ValueError(
                    f"Field {self}: group_by_field {target} groups other values "
                    f"than {self.type} {self.comodel_name or ''} does"
                )

    def _check_sql_hooks(self, model: BaseModel) -> None:
        for attribute, stand_in in (
            ("group_by_sql", "group_by_field"),
            ("order_by_sql", "order_by_field"),
            ("value_sql", None),
        ):
            method_name = getattr(self, attribute)
            if method_name is None:
                continue
            if not callable(getattr(type(model), method_name, None)):
                raise ValueError(
                    f"Field {self}: {attribute}={method_name!r} names no method of "
                    f"{model._name}"
                )
            if stand_in is not None and getattr(self, stand_in) is not None:
                raise ValueError(
                    f"Field {self}: {attribute} and {stand_in} cannot both be set"
                )

    def get_depends(self, model: BaseModel) -> tuple[Iterable[str], Iterable[str]]:
        return _setup.get_depends(self, model)

    def setup_related(self, model: BaseModel) -> None:
        _related.setup_related(self, model)

    def traverse_related(
        self, record: BaseModel
    ) -> tuple[BaseModel, Field[typing.Any]]:
        return _related.traverse_related(self, record)

    def _compute_related(self, records: BaseModel) -> None:
        _related.compute_related(self, records)

    def _process_related(self, value: typing.Any, env: Environment) -> typing.Any:
        return value

    def _inverse_related(self, records: BaseModel) -> None:
        _related.inverse_related(self, records)

    def _search_related(
        self, records: BaseModel, operator: str, value: typing.Any
    ) -> DomainType | NotImplementedType:
        return _related.search_related(self, records, operator, value)

    _related_comodel_name = property(attrgetter("comodel_name"))
    _related_string = property(attrgetter("string"))
    _related_help = property(attrgetter("help"))
    _related_groups = property(attrgetter("groups"))
    _related_write_groups = property(attrgetter("write_groups"))
    _related_classification = property(attrgetter("classification"))
    _related_write_classification = property(attrgetter("write_classification"))
    _related_aggregator = property(attrgetter("aggregator"))

    @functools.cached_property
    def is_stored_computed(self) -> bool:
        return bool(self.compute and self.store)

    def delegation_key_settled(self, env: Environment) -> bool:
        if not self.inherited:
            return True
        key = env[self.model_name]._fields[self._related_names[0]]
        core = env.core
        return not (core.has_pending_field(key) or core.get_dirty(key))

    @property
    def fetched_with_row(self) -> bool:
        if self.store:
            return True
        if not (self.inherited and self.compute_sudo and self.joins_delegation):
            return False
        target = self.related_field
        seq = self._related_field_seq
        key = seq[0] if seq else None
        return (
            target is not None
            and key is not None
            and bool(key.store)
            and bool(key.column_type)
            and bool(target.store)
            and bool(target.column_type)
            and not target.is_x2many
            and not target.is_binary
        )

    @property
    @typing.override
    def base_field(self) -> Self:
        return self.inherited_field.base_field if self.inherited_field else self

    @typing.override
    def get_company_dependent_fallback(self, records: ModelLike) -> typing.Any:
        assert self.company_dependent
        fallback = self._get_company_dependent_fallback_raw(records)
        _debug.logic(
            "field.company_dependent.fallback",
            model=self.model_name,
            field=self.name,
            company=records.env.company.id,
            has_fallback=fallback is not None and fallback is not False,
        )
        fallback = self.convert_to_cache(fallback, records, validate=False)
        return self.convert_to_record(fallback, records)

    def resolve_depends(
        self, registry: Registry
    ) -> Iterator[tuple[Field[typing.Any], ...]]:
        return _setup.resolve_depends(self, registry)

    _description_name = property(attrgetter("name"))
    _description_type = property(attrgetter("type"))
    _description_store = property(attrgetter("store"))
    _description_manual = property(attrgetter("manual"))
    _description_related = property(attrgetter("related"))
    _description_company_dependent = property(attrgetter("company_dependent"))
    _description_readonly = property(attrgetter("readonly"))
    _description_required = property(attrgetter("required"))
    _description_groups = property(attrgetter("groups"))
    _description_change_default = property(attrgetter("change_default"))
    _description_default_export_compatible = property(
        attrgetter("default_export_compatible")
    )
    _description_exportable = property(attrgetter("exportable"))

    def update_db(
        self, model: ModelLike, columns: dict[str, dict[str, typing.Any]]
    ) -> bool:
        return _ddl.update_db(self, model, columns)

    def update_db_column(self, model: ModelLike, column: dict[str, typing.Any]) -> None:
        _ddl.update_db_column(self, model, column)

    def _convert_db_column(
        self, model: ModelLike, column: dict[str, typing.Any]
    ) -> None:
        _ddl.convert_db_column(self, model, column)

    def update_db_notnull(
        self, model: ModelLike, column: dict[str, typing.Any]
    ) -> None:
        _ddl.update_db_notnull(self, model, column)

    def update_db_related(self, model: ModelLike) -> None:
        _ddl.update_db_related(self, model)

    def read(self, records: BaseModel) -> None:
        if not self.column_type:
            raise NotImplementedError(f"Method read() undefined on {self}")

    def create(self, record_values: Sequence[tuple[BaseModel, typing.Any]]) -> None:
        for record, value in record_values:
            self.mark_dirty(record, value)

    def mark_dirty(self, records: BaseModel, value: typing.Any) -> None:
        records, cache_value = self._mark_dirty_prologue(records, value)
        if not records:
            if _debug.logic.enabled:
                _debug.logic(
                    "field.mark_dirty.unchanged",
                    model=self.model_name,
                    field=self.name,
                )
            return

        self._update_cache(records, cache_value, dirty=True)

    def _mark_dirty_prologue(
        self, records: BaseModel, value: typing.Any
    ) -> tuple[BaseModel, typing.Any]:
        records.env.remove_to_compute(self, records)

        cache_value = self.convert_to_cache(value, records)
        if cache_value is None:
            self._settle_pending_as_null(records)
        records = self._filter_not_equal(records, cache_value)
        return records, cache_value

    def _settle_pending_as_null(self, records: BaseModel) -> None:
        field_cache = self._get_cache(records.env)
        dirty = records.env.core.get_dirty(self)
        settled = [
            id_
            for id_ in records._ids
            if id_
            and field_cache.get(id_, SENTINEL) is PENDING
            and not (dirty and id_ in dirty)
        ]
        if settled:
            field_cache.update(dict.fromkeys(settled, None))

    @typing.override
    def _get_cache(self, env: Environment) -> MutableMapping[IdType, typing.Any]:
        field_cache = env._field_cache_memo.get(self)
        if field_cache is not None:
            return field_cache
        field_cache = self._get_cache_impl(env)
        env._field_cache_memo[self] = field_cache
        return field_cache

    def _get_cache_impl(self, env: Environment) -> MutableMapping[IdType, typing.Any]:
        core = env.core
        if self._is_context_dependent(env):
            return core.get_context_data(self, env.get_cache_key(self))
        return core.get_field_data(self)

    def _peek_cache(self, env: Environment) -> Mapping[IdType, typing.Any] | None:
        core = env.core
        if self._is_context_dependent(env):
            return core.get_context_data_or_none(self, env.get_cache_key(self))
        return core.get_field_data_or_none(self)

    def _invalidate_cache(
        self,
        env: Environment,
        ids: Collection[IdType] | None = None,
        *,
        keep_dirty: bool = False,
    ) -> None:
        env.core.invalidate(self, ids, keep_dirty=keep_dirty)

    def _forget_draft_links(
        self,
        env: Environment,
        drafts: Collection[IdType],
        linked_ids: Collection[IdType],
    ) -> None:
        core = env.core
        caches = [cache for _key, cache in core.iter_context_caches(self)]
        if (data := core.get_field_data_or_none(self)) is not None:
            caches.append(data)
        for cache in caches:
            for draft in drafts:
                value = cache.get(draft, SENTINEL)
                if type(value) is tuple:
                    kept = tuple(id_ for id_ in value if id_ not in linked_ids)
                    if len(kept) < len(value):
                        cache[draft] = kept
                elif type(value) is NewId and value in linked_ids:
                    del cache[draft]
        if patches := core.get_patches(self):
            for draft in drafts:
                if ids := patches.get(draft):
                    if kept_ids := [id_ for id_ in ids if id_ not in linked_ids]:
                        patches[draft] = kept_ids
                    else:
                        del patches[draft]

    def _get_all_cache_ids(self, env: Environment) -> Mapping[IdType, typing.Any]:
        core = env.core
        if self._is_context_dependent(env):
            return core.get_context_cached_ids(self)
        return core.get_cached_ids(self)

    def _iter_cache_missing_ids(self, records: ModelLike) -> Iterator[IdType]:
        field_cache = self._get_cache(records.env)
        _pending = PENDING
        return (
            id_
            for id_ in records._ids
            if id_ not in field_cache or field_cache.get(id_) is _pending
        )

    def _has_cache_misses(self, records: ModelLike) -> bool:
        ids = records._ids
        field_cache = self._get_cache(records.env)
        if field_cache.__class__ is dict and ids.__class__ is tuple:
            return bool(_batch_cache_get(field_cache, ids, PENDING, None)[1])
        _pending = PENDING
        return any(
            id_ not in field_cache or field_cache.get(id_) is _pending for id_ in ids
        )

    def _filter_not_equal(
        self, records: ModelType, cache_value: typing.Any
    ) -> ModelType:
        field_cache = self._get_cache(records.env)
        ids = records._ids
        if len(ids) == 1:
            if field_cache.get(ids[0], SENTINEL) != cache_value:
                return records
            return records.browse()
        ids_to_update = tuple(
            record_id
            for record_id in ids
            if field_cache.get(record_id, SENTINEL) != cache_value
        )
        return records._spawn(records.env, ids_to_update, records._prefetch_ids)

    def _to_prefetch(self, record: ModelType) -> ModelType:
        field_cache = self._get_cache(record.env)
        prefetch_ids = record._prefetch_ids
        record_id = record.id
        if isinstance(prefetch_ids, tuple) and type(field_cache) is dict:
            scanned_ids = _to_prefetch_ids(
                record_id, prefetch_ids, field_cache, PREFETCH_MAX
            )
            if scanned_ids is not None:
                return record.browse(scanned_ids)
        kind = bool(record_id)
        ids_to_prefetch = [record_id]
        added = {record_id}
        for id_ in prefetch_ids:
            if len(ids_to_prefetch) >= PREFETCH_MAX:
                break
            if id_ not in field_cache and id_ not in added and bool(id_) == kind:
                ids_to_prefetch.append(id_)
                added.add(id_)
        return record.browse(ids_to_prefetch)

    def _clear_dead_pending(self, records: ModelLike) -> None:
        env = records.env
        field_cache = self._get_cache(env)
        if not field_cache:
            return
        core = env.core
        scheduled = core.get_pending_ids(self)
        dirty = core.get_dirty(self)
        cleared = 0
        for id_ in records._ids:
            if field_cache.get(id_) is not PENDING:
                continue
            if scheduled and id_ in scheduled:
                continue
            if dirty and id_ in dirty:
                continue
            del field_cache[id_]
            cleared += 1
        if _debug.logic.enabled and cleared:
            _debug.logic(
                "field.dead_pending_cleared",
                model=self.model_name,
                field=self.name,
                cleared=cleared,
                records=len(records._ids),
            )

    def _release_dead_pending_to_prefetch(self, record: BaseModel) -> None:
        env = record.env
        field_cache = self._get_cache(env)
        core = env.core
        dirty = core.get_dirty(self)
        protected = core.get_protected_ids(self)
        record_id = record._ids[0]
        kind = bool(record_id)
        budget = PREFETCH_MAX - 1
        released = 0
        for id_ in record._prefetch_ids:
            if budget <= 0:
                break
            if id_ == record_id or bool(id_) != kind:
                continue
            value = field_cache.get(id_, SENTINEL)
            if value is SENTINEL:
                budget -= 1
            elif (
                value is PENDING
                and id_ not in protected
                and not (dirty and id_ in dirty)
                and not core.is_pending_in_tree(self, id_)
            ):
                del field_cache[id_]
                budget -= 1
                released += 1
        if _debug.logic.enabled and released:
            _debug.logic(
                "field.dead_pending_released",
                model=self.model_name,
                field=self.name,
                record=record_id,
                released=released,
            )

    def _insert_cache(self, records: ModelLike, values: Iterable[typing.Any]) -> None:
        field_cache = self._get_cache(records.env)
        collections.deque(
            map(field_cache.setdefault, records._ids, values, strict=True), maxlen=0
        )

    def _update_cache_items(
        self, env: Environment, items: Iterable[tuple[IdType, typing.Any]]
    ) -> None:
        items = list(items)
        if not items:
            return

        self._check_not_dirty(env, [id_ for id_, _ in items], "_update_cache_items")

        self._get_cache(env).update(items)

    def _check_not_dirty(
        self, env: Environment, ids: Collection[IdType], caller: str
    ) -> None:
        if not self.is_column:
            return
        dirty_ids = env.core.get_dirty(self)
        if not dirty_ids or dirty_ids.isdisjoint(ids):
            return
        overlap = sorted(dirty_ids.intersection(ids))
        raise ValueError(
            f"Field.{caller}: refusing to overwrite the dirty value of {self} "
            f"on records {overlap} without dirty=True; the pending write would "
            f"be lost"
        )

    def _update_cache(
        self, records: ModelLike, cache_value: typing.Any, dirty: bool = False
    ) -> None:
        env = records.env

        if not dirty:
            self._check_not_dirty(env, records._ids, "_update_cache")

        field_cache = self._get_cache(env)
        ids = records._ids
        if len(ids) <= 1:
            if ids:
                field_cache[ids[0]] = cache_value
        else:
            field_cache.update(dict.fromkeys(ids, cache_value))

        if self.is_column and dirty:
            self._mark_column_dirty(records)

    def _mark_column_dirty(self, records: ModelLike) -> None:
        env = records.env
        real_ids = [id_ for id_ in records._ids if id_]
        env.core.mark_dirty(self, real_ids)
        snapshots = env.transaction.recompute_snapshots
        if snapshots and (snapshot := snapshots.get(self)):
            for id_ in real_ids:
                snapshot.pop(id_, None)
        for many2one in env.registry.order_key_inverses.get(self, ()):
            many2one._resort_inverses(records)
        for sibling in self.tree_siblings:
            sibling._invalidate_cache(env, real_ids, keep_dirty=True)

    if typing.TYPE_CHECKING:

        @typing.overload
        def __get__(self, record: None, owner: typing.Any = None) -> Self: ...
        @typing.overload
        def __get__(self, record: BaseModel, owner: typing.Any = None) -> T: ...
        @typing.overload
        def __get__(self, record: object, owner: typing.Any = None) -> typing.Any: ...

        @typing.override
        def __get__(self, record: typing.Any, owner: typing.Any = None) -> T | Self: ...

    else:
        __get__ = _prepare_fast_get()

    def _get_not_singleton(self, record: BaseModel, owner: typing.Any = None) -> T:
        if record._ids:
            record.check_singleton()
        if _debug.logic.enabled:
            _debug.logic(
                "field.get.empty_recordset",
                model=self.model_name,
                field=self.name,
            )
        value = self.convert_to_cache(False, record, validate=False)
        return self.convert_to_record(value, record)

    def _get_uncached(
        self, record: BaseModel, env: Environment, record_id: IdType
    ) -> T:
        field_cache = self._get_cache(env)
        try:
            value = field_cache[record_id]
        except KeyError:
            value = SENTINEL
        if value is not SENTINEL and value is not PENDING:
            if callable(self.translate):
                try:
                    return self.convert_to_record(value, record)
                except KeyError:
                    pass
            else:
                return self.convert_to_record(value, record)
        if value is PENDING:
            field_cache.pop(record_id, None)
            if env.is_protected(self, record):
                _debug.logic(
                    "field.get.pending_protected",
                    model=self.model_name,
                    field=self.name,
                    record=record_id,
                )
                value = self.convert_to_cache(False, record, validate=False)
                self._update_cache(record, value)
                return self.convert_to_record(value, record)
            self._release_dead_pending_to_prefetch(record)
        return self._get_cache_miss(record, env, record_id)

    def _get_origin_value(self, origin: BaseModel) -> typing.Any:
        return origin[self.name]

    def _get_cache_miss(
        self,
        record: BaseModel,
        env: Environment,
        record_id: IdType,
    ) -> T:
        return _cache_miss.get_cache_miss(self, record, env, record_id)

    def _value_after_delegated_fetch(
        self, env: Environment, record_id: IdType
    ) -> typing.Any:
        return SENTINEL

    def _protected_value_of_other_scope(
        self, env: Environment, record_id: IdType
    ) -> typing.Any:
        return SENTINEL

    def _settle_new_record_compute_group(self, records: BaseModel) -> None:
        group = records.pool.field_computed.get(self)
        if not group or len(group) == 1:
            return
        env = records.env
        record_id = records._ids[0]
        settled = 0
        for sibling in group:
            if sibling is self or not (sibling.compute and sibling.store):
                continue
            if record_id in sibling._get_cache(env):
                continue
            sibling.__get__(records)
            settled += 1
        if _debug.logic.enabled and settled:
            _debug.logic(
                "field.new_record.compute_group_settled",
                model=self.model_name,
                field=self.name,
                siblings=settled,
            )

    def __set__(self, records: BaseModel, value: typing.Any) -> None:
        record_ids = records._ids
        core = records.env.core
        if len(record_ids) == 1:
            record_id = record_ids[0]
            if core.is_protected(self, record_id):
                self.mark_dirty(records, value)
                if record_id and self.store:
                    records._access_inputs_written((self.name,))
                return
            if not record_id:
                self._settle_new_record_compute_group(records)
                self._update_new(records, [record_id], value)
                return
            write_value = self.convert_to_write(value, records)
            records.write({self.name: write_value})
            return

        _protected_ids = core.get_protected_ids(self)
        protected_ids = []
        new_ids = []
        other_ids = []
        for record_id in record_ids:
            if record_id in _protected_ids:
                protected_ids.append(record_id)
            elif not record_id:
                new_ids.append(record_id)
            else:
                other_ids.append(record_id)

        _debug.logic(
            "field.set.split",
            model=self.model_name,
            field=self.name,
            protected=len(protected_ids),
            new=len(new_ids),
            real=len(other_ids),
        )
        if protected_ids:
            self._update_protected(records, protected_ids, value)
        if new_ids:
            self._update_new(records, new_ids, value)
        if other_ids:
            self._update_real(records, other_ids, value)

    def _update_protected(
        self, records: BaseModel, ids: list[typing.Any], value: typing.Any
    ) -> None:
        recs = _get_recordset_like(records, ids)
        self.mark_dirty(recs, value)
        if self.store and any(ids):
            recs._access_inputs_written((self.name,))

    def _update_new(
        self, records: BaseModel, ids: list[typing.Any], value: typing.Any
    ) -> None:
        new_records = _get_recordset_like(records, ids)
        with records.env.protecting(
            records.pool.field_computed.get(self, [self]), new_records
        ):
            if self.relational:
                new_records._modified_before([self.name])
            self.mark_dirty(new_records, value)
            new_records.modified([self.name])

        if self.inherited:
            _debug.logic(
                "field.set.new_inherited_forwarded",
                model=self.model_name,
                field=self.name,
                records=len(ids),
            )
            parents = new_records[self._related_names[0]]
            parents._new_records[self.name] = value

    def _update_real(
        self, records: BaseModel, ids: list[typing.Any], value: typing.Any
    ) -> None:
        records = _get_recordset_like(records, ids)
        write_value = self.convert_to_write(value, records)
        records.write({self.name: write_value})

    @typing.override
    def check_read_access(self, record: ModelLike) -> None:
        env = record.env
        if (
            self.access_classes is not None
            and not env.su
            and not record._has_field_access(self, "read")
        ):
            record._check_field_access(self, "read")
        elif self.access_classes is not None and not env.su:
            record._check_field_access_records(self, "read")

    def read_cache(self, record_id: int, env: Environment) -> tuple[bool, typing.Any]:
        value = self._get_cache(env).get(record_id, SENTINEL)
        if value is SENTINEL or value is PENDING:
            return False, SENTINEL
        return True, value

    def recompute_pending(self, records: ModelLike) -> None:
        if self.is_stored_computed:
            self.recompute_where_scheduled(records)

    def recompute_where_scheduled(self, records: ModelLike) -> None:
        env = records.env
        core = env.core
        for field in (self, *self.tree_siblings):
            if core.has_pending_field(field):
                if field is self:
                    field.recompute(records)
                else:
                    field.recompute(env[field.model_name].browse(records._ids))

    def recompute(self, records: ModelLike) -> None:
        _compute.recompute(self, records)

    def _superuser_slot_snapshot(
        self, env: Environment, ids: Collection[IdType]
    ) -> dict[IdType, typing.Any] | None:
        return None

    def _adopt_superuser_assignments(
        self, env: Environment, before: dict[IdType, typing.Any] | None
    ) -> None:
        return

    def compute_value(self, records: ModelLike, validate: bool = True) -> None:
        _compute.compute_value(self, records, validate)

    def apply_inverse(self, records: ModelLike) -> None:
        _compute.apply_inverse(self, records)

    def get_search_domain(
        self, records: BaseModel, operator: str, value: typing.Any
    ) -> typing.Any:
        return call_hook(self.search, records, operator, value)

    def get_expanded_groups(
        self, records: BaseModel, values: typing.Any, domain: DomainType
    ) -> typing.Any:
        return call_hook(self.group_expand, records, values, domain)
