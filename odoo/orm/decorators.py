import typing
import warnings
from collections.abc import Callable, Collection, Mapping
from functools import wraps

from odoo.libs.debug_log import DebugLog

C = typing.TypeVar("C", bound=Callable[..., typing.Any])


class Decorator(typing.Protocol):
    def __call__[F: Callable[..., typing.Any]](self, method: F, /) -> F: ...


if typing.TYPE_CHECKING:
    from ._typing import BaseModel, ValuesType
else:
    ValuesType = typing.Any

_debug = DebugLog(__name__)


def stamp[F](method: F, **markers: object) -> F:
    for name, value in markers.items():
        setattr(method, name, value)
    return method


def attrsetter(attr: str, value: object) -> Decorator:

    def setter(method: C) -> C:
        setattr(method, attr, value)
        return method

    return setter


@typing.overload
def constrains(
    func: Callable[[BaseModel], Collection[str]], /, *, sudo: bool = True
) -> Decorator: ...


@typing.overload
def constrains(*args: str, sudo: bool = True) -> Decorator: ...


def constrains(*args: typing.Any, sudo: bool = True) -> Decorator:
    if args and callable(args[0]):
        if len(args) > 1:
            raise TypeError(
                "constrains() takes either a single callable or field-name "
                f"strings, not both (extra arguments {args[1:]!r} would be "
                "silently ignored)"
            )
        args = args[0]
    elif not all(isinstance(arg, str) for arg in args):
        raise TypeError(
            f"constrains() arguments must be field-name strings, got {args!r}"
        )
    else:
        _check_field_paths("constrains", args, dotted=True)

    def decorator(method: C) -> C:
        return stamp(method, _constrains=args, _constrains_sudo=sudo)

    return decorator


def ondelete(*, at_uninstall: bool) -> Decorator:
    return attrsetter("_ondelete", at_uninstall)


def onchange(*args: str) -> Decorator:
    if not all(isinstance(arg, str) for arg in args):
        raise TypeError(
            f"onchange() arguments must be field-name strings, got {args!r}"
        )
    _check_field_paths("onchange", args, dotted=False)
    return attrsetter("_onchange", args)


def _check_field_paths(what: str, args: typing.Iterable[str], *, dotted: bool) -> None:
    for arg in args:
        detail = None
        if not arg:
            detail = "is empty"
        elif "," in arg:
            detail = "contains a comma (pass one argument per field)"
        elif arg.strip() != arg or any(c.isspace() for c in arg):
            detail = "contains whitespace"
        elif not dotted and "." in arg:
            detail = "is dotted, which this decorator does not follow"
        else:
            for part in arg.split("."):
                if not part.isidentifier():
                    detail = (
                        "has an empty segment"
                        if not part
                        else f"has an invalid segment {part!r}"
                    )
                    break
        if detail is not None:
            raise ValueError(f"{what}() argument {arg!r} {detail}")


def _check_depends_id(deps: typing.Iterable[str]) -> None:
    for arg in deps:
        if "id" in arg.split("."):
            raise NotImplementedError("Compute method cannot depend on field 'id'.")


@typing.overload
def depends(func: Callable[[BaseModel], Collection[str]], /) -> Decorator: ...


@typing.overload
def depends(*args: str) -> Decorator: ...


def depends(*args: typing.Any) -> Decorator:
    marker: typing.Any
    if args and callable(args[0]):
        if len(args) > 1:
            raise TypeError(
                "depends() takes either a single callable or field-name "
                f"strings, not both (extra arguments {args[1:]!r} would be "
                "silently ignored)"
            )
        original = args[0]

        @wraps(original)
        def _depends_callable(self: typing.Any) -> tuple[str, ...]:
            deps = tuple(original(self))
            _check_depends_id(deps)
            return deps

        marker = _depends_callable
    else:
        if not all(isinstance(arg, str) for arg in args):
            raise TypeError(
                "depends() arguments must be dot-separated field-name "
                f"strings, got {args!r}"
            )
        _check_field_paths("depends", args, dotted=True)
        _check_depends_id(args)
        marker = args
    return attrsetter("_depends", marker)


def depends_context(*args: str) -> Decorator:
    if not all(isinstance(arg, str) for arg in args):
        raise TypeError(
            f"depends_context() arguments must be context-key strings, got {args!r}"
        )
    _check_field_paths("depends_context", args, dotted=False)
    return attrsetter("_depends_context", args)


def autovacuum[F: Callable[..., typing.Any]](method: F) -> F:
    if not method.__name__.startswith("_"):
        raise TypeError(
            f"{method.__name__}: autovacuum methods must be private (start with '_')"
        )
    return stamp(method, _autovacuum=True)


@typing.overload
def job[F: Callable[..., typing.Any]](
    method: F,
    /,
    *,
    channel: str = ...,
    priority: int = ...,
    max_retries: int = ...,
    max_defers: int = ...,
    idle_timeout: int | None = ...,
    trailing_run: bool = ...,
) -> F: ...


@typing.overload
def job(
    method: None = None,
    /,
    *,
    channel: str = ...,
    priority: int = ...,
    max_retries: int = ...,
    max_defers: int = ...,
    idle_timeout: int | None = ...,
    trailing_run: bool = ...,
) -> Decorator: ...


def job(
    method: Callable[..., typing.Any] | None = None,
    /,
    *,
    channel: str = "root",
    priority: int = 10,
    max_retries: int = 5,
    max_defers: int = 100,
    idle_timeout: int | None = None,
    trailing_run: bool = False,
) -> Callable[..., typing.Any]:

    def decorate[F: Callable[..., typing.Any]](func: F) -> F:
        if not func.__name__.startswith("_"):
            raise TypeError(
                f"{func.__name__}: job methods must be private (start with '_')"
            )
        if idle_timeout is not None and idle_timeout <= 0:
            raise ValueError(f"{func.__name__}: idle_timeout must be positive")
        return stamp(
            func,
            _job_config={
                "channel": channel,
                "priority": priority,
                "max_retries": max_retries,
                "max_defers": max_defers,
                "idle_timeout": idle_timeout,
                "trailing_run": trailing_run,
            },
        )

    if method is not None:
        return decorate(method)
    return decorate


def model[F: Callable[..., typing.Any]](method: F) -> F:
    return stamp(method, _api_model=True)


def private[F: Callable[..., typing.Any]](method: F) -> F:
    return stamp(method, _api_private=True)


def readonly[F: Callable[..., typing.Any]](method: F) -> F:
    return stamp(method, _readonly=True)


def is_readonly(model_class: type, method_name: str) -> bool:
    for cls in model_class.__mro__:
        method = cls.__dict__.get(method_name)
        if method is not None and hasattr(method, "_readonly"):
            return bool(method._readonly)
    return False


def deprecated(reason: str) -> Decorator:
    if not isinstance(reason, str):
        msg = (
            "Expected an object of type str for 'reason', not "
            f"{type(reason).__name__!r}"
        )
        raise TypeError(msg)

    def decorator(method: C) -> C:
        @wraps(method)
        def wrapper(*args: object, **kwargs: object) -> object:
            _debug.logic(
                "decorators.deprecated_called",
                method=method.__qualname__,
                reason=reason,
            )
            warnings.warn(
                f"Call to deprecated method {method.__qualname__}: {reason}",
                DeprecationWarning,
                stacklevel=2,
            )
            return method(*args, **kwargs)

        return typing.cast("C", stamp(wrapper, __deprecated__=reason))

    return decorator


def model_create_multi[T](
    method: Callable[[T, list[ValuesType]], T],
) -> Callable[[T, list[ValuesType] | ValuesType], T]:

    @wraps(method)
    def create(self: T, vals_list: list[ValuesType] | ValuesType) -> T:
        if isinstance(vals_list, Mapping):
            _debug.logic(
                "decorators.create_single_vals_wrapped",
                model=getattr(self, "_name", None),
                method=method.__qualname__,
            )
            vals_list = [vals_list]
        return method(self, vals_list)

    return stamp(create, _api_model=True)
