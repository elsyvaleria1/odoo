import annotationlib
import functools
import importlib
import inspect
from collections.abc import Iterator


def _probe(obj: object, label: str) -> str | None:
    target = inspect.unwrap(obj) if callable(obj) else obj
    if inspect.isfunction(target):
        try:
            annotationlib.get_annotations(target)
        except Exception as e:
            return f"{label}: {type(e).__name__}: {e}"
        return None
    try:
        inspect.signature(obj)
    except (NameError, AttributeError) as e:
        return f"{label}: {type(e).__name__}: {e}"
    except TypeError, ValueError:
        return None
    return None


def _class_callables(cls: type) -> Iterator[tuple[str, object]]:
    for name, value in vars(cls).items():
        if isinstance(value, staticmethod | classmethod):
            yield name, value.__func__
        elif isinstance(value, property):
            for accessor in (value.fget, value.fset, value.fdel):
                if accessor is not None:
                    yield name, accessor
        elif isinstance(value, functools.cached_property):
            yield name, value.func
        elif callable(value):
            yield name, value


def scan_module(modname: str) -> list[str]:
    try:
        m = importlib.import_module(modname)
    except Exception as e:
        return [f"{modname}: import-fail: {type(e).__name__}: {e}"]

    fails: list[str] = []
    for name, obj in list(vars(m).items()):
        if getattr(obj, "__module__", None) != modname:
            continue
        if callable(obj):
            err = _probe(obj, f"{modname}.{name}")
            if err:
                fails.append(err)
        if inspect.isclass(obj):
            for mname, mval in _class_callables(obj):
                if getattr(mval, "__module__", modname) != modname:
                    continue
                err = _probe(mval, f"{modname}.{name}.{mname}")
                if err:
                    fails.append(err)
    return fails


def scan_modules(modnames: list[str]) -> dict[str, list[str]]:
    return {m: fails for m in modnames if (fails := scan_module(m))}
