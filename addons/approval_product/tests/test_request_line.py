from odoo.exceptions import AccessError, ValidationError
from odoo.tests import common, tagged

from . import common as common_module
from .common import create_test_product
from odoo.addons.approval.tests.common import ApprovalCommon


@tagged("post_install", "-at_install")
class TestRequestLineConstraints(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.admin_user = cls.env.ref("base.user_admin")

        cls.category = cls.env["approval.category"].create(
            {
                "sequence_code": "SC0041",
                "name": "Test Line Constraints Category",
                "approval_minimum": 1,
                "has_product": "required",
            }
        )

        cls.product = cls.env["product.product"].create(
            {
                "name": "Test Product",
                "type": "consu",
            }
        )

        cls.request = cls.env["approval.request"].create(
            {
                "name": "Test Line Constraints Request",
                "request_owner_id": cls.admin_user.id,
                "category_id": cls.category.id,
            }
        )

    def test_quantity_must_be_positive(self):
        with self.assertRaises(ValidationError) as ctx:
            self.env["approval.request.line"].create(
                {
                    "approval_request_id": self.request.id,
                    "product_id": self.product.id,
                    "description": "Test Line",
                    "quantity": 0,
                    "price_unit": 10.0,
                }
            )
        self.assertIn("positive", str(ctx.exception).lower())

    def test_quantity_negative_not_allowed(self):
        with self.assertRaises(ValidationError) as ctx:
            self.env["approval.request.line"].create(
                {
                    "approval_request_id": self.request.id,
                    "product_id": self.product.id,
                    "description": "Test Line",
                    "quantity": -5,
                    "price_unit": 10.0,
                }
            )
        self.assertIn("positive", str(ctx.exception).lower())

    def test_quantity_positive_allowed(self):
        line = self.env["approval.request.line"].create(
            {
                "approval_request_id": self.request.id,
                "product_id": self.product.id,
                "description": "Test Line",
                "quantity": 5,
                "price_unit": 10.0,
            }
        )
        self.assertEqual(line.quantity, 5)

    def test_price_cannot_be_negative(self):
        with self.assertRaises(ValidationError) as ctx:
            self.env["approval.request.line"].create(
                {
                    "approval_request_id": self.request.id,
                    "product_id": self.product.id,
                    "description": "Test Line",
                    "quantity": 1,
                    "price_unit": -10.0,
                }
            )
        self.assertIn("negative", str(ctx.exception).lower())

    def test_price_zero_allowed(self):
        line = self.env["approval.request.line"].create(
            {
                "approval_request_id": self.request.id,
                "product_id": self.product.id,
                "description": "Free Item",
                "quantity": 1,
                "price_unit": 0,
            }
        )
        self.assertEqual(line.price_unit, 0)

    def test_price_positive_allowed(self):
        line = self.env["approval.request.line"].create(
            {
                "approval_request_id": self.request.id,
                "product_id": self.product.id,
                "description": "Test Line",
                "quantity": 1,
                "price_unit": 99.99,
            }
        )
        self.assertEqual(line.price_unit, 99.99)


@tagged("post_install", "-at_install")
class TestRequestLineAccessControl(ApprovalCommon):
    def test_line_write_blocked_for_non_owner(self):
        common_module.ensure_publish_date_field(self.env)
        product = create_test_product(self.env)
        category = self._make_category(
            approvers=[self.approver_1],
            has_product="required",
        )
        request = self._prepare_request(category, confirm=False)
        line = self.env["approval.request.line"].create(
            {
                "approval_request_id": request.id,
                "product_id": product.id,
                "quantity": 1,
                "price_unit": 10.0,
            },
        )
        with self.assertRaises(AccessError):
            line.with_user(self.approver_1).write({"quantity": 999})
        with self.assertRaises(AccessError):
            self.env["approval.request.line"].with_user(
                self.approver_1,
            ).create(
                {
                    "approval_request_id": request.id,
                    "product_id": product.id,
                    "quantity": 1,
                    "price_unit": 10.0,
                },
            )

    def test_line_locked_after_confirm_even_for_sudo(self):
        common_module.ensure_publish_date_field(self.env)
        product = create_test_product(self.env)
        category = self._make_category(
            approvers=[self.approver_1],
            has_product="required",
        )
        request = self._prepare_request(category, confirm=False)
        line = self.env["approval.request.line"].create(
            {
                "approval_request_id": request.id,
                "product_id": product.id,
                "quantity": 1,
                "price_unit": 10.0,
            },
        )
        request.action_confirm()
        with self.assertRaises(ValidationError):
            line.sudo().write({"quantity": 999})
        with self.assertRaises(ValidationError):
            line.sudo().unlink()

    def test_line_owner_can_edit_draft(self):
        common_module.ensure_publish_date_field(self.env)
        product = create_test_product(self.env)
        category = self._make_category(
            approvers=[self.approver_1],
            has_product="required",
        )
        request = self._prepare_request(category, confirm=False)
        line = (
            self.env["approval.request.line"]
            .with_user(
                self.owner_user,
            )
            .create(
                {
                    "approval_request_id": request.id,
                    "product_id": product.id,
                    "quantity": 1,
                    "price_unit": 10.0,
                },
            )
        )
        line.with_user(self.owner_user).write({"quantity": 3})
        self.assertEqual(line.quantity, 3)
