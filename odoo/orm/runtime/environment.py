import functools
import logging
import typing
from collections import defaultdict
from collections.abc import Collection, Hashable, Mapping, MutableMapping

from psycopg import ProgrammingError

from odoo.db import BaseCursor
from odoo.exceptions import AccessError, MissingError, UserError
from odoo.libs.accel import rows_to_dicts as _rows_to_dicts
from odoo.libs.collections import OrderedSet, ReadonlyDict, frozendict
from odoo.libs.datetime import timezone as get_timezone
from odoo.libs.datetime import utc
from odoo.libs.debug_log import DebugLog
from odoo.libs.func import reset_cached_properties
from odoo.libs.sql import SQL
from odoo.tools import clean_context
from odoo.tools.translate import (
    LazyGettext,
    get_translated_module,
    get_translation,
)

from ..constants import ACTING_PARTNER_KEY
from .access_memo import PrincipalVerdicts
from .registry import Registry
from .transaction import NO_PRIVILEGES, Transaction

if typing.TYPE_CHECKING:
    from datetime import tzinfo

    from odoo.libs.collections import Collector

    from .._typing import BaseModel, Field, ModelLike
    from ..components.core import OrmCore
    from ..primitives import IdType
    from ._model_types import (
        AuthUserClientModel,
        DecimalPrecisionModel,
        IrAccessLogModel,
        IrAccessModel,
        IrAccessObligationModel,
        IrAttachmentModel,
        IrConfigParameterModel,
        IrCronModel,
        IrDefaultModel,
        IrFieldsConverterModel,
        IrHttpModel,
        IrModelConstraintModel,
        IrModelDataModel,
        IrModelFieldsModel,
        IrModelFieldsSelectionModel,
        IrModelInheritModel,
        IrModelModel,
        IrModelRelationModel,
        IrModuleModuleModel,
        IrQWebModel,
        IrUiViewModel,
        ResCompanyModel,
        ResCountryModel,
        ResCurrencyModel,
        ResGroupsModel,
        ResLangModel,
        ResUsersApikeysScopeModel,
        ResUsersModel,
    )
    from .backend import StorageBackend

    M = typing.TypeVar("M", bound=BaseModel)
else:
    BaseModel = typing.Any
    Field = typing.Any

_logger = logging.getLogger("odoo.api")
_debug = DebugLog(__name__)
_MISSING = object()


class _Protecting:
    __slots__ = ("_active", "_core", "_records", "_what")

    def __init__(
        self, core: OrmCore[Field[typing.Any]], what: typing.Any, records: typing.Any
    ) -> None:
        self._core = core
        self._what = what
        self._records = records
        self._active = False

    def __enter__(self) -> None:
        what = self._what
        if not what:
            return
        records = self._records
        if records is not None:
            ids = frozenset(records._ids)
            protected = [(field, ids) for field in what]
        else:
            ids_by_field = defaultdict(list)
            for fields, what_records in what:
                for field in fields:
                    ids_by_field[field].extend(what_records._ids)
            protected = [
                (field, frozenset(rec_ids)) for field, rec_ids in ids_by_field.items()
            ]
        core = self._core
        core.push_protection()
        self._active = True
        for field, field_ids in protected:
            core.protect(field, field_ids)

    def __exit__(self, exc_type: object, *exc: object) -> None:
        if not self._active:
            return
        self._active = False
        core = self._core
        try:
            if core.protection_depth() == 1 and exc_type is None:
                core.run_deferred()
        finally:
            core.pop_protection()


class Environment(Mapping[str, "BaseModel"]):
    cr: BaseCursor
    uid: int | None
    context: frozendict[str, typing.Any]
    su: bool
    privileges: frozenset[int]
    transaction: Transaction

    def __new__(  # noqa: PYI034 - the transaction cache can return a different Environment subclass
        cls,
        cr: BaseCursor,
        uid: int | None,
        context: Mapping[str, typing.Any],
        su: bool = False,
        privileges: frozenset[int] = NO_PRIVILEGES,
    ) -> Environment:
        if not isinstance(cr, BaseCursor):
            raise TypeError(
                f"Environment(cr=...) expected BaseCursor, got {type(cr).__name__}"
            )
        if isinstance(uid, bool):
            raise TypeError(
                f"Environment(uid=...) expected int, None or a request "
                f"placeholder, got bool ({uid!r})"
            )
        transaction = cr.transaction
        if transaction is None:
            transaction = cr.transaction = Transaction(Registry(cr.dbname))
            _debug.lifecycle(
                "environment.transaction_attached", db=cr.dbname, uid=uid, su=su
            )
        return transaction.environment(cr, uid, context, su, privileges)

    @classmethod
    def _interned(
        cls,
        transaction: Transaction,
        cr: BaseCursor,
        uid: int | None,
        context: frozendict[str, typing.Any],
        su: bool,
        privileges: frozenset[int] = NO_PRIVILEGES,
    ) -> Environment:
        self = object.__new__(cls)
        self.cr, self.uid, self.su = cr, uid, su
        self.privileges = privileges
        self.context = context
        self.transaction = transaction
        return self

    @typing.override
    def __setattr__(self, name: str, value: typing.Any) -> None:
        if name in vars(self):
            raise AttributeError(
                f"Attribute {name!r} is read-only, call `env()` instead"
            )
        return super().__setattr__(name, value)

    @typing.override
    def __contains__(self, model_name: object) -> bool:
        return model_name in self.registry

    @typing.overload
    def __getitem__(
        self, model_name: typing.Literal["decimal.precision"]
    ) -> DecimalPrecisionModel: ...

    @typing.overload
    def __getitem__(
        self, model_name: typing.Literal["ir.attachment"]
    ) -> IrAttachmentModel: ...

    @typing.overload
    def __getitem__(
        self, model_name: typing.Literal["ir.config_parameter"]
    ) -> IrConfigParameterModel: ...

    @typing.overload
    def __getitem__(self, model_name: typing.Literal["ir.cron"]) -> IrCronModel: ...

    @typing.overload
    def __getitem__(self, model_name: typing.Literal["ir.http"]) -> IrHttpModel: ...

    @typing.overload
    def __getitem__(
        self, model_name: typing.Literal["ir.default"]
    ) -> IrDefaultModel: ...

    @typing.overload
    def __getitem__(self, model_name: typing.Literal["ir.model"]) -> IrModelModel: ...

    @typing.overload
    def __getitem__(self, model_name: typing.Literal["ir.access"]) -> IrAccessModel: ...

    @typing.overload
    def __getitem__(
        self, model_name: typing.Literal["ir.model.constraint"]
    ) -> IrModelConstraintModel: ...

    @typing.overload
    def __getitem__(
        self, model_name: typing.Literal["ir.model.data"]
    ) -> IrModelDataModel: ...

    @typing.overload
    def __getitem__(
        self, model_name: typing.Literal["ir.model.fields"]
    ) -> IrModelFieldsModel: ...

    @typing.overload
    def __getitem__(
        self, model_name: typing.Literal["ir.model.fields.selection"]
    ) -> IrModelFieldsSelectionModel: ...

    @typing.overload
    def __getitem__(
        self, model_name: typing.Literal["ir.model.inherit"]
    ) -> IrModelInheritModel: ...

    @typing.overload
    def __getitem__(
        self, model_name: typing.Literal["ir.model.relation"]
    ) -> IrModelRelationModel: ...

    @typing.overload
    def __getitem__(
        self, model_name: typing.Literal["ir.module.module"]
    ) -> IrModuleModuleModel: ...

    @typing.overload
    def __getitem__(self, model_name: typing.Literal["ir.qweb"]) -> IrQWebModel: ...

    @typing.overload
    def __getitem__(
        self, model_name: typing.Literal["ir.ui.view"]
    ) -> IrUiViewModel: ...

    @typing.overload
    def __getitem__(
        self, model_name: typing.Literal["ir.fields.converter"]
    ) -> IrFieldsConverterModel: ...

    @typing.overload
    def __getitem__(
        self, model_name: typing.Literal["res.company"]
    ) -> ResCompanyModel: ...

    @typing.overload
    def __getitem__(
        self, model_name: typing.Literal["res.country"]
    ) -> ResCountryModel: ...

    @typing.overload
    def __getitem__(
        self, model_name: typing.Literal["res.currency"]
    ) -> ResCurrencyModel: ...

    @typing.overload
    def __getitem__(self, model_name: typing.Literal["res.lang"]) -> ResLangModel: ...

    @typing.overload
    def __getitem__(self, model_name: typing.Literal["res.users"]) -> ResUsersModel: ...

    @typing.overload
    def __getitem__(
        self, model_name: typing.Literal["auth.user.client"]
    ) -> AuthUserClientModel: ...

    @typing.overload
    def __getitem__(
        self, model_name: typing.Literal["res.users.apikeys.scope"]
    ) -> ResUsersApikeysScopeModel: ...

    @typing.overload
    def __getitem__(
        self, model_name: typing.Literal["res.groups"]
    ) -> ResGroupsModel: ...

    @typing.overload
    def __getitem__(
        self, model_name: typing.Literal["ir.access.log"]
    ) -> IrAccessLogModel: ...

    @typing.overload
    def __getitem__(
        self, model_name: typing.Literal["ir.access.obligation"]
    ) -> IrAccessObligationModel: ...

    @typing.overload
    def __getitem__(self, model_name: str) -> BaseModel: ...

    @typing.override
    def __getitem__(self, model_name: str) -> BaseModel:
        registry = self.registry
        try:
            cls = registry.models[model_name]
        except KeyError:
            cls = registry[model_name]
        rs = object.__new__(cls)
        rs.env = self
        rs._ids = ()
        rs._prefetch_ids = ()
        return rs

    @typing.override
    def __iter__(self) -> typing.Iterator[str]:
        return iter(self.registry)

    @typing.override
    def __len__(self) -> int:
        return len(self.registry)

    __eq__ = object.__eq__
    __ne__ = object.__ne__
    __hash__ = object.__hash__

    def __call__(
        self,
        cr: BaseCursor | None = None,
        user: int | BaseModel | None = None,
        context: dict[str, typing.Any] | None = None,
        su: bool | None = None,
        privileges: frozenset[int] | None = None,
    ) -> Environment:
        cr = self.cr if cr is None else cr
        uid = self.uid if user is None else int(user)
        if context is None:
            context = self.context
            if su and not self.su and self._context_defaults:
                context = clean_context(context)
                if _debug.logic.enabled:
                    _debug.logic(
                        "environment.sudo_context_cleaned",
                        uid=uid,
                        keys=len(self.context) - len(context),
                    )
            if user is not None and ACTING_PARTNER_KEY in context:
                context = {
                    key: value
                    for key, value in context.items()
                    if key != ACTING_PARTNER_KEY
                }
        su = (user is None and self.su) if su is None else su
        if privileges is None:
            privileges = self.privileges if user is None else NO_PRIVILEGES
        return Environment(cr, uid, context, su, privileges)

    @typing.overload
    def ref(
        self, xml_id: str, raise_if_not_found: typing.Literal[True] = True
    ) -> BaseModel: ...

    @typing.overload
    def ref(
        self, xml_id: str, raise_if_not_found: typing.Literal[False]
    ) -> BaseModel | None: ...

    def ref(self, xml_id: str, raise_if_not_found: bool = True) -> BaseModel | None:
        res_model, res_id = self.registry.xmlids.target(
            self, xml_id, raise_if_not_found
        )

        if res_model and res_id:
            record = self[res_model].browse(res_id)
            ref_cache = self.transaction._ref_cache
            cache_key = (res_model, res_id)
            if ref_cache.get(cache_key) or record.exists():
                ref_cache[cache_key] = True
                return record
            _debug.logic(
                "environment.ref.record_missing",
                xml_id=xml_id,
                model=res_model,
                res_id=res_id,
                raise_if_not_found=raise_if_not_found,
            )
            if raise_if_not_found:
                raise ValueError(
                    f"No record found for unique ID {xml_id}. It may have been deleted."
                )
        return None

    def is_superuser(self) -> bool:
        return self.su

    def is_admin(self) -> bool:
        return self.su or self.user._is_admin()

    def is_system(self) -> bool:
        return self.su or self.user._is_system()

    @functools.cached_property
    def registry(self) -> Registry:
        return self.transaction.registry

    @functools.cached_property
    def cache(self) -> typing.Any:
        return self.transaction.cache

    @functools.cached_property
    def core(self) -> OrmCore[Field[typing.Any]]:
        return self.transaction.core

    @property
    def backend(self) -> StorageBackend:
        return self.transaction.backend

    @functools.cached_property
    def user(self) -> ResUsersModel:
        return self(su=True)["res.users"].browse(self.uid)

    def _get_allowed_company_ids(self) -> list[int]:
        company_ids: list[int] = self.context.get("allowed_company_ids", [])
        if company_ids and not self.su:
            if set(company_ids) - set(self.user._get_company_ids()):
                _debug.logic(
                    "environment.company.unauthorized",
                    uid=self.uid,
                    allowed=company_ids,
                    user_companies=self.user._get_company_ids(),
                )
                raise AccessError(
                    self._("Access to unauthorized or invalid companies.")
                )
        return company_ids

    @functools.cached_property
    def company(self) -> ResCompanyModel:
        if company_ids := self._get_allowed_company_ids():
            return self["res.company"].browse(company_ids[0])
        _debug.logic("environment.company.fallback_to_user", uid=self.uid)
        return self.user.company_id.with_env(self)

    @functools.cached_property
    def companies(self) -> ResCompanyModel:
        if company_ids := self._get_allowed_company_ids():
            return self["res.company"].browse(company_ids)
        _debug.logic("environment.companies.fallback_to_user", uid=self.uid)
        user_company_ids = list(self.user._get_company_ids())
        current = self.user.company_id.id
        if isinstance(current, int) and current in user_company_ids:
            user_company_ids.remove(current)
            user_company_ids.insert(0, current)
        return self["res.company"].browse(user_company_ids)

    @functools.cached_property
    def _principal_verdicts(self) -> PrincipalVerdicts:
        return PrincipalVerdicts()

    @property
    def access_signature(self) -> tuple[Hashable, ...]:
        return self.registry.access_policy.access_signature(self)

    @functools.cached_property
    def _read_access_key(self) -> tuple[Hashable, ...]:
        return (
            self.uid,
            self.su,
            self.privileges,
            self.registry.access_policy.rule_context(self),
        )

    def _access_scope(self, model_name: str | None = None) -> typing.Any:
        if self.su:
            return True
        acting = self.context.get(ACTING_PARTNER_KEY)
        if (
            (lang := self.context.get("lang"))
            and lang != "en_US"
            and (
                model_name is None
                or self.transaction.access_memo.reads_translated(self, model_name)
            )
        ):
            return (self._access_scope_of_user(), self.privileges, acting, lang)
        if acting:
            return (self._access_scope_of_user(), self.privileges, acting)
        if self.privileges:
            return (self._access_scope_of_user(), self.privileges)
        return self._access_scope_of_user()

    def _access_scope_of_user(self) -> typing.Any:
        if company_ids := self.context.get("allowed_company_ids"):
            _debug.logic(
                "environment.access_scope.from_context",
                uid=self.uid,
                companies=len(company_ids),
            )
            return (self.uid, tuple(sorted(company_ids)))
        try:
            scope = (self.uid, tuple(sorted(self.user._get_company_ids())))
        except MissingError:
            _debug.logic("environment.access_scope.user_missing", uid=self.uid)
            return (self.uid, None)
        _debug.logic(
            "environment.access_scope.from_user",
            uid=self.uid,
            companies=len(scope[1]),
        )
        return scope

    @functools.cached_property
    def tz(self) -> tzinfo:
        tz_name = self.context.get("tz") or self.user.tz
        if tz_name:
            try:
                return get_timezone(tz_name)
            except Exception:
                _logger.debug("Invalid timezone %r", tz_name, exc_info=True)
                _debug.logic("environment.tz.invalid", uid=self.uid, tz=tz_name)
        return utc

    @functools.cached_property
    def lang(self) -> str | None:
        lang = self.context.get("lang")
        if (
            lang
            and lang != "en_US"
            and not self.registry.locale.is_lang_installed(self, lang)
        ):
            raise UserError(f"Invalid language code: {lang}")  # noqa: E8505 -- see above: this one cannot be translated
        return lang or None

    @functools.cached_property
    def _lang(self) -> str:
        context = self.context
        lang = self.lang or "en_US"
        if context.get("edit_translations") or context.get("check_translations"):
            lang = "_" + lang
        return lang

    def _(
        self, source: str | LazyGettext, /, *args: typing.Any, **kwargs: typing.Any
    ) -> str:
        lang = self.lang or "en_US"
        if isinstance(source, str):
            if args and kwargs:
                raise TypeError("Use args or kwargs, not both")
            format_args = args or kwargs
        elif isinstance(source, LazyGettext):
            if args or kwargs:
                raise TypeError("All args should come from the lazy text")
            return source._translate(lang)
        else:
            raise TypeError(f"Cannot translate {source!r}")
        if lang == "en_US":
            return get_translation("base", "en_US", source, format_args)
        return get_translation(get_translated_module(2), lang, source, format_args)

    def clear(self) -> None:
        _debug.lifecycle("environment.clear", uid=self.uid)
        reset_cached_properties(self)
        self.transaction.clear()

    def invalidate_all(
        self, flush: bool = True, *, keep_new_records: bool = False
    ) -> None:
        _debug.lifecycle("environment.invalidate_all", uid=self.uid, flush=flush)
        if flush:
            self.flush_all()
        self.transaction.invalidate_field_data(keep_new_records=keep_new_records)

    def flush_all(self) -> None:
        self.transaction.flush(self)

    def is_protected(self, field: Field[typing.Any], record: ModelLike) -> bool:
        return self.core.is_protected(field, record.id)

    def protecting(self, what: typing.Any, records: typing.Any = None) -> _Protecting:
        return _Protecting(self.core, what, records)

    def fields_to_compute(self) -> Collection[Field[typing.Any]]:
        return self.core.get_pending_fields()

    def get_records_to_compute(self, field: Field[typing.Any]) -> BaseModel:
        return self[field.model_name].browse(self.core.get_pending_ids(field))

    def is_to_compute(self, field: Field[typing.Any], record: BaseModel) -> bool:
        return self.core.is_pending(field, record.id)

    def add_to_compute(self, field: Field[typing.Any], records: ModelLike) -> None:
        if not records:
            return
        assert field.store and field.compute, (
            "Cannot add to recompute no-store or no-computed field"
        )
        if _debug.pipeline.enabled:
            _debug.pipeline(
                "environment.to_compute_added",
                model=field.model_name,
                field=field.name,
                records=len(records),
            )
        self.core.schedule(field, records._ids)

    def remove_to_compute(self, field: Field[typing.Any], records: ModelLike) -> None:
        if not records:
            return
        self.core.mark_done(field, records._ids)

    def get_cache_key(self, field: Field[typing.Any]) -> typing.Any:

        def get(key: str, get_context: typing.Any = self.context.get) -> typing.Any:
            if key == "company":
                return self.company.id
            elif key == "uid":
                uid_key: typing.Any = (
                    self.uid if field.compute_sudo else (self.uid, self.su)
                )
                if self.privileges:
                    uid_key = (uid_key, self.privileges)
                if acting := get_context(ACTING_PARTNER_KEY):
                    uid_key = (uid_key, acting)
                return uid_key
            elif key == "access":
                if field.compute and field.compute_sudo and not field.store:
                    return None
                return self._access_scope(field.comodel_name)
            elif key == "lang":
                return get_context("lang") or "en_US"
            elif key == "active_test":
                return get_context(
                    "active_test", field.context.get("active_test", True)
                )
            elif key.startswith("bin_size"):
                return bool(get_context(key))
            else:
                val = get_context(key)
                if isinstance(val, list):
                    val = tuple(val)
                try:
                    hash(val)
                except TypeError:
                    raise TypeError(
                        "Can only create cache keys from hashable values, "
                        f"got non-hashable value {val!r} at context key {key!r} "
                        f"(dependency of field {field})"
                    ) from None
                else:
                    return val

        return tuple(get(key) for key in self._field_depends_context[field])

    @functools.cached_property
    def _derived_envs(
        self,
    ) -> dict[
        tuple[bool | None, tuple[tuple[str, typing.Any], ...]], Environment | object
    ]:
        return {}

    def _derive(
        self, *, su: bool | None = None, **overrides: typing.Any
    ) -> Environment:
        key = (su, tuple(sorted(overrides.items())))
        env = self._derived_envs.get(key)
        if env is None:
            env = self if su is None or su == self.su else self(su=su)
            if any(env.context.get(k, _MISSING) != v for k, v in overrides.items()):
                env = env(context=dict(env.context, **overrides))
            self._derived_envs[key] = _MISSING if env is self else env
        return env if isinstance(env, Environment) else self

    @functools.cached_property
    def _field_cache_memo(
        self,
    ) -> dict[Field[typing.Any], MutableMapping[IdType, typing.Any]]:
        return {}

    @functools.cached_property
    def _context_defaults(self) -> Mapping[str, typing.Any]:
        return ReadonlyDict(
            {
                key[8:]: value
                for key, value in self.context.items()
                if key.startswith("default_")
            }
        )

    @functools.cached_property
    def _field_depends_context(self) -> Collector[Field[typing.Any], str]:
        return self.registry.field_depends_context

    def flush_query(self, query: SQL) -> None:
        fields_to_flush = tuple(query.to_flush)
        if not fields_to_flush:
            return

        _debug.pipeline(
            "environment.flush_query",
            fields=len(fields_to_flush),
            first=f"{fields_to_flush[0].model_name}.{fields_to_flush[0].name}",
        )
        first = fields_to_flush[0]
        first_model = first.model_name
        single_model = len(fields_to_flush) == 1 or all(
            f.model_name == first_model for f in fields_to_flush
        )
        if single_model and not self.registry[first_model]._table_inheritance_root:
            self[first_model].flush_model([f.name for f in fields_to_flush])
            return

        fnames_to_flush = defaultdict[str, OrderedSet[str]](OrderedSet)
        for field in fields_to_flush:
            fnames_to_flush[field.model_name].add(field.name)
        for model_name, field_names in list(fnames_to_flush.items()):
            for tree_model_name in self._table_inheritance_tree(model_name):
                fnames_to_flush[tree_model_name].update(
                    name
                    for name in field_names
                    if name in self[tree_model_name]._fields
                )
        for model_name, field_names in fnames_to_flush.items():
            self[model_name].flush_model(field_names)

    def _table_inheritance_tree(self, model_name: str) -> tuple[str, ...]:
        root = self.registry[model_name]._table_inheritance_root
        if not root:
            return ()
        return tuple(
            name
            for name in self.registry.model_names_by_inheritance_root.get(root, ())
            if name != model_name
        )

    def execute_query(self, query: SQL) -> list[tuple[typing.Any, ...]]:
        if not isinstance(query, SQL):
            raise TypeError(f"execute_query expected SQL, got {type(query).__name__}")
        self.flush_query(query)
        self.cr.execute(query)  # noqa: E8501 -- query is checked to be SQL above
        try:
            return self.cr.fetchall()
        except ProgrammingError as exc:
            if exc.sqlstate is not None:
                raise
            _debug.logic("environment.execute_query.no_result_set", uid=self.uid)
            return []

    def execute_query_dict(self, query: SQL) -> list[dict[str, typing.Any]]:
        rows = self.execute_query(query)
        if not rows:
            return []
        description = self.cr.description
        if description is None:
            raise RuntimeError(
                "No cr.description, the executed query does not return a table."
            )
        cols = tuple(col.name for col in description)
        return _rows_to_dicts(cols, rows)
