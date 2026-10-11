import ast
import contextlib
import fnmatch
import functools
import inspect
import os
import re
from collections.abc import Iterable, Mapping
from pathlib import Path

from odoo import SUPERUSER_ID, api, tools
from odoo.libs.json import loads as json_loads
from odoo.modules import Manifest
from odoo.modules.registry import Registry
from odoo.tests.common import BaseCase, get_db_name, no_retry

from . import _parallel

_T_CALL_ASSETS_RE = re.compile(r"""t-call-assets=\\?["']([\w.]+)\\?["']""")

URL_FETCHED = frozenset(
    {
        "mail/static/src/discuss/voice_message/worklets/processor.js",
        "mail/static/src/service_worker.js",
        "mail/static/src/worklets/audio_processor.js",
        "mail_telegram/static/src/mini_app/inbox.css",
        "mail_telegram/static/src/mini_app/inbox.js",
        "project_telegram/static/src/mini_app/task_app.css",
        "sign/static/src/css/pdfjs_overrides.css",
        "speech/static/src/worklets/pcm_capture.js",
        "stock_fleet_trace/static/driver/driver.css",
        "web/static/src/module_loader.js",
        "web/static/src/public/database_manager.js",
        "web/static/src/service_worker.js",
        "website/static/src/js/content/cookie_watcher.js",
    }
)


def line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def core_root() -> str:
    return str(Path(tools.config.root_path).parent)


def is_core_path(path: str) -> bool:
    root = core_root()
    return path == root or path.startswith(root + os.sep)


@functools.cache
def repo_of(module_root: str) -> str:
    if is_core_path(module_root):
        return "odoo"
    path = Path(module_root)
    return next(
        (parent.name for parent in path.parents if (parent / ".git").exists()),
        path.parent.name,
    )


@functools.cache
def repositories() -> tuple[str, ...]:
    return tuple(
        sorted({repo_of(str(m.path)) for m in Manifest.get_all_addon_manifests()})
    )


_LAYERS = {
    "odoo": ("odoo",),
    "enterprise": ("odoo", "enterprise"),
    "l10n": ("odoo", "l10n"),
    "agromarin": ("odoo", "l10n", "agromarin"),
}


def visible(repo: str) -> tuple[str, ...]:
    return _LAYERS.get(repo, ("odoo", repo))


def repository_gate(gate: str, repo: str) -> str:
    return f"{gate}_{repo.replace('-', '_')}"


@functools.cache
def framework_paths() -> tuple[str, ...]:
    root = Path(tools.config.root_path)
    addons = root / "addons"
    return tuple(
        str(path)
        for path in sorted(root.rglob("*.py"))
        if addons not in path.parents and "__pycache__" not in path.parts
    )


def get_odoo_module_name(python_module_name: str) -> str:
    if python_module_name.startswith("odoo.addons."):
        return python_module_name.split(".")[2]
    if python_module_name == "odoo.models":
        return "odoo"
    return python_module_name


def _module_roots(modules: tuple[str, ...] | None = None) -> list[str]:
    if modules is None:
        return [m.path for m in Manifest.get_all_addon_manifests()]
    return [m.path for name in modules if (m := Manifest.for_addon(name))]


@functools.cache
def module_roots_by_repository() -> tuple[tuple[str, str], ...]:
    return tuple((root, repo_of(root)) for root in _module_roots())


@functools.cache
def module_file_paths(modules: tuple[str, ...] | None = None) -> tuple[str, ...]:
    return tuple(
        str(dirpath / name)
        for modroot in _module_roots(modules)
        for dirpath, _, filenames in Path(modroot).walk()
        for name in filenames
    )


def iter_module_files(*globs: str, modules=None):
    for path in module_file_paths(None if modules is None else tuple(modules)):
        if all(fnmatch.fnmatch(path, glob) for glob in globs):
            yield path


def core_xml_files() -> list[str]:
    return [path for path in iter_module_files("*.xml") if is_core_path(path)]


@functools.cache
def core_module_names() -> frozenset[str]:
    return frozenset(
        manifest.name
        for manifest in Manifest.get_all_addon_manifests()
        if is_core_path(str(manifest.path))
    )


@functools.cache
def _core_data_files() -> tuple[Path, ...]:
    from . import _pretty_xml

    return tuple(
        path for path in map(Path, core_xml_files()) if _pretty_xml.is_formattable(path)
    )


def core_data_files() -> list[Path]:
    return list(_core_data_files())


def core_module_roots() -> list[str]:
    return [path for path in _module_roots() if is_core_path(path)]


def _class_attribute(node: ast.ClassDef, name: str) -> ast.expr | None:
    for statement in node.body:
        if not isinstance(statement, ast.Assign):
            continue
        for target in statement.targets:
            if isinstance(target, ast.Name) and target.id == name:
                return statement.value
    return None


def _string(node: ast.expr | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


type ModelDeclarations = tuple[tuple[str, ...], tuple[tuple[str, str], ...]]


def _model_declarations(tree: ast.AST) -> ModelDeclarations:
    names: list[str] = []
    inherits: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        name = _string(_class_attribute(node, "_name"))
        if name is not None:
            names.append(name)
        parents = _class_attribute(node, "_inherits")
        model = name or _string(_class_attribute(node, "_inherit"))
        if model is None or not isinstance(parents, ast.Dict):
            continue
        inherits.extend(
            (model, parent)
            for key in parents.keys
            if (parent := _string(key)) is not None
        )
    return tuple(names), tuple(inherits)


def declared_model_names(source: str) -> tuple[str, ...]:
    return _model_declarations(ast.parse(source))[0]


def declared_model_inherits(source: str) -> tuple[tuple[str, str], ...]:
    return _model_declarations(ast.parse(source))[1]


def _declarations_of(path: str) -> ModelDeclarations:
    try:
        return _model_declarations(ast.parse(Path(path).read_bytes(), path))
    except OSError, SyntaxError, ValueError:
        return (), ()


@functools.cache
def model_declarations() -> dict[str, ModelDeclarations]:
    return _parallel.map_items(
        _declarations_of,
        [
            path
            for path in module_file_paths()
            if path.endswith(".py") and "/static/" not in path
        ],
    )


@functools.cache
def declared_models() -> frozenset[str]:
    return frozenset(
        name for names, _inherits in model_declarations().values() for name in names
    )


@functools.cache
def declared_inherits() -> dict[str, frozenset[str]]:
    parents: dict[str, set[str]] = {}
    for _names, inherits in model_declarations().values():
        for model, parent in inherits:
            parents.setdefault(model, set()).add(parent)
    return {model: frozenset(found) for model, found in parents.items()}


_FLOORS_PATH = Path(__file__).with_name("floors.json")


@functools.cache
def _floors() -> dict[str, int]:
    with _FLOORS_PATH.open(encoding="utf-8") as handle:
        return json_loads(handle.read())


def baseline_floor(gate: str) -> int:
    return _floors().get(gate, 0)


@no_retry
class LintCase(BaseCase):
    _module_roots = staticmethod(_module_roots)
    iter_module_files = staticmethod(iter_module_files)

    def assert_ratchet(
        self, findings, gate: str, what: str, fix: str, *, exact: bool = True
    ) -> None:
        if not isinstance(gate, str):
            raise TypeError(
                f"assert_ratchet takes a gate name, not {gate!r}. A floor belongs "
                f"in {_FLOORS_PATH.name}, beside this file."
            )
        floor = baseline_floor(gate)
        found = list(findings)
        if len(found) > floor:
            self.fail(
                f"{len(found)} {what}, floor is {floor} ({gate}). {fix}\n"
                + "\n".join(f"  {item}" for item in sorted(map(str, found))[:200])
                + (f"\n  ... and {len(found) - 200} more" if len(found) > 200 else "")
            )
        if exact and len(found) < floor:
            self.fail(
                f"{len(found)} {what} but the committed floor is {floor}. The debt "
                f"went down -- lower {gate} to {len(found)} in {_FLOORS_PATH.name} "
                f"in this same change."
            )

    def assert_ratchet_per_repository(
        self, found: Mapping[str, Iterable], gate: str, what: str, fix: str
    ) -> None:
        for repo in repositories():
            with self.subTest(repo=repo):
                self.assert_ratchet(
                    found.get(repo, ()),
                    repository_gate(gate, repo),
                    what.replace("<repo>", repo),
                    fix,
                )

    @staticmethod
    def served_bundle_names(env) -> list[str]:
        installed = frozenset(
            env["ir.module.module"].search([("state", "=", "installed")]).mapped("name")
        )
        return list(_served_bundle_names(installed, env))

    @staticmethod
    @contextlib.contextmanager
    def superuser_env():
        with Registry(get_db_name()).cursor() as cr:
            yield api.Environment(cr, SUPERUSER_ID, {})


def _served_bundle_names(installed: frozenset[str], env) -> tuple[str, ...]:
    cached = _SERVED_BUNDLES.get(installed)
    if cached is None:
        cached = _SERVED_BUNDLES[installed] = _compute_served_bundle_names(
            installed, env
        )
    return cached


_SERVED_BUNDLES: dict[frozenset[str], tuple[str, ...]] = {}


def _compute_served_bundle_names(installed: frozenset[str], env) -> tuple[str, ...]:
    names = set()
    included = set()
    built = set()
    for manifest in Manifest.get_all_addon_manifests():
        if manifest.name not in installed:
            continue
        assets = manifest.get("assets") or {}
        names.update(assets)
        for entries in assets.values():
            for entry in entries:
                if (
                    isinstance(entry, (list, tuple))
                    and len(entry) > 1
                    and entry[0] == "include"
                ):
                    included.add(entry[1])
        esm = manifest.get("esm") or {}
        built.update(esm.get("bundles") or ())
        built.update(esm.get("standalone_bundles") or ())

    env.cr.execute("SELECT arch_db::text FROM ir_ui_view WHERE arch_db IS NOT NULL")
    linked = {
        name
        for (arch,) in env.cr.fetchall()
        for name in _T_CALL_ASSETS_RE.findall(arch)
    }
    served = (names - included) | (names & linked) | (names & built)
    return tuple(sorted(name for name in served if "." in name))


def iter_registry_methods(registry=None):
    if registry is None:
        registry = Registry(get_db_name())
    for model_name, model_cls in registry.items():
        for method_name, _ in inspect.getmembers(model_cls, inspect.isroutine):
            if method_name.startswith("__"):
                continue
            for parent_class in model_cls.mro()[1:-1]:
                if method_name not in vars(parent_class):
                    continue
                method = getattr(parent_class, method_name, None)
                if callable(method):
                    break
            else:
                continue
            yield model_name, model_cls, method_name, method, parent_class


class NodeVisitor[T]:
    def visit(self, node: ast.AST) -> Iterable[T]:
        visitor = getattr(self, f"visit_{node.__class__.__name__}", self.generic_visit)
        return visitor(node)

    def generic_visit(self, node: ast.AST) -> Iterable[T]:
        for child in ast.iter_child_nodes(node):
            yield from self.visit(child)
