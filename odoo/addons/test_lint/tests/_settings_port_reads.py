"""Read a system setting through the registry's settings port, not an elevated
ir.config_parameter.

    X["ir.config_parameter"].sudo().get_param(key[, default])
    X["ir.config_parameter"].sudo().get_param_int / _float / _bool(key, default)

becomes ``X.registry.settings.get / get_int / get_float / get_bool(X, key,
default)``, which reads the same value through the same model method and hands
the caller no elevated recordset (coding_guidelines.rst §10.9). A bare
``get_param(key)`` answers False when the key is absent, the port None: the
rewrite passes False explicitly. Only an environment spelled as a name or an
attribute chain is rewritten, since the call names it twice.

A file is written only when the rewritten module parses to the tree its
original gives with each call replaced by the port call, and is then laid out
by ``ruff format`` when it was formatted before.

    python _settings_port_reads.py [--dry-run] [--skip PATH ...] <root>...
"""

import argparse
import ast
import copy
import io
import subprocess
import sys
import tokenize
from pathlib import Path

PORT_METHODS = {
    "get_param": "get",
    "get_param_int": "get_int",
    "get_param_float": "get_float",
    "get_param_bool": "get_bool",
}
SKIPPED_PARTS = frozenset({"tests", "migrations", "upgrades"})


def _environment(call: ast.Call) -> ast.expr | None:
    # the X of X["ir.config_parameter"].sudo().<method>(...)
    receiver = call.func.value
    if not (
        isinstance(receiver, ast.Call)
        and isinstance(receiver.func, ast.Attribute)
        and receiver.func.attr == "sudo"
        and not receiver.args
        and not receiver.keywords
    ):
        return None
    return _model_environment(receiver.func.value)


def _model_environment(model: ast.expr) -> ast.expr | None:
    if not (
        isinstance(model, ast.Subscript)
        and isinstance(model.slice, ast.Constant)
        and model.slice.value == "ir.config_parameter"
    ):
        return None
    if not _is_plain(model.value):
        return None
    return model.value


def _is_plain(node: ast.expr) -> bool:
    if isinstance(node, ast.Name):
        return True
    return isinstance(node, ast.Attribute) and _is_plain(node.value)


def _arguments(call: ast.Call) -> tuple[ast.expr, ast.expr | None] | None:
    if len(call.args) > 2 or any(isinstance(arg, ast.Starred) for arg in call.args):
        return None
    values = dict(zip(("key", "default"), call.args, strict=False))
    for keyword in call.keywords:
        if keyword.arg not in ("key", "default") or keyword.arg in values:
            return None
        values[keyword.arg] = keyword.value
    if "key" not in values:
        return None
    return values["key"], values.get("default")


def _port_call(call: ast.Call) -> ast.Call | None:
    methods = PORT_METHODS
    if not (isinstance(call.func, ast.Attribute) and call.func.attr in methods):
        return None
    environment = _environment(call)
    arguments = _arguments(call)
    if environment is None or arguments is None:
        return None
    key, default = arguments
    method = methods[call.func.attr]
    if default is None:
        if method == "get":
            default = ast.Constant(False)
        elif method != "get_bool":
            return None  # get_param_int/_float always take their default
    settings = ast.Attribute(
        ast.Attribute(copy.deepcopy(environment), "registry", ast.Load()),
        "settings",
        ast.Load(),
    )
    args = [
        copy.deepcopy(environment),
        key,
        *([default] if default is not None else []),
    ]
    return ast.Call(ast.Attribute(settings, method, ast.Load()), args, [])


class _Replacer(ast.NodeTransformer):
    # the calls the text rewrite replaced, by position, and nothing else
    def __init__(self, positions: set[tuple[int, int, int, int]]):
        self.positions = positions

    def visit_Call(self, node: ast.Call) -> ast.AST:
        position = (node.lineno, node.col_offset, node.end_lineno, node.end_col_offset)
        if position in self.positions:
            return _port_call(node)
        self.generic_visit(node)
        return node


def _offsets(source: bytes) -> list[int]:
    starts = [0]
    for line in source.splitlines(keepends=True):
        starts.append(starts[-1] + len(line))
    return starts


def _comment_offsets(source: bytes, starts: list[int]) -> list[int]:
    # tokenize counts columns in characters, the AST in bytes
    lines = source.splitlines(keepends=True)
    return [
        starts[token.start[0] - 1]
        + len(lines[token.start[0] - 1].decode()[: token.start[1]].encode())
        for token in tokenize.tokenize(io.BytesIO(source).readline)
        if token.type == tokenize.COMMENT
    ]


def rewrite(source: bytes) -> tuple[bytes, int]:
    tree = ast.parse(source)
    starts = _offsets(source)
    comments = _comment_offsets(source, starts)
    spans = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and (port := _port_call(node)) is not None:
            start = starts[node.lineno - 1] + node.col_offset
            end = starts[node.end_lineno - 1] + node.end_col_offset
            # a comment inside the call would not survive ast.unparse
            if not any(start <= offset < end for offset in comments):
                spans.append((start, end, port, node))
    # an outer rewrite contains its inner ones' text: rewrite the outermost
    spans = [
        span
        for span in spans
        if not any(
            other[0] <= span[0] and span[1] <= other[1] and other is not span
            for other in spans
        )
    ]
    out = source
    for start, end, port, _node in sorted(spans, key=lambda span: -span[0]):
        text = ast.unparse(port)
        out = out[:start] + text.encode() + out[end:]
    if spans:
        positions = {
            (node.lineno, node.col_offset, node.end_lineno, node.end_col_offset)
            for _start, _end, _port, node in spans
        }
        expected = ast.dump(_Replacer(positions).visit(ast.parse(source)))
        if ast.dump(ast.parse(out)) != expected:
            raise ValueError("the rewrite does not parse to the expected tree")
    return out, len(spans)


def _formatted(path: Path) -> bool:
    return (
        subprocess.run(
            [sys.executable, "-m", "ruff", "format", "--check", "--quiet", str(path)],
            check=False,
            capture_output=True,
        ).returncode
        == 0
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("roots", nargs="+")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip", action="append", default=[])
    args = parser.parse_args(argv)
    skip = {Path(path).resolve() for path in args.skip}
    total = files = 0
    for root in args.roots:
        for path in sorted(Path(root).rglob("*.py")):
            if SKIPPED_PARTS.intersection(path.parts) or path.resolve() in skip:
                continue
            source = path.read_bytes()
            if b"ir.config_parameter" not in source:
                continue
            try:
                new, count = rewrite(source)
            except (SyntaxError, ValueError) as exc:
                print(f"  SKIP  {path}: {exc}")  # noqa: T201, RUF100 CLI entry point: stdout is the fixer's report
                continue
            if not count:
                continue
            files += 1
            total += count
            if args.dry_run:
                continue
            was_formatted = _formatted(path)
            path.write_bytes(new)
            if was_formatted:
                subprocess.run(
                    [sys.executable, "-m", "ruff", "format", "--quiet", str(path)],
                    check=True,
                )
    print(f"{total} read(s) through the settings port in {files} file(s)")  # noqa: T201, RUF100 CLI entry point: stdout is the fixer's report
    return 0


if __name__ == "__main__":
    sys.exit(main())
