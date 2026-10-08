from odoo.tests import HttpCase, tagged

from odoo.addons.calendar_microsoft.tests.fake_outlook import FakeOutlook
from odoo.addons.calendar_sync.tests.contract import CalendarSyncContract


@tagged("post_install", "-at_install")
class TestOutlookContract(CalendarSyncContract, HttpCase):
    code = "microsoft"

    def fake_server(self):
        return FakeOutlook(self.env)
