from odoo.tests.common import HttpCase, new_test_user, tagged

from odoo.addons.web.tests.test_csp import CspPageAssertions


@tagged("post_install", "-at_install")
class TestPortalScriptPolicy(CspPageAssertions, HttpCase):
    def test_portal_pages(self):
        new_test_user(self.env, "csp_portal", groups="base.group_portal")
        for url in ("/my", "/my/account", "/my/security"):
            self.assertPageScriptsNonced(url, login="csp_portal")
