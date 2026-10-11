import logging

from odoo.tests import tagged

from odoo.addons.auth_totp.tests.test_totp import TestTOTPMixin
from odoo.addons.base.tests.common import HttpCaseWithUserPortal

_logger = logging.getLogger(__name__)


@tagged("post_install", "-at_install")
class TestTOTPortal(HttpCaseWithUserPortal, TestTOTPMixin):

    def test_totp(self):
        self.install_totphook()

        self.start_tour("/my/security", "totportal_tour_setup", login="portal")
        self.start_tour("/", "totportal_login_enabled", login=None)
        self.start_tour("/", "totportal_login_disabled", login=None)
