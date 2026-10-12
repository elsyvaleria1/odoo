from odoo.exceptions import AccessError
from odoo.tests import tagged, users
from odoo.tools import mute_logger

from odoo.addons.calendar.tests.booking.test_appointment_type_security import (
    TestAppointmentTypeSecurity,
)


@tagged("security")
class WebsiteAppointmentTypeSecurityTest(TestAppointmentTypeSecurity):
    @users("public_user")
    @mute_logger(
        "odoo.addons.base.models.ir_model", "odoo.addons.base.models.ir_access"
    )
    def test_website_appointment_type_website_published_access(self):
        self._prepare_types_with_user()
        for appointment_type in self.all_apt_types:
            with (
                self.subTest(appointment_type=appointment_type),
                self.assertRaises(AccessError),
            ):
                appointment_type.read(["name"])

        self.all_apt_types.with_user(self.apt_manager).write(
            {"website_published": True}
        )
        for appointment_type in self.all_apt_types:
            with self.subTest(appointment_type=appointment_type):
                appointment_type.read(["name"])
