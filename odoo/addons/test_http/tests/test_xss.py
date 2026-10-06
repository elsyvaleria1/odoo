from odoo.tests import tagged

from .test_common import TestHttpBase


@tagged("-at_install", "post_install")
class TestXSS(TestHttpBase):
    fake_success = "console.log('test successful')"

    def assertSvgScriptRefused(self, url):
        refused = []

        def expect_refused_script(message):
            if message.startswith("CSP violation") and "/test_http/fail" in message:
                refused.append(message)
                return False
            return True

        with self.assertLogs(level="ERROR") as logs:
            self.browser_js(url, self.fake_success, error_checker=expect_refused_script)
        self.assertEqual(len(refused), 1, refused)
        self.assertIn("\"default-src 'none'\"", refused[0])
        self.assertEqual(len(logs.records), 1, logs.output)
        self.assertEqual(logs.records[0].getMessage(), refused[0])

    def test_xss_static(self):
        self.assertSvgScriptRefused("/test_http/static/src/img/xss.svg")

    def test_xss_web_content(self):
        self.assertSvgScriptRefused("/web/content/test_http.xss_svg")

    def test_xss_web_image(self):
        self.assertSvgScriptRefused("/web/image/test_http.xss_svg")
