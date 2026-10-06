import re
from pathlib import Path

import odoo.tests
from odoo.tools.misc import file_path

import odoo.addons

FA_CSS_DIR = "web/static/src/libs/fontawesome7/css"

RE_DEFINED = re.compile(r"\.(fa-[a-z0-9-]+)")
RE_CLASS_ATTR = re.compile(r'\b(?:t-att-class|t-attf-class|class)\s*=\s*"([^"]*)"')
RE_FA_TOKEN = re.compile(r"^fa-[a-z0-9-]+$")
RE_ICON_ATTR = re.compile(r'\bicon\s*=\s*"([^"]*)"')
RE_STYLED_LITERAL = re.compile(
    r"[\"'`]((?:[a-z0-9-]+ )*(?:fa-solid|fa-regular)(?: [a-z0-9-]+)*)[\"'`]"
)
BRANDS_FACES = {"fa-brands", "fab"}
BRANDS_CSS = "brands.css"
UNSCANNED_DIRS = {"tests", "lib", "libs", "node_modules"}

NON_FA_CLASSES = {
    "fa-small",
}


class TestFontAwesomeIconNames(odoo.tests.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.addons_root = Path(file_path("web/__manifest__.py")).parent.parent
        cls.fa_css_dir = cls.addons_root / FA_CSS_DIR
        cls.scanned_roots = cls._addons_roots()

    @classmethod
    def _addons_roots(cls):
        roots, seen = [], set()
        for path in [str(cls.addons_root), *odoo.addons.__path__]:
            resolved = Path(path).resolve()
            if resolved.is_dir() and resolved not in seen:
                seen.add(resolved)
                roots.append(resolved)
        return roots

    def _defined_class_names(self):
        names = set()
        for css in sorted(self.fa_css_dir.glob("*.css")):
            names |= set(RE_DEFINED.findall(css.read_text(encoding="utf-8")))
        return names

    def _brand_only_glyphs(self):
        by_file = {
            css.name: set(RE_DEFINED.findall(css.read_text(encoding="utf-8")))
            for css in self.fa_css_dir.glob("*.css")
        }
        others = set().union(
            *(names for name, names in by_file.items() if name != BRANDS_CSS)
        )
        return by_file[BRANDS_CSS] - others

    def _scanned_sources(self, suffixes):
        for root in self.scanned_roots:
            for path in root.rglob("*"):
                if path.suffix not in suffixes or UNSCANNED_DIRS & set(path.parts):
                    continue
                try:
                    content = path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                if "fa-" in content:
                    yield str(path.relative_to(root)), content

    def _used_class_names(self):
        used = {}
        for root in self.scanned_roots:
            for path in root.rglob("*.xml"):
                if self.fa_css_dir in path.parents:
                    continue
                try:
                    content = path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                if "fa-" not in content:
                    continue
                for value in RE_CLASS_ATTR.findall(content):
                    if any(c in value for c in "{}#$"):
                        continue
                    for token in value.split():
                        if RE_FA_TOKEN.match(token):
                            used.setdefault(token, set()).add(
                                str(path.relative_to(root))
                            )
        return used

    def test_fontawesome_stylesheets_are_present(self):
        self.assertTrue(self.fa_css_dir.is_dir(), f"missing {FA_CSS_DIR}")
        defined = self._defined_class_names()
        self.assertGreater(len(defined), 4000, "font awesome css looks truncated")
        for expected in ("fa-solid", "fa-spin", "fa-trash", "fa-star-o"):
            self.assertIn(expected, defined)

    def test_every_icon_class_used_in_a_template_is_defined(self):
        defined = self._defined_class_names() | NON_FA_CLASSES
        used = self._used_class_names()
        self.assertGreater(len(used), 100, "icon scan found suspiciously little")
        undefined = {
            name: sorted(files) for name, files in used.items() if name not in defined
        }
        self.assertFalse(
            undefined,
            "these icon classes render no glyph because no stylesheet defines "
            "them — fix the name, or add it to NON_FA_CLASSES if another "
            "library owns it:\n"
            + "\n".join(
                f"  {name}: {', '.join(files)}"
                for name, files in sorted(undefined.items())
            ),
        )

    def test_a_brand_glyph_is_written_in_the_brands_face(self):
        brands = self._brand_only_glyphs()
        self.assertIn("fa-whatsapp", brands)
        self.assertNotIn("fa-bluetooth", brands, "a glyph of both fonts is not a brand")
        offenders = set()
        for name, content in self._scanned_sources({".xml"}):
            for value in RE_CLASS_ATTR.findall(content) + RE_ICON_ATTR.findall(content):
                if any(c in value for c in "{}#$"):
                    continue
                tokens = set(value.split())
                if tokens & brands and not tokens & BRANDS_FACES:
                    offenders.add(f"{name}: {value}")
        for name, content in self._scanned_sources({".js", ".py"}):
            for value in RE_STYLED_LITERAL.findall(content):
                if set(value.split()) & brands:
                    offenders.add(f"{name}: {value}")
        self.assertFalse(
            offenders,
            "a brand glyph is drawn only by the brands font: under fa-solid, "
            "fa-regular or no face it renders blank, and a bare view-button "
            "icon is completed to fa-solid -- write fa-brands:\n"
            + "\n".join(f"  {offender}" for offender in sorted(offenders)),
        )
