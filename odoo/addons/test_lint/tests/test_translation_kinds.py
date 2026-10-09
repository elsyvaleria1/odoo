import re
from pathlib import Path

from babel.messages import extract
from lxml import etree

from odoo.modules import Manifest
from odoo.tests import tagged
from odoo.tools.translate import xml_translate

from . import lint_case

PYTHON_EXTRACTOR = "odoo.tools.babel_extractors:extract_python"
SKIPPED_PYTHON_DIRS = ("/tests/", "/migrations/", "/upgrades/")


def _unescape(raw: str) -> str:
    return re.sub(
        r"\\(.)", lambda m: {"n": "\n", "t": "\t"}.get(m.group(1), m.group(1)), raw
    )


def _pot_entries(pot: Path) -> dict[str, list[str]]:
    entries = {}
    for block in pot.read_text(encoding="utf-8").split("\n\n"):
        if re.search(r"^msgctxt", block, re.MULTILINE):
            continue
        found = re.search(r'^msgid ((?:".*"\n?)+)', block + "\n", re.MULTILINE)
        if found:
            msgid = _unescape("".join(re.findall(r'"(.*)"', found.group(1))))
            entries[msgid] = block.split("\n")
    return entries


def _python_msgids(root: Path) -> set[str]:
    msgids = set()
    for path in root.rglob("*.py"):
        if any(part in str(path) for part in SKIPPED_PYTHON_DIRS):
            continue
        with path.open("rb") as source:
            for _lineno, message, _comments, _context in extract.extract(
                PYTHON_EXTRACTOR,
                source,
                keywords={"_": None, "_lt": None},
                options={"encoding": "UTF-8"},
            ):
                message = message[0] if isinstance(message, tuple) else message
                if message:
                    msgids.add(message)
    return msgids


def _view_terms(root: Path, module: str, data_files) -> set[tuple[str, str]]:
    terms = set()
    for relative in data_files:
        path = root / relative
        if path.suffix != ".xml" or not path.exists():
            continue
        try:
            tree = etree.parse(str(path))
        except etree.XMLSyntaxError:
            continue
        for node in tree.iter("template", "record"):
            if node.tag == "record":
                arch = node.find("field[@name='arch']")
                if node.get("model") != "ir.ui.view" or arch is None:
                    continue
                content = "".join(
                    etree.tostring(child, encoding="unicode") for child in arch
                )
            else:
                content = etree.tostring(node, encoding="unicode")
            xmlid = node.get("id")
            if not xmlid:
                continue
            xmlid = xmlid if "." in xmlid else f"{module}.{xmlid}"
            terms.update((term, xmlid) for term in _terms_of(content))
    return terms


def _terms_of(content: str) -> list[str]:
    found = []
    xml_translate(lambda term: found.append(term) or term, f"<div>{content}</div>")
    return found


@tagged("post_install", "-at_install")
class TestTranslationKinds(lint_case.LintCase):
    def test_a_server_string_is_not_translated_as_javascript_only(self):
        # Translations load by kind: a Python string from an odoo-python entry,
        # a view's term from an entry naming that view. A string moved from an
        # interaction into a route or a template keeps an entry that only says
        # odoo-javascript, and renders untranslated everywhere.
        found = []
        for manifest in Manifest.get_all_addon_manifests():
            root = Path(manifest.path)
            pot = root / "i18n" / f"{manifest.name}.pot"
            if not pot.exists():
                continue
            entries = {
                msgid: lines
                for msgid, lines in _pot_entries(pot).items()
                if "#. odoo-javascript" in lines
            }
            if not entries:
                continue
            found.extend(
                f"{manifest.name}: python {msgid!r}"
                for msgid in _python_msgids(root) & entries.keys()
                if "#. odoo-python" not in entries[msgid]
            )
            for term, xmlid in _view_terms(
                root, manifest.name, manifest.get("data") or ()
            ):
                lines = entries.get(term)
                if lines and not any(
                    line.startswith("#: model_terms:ir.ui.view") for line in lines
                ):
                    found.append(f"{manifest.name}: {xmlid} {term!r}")
        self.assert_ratchet(
            found,
            "translation_kind_lost",
            "string(s) used on the server whose .pot entry is odoo-javascript only",
            "Give the entry the kind it is used as, in the .pot and every .po: "
            "odoo-python and the file's reference for a Python string, "
            "model_terms:ir.ui.view,arch_db:<xmlid> for a view's term.",
        )
