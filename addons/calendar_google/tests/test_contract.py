from odoo.tests import HttpCase, tagged

from odoo.addons.calendar_google.tests.fake_google import FakeGoogle
from odoo.addons.calendar_sync.tests.contract import CalendarSyncContract


@tagged("post_install", "-at_install")
class TestGoogleContract(CalendarSyncContract, HttpCase):
    code = "google"

    def fake_server(self):
        return FakeGoogle(self.env)
