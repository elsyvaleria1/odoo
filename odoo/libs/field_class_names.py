"""The naming convention for field sensitivity classes, shared by the ORM
that compiles ``groups=`` into an anonymous class and by ``ir.access`` that
reads a row's class. Odoo-agnostic: it manipulates names only."""

from __future__ import annotations

import typing

from .refs import split_refs

if typing.TYPE_CHECKING:
    from collections.abc import Callable

    from .set_expression import SetDefinitions, SetExpression

__all__ = [
    "ANONYMOUS_PREFIX",
    "PER_RECORD",
    "anonymous_class",
    "anonymous_spec",
    "field_view_groups",
    "is_anonymous",
]

ANONYMOUS_PREFIX = "groups:"


PER_RECORD: typing.Final = "per-record"

type Verdict = bool | str


def anonymous_class(spec: str, no_access: str) -> str:
    if spec == no_access:
        return ANONYMOUS_PREFIX + no_access
    return ANONYMOUS_PREFIX + ",".join(sorted(set(split_refs(spec))))


def anonymous_spec(key: str) -> str | None:
    return key.removeprefix(ANONYMOUS_PREFIX) if is_anonymous(key) else None


def is_anonymous(key: str) -> bool:
    return key.startswith(ANONYMOUS_PREFIX)


def field_view_groups(
    definitions: SetDefinitions,
    field: typing.Any,
    resolve_named: Callable[[str], SetExpression],
    operation: str = "read",
) -> SetExpression:
    classes = getattr(field, "access_classes", None)
    if classes is None:
        return definitions.universe
    keys = classes.read if operation == "read" else classes.write
    expression = _keys_view_groups(definitions, keys, resolve_named)
    alternative = classes.read_alternative if operation == "read" else ()
    if alternative:
        expression |= _keys_view_groups(definitions, alternative, resolve_named)
    return expression


def _keys_view_groups(
    definitions: SetDefinitions,
    keys: typing.Iterable[str],
    resolve_named: Callable[[str], SetExpression],
) -> SetExpression:
    expression = definitions.universe
    for key in keys:
        spec = anonymous_spec(key)
        if spec is not None:
            expression &= definitions.parse(spec, raise_if_not_found=False)
        else:
            expression &= resolve_named(key)
    return expression
