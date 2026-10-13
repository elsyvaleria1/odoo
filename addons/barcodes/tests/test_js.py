from pathlib import Path

import odoo.tests
from odoo.tools.misc import file_path

import odoo.addons.web.tests.test_js as web_test_js

ALL_SUITE_PREFIXES = ("@barcodes",)


@odoo.tests.tagged("post_install", "-at_install", "barcodes_js")
class BarcodesSuite(web_test_js.HOOTCommon):
    @odoo.tests.no_retry
    def test_barcodes_unit(self):
        self._run_hoot("@barcodes", preset="desktop", timeout=900)

    @odoo.tests.no_retry
    def test_barcodes_unit_mobile(self):
        self._run_hoot("@barcodes", preset="mobile", tag="-headless", timeout=900)

    def test_suite_filters_cover_every_test_file(self):
        tests_root = Path(file_path("barcodes/static/tests"))
        uncovered = []
        for test_file in sorted(tests_root.rglob("*.test.js")):
            rel = test_file.relative_to(tests_root).as_posix()
            suite = "@barcodes/" + rel[: -len(".test.js")]
            if not any(
                suite == prefix or suite.startswith(prefix + "/")
                for prefix in ALL_SUITE_PREFIXES
            ):
                uncovered.append(suite)
        self.assertFalse(
            uncovered,
            "barcodes unit test files selected by no CI suite filter (they "
            "will never run):\n- " + "\n- ".join(uncovered),
        )
