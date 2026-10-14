from __future__ import annotations

import functools
import typing
from dataclasses import dataclass

from ..domain.constants import ACCESS_OPERATIONS

if typing.TYPE_CHECKING:
    from .base import BaseModel

ANY_STATE = "*"
_Value = str | typing.Literal[False]


class VerbMove(typing.NamedTuple):
    verb_name: str
    record_ids: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class Verb:
    requires: str = "write"
    methods: tuple[str, ...] = ()
    checkpoints: tuple[str, ...] = ()
    transition: tuple[str, _Value | tuple[_Value, ...], _Value] | None = None
    amount: str | None = None
    at_create: bool = True

    def moves(self, before: typing.Any, after: typing.Any) -> bool:
        before, after = _unset(before), _unset(after)
        if self.transition is None or before == after:
            return False
        _field, sources, target = self.transition
        if after != _unset(target):
            return False
        if sources == ANY_STATE:
            return True
        return before in tuple(
            map(_unset, sources if isinstance(sources, tuple) else (sources,))
        )


def _unset(value: typing.Any) -> typing.Any:
    return False if value is None else value


def collect_verbs(model_cls: type[BaseModel]) -> dict[str, Verb]:
    verbs: dict[str, Verb] = {}
    for cls in reversed(model_cls.mro()):
        verbs.update(vars(cls).get("_access_verbs") or {})
    for name, verb in verbs.items():
        if name in ACCESS_OPERATIONS:
            raise TypeError(f"{model_cls._name}: verb {name!r} is a CRUD operation")
        if verb.requires not in ACCESS_OPERATIONS:
            raise TypeError(
                f"{model_cls._name}: verb {name!r} requires {verb.requires!r}, "
                f"which is not one of {ACCESS_OPERATIONS}"
            )
        for method in (*verb.methods, *verb.checkpoints):
            if not callable(getattr(model_cls, method, None)):
                raise TypeError(
                    f"{model_cls._name}: verb {name!r} names {method!r}, "
                    f"which the model does not define"
                )
        if verb.amount is not None and verb.amount not in model_cls._fields:
            raise TypeError(
                f"{model_cls._name}: verb {name!r} reads its amount from "
                f"{verb.amount!r}, which is not a field"
            )
        if verb.transition is not None:
            field = model_cls._fields.get(verb.transition[0])
            if field is None or not field.store:
                raise TypeError(
                    f"{model_cls._name}: verb {name!r} moves {verb.transition[0]!r}, "
                    f"which is not a stored field"
                )
            if field.is_x2many:
                raise TypeError(
                    f"{model_cls._name}: verb {name!r} moves {verb.transition[0]!r}, "
                    f"which is an x2many; a transition moves a single value"
                )
    targets: dict[tuple[str, _Value], str] = {}
    for name, verb in verbs.items():
        if verb.transition is None:
            continue
        key = (verb.transition[0], verb.transition[2])
        if key in targets:
            raise TypeError(
                f"{model_cls._name}: verbs {targets[key]!r} and {name!r} both move "
                f"{key[0]} into {key[1]!r}"
            )
        targets[key] = name
    return verbs


VERB_ORIGIN = "access_verb_origin"


def _defined(
    model_cls: type[BaseModel], method: str
) -> typing.Callable[..., typing.Any]:
    defined: typing.Callable[..., typing.Any] = getattr(
        super(model_cls, model_cls), method
    )
    return defined


def _door(
    verb_name: str,
    model_cls: type[BaseModel],
    method: str,
    origin: typing.Callable[..., typing.Any],
) -> typing.Callable[..., typing.Any]:
    @functools.wraps(origin)
    def door(records: BaseModel, *args: typing.Any, **kwargs: typing.Any) -> typing.Any:
        defined = _defined(model_cls, method)
        return records._verb_door(
            verb_name, lambda admitted: defined(admitted, *args, **kwargs)
        )

    return door


def _checkpoint(
    verb_name: str,
    model_cls: type[BaseModel],
    method: str,
    origin: typing.Callable[..., typing.Any],
) -> typing.Callable[..., typing.Any]:
    @functools.wraps(origin)
    def checkpoint(
        records: BaseModel, *args: typing.Any, **kwargs: typing.Any
    ) -> typing.Any:
        defined = _defined(model_cls, method)
        checked = records._enforce_verb_checkpoint_and_get_ids(verb_name)
        if not checked:
            return defined(records, *args, **kwargs)
        with records.env.transaction.admitting(
            records._get_model_name(), verb_name, checked
        ):
            return defined(records, *args, **kwargs)

    return checkpoint


def uninstall_verb_doors(model_cls: type[BaseModel]) -> None:
    for name, value in list(vars(model_cls).items()):
        if getattr(value, VERB_ORIGIN, None) is not None:
            delattr(model_cls, name)


def install_verb_doors(model_cls: type[BaseModel], verbs: dict[str, Verb]) -> None:
    for verb_name, verb in verbs.items():
        for methods, wrap in ((verb.methods, _door), (verb.checkpoints, _checkpoint)):
            for method in methods:
                origin = getattr(model_cls, method)
                if getattr(origin, VERB_ORIGIN, None) is not None:
                    continue
                wrapper = wrap(verb_name, model_cls, method, origin)
                setattr(wrapper, VERB_ORIGIN, origin)
                setattr(model_cls, method, wrapper)
