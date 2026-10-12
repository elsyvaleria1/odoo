from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import new_test_user

from odoo.addons.hr.tests.common import TestHrCommon


@tagged("post_install", "-at_install")
class TestSelfPersonalInformation(TestHrCommon):
    PERSONAL_FIELDS = (
        "marital",
        "spouse_complete_name",
        "spouse_birthdate",
        "children",
        "legal_name",
        "birthday",
        "birthday_public_display",
        "place_of_birth",
        "country_of_birth",
        "sex",
    )

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.worker = new_test_user(
            cls.env,
            login="worker_personal_info",
            groups="base.group_user",
            name="Worker",
        )
        cls.worker_employee = cls.env["hr.employee"].create(
            {
                "name": "Worker",
                "user_id": cls.worker.id,
                "marital": "married",
                "children": 2,
                "birthday": "1990-05-04",
                "place_of_birth": "Culiacan",
            }
        )

    def test_the_employee_can_read_their_own_personal_information(self):
        me = self.worker.with_user(self.worker)

        values = me.read(list(self.PERSONAL_FIELDS))[0]

        self.assertEqual(values["marital"], "married")
        self.assertEqual(values["children"], 2)
        self.assertEqual(str(values["birthday"]), "1990-05-04")
        self.assertEqual(values["place_of_birth"], "Culiacan")

    def test_every_personal_field_is_self_readable(self):
        readable = self.env["res.users"].SELF_READABLE_FIELDS
        for field_name in self.PERSONAL_FIELDS:
            with self.subTest(field=field_name):
                self.assertIn(field_name, readable)

    def test_the_employee_cannot_read_somebody_else(self):
        other = self.env["hr.employee"].create(
            {"name": "Someone Else", "marital": "single"}
        )
        with self.assertRaises(AccessError):
            other.with_user(self.worker).read(["marital"])
