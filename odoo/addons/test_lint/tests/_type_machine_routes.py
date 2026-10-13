
import argparse
import ast
import re
import sys
from pathlib import Path

MACHINE_AUTH = frozenset({"bearer", "receiver"})
MACHINE_TYPE = "json2"

CONVERTERS = {
    "int": "int",
    "float": "float",
    "string": "str",
    "path": "str",
    "any": "str",
}
_RULE_ARG_RE = re.compile(
    r"<(?:(?P<converter>[a-zA-Z_][\w]*)(?:\([^>]*\))?:)?(?P<name>\w+)>"
)


def _route_calls(function):
    for decorator in function.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        func = decorator.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name == "route":
            yield decorator


def _constants(call):
    return {
        keyword.arg: keyword.value.value
        for keyword in call.keywords
        if keyword.arg and isinstance(keyword.value, ast.Constant)
    }


def _rules(call):
    rules = []
    for node in call.args:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            rules.append(node.value)
        elif isinstance(node, ast.List | ast.Tuple):
            rules.extend(
                item.value
                for item in node.elts
                if isinstance(item, ast.Constant) and isinstance(item.value, str)
            )
    for keyword in call.keywords:
        if keyword.arg == "route":
            if isinstance(keyword.value, ast.Constant):
                rules.append(keyword.value.value)
            elif isinstance(keyword.value, ast.List | ast.Tuple):
                rules.extend(
                    item.value
                    for item in keyword.value.elts
                    if isinstance(item, ast.Constant)
                )
    return rules


def _path_types(call):
    types = {}
    for rule in _rules(call):
        for match in _RULE_ARG_RE.finditer(rule):
            converter = match.group("converter") or "string"
            types[match.group("name")] = CONVERTERS.get(converter)
    return types


def _named_args(function):
    args = function.args
    return [*args.posonlyargs, *args.args, *args.kwonlyargs][1:]


LITERAL_TYPES = {bool: "bool", int: "int", float: "float", str: "str"}


def _defaults(function):
    args = function.args
    positional = [*args.posonlyargs, *args.args]
    defaults = dict(
        zip(
            positional[len(positional) - len(args.defaults) :],
            args.defaults,
            strict=True,
        )
    )
    defaults.update(dict(zip(args.kwonlyargs, args.kw_defaults, strict=True)))
    return defaults


def _annotate(lines, function, path_types):
    edits = []
    defaults = _defaults(function)
    for arg in _named_args(function):
        if arg.annotation is not None:
            continue
        annotation = path_types.get(arg.arg)
        if annotation is None:
            default = defaults.get(arg)
            if (
                isinstance(default, ast.Constant)
                and type(default.value) in LITERAL_TYPES
            ):
                annotation = LITERAL_TYPES[type(default.value)]
        if annotation is None:
            return None
        default = defaults.get(arg)
        if isinstance(default, ast.Constant) and default.value is None:
            annotation = f"{annotation} | None"
        edits.append((arg.lineno - 1, arg.col_offset + len(arg.arg), f": {annotation}"))
    for lineno, col, text in sorted(edits, reverse=True):
        line = lines[lineno]
        lines[lineno] = line[:col] + text + line[col:]
    return True


def _add_typed(lines, call):
    for keyword in call.keywords:
        if keyword.arg == "typed":
            value = keyword.value
            if value.lineno != value.end_lineno:
                return False
            line = lines[value.lineno - 1]
            lines[value.lineno - 1] = (
                line[: value.col_offset] + "True" + line[value.end_col_offset :]
            )
            return True
    anchor = call.keywords[-1] if call.keywords else None
    if anchor is None or anchor.arg is None:
        return False
    end_line = anchor.value.end_lineno - 1
    line = lines[end_line]
    after = anchor.value.end_col_offset
    if call.lineno == call.end_lineno or line[after:].lstrip().startswith(")"):
        lines[end_line] = line[:after] + ", typed=True" + line[after:]
        return True
    indent = len(line) - len(line.lstrip())
    suffix = "," if not line.rstrip().endswith(",") else ""
    lines[end_line] = line.rstrip() + suffix
    lines.insert(end_line + 1, " " * indent + "typed=True,")
    return True


def rewrite(source):
    tree = ast.parse(source)
    lines = source.splitlines()
    todo = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        calls = []
        for call in _route_calls(node):
            keywords = _constants(call)
            if (
                keywords.get("type") != MACHINE_TYPE
                and keywords.get("auth") not in MACHINE_AUTH
            ):
                continue
            if keywords.get("typed") is True and not [
                arg for arg in _named_args(node) if arg.annotation is None
            ]:
                continue
            calls.append((call, keywords))
        if calls:
            todo.append((node, calls))
    if not todo:
        return source, 0, []
    left = []
    done = 0
    for node, calls in sorted(todo, key=lambda item: item[0].lineno, reverse=True):
        path_types = {}
        for call, _keywords in calls:
            path_types.update(_path_types(call))
        if _annotate(lines, node, path_types) is None:
            left.append(node.name)
            continue
        untyped = [
            call
            for call, keywords in sorted(
                calls, key=lambda item: item[0].lineno, reverse=True
            )
            if keywords.get("typed") is not True
        ]
        if not all(_add_typed(lines, call) for call in untyped):
            left.append(node.name)
            continue
        done += 1
    rewritten = "\n".join(lines) + "\n"
    compile(rewritten, "<rewrite>", "exec")
    return rewritten, done, left


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    touched = total = 0
    left = []
    for root in args.paths:
        for path in sorted(Path(root).rglob("*.py")):
            if "/tests/" in str(path) or "/migrations/" in str(path):
                continue
            source = path.read_text()
            try:
                new, done, remaining = rewrite(source)
            except SyntaxError as exc:
                left.append(f"{path}: not rewritten, {exc.msg}")
                continue
            left.extend(f"{path}:{name}" for name in remaining)
            if not done:
                continue
            touched += 1
            total += done
            if not args.dry_run:
                path.write_text(new)
    print(f"{total} route(s) declared in {touched} file(s)")
    if left:
        print(f"{len(left)} route(s) name a parameter the rule does not:")
        for entry in left:
            print(f"  {entry}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
