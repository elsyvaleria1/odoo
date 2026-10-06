import re
from pathlib import Path

from odoo.modules.module import Manifest
from odoo.tests import TransactionCase, tagged
from odoo.tools.files import file_path


@tagged("post_install", "-at_install")
class TestTourHelperIsReachable(TransactionCase):
    HELPER = "mrp_workorder/static/tests/tours/running_tour_action_helper.js"
    IMPORTS_HELPER = re.compile(
        r"""^\s*import\b[^;]*["'](?:\.{1,2}/|@mrp_workorder/\.\./tests/tours/)"""
        r"""(?:[\w./-]*/)?running_tour_action_helper(?:\.js)?["']""",
        re.MULTILINE,
    )

    def test_a_tour_imports_the_helper(self):
        tours = Path(file_path("mrp_workorder/static/tests/tours", ("",)))
        importers = [
            path.name
            for path in tours.rglob("*.js")
            if path.name != "running_tour_action_helper.js"
            and self.IMPORTS_HELPER.search(path.read_text(encoding="utf-8"))
        ]
        self.assertTrue(
            importers,
            "no tour imports running_tour_action_helper.js: its `scan` action "
            "is registered only when something in web.assets_tests reaches it",
        )

    def test_the_helper_is_named_in_no_bundle(self):
        # the tours glob of web.assets_tests carries it; naming it in a second
        # bundle (it used to be in the lazy web_tour.automatic) evaluates it twice
        assets = Manifest.for_addon("mrp_workorder")["assets"]
        declaring = sorted(
            bundle
            for bundle, entries in assets.items()
            if self.HELPER in (entry for entry in entries if isinstance(entry, str))
        )
        self.assertEqual(declaring, [])
