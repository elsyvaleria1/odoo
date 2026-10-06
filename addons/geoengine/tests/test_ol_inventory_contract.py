import pathlib
import re

from odoo.tests import TransactionCase, tagged

MODULE_ROOT = pathlib.Path(__file__).resolve().parent.parent
ADDONS_ROOT = MODULE_ROOT.parent
ENTRY = MODULE_ROOT / "static" / "lib" / "ol" / "entry.js"

SEAM_SPECIFIER = "@geoengine/lib/geo_libs"

_OL_REFERENCE = re.compile(
    r"(?<![\w/.$-])ol\.([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)"
)

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"(?<![:/])//[^\n]*")


def strip_comments(source: str) -> str:
    source = _BLOCK_COMMENT.sub("", source)
    return _LINE_COMMENT.sub("", source)


def parse_entry_exports(source: str) -> dict:
    tree: dict = {}

    for match in re.finditer(r"^export \{([^}]*)\};", source, re.MULTILINE):
        for name in _split_keys(match.group(1)):
            tree[name] = None

    for match in re.finditer(r"^export const (\w+) = ", source, re.MULTILINE):
        name = match.group(1)
        body = _balanced_object(source, source.index("{", match.end() - 1))
        tree[name] = _parse_object(body)

    exports = len(re.findall(r"^export ", source, re.MULTILINE))
    if exports != len(re.findall(r"^export \{", source, re.MULTILINE)) + len(
        re.findall(r"^export const ", source, re.MULTILINE)
    ):
        raise ValueError(
            "entry.js uses an export shape this parser does not read; "
            "teach it the new shape rather than leaving the inventory partial."
        )
    return tree


def _split_keys(text: str) -> list[str]:
    return [part.strip() for part in text.split(",") if part.strip()]


def _balanced_object(source: str, start: int) -> str:
    depth = 0
    for index in range(start, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise ValueError("unbalanced object literal in entry.js")


def _parse_object(body: str) -> dict:
    inner = body.strip()[1:-1]
    result: dict = {}
    index = 0
    while index < len(inner):
        match = re.compile(r"\s*([A-Za-z_$][\w$]*)\s*(:)?").match(inner, index)
        if not match:
            break
        key = match.group(1)
        index = match.end()
        if match.group(2):
            rest = inner[index:].lstrip()
            if rest.startswith("{"):
                nested = _balanced_object(inner, inner.index("{", index))
                result[key] = _parse_object(nested)
                index = inner.index("{", index) + len(nested)
            else:
                result[key] = None
                index += len(rest) - len(rest.lstrip())
                index = inner.find(",", index)
                index = len(inner) if index == -1 else index
        else:
            result[key] = None
        comma = inner.find(",", index)
        index = len(inner) if comma == -1 else comma + 1
    return result


def resolve(tree: dict, path: str) -> bool:
    node = tree
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return False
        node = node[part]
        if node is None:
            return True
    return False


def consumer_files() -> list[pathlib.Path]:
    files: list[pathlib.Path] = []
    for addon in sorted(ADDONS_ROOT.iterdir()):
        static_src = addon / "static" / "src"
        if not static_src.is_dir():
            continue
        js_files = list(static_src.rglob("*.js"))
        if any(SEAM_SPECIFIER in f.read_text() for f in js_files) or addon.name == (
            MODULE_ROOT.name
        ):
            files.extend(js_files)
    return files


@tagged("post_install", "-at_install")
class TestOlInventoryContract(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tree = parse_entry_exports(ENTRY.read_text())

    def test_the_inventory_parsed(self):
        self.assertGreater(len(self.tree), 5, "entry.js parsed to almost nothing")
        self.assertTrue(resolve(self.tree, "Map"), "top-level export not parsed")
        self.assertTrue(resolve(self.tree, "layer.Tile"), "aliased key not parsed")
        self.assertTrue(
            resolve(self.tree, "events.condition.click"), "nested key not parsed"
        )

    def test_a_missing_symbol_would_be_caught(self):
        self.assertFalse(resolve(self.tree, "geom.NoSuchGeometry"))
        self.assertFalse(resolve(self.tree, "layer.Nonexistent"))
        self.assertFalse(resolve(self.tree, "layer"))

    def test_the_scanner_sees_real_call_sites_and_not_paths(self):
        sample = """
            // ol.layer.FromAComment
            /* ol.source.AlsoAComment */
            const url = "/geoengine/static/lib/ol/ol.esm.js";
            const layer = new ol.layer.Tile({source: new ol.source.OSM()});
        """
        found = set(_OL_REFERENCE.findall(strip_comments(sample)))
        self.assertEqual(found, {"layer.Tile", "source.OSM"})

    def test_the_shipped_bundle_was_rebuilt_for_the_current_inventory(self):
        bundle = (MODULE_ROOT / "static" / "lib" / "ol" / "ol.esm.js").read_text()
        absent = sorted(
            leaf.split(".")[-1]
            for leaf in self._exported_leaves()
            if leaf.split(".")[-1] not in bundle
        )
        self.assertFalse(
            absent,
            f"{ENTRY.relative_to(MODULE_ROOT)} exports {absent}, which do not "
            "appear in the built ol.esm.js -- the bundle is stale. Run "
            "static/lib/ol/build.sh and commit the result with the entry change.",
        )

    def test_no_export_is_referenced_nowhere_at_all(self):
        mentioned: set[str] = set()
        for path in consumer_files():
            mentioned.update(_OL_REFERENCE.findall(path.read_text()))

        def leaf_for(reference: str) -> str | None:
            node, walked = self.tree, []
            for part in reference.split("."):
                if not isinstance(node, dict) or part not in node:
                    return None
                walked.append(part)
                node = node[part]
                if node is None:
                    return ".".join(walked)
            return None

        reachable = {leaf for leaf in map(leaf_for, mentioned) if leaf}
        orphans = sorted(self._exported_leaves() - reachable)

        self.assertFalse(
            orphans,
            f"{ENTRY.relative_to(MODULE_ROOT)} exports symbols that no consumer "
            f"mentions, in code or in a comment: {orphans}. Each one is bundle "
            "weight bought for nothing -- remove them and re-run build.sh, or "
            "say in the file why they are kept.",
        )

    def _exported_leaves(self) -> set[str]:
        def walk(node, prefix=""):
            found = set()
            for key, value in node.items():
                if isinstance(value, dict):
                    found |= walk(value, f"{prefix}{key}.")
                else:
                    found.add(prefix + key)
            return found

        return walk(self.tree)

    def test_every_referenced_symbol_is_in_the_inventory(self):
        files = consumer_files()
        self.assertTrue(files, "found no consumer JS to check")

        missing: dict[str, set[str]] = {}
        for path in files:
            source = strip_comments(path.read_text())
            for reference in set(_OL_REFERENCE.findall(source)):
                if not resolve(self.tree, reference):
                    missing.setdefault(str(path.relative_to(ADDONS_ROOT)), set()).add(
                        reference
                    )

        self.assertFalse(
            missing,
            "These call sites use OpenLayers symbols that "
            f"{ENTRY.relative_to(MODULE_ROOT)} does not export, so the "
            "tree-shaken bundle does not ship them and they are undefined at "
            f"runtime: { {k: sorted(v) for k, v in missing.items()} }. "
            "Add them to entry.js and re-run its build.sh.",
        )

    def test_the_documented_symbol_count_matches_the_inventory(self):
        measured = len(self._exported_leaves())
        documented = {}
        for rel in ("static/lib/ol/build.sh", "static/lib/versions.json"):
            found = re.findall(r"(\d+) symbols", (MODULE_ROOT / rel).read_text())
            self.assertEqual(
                len(found),
                1,
                f"{rel} should state the symbol count exactly once, not "
                f"{len(found)} times -- this test reads that one figure.",
            )
            documented[rel] = int(found[0])

        wrong = {rel: n for rel, n in documented.items() if n != measured}
        self.assertFalse(
            wrong,
            f"entry.js exports {measured} symbols, but {wrong} says otherwise. "
            "The count is prose in two files and drifts silently every time a "
            "symbol is added or dropped -- update both in the same commit as "
            "the entry change.",
        )
