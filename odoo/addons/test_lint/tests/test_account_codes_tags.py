import csv
import functools
import importlib.util
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

from odoo.modules import Manifest

from . import lint_case
from ._xml_identity import PARSER

_logger = logging.getLogger(__name__)

TAG_MODEL = "account.account.tag"
XML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


@functools.cache
def report_engines():
    manifest = Manifest.for_addon("account", display_warning=False)
    spec = importlib.util.spec_from_file_location(
        "_test_lint_account_report_engines",
        Path(manifest.path, "tools", "report_engines.py"),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@dataclass(frozen=True, slots=True)
class FormulaSite:
    module: str
    path: str
    line: int
    formula: str
    position: tuple[int, int]


@dataclass(frozen=True, slots=True)
class ShippedData:
    tags: dict[str, tuple[int, int]]
    formulas: tuple[FormulaSite, ...]


def _qualify(module: str, xmlid: str) -> str:
    return xmlid if "." in xmlid else f"{module}.{xmlid}"


def _formula_fields(record: etree._Element):
    if record.get("model") == "report.formula.line":
        yield from record.findall("field[@name='account_codes_formula']")
    elif record.get("model") == "report.formula.expression":
        engine = record.find("field[@name='engine']")
        if engine is not None and (engine.text or "").strip() == "account_codes":
            yield from record.findall("field[@name='formula']")


def _read_module(manifest) -> tuple[dict[str, tuple[int, int]], list[FormulaSite]]:
    tags: dict[str, tuple[int, int]] = {}
    formulas: list[FormulaSite] = []
    files = [*manifest.declared.get("data", ()), *manifest.declared.get("demo", ())]
    for index, relative in enumerate(files):
        path = Path(manifest.path, relative)
        if path.suffix == ".csv" and path.stem == TAG_MODEL:
            try:
                with path.open(encoding="utf-8", newline="") as handle:
                    for row, values in enumerate(csv.DictReader(handle)):
                        if xmlid := values.get("id"):
                            tags[_qualify(manifest.name, xmlid)] = (index, row)
            except OSError:
                continue
        elif path.suffix == ".xml":
            try:
                root = etree.parse(str(path), PARSER).getroot()
            except OSError, etree.XMLSyntaxError:
                continue
            for record in root.iter("record"):
                if record.get("model") == TAG_MODEL and (xmlid := record.get("id")):
                    tags[_qualify(manifest.name, xmlid)] = (index, record.sourceline)
                formulas.extend(
                    FormulaSite(
                        manifest.name,
                        str(path),
                        field.sourceline,
                        " ".join((field.text or "").split()),
                        (index, field.sourceline),
                    )
                    for field in _formula_fields(record)
                )
    return tags, formulas


@functools.cache
def shipped_data() -> ShippedData:
    tags: dict[str, tuple[int, int]] = {}
    formulas: list[FormulaSite] = []
    for manifest in Manifest.get_all_addon_manifests():
        module_tags, module_formulas = _read_module(manifest)
        tags.update(module_tags)
        formulas.extend(module_formulas)
    return ShippedData(tags, tuple(formulas))


def raw_tag_references() -> int:
    total = 0
    for path in lint_case.iter_module_files("*.xml"):
        try:
            text = Path(path).read_text(encoding="utf-8")
        except OSError, UnicodeDecodeError:
            continue
        if "account_codes" in text:
            total += XML_COMMENT.sub("", text).count("tag(")
    return total


@functools.cache
def dependency_closure(module: str) -> frozenset[str]:
    manifest = Manifest.for_addon(module, display_warning=False)
    if manifest is None:
        return frozenset({module})
    return frozenset({module}).union(
        *(dependency_closure(name) for name in manifest.get("depends", ()))
    )


def problems(
    site: FormulaSite, tags: dict[str, tuple[int, int]], closure=dependency_closure
) -> list[str]:
    engines = report_engines()
    try:
        terms = engines.parse_account_codes_formula(site.formula)
    except engines.AccountCodesFormulaError as error:
        return [f"unparsable term {error.token!r}"]
    found = []
    for tag in (tag for term in terms for tag in term.tags):
        if tag.id:
            found.append(
                f"{tag.token} names a database id, which no other database shares"
            )
        if not tag.ref:
            continue
        module = tag.ref.partition(".")[0]
        if module not in closure(site.module):
            found.append(f"{tag.token}: {module} is not a dependency of {site.module}")
        elif tag.ref not in tags:
            found.append(f"{tag.token}: no {TAG_MODEL} record defines it")
        elif module == site.module and tags[tag.ref] > site.position:
            found.append(f"{tag.token}: defined after the formula that reads it")
    return found


class TestAccountCodesTags(lint_case.LintCase):
    def test_every_shipped_account_codes_tag_resolves(self):
        data = shipped_data()
        found: dict[str, list[str]] = {}
        references = 0
        for site in data.formulas:
            references += site.formula.count("tag(")
            for problem in problems(site, data.tags):
                found.setdefault(lint_case.repo_of(site.path), []).append(
                    f"{site.path}:{site.line}: {problem}"
                )
        _logger.info(
            "checked %s account_codes formula(s) holding %s tag reference(s) "
            "against %s shipped %s record(s)",
            len(data.formulas),
            references,
            len(data.tags),
            TAG_MODEL,
        )
        self.assertEqual(
            references,
            raw_tag_references(),
            "the scan missed tag() references the shipped report data holds",
        )
        self.assert_ratchet_per_repository(
            found,
            "lint_account_codes_tags",
            "account_codes formula term(s) in <repo> naming a tag the install "
            "cannot resolve",
            "A tag() that resolves to nothing matches no account, so the report "
            "line reads zero and nothing raises. Point it at a tag a dependency "
            "ships, load the tag before the report in the manifest, or spell the "
            "accounts as code prefixes.",
        )

    def test_the_rules_catch_each_way_a_reference_breaks(self):
        tags = {"base_tags.tag_a": (0, 1), "rep.tag_late": (3, 1), "rep.tag_ok": (0, 9)}

        def site(formula):
            return FormulaSite("rep", "rep/data/report.xml", 1, formula, (1, 1))

        cases = {
            "tag(base_tags.tag_a)": [],
            "-tag(rep.tag_ok) + 60": [],
            "tag(rep.tag_missing)": ["no account.account.tag"],
            "tag(rep.tag_late)": ["defined after"],
            "tag(sk.account_tag_pl_IX_1)": ["sk is not a dependency"],
            "tag(42)": ["database id"],
            "6+?": ["unparsable"],
            "60[tag(rep.tag_missing)]": ["no account.account.tag"],
            r"60[tag(rep.tag_ok)]\(tag(rep.tag_late))": ["defined after"],
            r"60\(601,tag(other.tag_x))": ["other is not a dependency"],
            "60[tag(foo)]": ["unparsable"],
        }
        for formula, expected in cases.items():
            with self.subTest(formula=formula):
                found = problems(
                    site(formula), tags, lambda module: frozenset({"rep", "base_tags"})
                )
                self.assertEqual(len(found), len(expected), found)
                for needle, problem in zip(expected, found, strict=True):
                    self.assertIn(needle, problem)
