import pathlib
import re

from odoo.tests import TransactionCase, tagged

MODULE_ROOT = pathlib.Path(__file__).resolve().parent.parent
REPO_ROOT = MODULE_ROOT.parent

CONSUMERS = ("device_gps_geoengine", "geoengine_demo", "geoengine_l10n_mx")

ENTRY_POINTS = frozenset(
    {
        "setup",
        "start",
        "load",
        "constructor",
        "getLayerData",
        "createLayer",
        "getName",
        "addFeatures",
        "parse",
        "displayValue",
        "get",
        "set",
        "hash",
    }
)

_DECLARATION = re.compile(
    r"^    (?:static\s+)?(?:async\s+)?(?:get\s+|set\s+)?([a-zA-Z_][\w$]*)\s*\(",
    re.MULTILINE,
)


@tagged("post_install", "-at_install", "geoengine_audit")
class TestNoDeadJs(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sources = {}
        for root, patterns in (
            (MODULE_ROOT / "static/src", ("*.js", "*.xml")),
            (MODULE_ROOT / "static/tests", ("*.js",)),
        ):
            for pattern in patterns:
                for path in root.rglob(pattern):
                    cls.sources[path] = path.read_text(encoding="utf-8")
        for consumer in CONSUMERS:
            static = REPO_ROOT / consumer / "static"
            if not static.exists():
                continue
            for pattern in ("*.js", "*.xml"):
                for path in static.rglob(pattern):
                    cls.sources[path] = path.read_text(encoding="utf-8")

    def test_no_method_is_declared_and_never_called(self):
        haystack = "\n".join(
            source
            for path, source in self.sources.items()
            if "/static/tests/" not in path.as_posix()
        )
        dead = []
        for path, source in self.sources.items():
            if path.suffix != ".js" or "/static/src/" not in path.as_posix():
                continue
            for name in set(_DECLARATION.findall(source)):
                if name in ENTRY_POINTS:
                    continue
                if len(re.findall(rf"\b{re.escape(name)}\b", haystack)) < 2:
                    dead.append(f"{path.relative_to(MODULE_ROOT)}: {name}()")

        self.assertFalse(
            sorted(dead),
            "declared and never called anywhere:\n  "
            + "\n  ".join(sorted(dead))
            + "\n\nCall it, or delete it. Add it to ENTRY_POINTS only if "
            "something outside this module's source calls it.",
        )
