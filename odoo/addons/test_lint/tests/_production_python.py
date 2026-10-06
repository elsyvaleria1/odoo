import ast
import functools
from collections.abc import Callable, Iterable
from pathlib import Path

from odoo.modules import Manifest

from . import _parallel, lint_case

# where elevation is the kernel's or not production code at all
SKIPPED_PARTS = frozenset({"tests", "migrations", "upgrades", "populate", "static"})

type Source = tuple[str, str, Path]


@functools.cache
def production_sources() -> tuple[Source, ...]:
    # (repo, module, path) of every production Python file on the addons path
    sources = []
    for manifest in Manifest.get_all_addon_manifests():
        root = Path(manifest.path)
        if manifest.name.startswith("test_"):
            continue
        repo = lint_case.repo_of(str(root))
        for path in sorted(root.rglob("*.py")):
            if SKIPPED_PARTS.intersection(path.relative_to(root).parts):
                continue
            sources.append((repo, manifest.name, path))
    return tuple(sources)


def parse(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError, UnicodeDecodeError:
        return None


def _extract_one[T](extract: Callable[[ast.Module], T], path: Path) -> T | None:
    tree = parse(path)
    return None if tree is None else extract(tree)


def extract[T](
    extract: Callable[[ast.Module], T], paths: Iterable[Path]
) -> dict[Path, T | None]:
    # One parse per file, in worker processes, and only what `extract` returns
    # comes back: keeping the trees of every addon cost the run 1.1 GiB at the
    # narrow scope and 1.9 GiB on the full addons path. `extract` must be a
    # module-level function, since each worker imports it by name.
    return _parallel.map_items(
        functools.partial(_extract_one, extract), list(dict.fromkeys(paths))
    )
