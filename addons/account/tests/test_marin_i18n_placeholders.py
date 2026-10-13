import re
from pathlib import Path

import polib

from odoo.tests.common import BaseCase

I18N = Path(__file__).parent.parent / "i18n"
PLACEHOLDER_PATTERNS = {
    "format": re.compile(r"(?<!\{)\{([^{}\s]*)\}(?!\})"),
    "percent": re.compile(r"%\(([^)]*)\)[sdfr]"),
}


class TestMarinI18nPlaceholders(BaseCase):
    def test_translations_name_only_placeholders_of_their_source(self):
        mismatches = []
        for po_path in sorted(I18N.glob("*.po")):
            for entry in polib.pofile(str(po_path)):
                if entry.obsolete or not entry.msgstr:
                    continue
                for kind, pattern in PLACEHOLDER_PATTERNS.items():
                    source = set(pattern.findall(entry.msgid))
                    if kind == "format" and not source:
                        continue
                    if extra := set(pattern.findall(entry.msgstr)) - source:
                        mismatches.append((po_path.name, entry.msgid, sorted(extra)))
        self.assertEqual(mismatches, [])
