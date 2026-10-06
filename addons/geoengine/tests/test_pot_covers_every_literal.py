import ast
import pathlib
import re

from odoo.tests import TransactionCase, tagged

MODULE_ROOT = pathlib.Path(__file__).resolve().parent.parent
POT = MODULE_ROOT / "i18n/geoengine.pot"

_MSGID = re.compile(r'^msgid ((?:"(?:[^"\\]|\\.)*"\s*)+)', re.MULTILINE)
_QUOTED = re.compile(r'"((?:[^"\\]|\\.)*)"')


def _translatable_literals(path):
    for node in ast.walk(ast.parse(path.read_text("utf-8"))):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = (
            func.attr
            if isinstance(func, ast.Attribute)
            else func.id
            if isinstance(func, ast.Name)
            else None
        )
        if name != "_" or not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            yield first.value


def _pot_msgids(pot_text):
    for match in _MSGID.finditer(pot_text):
        joined = "".join(_QUOTED.findall(match.group(1)))
        yield joined.replace("\\n", "\n").replace('\\"', '"')


@tagged("post_install", "-at_install", "geoengine_audit")
class TestPotCoversEveryLiteral(TransactionCase):
    def test_every_translatable_literal_has_a_msgid(self):
        msgids = set(_pot_msgids(POT.read_text("utf-8")))
        missing = {}
        for path in sorted(MODULE_ROOT.rglob("*.py")):
            if "static/lib" in path.as_posix():
                continue
            absent = sorted(
                literal
                for literal in _translatable_literals(path)
                if literal not in msgids
            )
            if absent:
                missing[path.relative_to(MODULE_ROOT).as_posix()] = absent

        self.assertFalse(
            missing,
            "translatable literals with no msgid in i18n/geoengine.pot:\n  "
            + "\n  ".join(
                f"{name}: {literals}" for name, literals in sorted(missing.items())
            )
            + "\n\nRegenerate with: odoo-bin i18n export geoengine -l pot -d <db>",
        )
