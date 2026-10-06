from odoo import Command
from odoo.exceptions import AccessError
from odoo.service.model import call_kw

from odoo.addons.device.tests.common import DeviceTransactionCase


class TestDAVSyncStateRpc(DeviceTransactionCase):
    def setUp(self):
        super().setUp()
        self.dav_user = self.env["res.users"].create(
            {
                "name": "DAV Phone Owner",
                "login": "dav_phone_owner",
                "group_ids": [
                    Command.link(self.env.ref("base.group_user").id),
                    Command.link(self.env.ref("device_dav_sync.group_dav_user").id),
                ],
            }
        )
        device = self.env["device.device"].create(
            {
                "name": "DAV Phone",
                "identifier": "dav-phone-rpc-001",
                "device_category_id": self.env["device.kind"]
                .create({"name": "DAV Client RPC", "code": "dav_client_rpc"})
                .id,
                "config_id": self.env["device.profile"]
                .create({"name": "DAV RPC", "protocol": "http"})
                .id,
                "dav_sync_enabled": True,
                "dav_user_id": self.dav_user.id,
            }
        )
        contact = self.env["res.partner"].create({"name": "Synced Contact"})
        self.state = self.env["dav.sync.state"].get_or_create_sync_state(
            device, "contact", "res.partner", contact.id
        )
        self.company = self.env.company

    def test_the_phone_owner_steers_their_sync_state(self):
        state = self.state.with_user(self.dav_user)
        state.write({"resource_model": "res.company", "resource_id": self.company.id})
        self.assertFalse(self.company.with_user(self.dav_user).has_access("write"))

    def test_a_sync_state_writes_no_record_for_its_caller(self):
        self.state.write(
            {"resource_model": "res.company", "resource_id": self.company.id}
        )
        name = self.company.name
        with self.assertRaises((AccessError, AttributeError)):
            call_kw(
                self.env["dav.sync.state"].with_user(self.dav_user),
                "resolve_conflict_for_resource",
                [[self.state.id], {"name": "Taken over"}, ""],
                {},
            )
        self.company.invalidate_recordset(["name"])
        self.assertEqual(self.company.name, name)
