import typing
import warnings
from collections.abc import Iterable, Iterator, Mapping, Reversible
from typing import Self, override

from odoo.libs.accel import origin_ids as _origin_ids
from odoo.libs.debug_log import DebugLog

from ... import decorators as api
from ..._protocols import ResCompanyProtocol
from ..._typing import (
    IdType,
    ValuesType,
)
from ...constants import ACTING_PARTNER_KEY
from ...helpers import invalid_field_message
from ...primitives import NewId
from ._model_stubs import _ModelStubs

if typing.TYPE_CHECKING:
    from ..._typing import BaseModel
    from ...runtime import Environment
else:
    BaseModel = typing.Any
    Environment = typing.Any

_debug = DebugLog(__name__)


class _OriginPrefetch(Reversible[IdType]):
    __slots__ = ("_ids",)

    def __init__(self, ids: Iterable[IdType]) -> None:
        self._ids = ids

    @override
    def __iter__(self) -> Iterator[IdType]:
        for id_ in self._ids:
            if origin := id_ or getattr(id_, "origin", None):
                yield origin

    @override
    def __reversed__(self) -> Iterator[IdType]:
        return reversed(_origin_ids(self._ids))


def _declared_privilege_names(
    env: Environment, names: tuple[str, ...]
) -> tuple[str, ...]:
    # A column default evaluated during schema setup runs before its module's
    # data declares the privilege it names; a name whose module has loaded its
    # data is a mistake, not an early read.
    policy = env.registry.access_policy
    declared = []
    for name in names:
        try:
            policy.privilege_ids(env, (name,))
        except ValueError:
            if name.partition(".")[0] in env.registry.loaded_modules:
                raise
            continue
        declared.append(name)
    return tuple(declared)


class EnvironmentMixin(_ModelStubs):
    __slots__ = ()

    @api.private
    @override
    def check_singleton(self) -> Self:
        try:
            (_id,) = self._ids
            return self
        except ValueError:
            _debug.logic(
                "env.singleton_expected", model=self._name, records=len(self._ids)
            )
            raise ValueError(f"Expected singleton: {self}") from None

    @api.private
    @override
    def with_env(self, env: Environment) -> Self:
        return self._spawn(env, self._ids, self._prefetch_ids)

    @api.private
    @override
    def sudo(self, flag: bool = True) -> Self:
        if not isinstance(flag, bool):
            raise TypeError(
                f"sudo() expects a bool, got {type(flag).__name__}; did you mean"
                " with_user()?"
            )
        if flag == self.env.su:
            return self
        return self.with_env(self.env(su=flag))

    @api.private
    @override
    def with_user(self, user: typing.Any) -> Self:
        if not user:
            return self
        return self.with_env(self.env(user=user, su=False))

    @api.private
    @override
    def with_privilege(self, *names: str, reason: str | None = None) -> Self:
        policy = self.env.registry.access_policy
        try:
            privileges = policy.privilege_ids(self.env, names)
        except ValueError:
            if not self.env.su or self.env.registry.ready:
                raise
            privileges = policy.privilege_ids(
                self.env, _declared_privilege_names(self.env, names)
            )
        env = self.env(privileges=self.env.privileges | privileges)
        if reason:
            env = env(context={**env.context, "privilege_reason": reason})
        return self.with_env(env)

    @api.private
    @override
    def with_acting_partner(self, partner: typing.Any) -> Self:
        if not partner:
            return self
        partner.check_singleton()
        acting = (partner.id, partner.commercial_partner_id.id)
        return self.with_context({**self.env.context, ACTING_PARTNER_KEY: acting})

    @api.private
    @override
    def with_company(
        self, company: BaseModel | ResCompanyProtocol | int | None
    ) -> Self:
        if not company:
            return self

        company_id = int(company)
        if not company_id:
            raise ValueError(
                f"with_company() requires a saved (real-id) company, got {company!r}"
            )
        allowed_company_ids = self.env.context.get("allowed_company_ids") or []
        if allowed_company_ids and company_id == allowed_company_ids[0]:
            return self
        allowed_company_ids = list(allowed_company_ids)
        if company_id in allowed_company_ids:
            allowed_company_ids.remove(company_id)
        allowed_company_ids.insert(0, company_id)

        _debug.logic(
            "env.company_switched",
            model=self._name,
            company=company_id,
            allowed=len(allowed_company_ids),
        )
        return self.with_context(allowed_company_ids=allowed_company_ids)

    @api.private
    @override
    def with_context(
        self, ctx: dict[str, typing.Any] | None = None, /, **overrides: typing.Any
    ) -> Self:
        context = dict(ctx if ctx is not None else self.env.context, **overrides)
        if "force_company" in context:
            warnings.warn(
                "Since 19.0, context key 'force_company' is no longer supported. "
                "Use with_company(company) instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            _debug.logic(
                "env.context_key_unsupported", model=self._name, key="force_company"
            )
        if "company" in context:
            warnings.warn(
                "Context key 'company' is not recommended, because "
                "of its special meaning in @depends_context.",
                stacklevel=2,
            )
            _debug.logic("env.context_key_discouraged", model=self._name, key="company")
        if (
            "allowed_company_ids" not in context
            and "allowed_company_ids" in self.env.context
        ):
            context["allowed_company_ids"] = self.env.context["allowed_company_ids"]
        return self.with_env(self.env(context=context))

    @api.private
    @override
    def with_prefetch(self, prefetch_ids: Reversible[IdType] | None = None) -> Self:
        if prefetch_ids is None:
            prefetch_ids = self._ids
        return self._spawn(self.env, self._ids, prefetch_ids)

    @staticmethod
    def _can_cache_value_hold_new_ids(value: typing.Any) -> bool:
        if type(value) is tuple:
            return any(not id_ for id_ in value)
        return not (value is None or type(value) is int)

    @override
    def _update_cache(self, values: ValuesType, validate: bool = True) -> None:
        self.check_singleton()
        fields = self._fields
        try:
            field_values = [
                (fields[name], value) for name, value in values.items() if name != "id"
            ]
        except KeyError as e:
            raise ValueError(invalid_field_message(self, e.args[0])) from e

        if len(field_values) > 1:
            field_values.sort(key=lambda item: item[0].write_sequence)

        field_inverses = self.pool.field_inverses
        with_new_corecords = []
        for field, value in field_values:
            value = field.convert_to_cache(value, self, validate)
            field._update_cache(self, value)
            if (
                field.relational
                and field_inverses[field]
                and self._can_cache_value_hold_new_ids(value)
            ):
                with_new_corecords.append(field)

        for field in with_new_corecords:
            inv_recs = self[field.name]._new_records
            if not inv_recs:
                continue
            inverses = field_inverses[field]
            _debug.logic(
                "env.new_inverses_updated",
                model=self._name,
                field=field.name,
                inverses=len(inverses),
                new_records=len(inv_recs),
            )
            for invf in inverses:
                if invf.is_x2many and not self.filtered_domain(
                    invf.get_comodel_domain(inv_recs)
                ):
                    continue
                invf._update_inverse(inv_recs, typing.cast("BaseModel", self))

    def _convert_to_write(self, values: Mapping[str, typing.Any]) -> ValuesType:
        fields = self._fields
        result = {}
        for name, value in values.items():
            if name in fields:
                field = fields[name]
                value = field.convert_to_write(value, self)
                if not isinstance(value, NewId):
                    result[name] = value
        return result

    @api.model
    @api.private
    @override
    def new(
        self,
        values: ValuesType | None = None,
        origin: Self | None = None,
        ref: typing.Any = None,
    ) -> Self:
        if values is None:
            values = {}
        origin_id = origin.id if origin else None
        if not isinstance(origin_id, int):
            origin_id = None
        if not ref:
            ref = None
        record = self.browse((NewId(origin_id, ref),))
        record._update_cache(values, validate=False)
        if _debug.lifecycle.enabled:
            _debug.lifecycle(
                "env.new_record",
                model=self._name,
                origin=origin_id,
                ref=ref is not None,
                fields=sorted(values),
            )

        return record

    @property
    @override
    def _has_origin(self) -> bool:
        return any(id_ or getattr(id_, "origin", None) for id_ in self._ids)

    @property
    @override
    def _origin(self) -> Self:
        record_ids = self._ids
        if all(record_ids):
            return self
        ids = _origin_ids(record_ids)
        if not ids:
            return self._spawn(self.env, (), ())
        prefetch_ids = self._prefetch_ids
        return self._spawn(
            self.env,
            ids,
            ids if prefetch_ids is record_ids else _OriginPrefetch(prefetch_ids),
        )
