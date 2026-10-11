from datetime import datetime

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestSystemOnlyModelsStayReadOnlyForPlainUsers(TransactionCase):
    MODELS = ("resource.assignment", "resource.role", "resource.reservation")

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.reader = cls.env["res.users"].create(
            {
                "name": "Resource ACL reader",
                "login": "resource_acl_reader",
                "group_ids": [(6, 0, [cls.env.ref("base.group_user").id])],
            }
        )

    def test_plain_user_can_read_but_not_write(self):
        for model in self.MODELS:
            Model = self.env[model].with_user(self.reader)
            with self.subTest(model=model):
                Model.check_access("read")
                for operation in ("write", "create", "unlink"):
                    with (
                        self.subTest(operation=operation),
                        self.assertRaises(AccessError),
                    ):
                        Model.check_access(operation)


@tagged("post_install", "-at_install")
class TestMultiCompanyRuleVisibility(TransactionCase):
    def setUp(self):
        super().setUp()
        self.other_company = self.env["res.company"].create({"name": "Other Co ACL"})

    def test_assignment_from_another_company_is_not_visible(self):
        resource = (
            self.env["resource.resource"]
            .with_company(self.other_company)
            .create(
                {
                    "name": "Foreign asset",
                    "type": "material",
                    "tz": "UTC",
                    "company_id": self.other_company.id,
                }
            )
        )
        assignee = (
            self.env["resource.resource"]
            .with_company(self.other_company)
            .create(
                {
                    "name": "Foreign holder",
                    "type": "human",
                    "tz": "UTC",
                    "company_id": self.other_company.id,
                }
            )
        )
        assignment = (
            self.env["resource.assignment"]
            .sudo()
            .create({"resource_id": resource.id, "assignee_id": assignee.id})
        )
        admin = self.env.ref("base.user_admin")
        self.assertNotIn(
            assignment,
            self.env["resource.assignment"].with_user(admin).search([]),
        )

    def test_reservation_from_another_company_is_not_visible(self):

        resource = (
            self.env["resource.resource"]
            .with_company(self.other_company)
            .create(
                {
                    "name": "Foreign asset",
                    "type": "material",
                    "tz": "UTC",
                    "company_id": self.other_company.id,
                }
            )
        )
        reservation = (
            self.env["resource.reservation"]
            .sudo()
            .create(
                {
                    "name": "Foreign booking",
                    "resource_id": resource.id,
                    "date_start": datetime(2026, 6, 1, 8, 0),
                    "date_end": datetime(2026, 6, 1, 17, 0),
                    "res_model": "res.partner",
                    "res_id": 1,
                    "company_id": self.other_company.id,
                }
            )
        )
        admin = self.env.ref("base.user_admin")
        self.assertNotIn(
            reservation,
            self.env["resource.reservation"].with_user(admin).search([]),
        )


@tagged("post_install", "-at_install")
class TestScheduleExceptionAccess(TransactionCase):
    def test_who_may_edit_an_exception_may_read_it(self):
        employee = new_test_user(
            self.env, login="acl_employee", groups="base.group_user"
        )
        manager = new_test_user(
            self.env,
            login="acl_manager",
            groups="base.group_user,base.group_erp_manager",
        )
        resource = self.env["resource.resource"].create(
            {"name": "Employee", "user_id": employee.id, "tz": "UTC"}
        )
        exception = self.env["resource.schedule.exception"].create(
            {
                "name": "Dentist",
                "resource_id": resource.id,
                "date_from": "2026-10-05 08:00:00",
                "date_to": "2026-10-05 10:00:00",
            }
        )
        as_manager = exception.with_user(manager)
        self.assertEqual(as_manager.read(["name"])[0]["name"], "Dentist")
        as_manager.name = "Dentist, moved"
        other = new_test_user(self.env, login="acl_other", groups="base.group_user")
        with self.assertRaises(AccessError):
            exception.with_user(other).read(["name"])


@tagged("post_install", "-at_install")
class TestResourceAdminAccess(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sysadmin = cls.env["res.users"].create(
            {
                "name": "Resource sysadmin",
                "login": "resource_sysadmin",
                "group_ids": [
                    (
                        6,
                        0,
                        [
                            cls.env.ref("base.group_user").id,
                            cls.env.ref("base.group_system").id,
                        ],
                    )
                ],
            }
        )

    def test_sysadmin_can_manage_resources(self):
        Resource = self.env["resource.resource"].with_user(self.sysadmin)
        for operation in ("read", "write", "create", "unlink"):
            with self.subTest(operation=operation):
                Resource.check_access(operation)

    def test_the_menu_action_actually_works(self):
        resource = (
            self.env["resource.resource"]
            .with_user(self.sysadmin)
            .create({"name": "made from the menu", "tz": "UTC"})
        )
        resource.name = "renamed"
        self.assertEqual(resource.name, "renamed")
        resource.unlink()

    def test_plain_user_stays_read_only(self):
        reader = self.env["res.users"].create(
            {
                "name": "Resource reader",
                "login": "resource_reader",
                "group_ids": [(6, 0, [self.env.ref("base.group_user").id])],
            }
        )
        Resource = self.env["resource.resource"].with_user(reader)
        Resource.check_access("read")
        for operation in ("write", "create", "unlink"):
            with self.subTest(operation=operation), self.assertRaises(AccessError):
                Resource.check_access(operation)
