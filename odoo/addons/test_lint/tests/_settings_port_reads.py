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
            return None
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
            if not any(start <= offset < end for offset in comments):
                spans.append((start, end, port, node))
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
                print(f"  SKIP  {path}: {exc}")
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
    print(f"{total} read(s) through the settings port in {files} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
