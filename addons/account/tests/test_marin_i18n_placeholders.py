import re
from pathlib import Path

import polib

from odoo.tests.common import BaseCase

I18N = Path(__file__).parent.parent / "i18n"
FORMAT_FIELD = re.compile(r"(?<!\{)\{([A-Za-z_]\w*)\}(?!\})")
NAMED = re.compile(r"%\(([^)]*)\)[sdfr]")
POSITIONAL = re.compile(r"%(?!\()[-#0 +]*\d*(?:\.\d+)?[sdfr]")


def placeholder_fault(source, translation):
    fields = set(FORMAT_FIELD.findall(source))
    if fields and (extra := set(FORMAT_FIELD.findall(translation)) - fields):
        return f"unknown format fields {sorted(extra)}"
    names = set(NAMED.findall(source))
    if names:
        if set(NAMED.findall(translation)) != names:
            return f"named placeholders differ from {sorted(names)}"
        try:
            translation % dict.fromkeys(names, 1)
        except (TypeError, ValueError, KeyError) as error:
            return f"{type(error).__name__}: {error}"
        return None
    if count := len(POSITIONAL.findall(source.replace("%%", ""))):
        try:
            source % ((1,) * count)
        except TypeError, ValueError:
            return None
        try:
            translation % ((1,) * count)
        except (TypeError, ValueError) as error:
            return f"{type(error).__name__}: {error}"
    return None


class TestMarinI18nPlaceholders(BaseCase):
    def test_translations_format_with_the_arguments_of_their_source(self):
        faults = [
            (po_path.name, entry.msgid, fault)
            for po_path in sorted(I18N.glob("*.po"))
            for entry in polib.pofile(str(po_path))
            if not entry.obsolete
            and entry.msgstr
            and (fault := placeholder_fault(entry.msgid, entry.msgstr))
        ]
        self.assertEqual(faults, [])

    def test_the_check_sees_each_kind_of_fault(self):
        cases = {
            ("Cut-off {label}", "Mejna vrednost {oznaka}"): True,
            ("Entry to %(destination)s", "Vnos v %s"): True,
            ("Bad %(vat_label)s", "Slabo %(vat_label) x"): True,
            ("Draft (%(amount)s)", "Osnutek"): True,
            ("Balance of '%s'", "Saldo"): True,
            ("Balance of '%s'", "Saldo '%s'"): False,
            ("Regex {4} part", "Regex {4} del"): False,
            ("30% Advance", "30% d'avançament"): False,
        }
        for (source, translation), faulty in cases.items():
            with self.subTest(source=source, translation=translation):
                self.assertEqual(bool(placeholder_fault(source, translation)), faulty)
