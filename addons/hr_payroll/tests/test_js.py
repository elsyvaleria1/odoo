import odoo.tests

from odoo.addons.web.tests.test_js import HOOTCommon


@odoo.tests.tagged("post_install", "-at_install", "web_js")
class HrPayrollSuite(HOOTCommon):

    @odoo.tests.no_retry
    def test_hr_payroll(self):
        self._run_hoot("@hr_payroll", preset="desktop")
