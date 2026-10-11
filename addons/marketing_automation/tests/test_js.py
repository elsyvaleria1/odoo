"""CI entry point for the ``marketing_automation`` addon's HOOT (JS unit) suite.

Mirrors ``pos_enterprise/tests/test_js.py``: the runner machinery (hash,
``&id=`` filter, ``_run_hoot`` warm navigation) is reused from ``web`` via
``HOOTCommon``, imported through the module object so Odoo's unittest loader
does not collect ``web``'s base meta-tests a second time under
``marketing_automation``.

Without this file the ``static/tests/*.test.js`` bundled into
``web.assets_unit_tests`` by the manifest were selected by no suite filter and
therefore never ran -- the exact failure mode ``web/tests/test_js.py`` documents.
A stale ``.fa-trash`` selector left behind by the FontAwesome upgrade
(``fa fa-trash`` -> ``fa-solid fa-trash-can``) survived unnoticed that way.
"""

from pathlib import Path

import odoo.tests
from odoo.tools.misc import file_path

import odoo.addons.web.tests.test_js as web_test_js

ALL_SUITE_PREFIXES = ("@marketing_automation",)


@odoo.tests.tagged("post_install", "-at_install", "marketing_automation_js")
class MarketingAutomationSuite(web_test_js.HOOTCommon):
    @odoo.tests.no_retry
    def test_marketing_automation_unit(self):
        self._run_hoot("@marketing_automation", preset="desktop", timeout=900)

    def test_suite_filters_cover_every_test_file(self):
        tests_root = Path(file_path("marketing_automation/static/tests"))
        test_files = sorted(tests_root.rglob("*.test.js"))
        self.assertTrue(
            test_files,
            f"No *.test.js found under {tests_root}: the suite filter would "
            "match nothing and the run would trivially succeed.",
        )
        uncovered = []
        for test_file in test_files:
            rel = test_file.relative_to(tests_root).as_posix()
            suite = "@marketing_automation/" + rel[: -len(".test.js")]
            if not any(
                suite == prefix or suite.startswith(prefix + "/")
                for prefix in ALL_SUITE_PREFIXES
            ):
                uncovered.append(suite)
        self.assertFalse(
            uncovered,
            "marketing_automation unit test files selected by no CI suite filter "
            "(they will never run):\n- " + "\n- ".join(uncovered),
        )
