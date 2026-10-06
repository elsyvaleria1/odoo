from __future__ import annotations

import typing
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from odoo.libs.field_class_names import (
    ANONYMOUS_PREFIX,
    anonymous_spec,
    is_anonymous,
)
from odoo.libs.field_class_names import anonymous_class as _anonymous_class

from ..primitives import NO_ACCESS

if typing.TYPE_CHECKING:
    from .._typing import BaseModel
    from ..fields import Field

__all__ = ["ANONYMOUS_PREFIX", "anonymous_spec", "is_anonymous", "unmasked_values"]

# a fetch reads a column's true value into the cache, which stays truthful:
# a value the principal may not read on a record is masked where it leaves
# (read, a WHERE, an ORDER BY, a GROUP BY), never where it is fetched
_UNMASKED: ContextVar[bool] = ContextVar("unmasked_field_values", default=False)


@contextmanager
def unmasked_values() -> Iterator[None]:
    token = _UNMASKED.set(True)
    try:
        yield
    finally:
        _UNMASKED.reset(token)


def values_unmasked() -> bool:
    return _UNMASKED.get()


class FieldAccessClasses(typing.NamedTuple):
    read: tuple[str, ...]
    write: tuple[str, ...]
    write_hook: Callable[[BaseModel], bool] | None = None
    # classes that grant reading on their own, in place of those of `read`
    # (a user's own record): the read verdict is read OR read_alternative
    read_alternative: tuple[str, ...] = ()


class ModelFieldClasses(typing.NamedTuple):
    # what a model says of one of its fields, asked once at registry setup:
    # a class it adds to the field's own (a residual or a whitelist class),
    # a class needed to write it, and a class that grants reading it alone
    own: str | None = None
    write: str | None = None
    alternative: str | None = None


NO_MODEL_CLASSES = ModelFieldClasses()


def anonymous_class(spec: str) -> str:
    return _anonymous_class(spec, NO_ACCESS)


FIELD_CLASS_HOOKS = (
    "_access_field_class",
    "_access_field_write_class",
    "_access_field_alternative_class",
)


def model_field_classes(
    model: BaseModel, defaults: typing.Mapping[str, typing.Any]
) -> dict[str, ModelFieldClasses]:
    # the model's own hooks, asked with an environment; only the fields they
    # say something of are kept, and a model that overrides none of them and
    # names no residual class says nothing
    model_cls = type(model)
    if model_cls._access_residual_class is None and all(
        getattr(model_cls, hook) is defaults[hook] for hook in FIELD_CLASS_HOOKS
    ):
        return {}
    found = {}
    for name, field in model._fields.items():
        said = ModelFieldClasses(
            model._access_field_class(field),
            model._access_field_write_class(field),
            model._access_field_alternative_class(field),
        )
        if said != NO_MODEL_CLASSES:
            found[name] = said
    return found


def field_access_classes(
    said: typing.Mapping[str, ModelFieldClasses], field: Field[typing.Any]
) -> FieldAccessClasses | None:
    # what a principal must be granted to read, and to write, the field: its
    # named class, its groups, and what its model says of it; None for a
    # field anyone who reaches the record may read
    model_says = said.get(field.name, NO_MODEL_CLASSES)
    read: list[str] = []
    if field.classification:
        read.append(field.classification)
    if model_says.own:
        read.append(model_says.own)
    if field.groups:
        read.append(anonymous_class(field.groups))
    write = list(read)
    if field.write_classification:
        write.append(field.write_classification)
    if model_says.write:
        write.append(model_says.write)
    write_hook = None
    if callable(field.write_groups):
        write_hook = field.write_groups
    elif field.write_groups:
        write.append(anonymous_class(field.write_groups))
    if not (read or write or write_hook):
        return None
    alternative = (model_says.alternative,) if model_says.alternative and read else ()
    return FieldAccessClasses(
        tuple(dict.fromkeys(read)),
        tuple(dict.fromkeys(write)),
        write_hook,
        alternative,
    )
