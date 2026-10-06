from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged("post_install", "-at_install")
class TestWebhookReadsEmployees(TransactionCase):
    def test_the_webhook_processor_reads_an_employee_through_its_group(self):
        # an employee binds its version's and its partner's read permissions
        # (plan section 3.1): the processor's group holds both for employees
        processor = new_test_user(
            self.env,
            login="webhook_group_only",
            groups="device_access_control.group_access_device_webhook",
        )
        employee = self.env["hr.employee"].create({"name": "Door Walker"})
        self.assertEqual(employee.with_user(processor).name, "Door Walker")
        self.assertTrue(employee.with_user(processor).has_access("read"))
        stranger = self.env["res.partner"].create({"name": "Not an employee"})
        self.assertFalse(stranger.with_user(processor).has_access("read"))
