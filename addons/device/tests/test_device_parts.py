from psycopg.errors import RestrictViolation, UniqueViolation

from odoo.exceptions import AccessError, ValidationError
from odoo.orm.primitives import MODULE_UNINSTALL_FLAG
from odoo.tests import TransactionCase, new_test_user, tagged
from odoo.tools import mute_logger

from .common import DeviceFixtureMixin


@tagged("post_install", "-at_install")
class TestDeviceParts(TransactionCase, DeviceFixtureMixin):
    """A device that carries others is one registry entry carrying others,
    not a second registry."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.profile = cls._create_device_profile()

    def test_a_part_belongs_to_the_device_that_carries_it(self):
        box = self._create_device_device(self.profile, identifier="BOX-1")
        scale = self._create_device_device(
            self.profile, identifier="SCALE-1", parent_id=box.id
        )

        self.assertEqual(scale.parent_id, box)
        self.assertEqual(box.child_ids, scale)
        self.assertEqual(box.child_count, 1)

    def test_parts_of_different_devices_may_share_an_identifier(self):
        first = self._create_device_device(self.profile, identifier="BOX-SHARED-1")
        second = self._create_device_device(self.profile, identifier="BOX-SHARED-2")
        displays = self._create_device_device(
            self.profile, identifier="hdmi_0", parent_id=first.id
        ) | self._create_device_device(
            self.profile, identifier="hdmi_0", parent_id=second.id
        )

        self.assertEqual(displays.parent_id, first | second)
        self.assertEqual(len(displays.sudo().credential_id), 2)

    @mute_logger("odoo.sql_db")
    def test_two_parts_of_one_device_may_not_share_an_identifier(self):
        box = self._create_device_device(self.profile, identifier="BOX-TWIN")
        self._create_device_device(self.profile, identifier="hdmi_0", parent_id=box.id)

        with self.assertRaises(UniqueViolation), self.env.cr.savepoint():
            self._create_device_device(
                self.profile, identifier="hdmi_0", parent_id=box.id
            )

    @mute_logger("odoo.sql_db")
    def test_two_devices_with_no_parent_may_not_share_an_identifier(self):
        self._create_device_device(self.profile, identifier="ROOT-TWIN")

        with self.assertRaises(UniqueViolation), self.env.cr.savepoint():
            self._create_device_device(self.profile, identifier="ROOT-TWIN")

    def test_a_part_goes_with_the_device_it_is_part_of(self):
        box = self._create_device_device(self.profile, identifier="BOX-2")
        scale = self._create_device_device(
            self.profile, identifier="SCALE-2", parent_id=box.id
        )

        box.unlink()

        self.assertFalse(scale.exists())

    def test_deleting_parts_cleans_their_connections_including_archived_parts(self):
        box = self._create_device_device(self.profile, identifier="BOX-CLEANUP")
        part = self._create_device_device(
            self.profile, identifier="PART-CLEANUP", parent_id=box.id, active=False
        )
        nested = self._create_device_device(
            self.profile, identifier="NESTED-CLEANUP", parent_id=part.id
        )
        kept = self._create_device_device(self.profile, identifier="KEPT-CLEANUP")
        connections = (box | part | nested).sudo().connection_id
        self.assertEqual(len(connections), 3)

        box.unlink()

        self.assertFalse((box | part | nested).exists())
        self.assertFalse(connections.exists())
        self.assertTrue(kept.connection_id.exists())

    def test_deleting_an_ancestor_and_nested_part_together(self):
        box = self._create_device_device(self.profile, identifier="BOX-OVERLAP")
        part = self._create_device_device(
            self.profile, identifier="PART-OVERLAP", parent_id=box.id
        )
        nested = self._create_device_device(
            self.profile, identifier="NESTED-OVERLAP", parent_id=part.id
        )
        connections = (box | part | nested).sudo().connection_id
        (box | nested).unlink()
        self.assertFalse((box | part | nested).exists())
        self.assertFalse(connections.exists())

    def test_database_refuses_to_bypass_part_cleanup(self):
        box = self._create_device_device(self.profile, identifier="BOX-RESTRICT")
        part = self._create_device_device(
            self.profile, identifier="PART-RESTRICT", parent_id=box.id
        )
        with self.assertRaises(RestrictViolation), self.env.cr.savepoint():
            self.env.cr.execute("DELETE FROM device_device WHERE id = %s", [box.id])
        self.assertTrue(box.exists())
        self.assertTrue(part.exists())

    def test_deleting_a_parent_does_not_bypass_a_hidden_parts_access(self):
        box = self._create_device_device(self.profile, identifier="BOX-ACCESS")
        other_company = self.env["res.company"].create({"name": "Protected parts"})
        part = self._create_device_device(
            self.profile,
            identifier="PART-ACCESS",
            parent_id=box.id,
            company_id=other_company.id,
        )
        manager = new_test_user(
            self.env, login="parts_manager", groups="device.group_device_manager"
        )
        self.assertFalse(box.with_user(manager).child_ids)
        with self.assertRaises(AccessError), self.env.cr.savepoint():
            box.with_user(manager).unlink()
        self.assertTrue(box.exists())
        self.assertTrue(part.exists())
        self.assertTrue((box | part).sudo().connection_id.exists())

    def test_a_device_cannot_be_part_of_itself(self):
        box = self._create_device_device(self.profile, identifier="BOX-3")

        with self.assertRaises(ValidationError):
            box.parent_id = box

    def test_a_cycle_of_parts_is_refused(self):
        first = self._create_device_device(self.profile, identifier="BOX-4")
        second = self._create_device_device(
            self.profile, identifier="BOX-5", parent_id=first.id
        )

        with self.assertRaises(ValidationError):
            first.parent_id = second

    def test_corrupt_cycle_stops_cleanup_even_during_uninstall(self):
        first = self._create_device_device(self.profile, identifier="CORRUPT-FIRST")
        second = self._create_device_device(
            self.profile, identifier="CORRUPT-SECOND", parent_id=first.id
        )
        self.env.cr.execute(
            "UPDATE device_device SET parent_id = %s WHERE id = %s",
            [second.id, first.id],
        )
        first.invalidate_recordset(["parent_id"])
        for uninstall in (False, True):
            with self.subTest(uninstall=uninstall):
                with self.assertRaises(ValidationError), self.env.cr.savepoint():
                    first.with_context({MODULE_UNINSTALL_FLAG: uninstall}).unlink()
        self.assertEqual(len((first | second).exists()), 2)
        self.assertEqual(len((first | second).sudo().connection_id.exists()), 2)

    def test_a_device_needs_no_profile(self):
        # An IoT box has no device.profile: the profile is a device model, and
        # not every device in the registry has one.
        device = self.env["device.device"].create(
            {"name": "Profileless", "identifier": "NO-PROFILE"}
        )

        self.assertFalse(device.config_id)
        self.assertTrue(device.credential_id)
