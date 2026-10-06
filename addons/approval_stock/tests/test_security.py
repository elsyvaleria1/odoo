from odoo.exceptions import AccessError
from odoo.fields import Command
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user

from odoo.addons.approval.tests.common import pool_step


@tagged("post_install", "-at_install")
class TestApprovalCategoryAccess(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.stock_manager = new_test_user(
            cls.env,
            login="approval_stock_manager_acl",
            groups="base.group_user,stock.group_stock_manager",
        )
        cls.foreign_category = cls.env["approval.category"].create(
            {
                "name": "Payroll Advance",
                "approval_type": "hr",
                "approval_minimum": 3,
            },
        )

    def test_stock_manager_is_not_an_approval_manager(self):
        self.assertFalse(
            self.stock_manager.has_group("approval.group_approval_manager"),
            "the premise of this file: the stock role is not the approval role",
        )

    def test_stock_manager_cannot_rewrite_a_foreign_category(self):
        category = self.foreign_category.with_user(self.stock_manager)

        with self.assertRaises(AccessError):
            category.write({"approval_minimum": 1})

    def test_stock_manager_cannot_delete_a_foreign_category(self):
        category = self.foreign_category.with_user(self.stock_manager)

        with self.assertRaises(AccessError):
            category.unlink()

    def test_stock_manager_still_reads_categories(self):
        category = self.foreign_category.with_user(self.stock_manager)

        self.assertEqual(
            category.name,
            "Payroll Advance",
            "the mixin has to FIND categories to route an approval; only "
            "editing them is the approval manager's job",
        )


@tagged("post_install", "-at_install")
class TestApprovalRequestVisibility(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.owner = new_test_user(
            cls.env,
            login="approval_stock_request_owner",
            groups="base.group_user",
        )
        cls.bystander = new_test_user(
            cls.env,
            login="approval_stock_bystander",
            groups="base.group_user,stock.group_stock_user",
        )
        cls.category = cls.env["approval.category"].create(
            {
                "name": "Restricted Stock Transfer",
                "approval_type": "stock",
                "approval_minimum": 1,
                "privacy_visibility": "restricted_users",
                "allowed_user_ids": [Command.link(cls.owner.id)],
            },
        )
        cls.request = cls.env["approval.request"].create(
            {
                "name": "Restricted Stock Request",
                "category_id": cls.category.id,
                "request_owner_id": cls.owner.id,
            },
        )
        cls.open_category = cls.env["approval.category"].create(
            {
                "name": "Open Stock Transfer",
                "approval_type": "stock",
                "approval_minimum": 1,
                "privacy_visibility": "employees",
            },
        )

    def test_stock_user_does_not_see_a_restricted_request(self):
        with self.assertRaises(AccessError):
            self.request.with_user(self.bystander).read(["name"])

    def test_the_audience_still_sees_its_own_request(self):
        self.assertEqual(
            self.request.with_user(self.owner).name,
            "Restricted Stock Request",
            "the base approval rules grant the owner their own request; "
            "removing the blanket stock rule must not touch that",
        )

    def test_a_stock_user_still_creates_their_own_request(self):
        request = (
            self.env["approval.request"]
            .with_user(self.bystander)
            .create(
                {
                    "name": "Own Stock Request",
                    "category_id": self.open_category.id,
                    "request_owner_id": self.bystander.id,
                },
            )
        )

        self.assertEqual(
            request.request_owner_id,
            self.bystander,
            "approval.approval_request_user_create covers the mixin flow, "
            "which sets request_owner_id to env.user",
        )


@tagged("post_install", "-at_install")
class TestApprovalNotificationAudience(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.company.id)],
            limit=1,
        )
        cls.picking_type = cls.warehouse.int_type_id
        cls.picking_type.active = True
        cls.location_src = cls.env["stock.location"].create(
            {
                "name": "Audience Source",
                "usage": "internal",
                "location_id": cls.warehouse.view_location_id.id,
                "company_id": cls.company.id,
                "stock_approval_required": True,
            },
        )
        cls.location_dest = cls.env["stock.location"].create(
            {
                "name": "Audience Dest",
                "usage": "internal",
                "location_id": cls.warehouse.view_location_id.id,
                "company_id": cls.company.id,
            },
        )
        cls.product = cls.env["product.product"].create(
            {"name": "Audience Product", "is_storable": True},
        )
        cls.category = cls.env["approval.category"].create(
            {
                "name": "Audience Stock Approval",
                "approval_type": "stock",
                "company_id": cls.company.id,
                "stock_approval_mode": "location",
                "location_ids": [Command.link(cls.location_src.id)],
                "step_ids": pool_step(
                    [(cls.env.ref("base.user_admin").id, False, 10)], minimum=1
                ),
            },
        )
        cls.customer = cls.env["res.partner"].create(
            {"name": "Following Customer", "email": "customer@example.com"},
        )
        cls.approved_subtype = cls.env.ref("approval_stock.mt_stock_approved")
        cls.refused_subtype = cls.env.ref("approval_stock.mt_stock_refused")

    def test_both_subtypes_are_internal(self):
        self.assertTrue(self.approved_subtype.internal)
        self.assertTrue(self.refused_subtype.internal)

    def test_a_customer_following_the_transfer_is_not_told_who_approved_it(self):
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": self.picking_type.id,
                "location_id": self.location_src.id,
                "location_dest_id": self.location_dest.id,
                "company_id": self.company.id,
                "move_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": 3.0,
                            "location_id": self.location_src.id,
                            "location_dest_id": self.location_dest.id,
                        },
                    ),
                ],
            },
        )
        picking.message_subscribe(partner_ids=[self.customer.id])
        picking.action_create_approval_request()
        picking.approval_request_id.approver_ids[0].with_context(
            skip_wizard=True,
        ).action_approve()
        picking.invalidate_recordset()

        message = picking.message_ids.filtered(
            lambda m: m.subtype_id == self.approved_subtype,
        )
        self.assertTrue(message, "the approval message is still posted")
        notified = self.env["mail.notification"].search(
            [("mail_message_id", "in", message.ids)],
        )

        self.assertNotIn(
            self.customer,
            notified.res_partner_id,
            "who approved an internal warehouse transfer is internal workflow",
        )
