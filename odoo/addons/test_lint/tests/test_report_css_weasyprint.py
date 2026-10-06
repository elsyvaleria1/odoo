import base64
import re

from odoo.tests import tagged
from odoo.tests.css import parse

from . import lint_case

REPORT_BUNDLES = ("web.report_assets_common", "web.report_assets_pdf")

UNPARSED_BY_WEASYPRINT_RE = re.compile(
    r"color-mix\(|\b(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch|color)\(\s*from\b"
)

NOT_PAINTED_RE = re.compile(
    r":(?:hover|focus|focus-visible|focus-within|active)\b|::placeholder"
)

UNPAINTED_PROPERTIES = frozenset({"box-shadow"})


def unparsed_paint(css):
    return sorted(
        f"{source} {selector} {prop}"
        for source, selector, prop, value in parse(css)
        if not prop.startswith("--")
        and prop not in UNPAINTED_PROPERTIES
        and not NOT_PAINTED_RE.search(selector)
        and UNPARSED_BY_WEASYPRINT_RE.search(value)
    )


@tagged("post_install", "-at_install")
class TestReportCssWeasyPrint(lint_case.LintCase):
    def test_the_detector_reads_what_weasyprint_drops(self):
        css = (
            "/* /a/x.scss */"
            ".a{background-color:color-mix(in srgb, red 50%, transparent)}"
            ".b{color:hsl(from var(--c) h s calc(l - 10))}"
            ".c{background-color:rgba(var(--c-rgb), .5)}"
            ".d{--shade:color-mix(in srgb, red 50%, blue)}"
            ".e{box-shadow:0 0 1px color-mix(in srgb, red 50%, blue)}"
            ".f:hover{background-color:color-mix(in srgb, red 50%, blue)}"
            ".g::placeholder{color:color-mix(in srgb, red 50%, blue)}"
            "@media print{.h{border-color:oklch(from red l c h)}}"
        )
        self.assertEqual(
            unparsed_paint(css),
            [
                "/a/x.scss .a background-color",
                "/a/x.scss .b color",
                "/a/x.scss @media print .h border-color",
            ],
        )

    def test_report_css_paints_only_with_what_weasyprint_parses(self):
        with self.superuser_env() as env:
            bundles = {
                name: env["ir.qweb"]._get_asset_bundle(name, css=True, js=False)
                for name in REPORT_BUNDLES
            }
            css = {
                name: base64.b64decode(assets.css().datas).decode("utf-8", "replace")
                for name, assets in bundles.items()
                if assets.stylesheets
            }

        self.assertIn("web.report_assets_common", css)
        offenders = [
            f"{name} {offender}"
            for name, text in css.items()
            for offender in unparsed_paint(text)
        ]
        self.assertFalse(
            offenders,
            f"{len(offenders)} painted declaration(s) in a PDF report bundle use "
            f"color-mix() or a relative colour. WeasyPrint parses neither and drops "
            f"the declaration, so the PDF paints nothing there (coding_guidelines "
            f"§5.3):\n  " + "\n  ".join(offenders),
        )
