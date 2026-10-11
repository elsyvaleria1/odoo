"""Two addons that patch the same key of the same target, neither depending on
the other, run in an order no manifest states: bundle order makes one the
other's ``super``. Such a pair is reviewed as order-independent and listed in
patch_order_reviewed.json (the pairs found when this gate came in are its
baseline, held by a floor), or one of the addons depends on the other.

An addon that depends on another is loaded after it, so its patch wraps the
other's by construction and is not reported. The targets are named by the
module that exports them (``@mail/core/common/thread:Thread.prototype``); a
patch whose target or extension the scanner cannot name statically (a class
passed as a parameter, an instance) is counted per repository instead.
"""

import functools
import itertools
import shutil
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path

from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads
from odoo.modules import Manifest

from . import _js_sources, lint_case

_SCANNER = Path(__file__).parent / "js" / "patch_scan.mjs"
_REVIEWED_PATH = Path(__file__).parent / "patch_order_reviewed.json"


def scan_patches(files: list[dict]) -> dict:
    node = shutil.which("node")
    if not node:
        raise RuntimeError("the patch scanner needs node on PATH")
    odoo_root = Path(__file__).parents[4]
    with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8") as listing:
        listing.write(json_dumps(files))
        listing.flush()
        completed = subprocess.run(
            [node, str(_SCANNER), listing.name],
            capture_output=True,
            text=True,
            cwd=odoo_root,
            check=False,
            timeout=300,
        )
    if completed.returncode:
        raise RuntimeError(f"the patch scanner failed: {completed.stderr[-2000:]}")
    return json_loads(completed.stdout)


def _source_files() -> list[dict]:
    files = []
    for addon, path, _source in _js_sources.addon_js_outside_lib():
        parts = path.as_posix().split("/static/src/", 1)
        if len(parts) == 2:
            module = f"@{addon}/{parts[1].removesuffix('.js')}"
            files.append({"addon": addon, "module": module, "path": str(path)})
    return files


@functools.cache
def _tree_scan() -> dict:
    return scan_patches(_source_files())


@functools.cache
def depends_closure(addon: str) -> frozenset[str]:
    seen = set()
    todo = [addon]
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        seen.add(name)
        manifest = Manifest.for_addon(name, display_warning=False)
        todo.extend(manifest.get("depends", ()) if manifest else ())
    return frozenset(seen)


def unordered_pairs(patches: list[dict], closure=depends_closure) -> set[str]:
    addons_by_key = defaultdict(set)
    for patch in patches:
        if patch["target"] and patch["keys"] is not None:
            for key in patch["keys"]:
                addons_by_key[patch["target"], key].add(patch["addon"])
    pairs = set()
    for (target, key), addons in addons_by_key.items():
        for first, second in itertools.combinations(sorted(addons), 2):
            if first not in closure(second) and second not in closure(first):
                pairs.add(f"{target} :: {key} :: {first} | {second}")
    return pairs


def entry_addons(entry: str) -> tuple[str, str]:
    first, second = entry.rsplit(" :: ", 1)[1].split(" | ")
    return first, second


class TestPatchOrder(lint_case.LintCase):
    def _scan_sources(self, sources: dict[str, str]) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            files = []
            for module, text in sources.items():
                addon = module.split("/", 1)[0].removeprefix("@")
                path = Path(tmp) / f"{module.replace('/', '_')}.js"
                path.write_text(text, encoding="utf-8")
                files.append({"addon": addon, "module": module, "path": str(path)})
            return scan_patches(files)

    def test_targets_are_named_by_the_module_exporting_them(self):
        result = self._scan_sources(
            {
                "@mod_a/patches": """
                    import { patch } from "@web/core/utils/patch";
                    import { Thread as T } from "@mail/core/common/thread";
                    import { registry } from "@web/core/registry";
                    import { thing } from "./thing";
                    const actions = registry.category("mail.thread/actions");
                    const mixin = { b() {} };
                    const factory = () => ({ c() {} });
                    patch(T.prototype, { a() {}, get g() { return 1; } });
                    patch(T, mixin);
                    patch(actions.get("call"), factory());
                    patch(thing.Record.prototype, { d() {} });
                    function helper(Cls) { patch(Cls.prototype, { e() {} }); }
                    import * as lib from "@odoo/lib";
                    const { Store } = lib.stores;
                    patch(Store.prototype, { f() {} });
                    patch(lib.stores.Other.prototype, { g() {} });
                """,
            }
        )
        self.assertEqual(result["errors"], [])
        found = {(p["target"], tuple(p["keys"] or ())) for p in result["patches"]}
        self.assertEqual(
            found,
            {
                ("@mail/core/common/thread:Thread.prototype", ("a", "g")),
                ("@mail/core/common/thread:Thread", ("b",)),
                ("registry:mail.thread/actions/call", ("c",)),
                ("@mod_a/thing:thing.Record.prototype", ("d",)),
                (None, ("e",)),
                ("@odoo/lib:stores.Store.prototype", ("f",)),
                ("@odoo/lib:stores.Other.prototype", ("g",)),
            },
        )

    def test_an_imported_extension_is_read_from_its_module(self):
        result = self._scan_sources(
            {
                "@mod_a/mixin": "export const Mixin = { a() {}, b: 1 };",
                "@mod_b/use": """
                    import { patch } from "@web/core/utils/patch";
                    import { Mixin } from "@mod_a/mixin";
                    import { X } from "@web/x";
                    patch(X.prototype, Mixin);
                """,
            }
        )
        (patch,) = result["patches"]
        self.assertEqual(patch["keys"], ["a", "b"])

    def test_only_addons_neither_depending_on_the_other_pair_up(self):
        closure = {
            "base": {"base"},
            "a": {"a", "base"},
            "b": {"b", "base"},
            "c": {"c", "a", "base"},
        }.__getitem__
        patches = [
            {"addon": addon, "target": "T", "keys": ["k"]} for addon in "abc"
        ] + [{"addon": "a", "target": "T", "keys": ["k"]}]
        self.assertEqual(
            unordered_pairs(patches, closure),
            {"T :: k :: a | b", "T :: k :: b | c"},
            "c depends on a: its patch wraps a's by construction",
        )

    def test_every_unordered_double_patch_is_reviewed(self):
        result = _tree_scan()
        self.assertEqual(result["errors"], [], "sources the scanner cannot parse")
        found = unordered_pairs(result["patches"])
        on_path = {manifest.name for manifest in Manifest.get_all_addon_manifests()}
        data = json_loads(_REVIEWED_PATH.read_text())
        self.assertFalse(
            set(data["reviewed"]) & set(data["baseline"]),
            "a pair is either reviewed or in the baseline",
        )
        listed = {
            entry
            for entry in (*data["reviewed"], *data["baseline"])
            if set(entry_addons(entry)) <= on_path
        }
        self.assertEqual(
            sorted(found - listed),
            [],
            "two addons, neither depending on the other, patch the same key: "
            "their order is the bundle's. Make one depend on the other, or review "
            f"the pair as order-independent and list it in {_REVIEWED_PATH.name}",
        )
        self.assertEqual(
            sorted(listed - found),
            [],
            f"listed pairs no longer found: remove them from {_REVIEWED_PATH.name}",
        )

    def test_the_unreviewed_baseline_only_goes_down(self):
        data = json_loads(_REVIEWED_PATH.read_text())
        self.assert_ratchet(
            data["baseline"],
            "patch_order_baseline",
            f"double patch(es) not yet reviewed in {_REVIEWED_PATH.name}",
            "Review a pair and move it to 'reviewed' with its reason.",
        )

    def test_unnamed_patches_only_go_down(self):
        result = _tree_scan()
        roots = {
            manifest.name: manifest.path
            for manifest in Manifest.get_all_addon_manifests()
        }
        by_repo = defaultdict(list)
        for patch in result["patches"]:
            if not patch["target"] or patch["keys"] is None:
                by_repo[lint_case.repo_of(roots[patch["addon"]])].append(
                    f"{patch['path']}:{patch['line']}"
                )
        self.assert_ratchet_per_repository(
            by_repo,
            "patch_unnamed",
            "patch() call(s) whose target or keys cannot be named in <repo>",
            "Patch a target imported from its module with an object "
            "literal, a module-level const or an exported mixin.",
        )
