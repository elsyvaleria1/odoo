import logging
import re

from odoo.libs.lint import scan_regex_patterns
from odoo.modules import get_resource_from_path

from . import _js_sources, lint_case

_logger = logging.getLogger(__name__)

TSTRING_PAT = r"(?s)_t\(\s*`[^`]*`"
UNDERSCORE_PAT = r"""\b_\(\s*['"]"""
LITERAL_PAT = r"""(?:"[^"\n]*"|'[^'\n]*'|`[^`]*`)"""
OPERAND_PAT = rf"(?:{LITERAL_PAT}|[\w.$]+)"
CONCAT_PAT = rf"\b_t\(\s*{OPERAND_PAT}(?:\s*\+\s*{OPERAND_PAT})+"
PATTERNS = (TSTRING_PAT, UNDERSCORE_PAT, CONCAT_PAT)

TSTRING_RE = re.compile(TSTRING_PAT)
UNDERSCORE_RE = re.compile(UNDERSCORE_PAT)
CONCAT_RE = re.compile(CONCAT_PAT)
LITERAL_RE = re.compile(LITERAL_PAT)
EXPRESSION_RE = re.compile(r"(?s)\$\{.+?\}")


def concatenates_a_value(call):
    return any(
        not LITERAL_RE.fullmatch(operand) or EXPRESSION_RE.search(operand)
        for operand in re.findall(OPERAND_PAT, call.partition("(")[2])
    )


class TestJsTranslations(lint_case.LintCase):
    def check_text(self, text):
        error_list = []
        for m in TSTRING_RE.finditer(text):
            template_string = m.group(0)
            if EXPRESSION_RE.search(template_string):
                line_nb = lint_case.line_of(text, m.start())
                error_list.append((line_nb, template_string))

        for m in UNDERSCORE_RE.finditer(text):
            lineno = lint_case.line_of(text, m.start())
            error_list.append((lineno, None))

        for m in CONCAT_RE.finditer(text):
            if concatenates_a_value(m.group(0)):
                lineno = lint_case.line_of(text, m.start())
                error_list.append((lineno, m.group(0)))

        return error_list

    def test_regular_expression(self):
        bad_js = """
        const foo = {
            valid: _t(`not useful but valid template-string`),
            invalid: _t(`invalid template-string
            that spans multiple lines ${expression}`)
        };
        """
        error_list = self.check_text(bad_js)
        self.assertEqual(len(error_list), 1)
        [(line, template_string)] = error_list
        self.assertEqual(line, 4)
        self.assertIn("invalid template-string", template_string)
        self.assertNotIn("but valid template-string", template_string)

    def test_regular_expression_long(self):
        bad_js = """
        thing = _t(
            `foo ${this + is(a, very) - long == expression}`
        );
        """

        error_list = self.check_text(bad_js)
        self.assertEqual(len(error_list), 1)
        [(line, template_string)] = error_list
        self.assertEqual(line, 2)
        self.assertIn("foo ${this + is(a, very) - long == expression}", template_string)

    def test_regular_expression_with_trailing_comma(self):
        bad_js = """
        body: _t(
            `destroy all ${paid ? "paid" : "unpaid"} orders`,
        ),
        """
        [(line, template_string)] = self.check_text(bad_js)
        self.assertEqual(line, 2)
        self.assertIn("${paid", template_string)

    def test_matches_concatenation(self):
        bad_js = """
        a = _t("Error while updating " + platform + " status.");
        b = _t(this.config.name + " is online.");
        c = _t("%s is online.", name);
        d = _t("a + b");
        e = _t("a long sentence " +
            "wrapped by the formatter");
        f = _t("a value " + `in ${place}`);
        """
        self.assertEqual([line for line, _ in self.check_text(bad_js)], [2, 3, 8])

    def test_matches_underscore(self):
        bad_js = """
        const thing1 = _('literal0');
        const thing0 = _([]);
        const thing2 = _("literal1");
        """
        self.assertEqual(self.check_text(bad_js), [(2, None), (4, None)])

    def offenders(self, results):
        offenders = []
        for path, line, pat_idx, matched_text in results:
            if _js_sources.vendored(path):
                continue

            if pat_idx == 0:
                if not EXPRESSION_RE.search(matched_text):
                    continue
                prefix = "translated template string"
                suffix = " ".join(matched_text.split())[:100]
            elif pat_idx == 1:
                prefix = "underscore.js used as a translation function"
                suffix = "_t is the JS translation function"
            else:
                if not concatenates_a_value(matched_text):
                    continue
                prefix = "translated concatenation"
                suffix = " ".join(matched_text.split())[:100]

            try:
                mod, relative_path = get_resource_from_path(path)
            except TypeError:
                mod, relative_path = "?", path
            offenders.append(f"{mod}/{relative_path}:{line}: {prefix}: {suffix}")
        return offenders

    def test_a_vendored_library_is_not_scanned(self):
        call = "_t(c+BigInt"
        found = self.offenders(
            [
                (
                    "/x/web/static/lib/temporal-polyfill/temporal-polyfill.js",
                    9,
                    2,
                    call,
                ),
                (
                    "/x/spreadsheet/static/src/o_spreadsheet/o_spreadsheet.js",
                    9,
                    2,
                    call,
                ),
                ("/x/web/static/src/core/l10n/dates.js", 9, 2, call),
            ]
        )
        self.assertEqual(len(found), 1)
        self.assertIn("static/src/core/l10n/dates.js:9", found[0])

    def test_js_translations(self):
        results = scan_regex_patterns(
            lint_case.core_module_roots(),
            [".js"],
            list(PATTERNS),
            ["node_modules", "__pycache__"],
        )
        offenders = self.offenders(results)

        self.assert_ratchet(
            offenders,
            "lint_js_translation_call",
            "invalid translation call(s) in JS",
            "Use _t with a plain string and pass the values as its arguments; a "
            "template string or a concatenation is extracted as its literal parts, "
            "which no translation matches at runtime.",
        )
