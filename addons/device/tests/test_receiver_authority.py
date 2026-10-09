import importlib.util
from pathlib import Path
from unittest.mock import patch

from odoo import Command
from odoo.http import request
from odoo.libs.json import dumps_bytes as json_dumps_bytes
from odoo.tests import tagged
from odoo.tests.common import new_test_user

from .common import DeviceHttpCase, DeviceTransactionCase, NarrowedReceiver
from odoo.addons.integration.tools.admission import Admission


@tagged("post_install", "-at_install")
class TestReceiverAuthority(NarrowedReceiver, DeviceHttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.receiver = cls.env.ref("device.user_device_receiver")
        cls.device = cls._create_device_device(
            config=cls._create_device_profile(name="Authority Config"),
            name="Authority Device",
            identifier="AUTHORITY-1",
            processing_mode="sync",
        )
        cls.token = cls._device_token(cls.device)

    def _push(self):
        self.env.flush_all()
        return self.url_open(
            f"/remote/device/{self.device.identifier}/data",
            data=json_dumps_bytes({"t": 1}),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.token}",
            },
        )

    def _point(self):
        return self.env["device.data.log"].search(
            [("device_id", "=", self.device.id)], order="id desc", limit=1
        )

    def test_a_push_is_filed_by_the_receiver_without_su(self):
        seen = []
        settle = Admission.settle

        def spy(admission, *args, **kwargs):
            seen.append(
                (
                    request.env.uid,
                    request.env.su,
                    admission.subject.env.su,
                    request.env.privileges,
                )
            )
            return settle(admission, *args, **kwargs)

        with patch.object(Admission, "settle", spy):
            response = self._push()

        self.assertEqual(response.status_code, 200)
        privileges = frozenset(
            {
                self.env.ref("device.privilege_receive_device_data").id,
                self.env.ref("integration.privilege_keep_inbound_exchange").id,
            }
        )
        self.assertEqual(seen, [(self.receiver.id, False, False, privileges)])
        point = self._point()
        self.assertEqual(point.create_uid, self.receiver)
        self.device.invalidate_recordset()
        self.assertEqual(self.device.log_last_id, point)
        self.assertEqual(self.device.connection_state, "connected")

    def test_the_status_read_answers_without_su(self):
        self.env.flush_all()
        response = self.url_open(
            f"/remote/device/{self.device.identifier}/status",
            headers={"Authorization": f"Bearer {self.token}"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["device"]["name"], "Authority Device")

    def test_an_async_push_queues_its_job_with_the_receiver_s_privilege(self):
        self.device.processing_mode = "async"

        self.assertEqual(self._push().status_code, 202)

        job = (
            self.env["ir.job"]
            .sudo()
            .search(
                [("method_name", "=", "_job_process_inbound")],
                order="id desc",
                limit=1,
            )
        )
        self.assertEqual(job.user_id, self.receiver)
        self.assertFalse(job.elevated)
        self.assertEqual(
            set(job.privileges),
            {
                self.env.ref("device.privilege_receive_device_data").id,
                self.env.ref("integration.privilege_keep_inbound_exchange").id,
            },
        )
        job.action_run_now()
        self.assertEqual(job.state, "done")
        self.assertEqual(self._point().create_uid, self.receiver)

    def test_a_receiver_outside_the_device_s_company_is_refused(self):
        self.receiver.company_ids = [Command.set(self.receiver.company_id.ids)]
        other_company = self.env["res.company"].create({"name": "Unplaced Co"})
        self.env.cr.execute(
            "UPDATE device_device SET company_id = %s WHERE id = %s",
            (other_company.id, self.device.id),
        )
        self.device.invalidate_recordset()

        response = self._push()

        self.assertEqual(response.status_code, 403)
        self.assertIn("principal_unfit", response.text)


@tagged("post_install", "-at_install")
class TestReceiverPlacement(DeviceTransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.receiver = cls.env.ref("device.user_device_receiver")
        cls.other_company = cls.env["res.company"].create({"name": "Device tenant"})

    def test_a_device_in_another_company_puts_its_receiver_there(self):
        manager = new_test_user(
            self.env,
            login="tenant_device_manager",
            groups="device.group_device_manager",
            company_id=self.other_company.id,
            company_ids=[Command.set(self.other_company.ids)],
        )
        self.assertNotIn(self.other_company, self.receiver.company_ids)

        self.env["device.device"].with_user(manager).create(
            {
                "name": "Tenant device",
                "identifier": "TENANT-1",
                "config_id": self._create_device_profile().id,
                "company_id": self.other_company.id,
            }
        )

        self.assertIn(self.other_company, self.receiver.company_ids)

    def test_the_upgrade_puts_the_receiver_in_each_device_s_company(self):
        self._create_device_device(
            identifier="TENANT-2", company_id=self.other_company.id
        )
        self.receiver.company_ids = [Command.unlink(self.other_company.id)]
        migration = (
            Path(__file__).parents[1] / "migrations" / "2.3.3" / "post-migrate.py"
        )
        spec = importlib.util.spec_from_file_location("device_2_3_3", migration)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        module.migrate(self.env.cr, "2.3.2")

        self.assertIn(self.other_company, self.receiver.company_ids)
