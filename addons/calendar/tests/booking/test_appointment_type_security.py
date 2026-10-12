import base64
from datetime import datetime, timedelta

from odoo.exceptions import AccessError
from odoo.tests import tagged, users
from odoo.tools import file_open, mute_logger

from odoo.addons.calendar.tests.booking.common import AppointmentSecurityCommon
from odoo.addons.mail.tests.common import mail_new_test_user


@tagged("security")
class TestAppointmentTypeSecurity(AppointmentSecurityCommon):
    @users("apt_manager")
    @mute_logger(
        "odoo.addons.base.models.ir_model", "odoo.addons.base.models.ir_access"
    )
    def test_appointment_type_access_apt_manager(self):
        self._prepare_types_with_user()
        for appointment_type in self.all_apt_types:
            with self.subTest(appointment_type=appointment_type):
                appointment_type.read(["name"])
                appointment_type.write({"is_published": True})
                appointment_type.unlink()
        self.env["appointment.type"].create({"name": "Test Create"})

    @users("apt_user")
    @mute_logger(
        "odoo.addons.base.models.ir_model", "odoo.addons.base.models.ir_access"
    )
    def test_appointment_type_access_apt_user(self):
        self._prepare_types_with_user()
        with self.assertRaises(AccessError):
            self.apt_type_apt_manager.read(["name"])
        with self.assertRaises(AccessError):
            self.apt_type_internal_user.read(["name"])
        (self.apt_type_apt_user + self.apt_type_resource + self.apt_type_no_staff).read(
            ["name"]
        )
        for appointment_type in self.apt_type_apt_manager + self.apt_type_internal_user:
            with self.subTest(appointment_type=appointment_type):
                appointment_type.with_user(self.apt_manager).write(
                    {"is_published": True}
                )
                appointment_type.read(["name"])

        created_apt = self.env["appointment.type"].create(
            {
                "name": "Test Create",
            }
        )

        for appointment_type in self.all_apt_types:
            with (
                self.subTest(appointment_type=appointment_type),
                self.assertRaises(AccessError),
            ):
                appointment_type.write({"name": "test"})
            with (
                self.subTest(appointment_type=appointment_type),
                self.assertRaises(AccessError),
            ):
                appointment_type.unlink()

        created_apt.write({"name": "test"})
        created_apt.unlink()

    @users("internal_user")
    @mute_logger(
        "odoo.addons.base.models.ir_model", "odoo.addons.base.models.ir_access"
    )
    def test_appointment_type_access_internal_user(self):
        self._prepare_types_with_user()
        with self.assertRaises(AccessError):
            self.apt_type_apt_manager.read(["name"])
        with self.assertRaises(AccessError):
            self.apt_type_apt_user.read(["name"])
        (
            self.apt_type_internal_user
            + self.apt_type_resource
            + self.apt_type_no_staff
        ).read(["name"])
        for appointment_type in self.apt_type_apt_manager + self.apt_type_apt_user:
            with self.subTest(appointment_type=appointment_type):
                appointment_type.with_user(self.apt_manager).write(
                    {"is_published": True}
                )
                appointment_type.read(["name"])
        with self.assertRaises(AccessError):
            self.env["appointment.type"].create({"name": "Test Create"})
        for appointment_type in self.all_apt_types:
            with self.subTest(appointment_type=appointment_type):
                with self.assertRaises(AccessError):
                    appointment_type.write({"is_published": True})
                with self.assertRaises(AccessError):
                    appointment_type.unlink()

    @users("public_user")
    @mute_logger(
        "odoo.addons.base.models.ir_model", "odoo.addons.base.models.ir_access"
    )
    def test_appointment_type_access_public_user(self):
        self._prepare_types_with_user()
        for appointment_type in self.all_apt_types:
            with self.subTest(appointment_type=appointment_type):
                with self.assertRaises(AccessError):
                    appointment_type.read(["name"])
                with self.assertRaises(AccessError):
                    appointment_type.write({"is_published": True})
                with self.assertRaises(AccessError):
                    appointment_type.unlink()
        with self.assertRaises(AccessError):
            self.env["appointment.type"].create({"name": "Test Create"})

    @users("staff_user_aust")
    def test_appointment_type_customer_description_access(self):
        appointment_type = self.apt_type_bxls_2days
        appointment_type.sudo().staff_user_ids = [self.apt_manager.id]
        appointment_type.sudo().message_confirmation = "Test confirmation message"

        test_event = self.env["calendar.event"].create(
            {
                "name": "Test Event for Non-staff Attendee",
                "start": datetime.now(),
                "stop": datetime.now() + timedelta(hours=1),
                "appointment_type_id": appointment_type.id,
                "user_id": self.apt_manager.id,
                "partner_ids": [
                    (
                        6,
                        0,
                        [self.env.user.partner_id.id, self.apt_manager.partner_id.id],
                    )
                ],
            }
        )

        test_event.appointment_type_id.invalidate_recordset(["message_confirmation"])
        self.assertIn(
            "Test confirmation message", test_event._get_customer_description()
        )

    @users("public_user")
    @mute_logger(
        "odoo.addons.base.models.ir_model", "odoo.addons.base.models.ir_access"
    )
    def test_appointment_type_image_access_public_user(self):
        self._prepare_types_with_user()

        placeholder_image = file_open(
            self.env["appointment.type"]._get_placeholder_filename("image_1920"), "rb"
        ).read()
        test_image_b64 = b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGNgYGAAAAAEAAH2FzhVAAAAAElFTkSuQmCC"
        test_image = base64.b64decode(test_image_b64)

        (self.apt_type_apt_manager + self.apt_type_resource).with_user(
            self.apt_manager
        ).write({"image_1920": test_image_b64})
        cases = [
            (self.apt_type_apt_manager, test_image),
            (self.apt_type_apt_user, placeholder_image),
            (self.apt_type_internal_user, placeholder_image),
            (self.apt_type_resource, test_image),
            (self.apt_type_no_staff, placeholder_image),
        ]
        for appointment_type, expected_image in cases:
            with self.subTest(appointment_type=appointment_type):
                res = self.url_open(
                    f"/web/image/appointment.type/{appointment_type.id}/image_1920"
                )
                self.assertEqual(res.status_code, 200)
                self.assertEqual(res.content, expected_image)

    def test_portal_attendee_can_search_appointment_events(self):
        portal_user = mail_new_test_user(
            self.env, login="portal_attendee", groups="base.group_portal"
        )
        events = self.env["calendar.event"].create(
            [
                {
                    "name": f"Booked with {appointment_type.name}",
                    "appointment_type_id": appointment_type.id,
                    "partner_ids": [(4, portal_user.partner_id.id)],
                    "start": self.reference_monday,
                    "stop": self.reference_monday + timedelta(hours=1),
                    "user_id": self.apt_manager.id,
                }
                for appointment_type in self.apt_type_apt_manager
                + self.apt_type_resource
            ]
        )
        with self.assertRaises(AccessError):
            self.apt_type_resource.with_user(portal_user).read(["name"])

        found = (
            self.env["calendar.event"]
            .with_user(portal_user)
            .search(
                [
                    ("user_id", "!=", portal_user.id),
                    ("partner_ids", "in", portal_user.partner_id.ids),
                    ("appointment_type_id", "!=", False),
                ]
            )
        )
        self.assertEqual(found, events)

    def _prepare_types_with_user(self):
        self.apt_type_apt_manager = self.apt_type_apt_manager.with_user(self.env.user)
        self.apt_type_apt_user = self.apt_type_apt_user.with_user(self.env.user)
        self.apt_type_internal_user = self.apt_type_internal_user.with_user(
            self.env.user
        )
        self.apt_type_resource = self.apt_type_resource.with_user(self.env.user)
        self.apt_type_no_staff = self.apt_type_no_staff.with_user(self.env.user)
        self.all_apt_types = (
            self.apt_type_apt_manager
            + self.apt_type_apt_user
            + self.apt_type_internal_user
            + self.apt_type_resource
            + self.apt_type_no_staff
        )
