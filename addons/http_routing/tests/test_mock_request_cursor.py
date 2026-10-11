from odoo.tests import HttpCase, tagged

from odoo.addons.http_routing.tests.common import MockRequest


@tagged("post_install", "-at_install")
class TestMockRequestCursor(HttpCase):
    def test_the_test_thread_may_open_a_cursor_under_its_own_mock_request(self):
        with MockRequest(self.env), self.registry.cursor() as cr:
            cr.execute("SELECT 1")
            self.assertEqual(cr.fetchone(), (1,))

    def test_a_mock_request_does_not_stop_a_login(self):
        admin = self.env.ref("base.user_admin")
        with MockRequest(self.env):
            session = self.authenticate(admin.login, admin.login)
        self.assertEqual(session.uid, admin.id)
