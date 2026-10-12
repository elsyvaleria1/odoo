from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestHrAccessBind(TransactionCase):
    def test_employees_and_units(self):
        user = self.env["res.users"].create(
            {
                "login": "binder",
                "name": "Binder",
                "group_ids": [Command.set(self.env.ref("base.group_user").ids)],
            }
        )
        sales = self.env["hr.department"].create({"name": "Sales"})
        other = self.env["res.company"].create({"name": "Other"})
        working = self.env["hr.employee"].create(
            {"name": "Binder", "user_id": user.id, "department_id": sales.id}
        )
        gone = self.env["hr.employee"].create(
            {
                "name": "Binder elsewhere",
                "user_id": user.id,
                "company_id": other.id,
                "department_id": self.env["hr.department"]
                .create({"name": "Gone", "company_id": other.id})
                .id,
            }
        )
        gone.action_archive()
        access = self.env["ir.access"].with_user(user)
        self.assertEqual(access._access_bind_employees(), sorted((working + gone).ids))
        self.assertEqual(
            access._access_bind_employees(),
            self.env["hr.employee"]
            .with_context(active_test=False)
            .search([("user_id", "=", user.id)], order="id")
            .ids,
        )
        self.assertEqual(access._access_bind_units(), sales.ids)

    def test_relinking_an_employee_moves_what_its_rows_reach(self):
        group_user = self.env.ref("base.group_user")
        first, second = self.env["res.users"].create(
            [
                {
                    "login": login,
                    "name": login,
                    "group_ids": [Command.set(group_user.ids)],
                }
                for login in ("bind_first", "bind_second")
            ]
        )
        employee = self.env["hr.employee"].create(
            {"name": "Relinked", "user_id": first.id}
        )
        request = self.env["hr.employee.change.request"].create(
            {"employee_id": employee.id}
        )
        Requests = self.env["hr.employee.change.request"]
        self.assertEqual(
            Requests.with_user(first).search([("id", "=", request.id)]), request
        )

        employee.user_id = second

        self.assertFalse(Requests.with_user(first).search([("id", "=", request.id)]))
        self.assertEqual(
            Requests.with_user(second).search([("id", "=", request.id)]), request
        )
