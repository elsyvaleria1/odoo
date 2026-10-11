from odoo.exceptions import AccessError
from odoo.tests import tagged, users
from odoo.tools import mute_logger

from odoo.addons.calendar.tests.booking.common import AppointmentSecurityCommon


@tagged("post_install", "-at_install", "security")
class TestAppointmentInviteSecurity(AppointmentSecurityCommon):
    @users("apt_manager")
    @mute_logger("odoo.addons.base.models.ir_model", "odoo.addons.base.models.ir_access")
    def test_appointment_invite_access_apt_manager(self):
        self._prepare_link_with_user()
        for share_link in self.all_share_link:
            with self.subTest(share_link=share_link):
                share_link.read(["resources_choice"])
                share_link.write({"resources_choice": "current_user"})
                share_link.unlink()

        self.env["appointment.invite"].create(
            {"appointment_type_ids": self.apt_type_apt_manager}
        )

    @users("apt_user")
    @mute_logger("odoo.addons.base.models.ir_model", "odoo.addons.base.models.ir_access")
    def test_appointment_invite_access_apt_user(self):
        self._prepare_link_with_user()
        self.share_link_apt_user.read(["resources_choice"])

        with self.assertRaises(AccessError):
            self.share_link_apt_manager.read(["resources_choice"])

        test_share_link = self.env["appointment.invite"].create(
            {
                "appointment_type_ids": self.apt_type_apt_user,
            }
        )

        for share_link in self.all_share_link:
            with self.subTest(share_link=share_link), self.assertRaises(AccessError):
                share_link.write({"resources_choice": "current_user"})
            with self.subTest(share_link=share_link), self.assertRaises(AccessError):
                share_link.unlink()

        test_share_link.write({"resources_choice": "specific_resources"})
        test_share_link.unlink()

    @users("internal_user")
    @mute_logger("odoo.addons.base.models.ir_model", "odoo.addons.base.models.ir_access")
    def test_appointment_invite_access_internal_user(self):
        self._prepare_link_with_user()
        self.share_link_internal_user.read(["resources_choice"])

        with self.assertRaises(AccessError):
            self.share_link_apt_manager.read(["resources_choice"])

        test_share_link = self.env["appointment.invite"].create(
            {
                "appointment_type_ids": self.apt_type_internal_user,
            }
        )

        for share_link in self.all_share_link:
            with self.subTest(share_link=share_link), self.assertRaises(AccessError):
                share_link.write({"resources_choice": "current_user"})
        test_share_link.write({"resources_choice": "specific_resources"})

    def _prepare_link_with_user(self):
        self.share_link_apt_manager = self.share_link_apt_manager.with_user(
            self.env.user
        )
        self.share_link_apt_user = self.share_link_apt_user.with_user(self.env.user)
        self.share_link_internal_user = self.share_link_internal_user.with_user(
            self.env.user
        )
        self.all_share_link = (
            self.share_link_apt_manager
            + self.share_link_apt_user
            + self.share_link_internal_user
        )
