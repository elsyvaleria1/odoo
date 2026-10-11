import base64
import re

from odoo.tests import tagged
from odoo.tests.css import parse_per_selector

from . import lint_case

COMBINATORS = " >+~"
FUNCTIONAL_PSEUDO_RE = re.compile(r"::?[a-zA-Z-]+\(")
PSEUDO_RE = re.compile(r"::?[a-zA-Z-]+")
OWN_FEATURE_RE = re.compile(r"[.#][A-Za-z_-]")
OWN_ATTRIBUTE_RE = re.compile(r"\[\s*(?!class\b|style\b)[A-Za-z_-]+")


def _compounds(selector: str) -> list[str]:
    compounds, depth, current = [], 0, ""
    for char in selector:
        if char in "([":
            depth += 1
        elif char in ")]":
            depth -= 1
        if char in COMBINATORS and not depth:
            if current:
                compounds.append(current)
            current = ""
        else:
            current += char
    if current:
        compounds.append(current)
    return compounds


def _without_functional_pseudos(compound: str) -> str:
    kept, index = "", 0
    while index < len(compound):
        match = FUNCTIONAL_PSEUDO_RE.match(compound, index)
        if not match:
            kept += compound[index]
            index += 1
            continue
        depth, index = 1, match.end()
        while index < len(compound) and depth:
            depth += {"(": 1, ")": -1}.get(compound[index], 0)
            index += 1
    return kept


def ancestor_has_subject(selector: str) -> str | None:
    compounds = _compounds(selector)
    asked = [index for index, compound in enumerate(compounds) if ":has(" in compound]
    if not asked or asked[0] == len(compounds) - 1:
        return None
    return compounds[-1]


def is_broad_subject(subject: str) -> bool:
    plain = PSEUDO_RE.sub("", _without_functional_pseudos(subject))
    if OWN_ATTRIBUTE_RE.search(plain):
        return False
    return not OWN_FEATURE_RE.search(re.sub(r"\[[^\]]*\]", "", plain))


def broad_ancestor_has_findings(css: str) -> list[str]:
    findings = set()
    for source, selector, _prop, _value in parse_per_selector(css):
        if ":has(" not in selector:
            continue
        subject = ancestor_has_subject(selector)
        if subject is not None and is_broad_subject(subject):
            findings.add(f"{source} {selector}")
    return sorted(findings)


@tagged("post_install", "-at_install")
class TestHasSelectors(lint_case.LintCase):
    def test_what_counts_as_an_ancestor_has(self):
        self.assertIsNone(ancestor_has_subject(".btn:has(.icon)"))
        self.assertIsNone(ancestor_has_subject(".list .row:not(:has(.x))"))
        self.assertEqual(ancestor_has_subject(".screen:has(.marker) .btn"), ".btn")
        self.assertEqual(
            ancestor_has_subject("ul:not(:has(li.o_dragged)) .group:hover > *"), "*"
        )
        self.assertEqual(
            ancestor_has_subject("body:has(.a, .b) .x > td:not(:has(.y))"),
            "td:not(:has(.y))",
        )

    def test_what_counts_as_a_broad_subject(self):
        for subject in ("*", "span", "div:last-child", "td:not(:has(.y))", "i"):
            self.assertTrue(is_broad_subject(subject), subject)
        for subject in ('[class*="col-"]', 'div[class*="col-"]:last-child', "::before"):
            self.assertTrue(is_broad_subject(subject), subject)
        for subject in (".o_navbar", "span.o_label", "#wrap", ".btn:hover::after"):
            self.assertFalse(is_broad_subject(subject), subject)
        for subject in ('[data-embedded="view"]', "a[href]:hover"):
            self.assertFalse(is_broad_subject(subject), subject)

    def test_an_ancestor_has_styles_a_class_of_its_own(self):
        with self.superuser_env() as env:
            assets = env["ir.qweb"]._get_asset_bundle(
                "web.assets_web", css=True, js=False
            )
            css = base64.b64decode(assets.css().datas).decode("utf-8", "replace")
        self.assert_ratchet(
            broad_ancestor_has_findings(css),
            "ancestor_has_broad_subject",
            "selector(s) in web.assets_web ask `:has()` of an ancestor and style "
            "a subject with no class or id of its own",
            "Every DOM change, on every screen that loads the bundle, restyles "
            "every element that could be that subject. Name the subject by a "
            "class of the component, put the `:has()` on the element being "
            "styled, or have the screen mark <body> (useBodyClass) and key the "
            "rule on that class.",
        )
