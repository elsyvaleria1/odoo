import importlib.util
from pathlib import Path
from unittest.mock import patch

from odoo import Command
from odoo.http import request
from odoo.tests import tagged
from odoo.tests.common import new_test_user

from .test_channels import EnrollmentFixture
from odoo.addons.device.tests.common import DeviceHttpCase, DeviceTransactionCase
from odoo.addons.integration.tools.admission import Admission


@tagged("post_install", "-at_install")
class TestChannelPrincipalPlacement(EnrollmentFixture, DeviceTransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.principal = cls.env.ref("device_transport.user_channel_receiver")
        cls.other_company = cls.env["res.company"].create({"name": "Channel tenant"})

    def test_an_enrollment_in_another_company_puts_its_principal_there(self):
        manager = new_test_user(
            self.env,
            login="tenant_channel_manager",
            groups="device.group_device_manager",
            company_id=self.other_company.id,
            company_ids=[Command.set(self.other_company.ids)],
        )
        self.assertNotIn(self.other_company, self.principal.company_ids)

        self.env["device.enrollment"].with_user(manager).create(
            {"name": "Tenant enrollment", "company_id": self.other_company.id}
        )

        self.assertIn(self.other_company, self.principal.company_ids)

    def test_the_upgrade_puts_each_principal_in_its_enrollments_companies(self):
        self._enroll(company_id=self.other_company.id)
        self.principal.company_ids = [Command.unlink(self.other_company.id)]
        migration = (
            Path(__file__).parents[1] / "migrations" / "1.3.0" / "post-migrate.py"
        )
        spec = importlib.util.spec_from_file_location("device_transport_1_3", migration)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        module.migrate(self.env.cr, "1.2.0")

        self.assertIn(self.other_company, self.principal.company_ids)


@tagged("post_install", "-at_install")
class TestChannelPrincipalHttp(EnrollmentFixture, DeviceHttpCase):
    # device.channel keeps su until device_gps's channel route holds its own
    # privilege; the status route runs without it here
    def setUp(self):
        super().setUp()
        self.startPatcher(
            patch.object(type(self.env["device.channel"]), "_inbound_elevated", False)
        )

    def _get(self, enrollment, key, token):
        return self.url_open(
            f"/device/v1/enrollments/{enrollment.key}/channels/{key}/status",
            headers={"Authorization": f"Bearer {token}"},
        )

    def test_the_status_handler_runs_as_the_principal_without_su(self):
        enrollment = self._enroll()
        self._channel(enrollment)
        token = enrollment.credential_id.sudo().credential_value
        seen = []
        settle = Admission.settle

        def spy(admission, *args, **kwargs):
            seen.append(
                (
                    request.env.uid,
                    request.env.su,
                    admission.subject.env.su,
                    request.env.context.get("allowed_company_ids"),
                )
            )
            return settle(admission, *args, **kwargs)

        with patch.object(Admission, "settle", spy):
            response = self._get(enrollment, "telemetry", token)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["purpose"], "telemetry")
        self.assertEqual(
            seen,
            [
                (
                    enrollment.service_user_id.id,
                    False,
                    False,
                    [enrollment.company_id.id],
                )
            ],
        )

    def test_a_principal_outside_the_enrollment_s_company_is_refused(self):
        other_company = self.env["res.company"].create({"name": "Status tenant"})
        enrollment = self._enroll(company_id=other_company.id)
        self._channel(enrollment)
        token = enrollment.credential_id.sudo().credential_value
        enrollment.service_user_id.company_ids = [Command.unlink(other_company.id)]

        response = self._get(enrollment, "telemetry", token)

        self.assertEqual(response.status_code, 403)
        self.assertIn("principal_unfit", response.text)
