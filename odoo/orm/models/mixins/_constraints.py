from __future__ import annotations

import logging
import typing
from inspect import getmembers

from odoo.exceptions import ValidationError
from odoo.libs.debug_log import DebugLog

from ... import decorators as api
from ...helpers import get_or_create_class_memo
from ...profiling import _OrmProfile
from ._model_stubs import _ModelStubs

if typing.TYPE_CHECKING:
    from collections.abc import Collection, Iterable

    from ..._typing import ModelLike

_logger = logging.getLogger("odoo.models")
_orm_crud = logging.getLogger("odoo.orm.crud")
_debug = DebugLog(__name__)


class ConstraintMethod(typing.Protocol):
    _constrains: Collection[str]

    def __call__(self, records: ModelLike, /) -> object: ...


class _ConstraintsMixin(_ModelStubs):
    __slots__ = ()

    @property
    def _constraint_methods(self) -> list[ConstraintMethod]:

        def is_constraint(func: typing.Any) -> bool:
            return callable(func) and hasattr(func, "_constrains")

        def wrap(func: typing.Any, names: Iterable[str]) -> typing.Any:
            sudo_flag = getattr(func, "_constrains_sudo", True)

            @api.constrains(*names, sudo=sudo_flag)
            def wrapper(self: typing.Any) -> typing.Any:
                return func(self)

            return wrapper

        cls = self.env.registry[self._name]

        def get_constraint_methods() -> list[ConstraintMethod]:
            methods: list[ConstraintMethod] = []
            for attr, func in getmembers(cls, is_constraint):
                if callable(func._constrains):
                    func = wrap(func, func._constrains(self.sudo()))
                for name in func._constrains:
                    field = cls._fields.get(name)
                    if not field:
                        _logger.warning(
                            "method %s.%s: @constrains parameter %r is not a field name",
                            cls._name,
                            attr,
                            name,
                        )
                        _debug.logic(
                            "constraints.parameter_invalid",
                            model=cls._name,
                            method=attr,
                            field=name,
                            reason="not_a_field",
                        )
                    elif not (
                        field.store or field.inverse or field.inherited or field.related
                    ):
                        _logger.warning(
                            "method %s.%s: @constrains parameter %r is not writeable",
                            cls._name,
                            attr,
                            name,
                        )
                        _debug.logic(
                            "constraints.parameter_invalid",
                            model=cls._name,
                            method=attr,
                            field=name,
                            reason="not_writeable",
                        )
                methods.append(func)
            methods.extend(
                _required_attachment_check(cls._fields[name])
                for name in self._required_attachment_names
            )
            _debug.perf.count(
                "constraints.methods_collected", model=cls._name, methods=len(methods)
            )
            return methods

        return get_or_create_class_memo(
            cls, "_constraint_methods__", get_constraint_methods
        )

    @property
    def _constrained_field_names(self) -> frozenset[str]:
        cls = self.env.registry[self._name]
        return get_or_create_class_memo(
            cls,
            "_constrained_field_names__",
            lambda: frozenset(
                name for check in self._constraint_methods for name in check._constrains
            ),
        )

    @property
    def _required_attachment_names(self) -> frozenset[str]:
        cls = self.env.registry[self._name]
        return get_or_create_class_memo(
            cls,
            "_required_attachment_names__",
            lambda: frozenset(
                name
                for name, field in cls._fields.items()
                if field.required and field.store and field.is_attachment_backed
            ),
        )

    def _check_required_attachment(self, field_name: str) -> None:
        self.flush_recordset([field_name])
        present = self.env.registry.file_store.ids_with_field(self, field_name)
        missing = self.filtered(lambda record: record.id not in present)
        _debug.logic(
            "constraints.required_attachment",
            model=self._name,
            field=field_name,
            records=len(self),
            missing=missing.ids,
        )
        if not missing:
            return
        field = self._fields[field_name]
        raise ValidationError(
            self.env._(
                "Missing required value for the field '%(field)s' (%(field_name)s).\n"
                "Model: '%(model)s' (%(model_name)s)\n"
                "Records: %(records)s",
                field=field._description_string(self.env),
                field_name=field_name,
                model=self._description,
                model_name=self._name,
                records=", ".join(map(str, missing.ids)),
            )
        )

    @property
    def _constrained_projection_names(self) -> frozenset[str]:
        cls = self.env.registry[self._name]
        return get_or_create_class_memo(
            cls,
            "_constrained_projection_names__",
            lambda: frozenset(
                name
                for name in self._constrained_field_names
                if (field := cls._fields.get(name)) is not None
                and field.related
                and not field.store
            ),
        )

    def _check_fields(
        self, field_names: Iterable[str], excluded_names: Iterable[str] = ()
    ) -> None:
        methods = self._constraint_methods
        if not methods:
            return

        prof = _OrmProfile(_orm_crud)
        _count = 0

        records_sudo = self.sudo()
        records_user = self
        field_names = set(field_names)
        excluded_names = set(excluded_names)
        for check in methods:
            if not field_names.isdisjoint(
                check._constrains
            ) and excluded_names.isdisjoint(check._constrains):
                use_sudo = getattr(check, "_constrains_sudo", True)
                _debug.pipeline(
                    "constraints.check",
                    model=self._name,
                    method=getattr(check, "__name__", "?"),
                    records=len(self),
                    sudo=use_sudo,
                )
                check(records_sudo if use_sudo else records_user)
                if prof.debug:
                    _count += 1

        prof.stop()
        prof.report(_orm_crud, "_check_fields %s: %d constraints", self._name, _count)
        if _debug.perf.enabled:
            _debug.perf.count(
                "constraints.checked",
                model=self._name,
                records=len(self),
                fields=len(field_names),
                excluded=len(excluded_names),
                candidates=len(methods),
            )


def _required_attachment_check(field: typing.Any) -> typing.Any:
    @api.constrains(field.name)
    def check(self: typing.Any) -> None:
        self._check_required_attachment(field.name)

    check.__name__ = f"_check_required_attachment_{field.name}"
    return check
