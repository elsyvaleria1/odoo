from odoo.exceptions import AccessError
from odoo.fields import Command
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.approval.tests.common import pool_step


@tagged("post_install", "-at_install")
class TestApprovalRequestSecurity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")

        cls.owner = cls._make_salesperson("security_owner")
        cls.other = cls._make_salesperson("security_other")

        cls.restricted_category = cls.env["approval.category"].create(
            {
                "name": "Restricted Category",
                "approval_type": "sale",
                "target_model": False,
                "approval_minimum": 1,
                "company_id": cls.company.id,
                "privacy_visibility": "restricted_users",
                "allowed_user_ids": [Command.set([])],
            },
        )
        cls.foreign_request = cls.env["approval.request"].create(
            {
                "name": "Foreign Request",
                "category_id": cls.restricted_category.id,
                "request_owner_id": cls.owner.id,
                "company_id": cls.company.id,
            },
        )

    @classmethod
    def _make_salesperson(cls, login):
        return cls.env["res.users"].create(
            {
                "name": login,
                "login": login,
                "company_id": cls.company.id,
                "company_ids": [Command.set(cls.company.ids)],
                "group_ids": [
                    Command.set(
                        [
                            cls.env.ref("base.group_user").id,
                            cls.env.ref("sale.group_sale_salesman").id,
                        ],
                    ),
                ],
            },
        )

    def test_the_blanket_sale_user_rules_are_gone(self):
        for xmlid in (
            "approval_sale.approval_request_sale_user",
            "approval_sale.approval_approver_sale_user",
        ):
            self.assertFalse(self.env.ref(xmlid, raise_if_not_found=False))

    def test_a_salesperson_cannot_read_a_foreign_restricted_request(self):
        found = (
            self.env["approval.request"]
            .with_user(self.other)
            .search([("id", "=", self.foreign_request.id)])
        )

        self.assertFalse(found)

    def test_a_salesperson_cannot_create_a_request_owned_by_someone_else(self):
        with self.assertRaises(AccessError):
            self.env["approval.request"].with_user(self.other).create(
                {
                    "name": "Forged Request",
                    "category_id": self.restricted_category.id,
                    "request_owner_id": self.owner.id,
                    "company_id": self.company.id,
                },
            )

    def test_the_owner_still_reads_their_own_request(self):
        found = (
            self.env["approval.request"]
            .with_user(self.owner)
            .search([("id", "=", self.foreign_request.id)])
        )

        self.assertEqual(found, self.foreign_request)

    def test_an_approver_still_reads_the_request_they_approve(self):
        self.foreign_request.sudo().write(
            {
                "approver_ids": [
                    Command.create({"user_id": self.other.id, "required": True}),
                ],
            },
        )

        found = (
            self.env["approval.request"]
            .with_user(self.other)
            .search([("id", "=", self.foreign_request.id)])
        )

        self.assertEqual(found, self.foreign_request)

    def test_an_employees_category_is_still_readable_by_everyone(self):
        category = self.env["approval.category"].create(
            {
                "name": "Employees Category",
                "approval_type": "sale",
                "target_model": False,
                "approval_minimum": 1,
                "company_id": self.company.id,
                "privacy_visibility": "employees",
            },
        )
        request = self.env["approval.request"].create(
            {
                "name": "Employees Request",
                "category_id": category.id,
                "request_owner_id": self.owner.id,
                "company_id": self.company.id,
            },
        )

        found = (
            self.env["approval.request"]
            .with_user(self.other)
            .search([("id", "=", request.id)])
        )

        self.assertEqual(found, request)

    def test_a_sales_manager_still_reads_every_sale_request(self):
        manager = self.env["res.users"].create(
            {
                "name": "security_manager",
                "login": "security_manager",
                "company_id": self.company.id,
                "company_ids": [Command.set(self.company.ids)],
                "group_ids": [
                    Command.set(
                        [
                            self.env.ref("base.group_user").id,
                            self.env.ref("sale.group_sale_manager").id,
                        ],
                    ),
                ],
            },
        )

        found = (
            self.env["approval.request"]
            .with_user(manager)
            .search([("id", "=", self.foreign_request.id)])
        )

        self.assertEqual(found, self.foreign_request)

    def _category_of_another_department(self):
        return self.env["approval.category"].create(
            {
                "name": "Another Department Category",
                "approval_minimum": 1,
                "company_id": self.company.id,
            },
        )

    def _manager(self, login, group_xmlids):
        return self.env["res.users"].create(
            {
                "name": login,
                "login": login,
                "company_id": self.company.id,
                "company_ids": [Command.set(self.company.ids)],
                "group_ids": [
                    Command.set(
                        [self.env.ref(xmlid).id for xmlid in group_xmlids],
                    ),
                ],
            },
        )

    def test_a_sales_manager_cannot_write_a_foreign_type_category(self):
        manager = self._manager(
            "category_sale_manager",
            ("base.group_user", "sale.group_sale_manager"),
        )
        foreign = self._category_of_another_department()

        for operation in ("write", "unlink"):
            with self.assertRaises(AccessError):
                foreign.with_user(manager).check_access(operation)

        with self.assertRaises(AccessError):
            foreign.with_user(manager).write({"name": "Renamed by sales"})

    def test_a_sales_manager_still_writes_sale_categories(self):
        manager = self._manager(
            "category_sale_manager_own",
            ("base.group_user", "sale.group_sale_manager"),
        )

        self.restricted_category.with_user(manager).check_access("write")
        self.restricted_category.with_user(manager).write({"name": "Renamed"})
        self.assertEqual(self.restricted_category.name, "Renamed")

        created = (
            self.env["approval.category"]
            .with_user(manager)
            .create(
                {
                    "name": "Created by a sales manager",
                    "approval_type": "sale",
                    "approval_minimum": 1,
                    "company_id": self.company.id,
                },
            )
        )
        self.assertEqual(created.approval_type, "sale")

    def test_an_approval_manager_still_writes_every_category(self):
        manager = self._manager(
            "category_both_manager",
            (
                "base.group_user",
                "sale.group_sale_manager",
                "approval.group_approval_manager",
            ),
        )
        foreign = self._category_of_another_department()

        foreign.with_user(manager).check_access("write")
        foreign.with_user(manager).write({"name": "Renamed by approvals"})
        self.assertEqual(
            foreign.name,
            "Renamed by approvals",
            "narrowing the sales manager must not narrow the approval manager: "
            "rules of different groups are OR'ed, but a group with no rule "
            "contributes nothing to the union",
        )

    def test_a_sales_manager_cannot_unlink_a_submitted_request(self):
        manager = self._manager(
            "security_manager_unlink",
            ("base.group_user", "sale.group_sale_manager"),
        )
        category = self.env["approval.category"].create(
            {
                "name": "Confirmable Sale Category",
                "approval_type": "sale",
                "approval_minimum": 1,
                "company_id": self.company.id,
                "step_ids": pool_step([(self.env.user.id, True, 10)], minimum=1),
            },
        )
        request = self.env["approval.request"].create(
            {
                "name": "Submitted Request",
                "category_id": category.id,
                "request_owner_id": manager.id,
                "company_id": self.company.id,
            },
        )
        request.with_user(manager).action_confirm()
        self.assertEqual(request.state, "pending")

        with self.assertRaises(AccessError):
            request.with_user(manager).check_access("unlink")

    def test_a_sales_manager_still_unlinks_their_own_draft(self):
        manager = self._manager(
            "security_manager_draft",
            ("base.group_user", "sale.group_sale_manager"),
        )
        draft = self.env["approval.request"].create(
            {
                "name": "Draft Request",
                "category_id": self.restricted_category.id,
                "request_owner_id": manager.id,
                "company_id": self.company.id,
            },
        )
        self.assertEqual(draft.state, "new")

        draft.with_user(manager).check_access("unlink")
        draft.with_user(manager).unlink()

    def test_the_redundant_acl_rows_are_gone(self):
        for xmlid in (
            "approval_sale.access_approval_category_user_sale",
            "approval_sale.access_approval_request_user_sale",
            "approval_sale.access_approval_request_manager_sale",
            "approval_sale.access_approval_approver_user_sale",
            "approval_sale.access_approval_approver_manager_sale",
        ):
            self.assertFalse(
                self.env.ref(xmlid, raise_if_not_found=False),
                f"{xmlid} granted no more than base already grants every "
                f"internal user, so it only made the file read as if it "
                f"scoped access",
            )

    def test_base_still_grants_what_those_rows_restated(self):
        seller = self._make_salesperson("acl_seller")
        manager = self._manager(
            "acl_manager",
            ("base.group_user", "sale.group_sale_manager"),
        )

        for user in (seller, manager):
            self.env["approval.category"].with_user(user).check_access("read")
            for model in ("approval.request", "approval.approver"):
                for operation in ("read", "write", "create", "unlink"):
                    self.env[model].with_user(user).check_access(operation)

    def test_a_salesperson_still_runs_a_request_end_to_end(self):
        seller = self._make_salesperson("acl_flow_seller")
        approver = self._manager(
            "acl_flow_approver",
            ("base.group_user", "sale.group_sale_manager"),
        )
        category = self.env["approval.category"].create(
            {
                "name": "ACL Flow Category",
                "approval_type": "sale",
                "approval_minimum": 1,
                "company_id": self.company.id,
                "step_ids": pool_step([(approver.id, True, 10)], minimum=1),
            },
        )

        request = (
            self.env["approval.request"]
            .with_user(seller)
            .create({"category_id": category.id, "name": "ACL Flow Request"})
        )
        request.with_user(seller).action_confirm()
        self.assertEqual(
            request.with_user(seller).read(["state"])[0]["state"], "pending"
        )

        request.with_user(approver).action_approve()
        self.assertEqual(request.state, "approved")
