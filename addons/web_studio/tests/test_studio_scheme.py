import base64

from odoo.tests import TransactionCase, tagged
from odoo.tests.css import measure


@tagged("-at_install", "post_install")
class TestStudioScheme(TransactionCase):
    def _css(self, bundle):
        assets = self.env["ir.qweb"]._get_asset_bundle(bundle, css=True, js=False)
        attachment = assets.css()
        self.assertFalse(assets.css_errors, f"{bundle} does not compile")
        return base64.b64decode(attachment.datas).decode("utf-8", "replace")

    def test_studio_answers_the_dark_scheme_from_its_one_stylesheet(self):
        gap, answered, _, _ = measure(
            self._css("web.assets_web") + self._css("web_studio.studio_assets"),
            self._css("web.assets_web_dark")
            + self._css("web_studio.studio_assets_dark"),
        )
        self.assertGreater(
            answered,
            1000,
            "the attribute answered almost nothing, so the bundles did not carry "
            "the dark scope they should",
        )
        studio = sorted(
            f"{source} {selector} {prop}"
            for source, selector, prop in gap
            if "/web_studio/" in source
        )
        self.assertFalse(
            studio,
            f"{len(studio)} Studio declaration(s) paint differently under "
            f'`data-color-scheme="dark"` in web_studio.studio_assets than '
            f"web_studio.studio_assets_dark serves them. Studio loads the one "
            f"stylesheet in both schemes: read the colour through a token "
            f"(--o-web-studio-*, --o-*) or restate it under the attribute:\n  "
            + "\n  ".join(studio),
        )
