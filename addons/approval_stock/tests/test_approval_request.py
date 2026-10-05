from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.approval.tests.common import add_category_approver
from odoo.addons.approval_product.tests.common import create_test_product


class TestApprovalRequestStock(TransactionCase):
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

        cls.location_src = cls.warehouse.lot_stock_id
        cls.location_dest = cls.env["stock.location"].create(
            {
                "name": "Test Dest Location",
                "usage": "internal",
                "company_id": cls.company.id,
            },
        )

        cls.product = create_test_product(
            cls.env,
            name="Test Product for Approval",
            type="consu",
            is_storable=True,
        )

        cls.stock_category = cls.env["approval.category"].create(
            {
                "name": "Stock Transfer Approval (request tests)",
                "approval_type": "stock",
                "target_model": "stock.picking",
                "has_product": "required",
                "company_id": cls.company.id,
            },
        )

        cls.user = cls.env.ref("base.user_admin")

    def test_create_approval_request_for_stock(self):
        request = self.env["approval.request"].create(
            {
                "name": "Stock Transfer Request",
                "category_id": self.stock_category.id,
                "request_owner_id": self.user.id,
                "company_id": self.company.id,
            },
        )

        self.assertEqual(request.category_id, self.stock_category)
        self.assertEqual(request.request_owner_id, self.user)

    def test_count_stock_picking_empty(self):
        request = self.env["approval.request"].create(
            {
                "name": "Empty Stock Request",
                "category_id": self.stock_category.id,
                "request_owner_id": self.user.id,
                "company_id": self.company.id,
            },
        )

        self.assertEqual(request.count_stock_picking, 0)

    def test_action_view_target_documents_empty(self):
        request = self.env["approval.request"].create(
            {
                "name": "View Picking Test",
                "category_id": self.stock_category.id,
                "request_owner_id": self.user.id,
                "company_id": self.company.id,
            },
        )

        action = request.action_view_target_documents()

        self.assertEqual(action["type"], "ir.actions.act_window")
        self.assertEqual(action["res_model"], "stock.picking")


@tagged("post_install", "-at_install")
class TestApprovalRequestAssetLog(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")

        cls.asset_category = cls.env["approval.category"].create(
            {
                "name": "Asset Log Approval",
                "approval_type": "asset_log",
                "has_asset": "required",
                "has_odometer": "required",
                "has_date": "required",
                "company_id": cls.company.id,
            },
        )

        cls.user = cls.env.ref("base.user_admin")

    def test_has_asset_field_related(self):
        request = self.env["approval.request"].create(
            {
                "name": "Asset Log Request",
                "category_id": self.asset_category.id,
                "request_owner_id": self.user.id,
                "company_id": self.company.id,
            },
        )

        self.assertEqual(request.has_asset, "required")

    def test_has_odometer_field_related(self):
        request = self.env["approval.request"].create(
            {
                "name": "Asset Log Request",
                "category_id": self.asset_category.id,
                "request_owner_id": self.user.id,
                "company_id": self.company.id,
            },
        )

        self.assertEqual(request.has_odometer, "required")

    def test_action_create_asset_log_missing_vehicle(self):
        request = self.env["approval.request"].create(
            {
                "name": "Missing Vehicle Request",
                "category_id": self.asset_category.id,
                "request_owner_id": self.user.id,
                "company_id": self.company.id,
            },
        )

        with self.assertRaises(UserError):
            request.action_create_asset_log()

    def test_an_approved_request_books_a_log_against_its_vehicle(self):
        vehicle_template = self.env["product.template"].create(
            {
                "name": "Approval probe truck",
                "is_storable": True,
                "tracking": "serial",
                "asset_kind_id": self.env.ref("resource_asset.kind_vehicle").id,
            }
        )
        vehicle = self.env["product.trace"].create(
            {
                "name": "APPROVAL-VEH-1",
                "product_id": vehicle_template.product_variant_ids[0].id,
            }
        )
        add_category_approver(self.asset_category, self.env.user, required=True)
        request = self.env["approval.request"].create(
            {
                "name": "Booked Asset Log Request",
                "category_id": self.asset_category.id,
                "request_owner_id": self.user.id,
                "company_id": self.company.id,
                "asset_id": vehicle.asset_id.id,
                "odometer": 4200,
                "date": fields.Date.today(),
            },
        )
        request.action_confirm()
        request.approver_ids[0].with_context(skip_wizard=True).action_approve()
        self.assertEqual(request.state, "approved")

        action = request.action_create_asset_log()

        log = self.env["resource.log"].browse(action["res_id"])
        self.assertEqual(log.asset_id, vehicle.asset_id)
        self.assertEqual(log.trace_id, vehicle)
        self.assertEqual(log.odometer, 4200)
        self.assertEqual(log.state, "done")
        self.assertEqual(
            log.approval_request_id,
            request,
            "the log must say which approval booked it",
        )

    def test_action_view_asset_log_missing_vehicle(self):
        request = self.env["approval.request"].create(
            {
                "name": "View Asset Log Request",
                "category_id": self.asset_category.id,
                "request_owner_id": self.user.id,
                "company_id": self.company.id,
            },
        )

        with self.assertRaises(UserError):
            request.action_view_asset_log()


class TestApprovalRequestValidation(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")

        cls.stock_category = cls.env["approval.category"].create(
            {
                "name": "Stock Picking Creation",
                "approval_type": "stock",
                "target_model": "stock.picking",
                "has_product": "no",
                "company_id": cls.company.id,
            },
        )

        cls.user = cls.env.ref("base.user_admin")

    def test_check_stock_type_no_product_lines_enabled(self):
        request = self.env["approval.request"].create(
            {
                "name": "Stock Request No Product",
                "category_id": self.stock_category.id,
                "request_owner_id": self.user.id,
                "company_id": self.company.id,
            },
        )

        with self.assertRaises(UserError):
            request._check_stock_type_has_product_lines()


@tagged("post_install", "-at_install")
class TestApprovalRequestLineChecks(TransactionCase):
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
        cls.location = cls.warehouse.lot_stock_id
        cls.product = create_test_product(
            cls.env,
            name="Line Check Product",
            type="consu",
            is_storable=True,
        )
        cls.category = cls.env["approval.category"].create(
            {
                "name": "Line Check Requests",
                "approval_type": "stock",
                "target_model": "stock.picking",
                "has_product": "required",
                "company_id": cls.company.id,
            },
        )

    def _line(self, **values):
        request = self.env["approval.request"].create(
            {
                "name": "Line Check Request",
                "category_id": self.category.id,
                "request_owner_id": self.env.user.id,
                "company_id": self.company.id,
                "line_ids": [
                    Command.create({"product_id": self.product.id, **values}),
                ],
            },
        )
        return request.line_ids

    def test_the_missing_location_error_names_the_line(self):
        line = self._line(picking_type_id=self.picking_type.id)

        with self.assertRaises(UserError) as caught:
            line._check_locations()

        self.assertIn(str(line.id), str(caught.exception))
        self.assertIn(self.product.display_name, str(caught.exception))

    def test_the_missing_operation_type_error_names_the_line(self):
        line = self._line(
            location_id=self.location.id,
            location_dest_id=self.location.id,
        )

        with self.assertRaises(UserError) as caught:
            line._check_picking_type()

        self.assertIn(str(line.id), str(caught.exception))
        self.assertIn(self.product.display_name, str(caught.exception))

    def test_the_count_sees_a_transfer_linked_through_the_mixin(self):
        request = self.env["approval.request"].create(
            {
                "name": "Mixin Link Request",
                "category_id": self.category.id,
                "request_owner_id": self.env.user.id,
                "company_id": self.company.id,
            },
        )
        self.assertEqual(request.count_stock_picking, 0)

        self.env["stock.picking"].create(
            {
                "picking_type_id": self.picking_type.id,
                "location_id": self.location.id,
                "location_dest_id": self.location.id,
                "company_id": self.company.id,
                "approval_request_id": request.id,
            },
        )

        self.assertEqual(
            request.count_stock_picking,
            len(request._get_all_pickings()),
            "the count unions the lines with a reverse search on the mixin "
            "back-link, so it has to depend on both",
        )
