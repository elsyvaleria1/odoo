from pathlib import Path

import odoo.tests
from odoo.tools.misc import file_path

import odoo.addons.web.tests.test_js as web_test_js

ACTIVITY_SUITES = (
    "@test_mail/activity",
    "@test_mail/activity_mobile",
    "@test_mail/systray_activity_menu",
)
MISC_SUITES = (
    "@test_mail/attachment_view",
    "@test_mail/chatter",
    "@test_mail/properties_field",
    "@test_mail/tracking_value",
)
ALL_TEST_MAIL_SUITE_PREFIXES = (*ACTIVITY_SUITES, *MISC_SUITES)


@odoo.tests.tagged("post_install", "-at_install", "test_mail_js")
class TestMailSuite(web_test_js.HOOTCommon):
    @odoo.tests.no_retry
    def test_activity(self):
        self._run_hoot(*ACTIVITY_SUITES, preset="desktop")

    @odoo.tests.no_retry
    def test_misc(self):
        self._run_hoot(*MISC_SUITES, preset="desktop")

    def test_suite_filters_cover_every_test_file(self):
        tests_root = Path(file_path("test_mail/static/tests"))
        uncovered = []
        for test_file in sorted(tests_root.rglob("*.test.js")):
            rel = test_file.relative_to(tests_root).as_posix()
            suite = "@test_mail/" + rel[: -len(".test.js")]
            if not any(
                suite == prefix or suite.startswith(prefix + "/")
                for prefix in ALL_TEST_MAIL_SUITE_PREFIXES
            ):
                uncovered.append(suite)
        self.assertFalse(
            uncovered,
            "test_mail test files selected by no CI suite filter (they will "
            "never run):\n- " + "\n- ".join(uncovered),
        )


@odoo.tests.tagged("post_install", "-at_install", "test_mail_js")
class MobileTestMailSuite(web_test_js.HOOTCommon):
    browser_size = "375x667"
    touch_enabled = True

    @odoo.tests.no_retry
    def test_all(self):
        self._run_hoot(*ACTIVITY_SUITES, *MISC_SUITES, preset="mobile", tag="-headless")
