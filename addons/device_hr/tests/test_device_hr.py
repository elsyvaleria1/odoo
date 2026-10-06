from odoo.tests import tagged

from odoo.addons.device.tests.common import DeviceTransactionCase


@tagged("post_install", "-at_install")
class TestRemoteHrSetup(DeviceTransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")

        cls.config = cls.env["device.profile"].create(
            {
                "name": "HR GPS Config",
                "auth_type": "bearer",
                "auth_token": "hr_test_token",
            }
        )

        cls.employee = cls.env["hr.employee"].create(
            {"name": "GPS Field Worker", "company_id": cls.company.id}
        )

    def _create_device(self, identifier, employee=None):
        vals = {
            "name": f"Device {identifier}",
            "identifier": identifier,
            "config_id": self.config.id,
            "comm_protocol": "http",
            "endpoint": f"10.0.0.{identifier[-1]}",
            "company_id": self.company.id,
        }
        if employee:
            vals["employee_id"] = employee.id
        return self.env["device.device"].create(vals)


@tagged("post_install", "-at_install")
class TestDeviceCount(TestRemoteHrSetup):
    def test_observation_target_and_device_custody_are_distinct(self):
        device = self._create_device("TARGET-D1")
        self.employee.gps_device_id = device
        self.assertEqual(self.employee.resource_id.gps_device_id, device)
        self.assertEqual(device.tracked_resource_id, self.employee.resource_id)
        self.assertFalse(device.employee_id)
        self.assertEqual(self.employee.device_count, 0)

    def test_tracking_attachment_is_created_on_the_shared_resource(self):
        device = self._create_device("TARGET-D2")
        employee = self.env["hr.employee"].create(
            {"name": "Tracked person", "gps_device_id": device.id}
        )
        self.assertEqual(employee.gps_device_id, device)
        self.assertEqual(device.tracked_resource_id, employee.resource_id)
        self.assertFalse(employee.copy().gps_device_id)

    def test_count_is_zero_with_no_devices(self):
        employee = self.env["hr.employee"].create(
            {"name": "Employee No Devices", "company_id": self.company.id}
        )
        self.assertEqual(employee.device_count, 0)

    def test_count_reflects_single_device(self):
        employee = self.env["hr.employee"].create(
            {"name": "Employee One Device", "company_id": self.company.id}
        )
        self._create_device("DEV-A1", employee=employee)
        employee.invalidate_recordset()
        self.assertEqual(employee.device_count, 1)

    def test_count_reflects_multiple_devices(self):
        employee = self.env["hr.employee"].create(
            {"name": "Employee Multi Device", "company_id": self.company.id}
        )
        self._create_device("DEV-B1", employee=employee)
        self._create_device("DEV-B2", employee=employee)
        self._create_device("DEV-B3", employee=employee)
        employee.invalidate_recordset()
        self.assertEqual(employee.device_count, 3)

    def test_count_does_not_include_other_employees_devices(self):
        emp_a = self.env["hr.employee"].create(
            {"name": "Employee A", "company_id": self.company.id}
        )
        emp_b = self.env["hr.employee"].create(
            {"name": "Employee B", "company_id": self.company.id}
        )
        self._create_device("DEV-C1", employee=emp_a)
        self._create_device("DEV-C2", employee=emp_a)
        self._create_device("DEV-C3", employee=emp_b)
        emp_a.invalidate_recordset()
        emp_b.invalidate_recordset()
        self.assertEqual(emp_a.device_count, 2)
        self.assertEqual(emp_b.device_count, 1)


@tagged("post_install", "-at_install")
class TestActionViewGpsDevices(TestRemoteHrSetup):
    def test_action_targets_device_device_model(self):
        action = self.employee.action_view_devices()
        self.assertEqual(action["type"], "ir.actions.act_window")
        self.assertEqual(action["res_model"], "device.device")

    def test_action_domain_filters_by_employee(self):
        action = self.employee.action_view_devices()
        self.assertIn(("employee_id", "=", self.employee.id), action["domain"])

    def test_action_default_context_sets_employee(self):
        action = self.employee.action_view_devices()
        self.assertEqual(action["context"].get("default_employee_id"), self.employee.id)

    def test_action_name_contains_employee_name(self):
        action = self.employee.action_view_devices()
        self.assertIn(self.employee.name, action["name"])


@tagged("post_install", "-at_install")
class TestActionViewTrackingHistory(TestRemoteHrSetup):
    def test_action_targets_gps_log_model(self):
        action = self.employee.action_view_tracking_history()
        self.assertEqual(action["type"], "ir.actions.act_window")
        self.assertEqual(action["res_model"], "device.data.log.gps")

    def test_action_domain_filters_by_employee_devices(self):
        action = self.employee.action_view_tracking_history()
        self.assertIn(
            ("device_id.employee_id", "=", self.employee.id), action["domain"]
        )

    def test_action_context_has_last_week_filter(self):
        action = self.employee.action_view_tracking_history()
        self.assertTrue(action["context"].get("search_default_last_week"))

    def test_action_name_contains_employee_name(self):
        action = self.employee.action_view_tracking_history()
        self.assertIn(self.employee.name, action["name"])
