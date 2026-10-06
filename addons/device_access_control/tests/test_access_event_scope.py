import contextlib
import os
from unittest.mock import patch

from odoo import Command, fields
from odoo.exceptions import AccessError
from odoo.libs import sealing
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestAccessEventCompanyScope(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        key_patcher = patch.dict(
            os.environ,
            sealing.rotated_environ("7ftr9ALjwK7f4IqWwnpFxWx4Wn8vetsznoGT3Oh46eU="),
        )
        key_patcher.start()
        cls.addClassCleanup(key_patcher.stop)

        cls.company_a = cls.env.ref("base.main_company")
        cls.company_b = cls.env["res.company"].create({"name": "Access Co B"})
        config = cls.env.ref("device_access_control.device_profile_isapi_access")
        cls.device_a = cls.env["device.device"].create(
            {
                "name": "Door A",
                "identifier": "SCOPE-DOOR-A",
                "config_id": config.id,
                "company_id": cls.company_a.id,
                "is_demo": True,
            }
        )
        cls.device_b = cls.env["device.device"].create(
            {
                "name": "Door B",
                "identifier": "SCOPE-DOOR-B",
                "config_id": config.id,
                "company_id": cls.company_b.id,
                "is_demo": True,
            }
        )
        for device in (cls.device_a, cls.device_b):
            cls.env["access.event"].create(
                {
                    "device_id": device.id,
                    "event_type": "access_granted",
                    "event_time": fields.Datetime.now(),
                    "card_no": "SECRET-CARD",
                }
            )
        cls.user_a = cls.env["res.users"].create(
            {
                "name": "Door User A",
                "login": "access_scope_user_a",
                "group_ids": [Command.link(cls.env.ref("base.group_user").id)],
                "company_ids": [Command.set([cls.company_a.id])],
                "company_id": cls.company_a.id,
            }
        )

    def test_events_scoped_to_reader_company(self):
        visible = self.env["access.event"].with_user(self.user_a).search([])
        companies = visible.mapped("company_id")
        self.assertIn(self.company_a, companies, "own-company events are visible")
        self.assertNotIn(
            self.company_b, companies, "another company's door events must not leak"
        )

    def test_a_command_goes_only_to_a_door_its_sender_operates(self):
        # a command opens or closes a door: it is sent to a device its sender
        # may write, as the door buttons write it, and read where the device is
        manager = self.env["res.users"].create(
            {
                "name": "Door Manager A",
                "login": "access_scope_manager_a",
                "group_ids": [
                    Command.link(self.env.ref("device.group_device_manager").id)
                ],
                "company_ids": [Command.set([self.company_a.id])],
                "company_id": self.company_a.id,
            }
        )
        doors = self.device_a + self.device_b
        commands = self.env["access.command"]
        elsewhere = commands.create(
            {"device_id": self.device_b.id, "command_type": "open_door"}
        )

        sent = commands.with_user(manager).create(
            {"device_id": self.device_a.id, "command_type": "open_door"}
        )
        for sender, door in ((manager, self.device_b), (self.user_a, self.device_a)):
            with self.subTest(sender=sender.login, door=door.name):
                with self.assertRaises(AccessError):
                    commands.with_user(sender).create(
                        {"device_id": door.id, "command_type": "open_door"}
                    )

        read = commands.with_user(manager).search([("device_id", "in", doors.ids)])
        self.assertEqual(read, sent)
        self.assertNotIn(elsewhere, read)
        # reading no door, a plain user has no command to read at all: the
        # search is refused where device.device is closed to them, and empty
        # where another module opens some of its rows (iot)
        with contextlib.suppress(AccessError):
            self.assertFalse(
                commands.with_user(self.user_a).search([("device_id", "in", doors.ids)])
            )
