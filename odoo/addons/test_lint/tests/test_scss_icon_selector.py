import re

from odoo.libs.lint import scan_regex_patterns
from odoo.modules import get_resource_from_path

from . import lint_case

BARE_FA_PAT = r"(?m)\.fa(?:[^\w-]|$)"
BARE_FA_RE = re.compile(BARE_FA_PAT)

ALLOWED = {"web/static/src/webclient/icons.variables.scss"}


class TestScssIconSelector(lint_case.LintCase):
    def check_text(self, text):
        return sorted(
            lint_case.line_of(text, m.start() + m.group().index(".fa"))
            for m in BARE_FA_RE.finditer(text)
        )

    def test_regular_expression(self):
        bad = """
        .fa { color: red; }
        .fa-lg { color: red; }
        span.fa:before { color: red; }
        :is(#{$o-icon-selector}) { color: red; }
        .o_faq { color: red; }
        &:not(.fa) { color: red; }
        """
        self.assertEqual(self.check_text(bad), [2, 4, 7])

    def test_no_stylesheet_matches_an_icon_by_its_fa4_base_alone(self):
        results = scan_regex_patterns(
            lint_case.core_module_roots(),
            [".scss"],
            [BARE_FA_PAT],
            ["node_modules", "__pycache__"],
        )
        offenders = []
        for path, line, _idx, matched in results:
            if "/static/lib/" in path or "/static/tests/" in path:
                continue
            try:
                mod, relative_path = get_resource_from_path(path)
            except TypeError:
                mod, relative_path = "?", path
            if f"{mod}/{relative_path}" in ALLOWED:
                continue
            offenders.append(f"{mod}/{relative_path}:{line}: {matched.strip()}")

        self.assert_ratchet(
            offenders,
            "lint_scss_bare_fa",
            "selector(s) matching an icon by `.fa` alone",
            "Font Awesome 7 markup carries `fa-solid`/`fa-regular`/`fa-brands` "
            "and no `fa`, so the rule misses most icons. Use "
            "`:is(#{$o-icon-selector})`.",
        )
