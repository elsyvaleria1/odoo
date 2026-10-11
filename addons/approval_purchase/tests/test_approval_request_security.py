from odoo.exceptions import AccessError
from odoo.fields import Command
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestApprovalRequestSecurity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.owner = cls.env["res.users"].create(
            {
                "name": "Request Owner",
                "login": "security_owner",
                "group_ids": [Command.set([cls.env.ref("base.group_user").id])],
            },
        )
        cls.buyer = cls.env["res.users"].create(
            {
                "name": "Other Buyer",
                "login": "security_buyer",
                "group_ids": [
                    Command.set(
                        [
                            cls.env.ref("base.group_user").id,
                            cls.env.ref("purchase.group_purchase_user").id,
                        ],
                    ),
                ],
            },
        )
        cls.purchase_manager = cls.env["res.users"].create(
            {
                "name": "Purchase Manager",
                "login": "security_manager",
                "group_ids": [
                    Command.set(
                        [
                            cls.env.ref("base.group_user").id,
                            cls.env.ref("purchase.group_purchase_manager").id,
                        ],
                    ),
                ],
            },
        )

        cls.category = cls.env["approval.category"].create(
            {
                "name": "Confidential Purchase Request",
                "approval_type": "purchase",
                "target_model": "purchase.order",
                "approval_minimum": 1,
                "has_product": "required",
                "privacy_visibility": "restricted_users",
                "allowed_user_ids": [Command.set([cls.owner.id])],
            },
        )
        cls.request = cls.env["approval.request"].create(
            {
                "name": "Confidential Request",
                "category_id": cls.category.id,
                "request_owner_id": cls.owner.id,
            },
        )
        cls.env.flush_all()

    def test_buyer_cannot_read_a_request_of_a_restricted_category(self):
        with self.assertRaises(AccessError):
            self.request.with_user(self.buyer).read(["name"])

    def test_buyer_cannot_search_up_a_request_they_do_not_own(self):
        found = (
            self.env["approval.request"]
            .with_user(self.buyer)
            .search([("id", "=", self.request.id)])
        )

        self.assertFalse(found, "privacy_visibility must survive purchase groups")

    def test_buyer_cannot_write_a_request_they_do_not_own(self):
        with self.assertRaises(AccessError):
            self.request.with_user(self.buyer).write({"name": "renamed"})

    def test_buyer_cannot_create_a_request_owned_by_somebody_else(self):
        with self.assertRaises(AccessError):
            self.env["approval.request"].with_user(self.buyer).create(
                {
                    "name": "Forged Request",
                    "category_id": self.category.id,
                    "request_owner_id": self.owner.id,
                },
            )

    def test_buyer_still_owns_their_own_requests(self):
        open_category = self.env["approval.category"].create(
            {
                "name": "Open Purchase Request",
                "approval_type": "purchase",
                "target_model": "purchase.order",
                "approval_minimum": 1,
                "has_product": "required",
            },
        )
        own_request = (
            self.env["approval.request"]
            .with_user(self.buyer)
            .create(
                {
                    "name": "My Own Request",
                    "category_id": open_category.id,
                    "request_owner_id": self.buyer.id,
                },
            )
        )

        self.assertEqual(own_request.with_user(self.buyer).name, "My Own Request")
        own_request.with_user(self.buyer).write({"name": "My Own Request (edited)"})

    def test_approver_reads_the_request_they_must_decide(self):
        approver = self.env["res.users"].create(
            {
                "name": "Assigned Approver",
                "login": "security_approver",
                "group_ids": [
                    Command.set(
                        [
                            self.env.ref("base.group_user").id,
                            self.env.ref("purchase.group_purchase_user").id,
                        ],
                    ),
                ],
            },
        )
        self.env["approval.approver"].create(
            {
                "user_id": approver.id,
                "request_id": self.request.id,
            },
        )
        self.env.flush_all()

        self.assertEqual(self.request.with_user(approver).name, "Confidential Request")

    def test_purchase_manager_still_oversees_purchase_requests(self):
        self.assertEqual(
            self.request.with_user(self.purchase_manager).name,
            "Confidential Request",
        )

    def test_the_purchase_groups_keep_the_access_base_group_user_grants(self):
        base_only = self.env["res.users"].create(
            {
                "name": "Plain Internal User",
                "login": "security_plain_internal",
                "group_ids": [Command.set([self.env.ref("base.group_user").id])],
            },
        )

        for user in (base_only, self.buyer, self.purchase_manager):
            with self.subTest(user=user.login):
                self.assertTrue(
                    self.env["approval.category"].with_user(user).has_access("read"),
                    "every internal user reads approval categories",
                )
                for model in ("approval.request", "approval.approver"):
                    for operation in ("read", "write", "create"):
                        self.assertTrue(
                            self.env[model].with_user(user).has_access(operation),
                            f"{user.login} lost {operation} on {model}",
                        )

    def test_a_purchase_manager_still_administers_approval_categories(self):
        category = self.env["approval.category"].create(
            {"name": "Managed Category", "approval_type": "purchase"},
        )

        self.assertFalse(
            self.purchase_manager.has_group("approval.group_approval_manager"),
            "the right to write must come from the purchase row, not this one",
        )

        category.with_user(self.purchase_manager).name = "Renamed By Manager"

        self.assertEqual(category.name, "Renamed By Manager")
        self.assertFalse(
            self.env["approval.category"].with_user(self.buyer).has_access("write"),
            "a purchase user must stay read-only on categories",
        )
