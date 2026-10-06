import shutil
from types import SimpleNamespace

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestABridgeReadAtEvaluationIsNamed(TransactionCase):
    def setUp(self):
        super().setUp()
        if shutil.which("node") is None:
            self.skipTest("no node on PATH; the evaluation uses cannot be read")

    def test_the_build_names_the_module_the_line_and_the_binding(self):
        module = SimpleNamespace(
            module_path="@forum_like/plugins/font",
            url="/forum_like/static/src/plugins/font.js",
            raw_content=(
                'import { FontPlugin } from "@html_editor/main/font/font_plugin";\n'
                "export class ForumFontPlugin extends FontPlugin {}\n"
            ),
        )
        with self.assertLogs("odoo.assets.bridge", "ERROR") as logged:
            self.env["ir.qweb"]._warn_bridges_read_at_evaluation(
                "web.assets_frontend", [module], {"@html_editor/main/font/font_plugin"}
            )
        (line,) = logged.output
        for part in ("@forum_like/plugins/font", "line=2", "binding=FontPlugin"):
            self.assertIn(part, line)

    def test_a_binding_read_only_later_is_not_reported(self):
        module = SimpleNamespace(
            module_path="@forum_like/interactions/forum",
            url="/forum_like/static/src/interactions/forum.js",
            raw_content=(
                'import { Wysiwyg } from "@html_editor/wysiwyg";\n'
                "export function mount() { return Wysiwyg; }\n"
            ),
        )
        with self.assertNoLogs("odoo.assets.bridge", "ERROR"):
            self.env["ir.qweb"]._warn_bridges_read_at_evaluation(
                "web.assets_frontend", [module], {"@html_editor/wysiwyg"}
            )
