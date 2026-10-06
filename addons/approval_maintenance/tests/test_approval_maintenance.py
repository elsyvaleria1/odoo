from markupsafe import Markup

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.approval.tests.common import add_category_approver


@tagged("post_install", "-at_install")
class TestApprovalMaintenanceSetup(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.company.id)], limit=1
        )

        cls.location_src = cls.env["stock.location"].create(
            {"name": "Storage Test", "usage": "internal"}
        )
        cls.location_dest = cls.env["stock.location"].create(
            {"name": "Workshop Test", "usage": "internal", "maintenance_location": True}
        )
        cls.picking_type = cls.env["stock.picking.type"].create(
            {"name": "Test Internal", "code": "internal", "sequence_code": "TINT"}
        )

        cls.product = cls.env["product.product"].create(
            {
                "name": "Test Equipment",
                "is_storable": True,
                "tracking": "serial",
                "maintenance_ok": True,
                "asset_kind_id": cls.env.ref("resource_asset.kind_equipment").id,
            }
        )
        cls.equipment = cls.env["product.trace"].create(
            {"name": "EQUIP-TEST-001", "product_id": cls.product.id}
        )
        cls.vendor = cls.env["res.partner"].create({"name": "Maintenance Vendor Test"})

        cls.category_preventive = cls.env["approval.category"].create(
            {
                "name": "Mantenimiento Preventivo Test",
                "approval_type": "maintenance_preventive",
                "company_id": cls.company.id,
            }
        )
        cls.category_corrective = cls.env["approval.category"].create(
            {
                "name": "Mantenimiento Correctivo Test",
                "approval_type": "maintenance_corrective",
                "company_id": cls.company.id,
            }
        )

        cls.approver_user = cls.env["res.users"].create(
            {
                "name": "Maintenance Approver",
                "login": "approval_maintenance_approver",
                "email": "maintenance.approver@test.com",
                "group_ids": [
                    (4, cls.env.ref("approval.group_approval_approver").id),
                ],
            },
        )
        add_category_approver(
            cls.category_preventive, cls.approver_user, required=False, sequence=10
        )

    def _prepare_approval(self, state, order=None):
        vals = {"category_id": self.category_preventive.id}
        if order:
            vals.update(res_model=order._name, res_id=order.id)
        request = self.env["approval.request"].create(vals)
        if state == "new":
            return request
        request.action_confirm()
        if state == "pending":
            return request
        if state == "approved":
            request.with_user(self.approver_user).action_approve()
        elif state == "refused":
            request.with_user(self.approver_user).with_context(
                skip_wizard=True,
            ).action_refuse()
        self.assertEqual(request.state, state)
        return request

    def _create_order(
        self,
        maintenance_type="preventive",
        name="Routine check",
        lot=None,
        vendor=False,
    ):
        lot = self.equipment if lot is None else lot
        return self.env["maintenance.order"].create(
            {
                "name": name,
                "maintenance_type": maintenance_type,
                "resource_ids": lot.asset_id.resource_id.ids,
                "vendor_id": vendor and vendor.id,
            }
        )


@tagged("post_install", "-at_install")
class TestApprovalCategoryRouting(TestApprovalMaintenanceSetup):
    def test_preventive_order_uses_preventive_category_domain(self):
        order = self._create_order(maintenance_type="preventive")
        domain = order._get_domain_approval_category()
        self.assertIn(("approval_type", "=", "maintenance_preventive"), domain)

    def test_corrective_order_uses_corrective_category_domain(self):
        order = self._create_order(maintenance_type="corrective")
        domain = order._get_domain_approval_category()
        self.assertIn(("approval_type", "=", "maintenance_corrective"), domain)

    def test_get_approval_category_returns_correct_category(self):
        order = self._create_order(maintenance_type="preventive")
        category = order._get_approval_category()
        self.assertEqual(category.approval_type, "maintenance_preventive")

    def test_an_order_no_active_category_applies_to_confirms_directly(self):
        self.env["approval.category"].sudo().search(
            [("approval_type", "=", "maintenance_preventive")],
        ).write({"active": False})
        order = self._create_order(maintenance_type="preventive")
        self.assertFalse(order.approval_required)
        order.action_confirm()
        self.assertEqual(order.state, "confirmed")

    def test_a_maintenance_transfer_no_longer_asks_for_approval_itself(self):
        order = self._create_order()
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": self.picking_type.id,
                "location_id": self.location_src.id,
                "location_dest_id": self.location_dest.id,
                "maintenance_order_id": order.id,
            }
        )
        domain = picking._get_domain_approval_category()
        type_values = [v for f, _op, v in domain if f == "approval_type"]
        self.assertFalse(any("maintenance" in str(v) for v in type_values))


@tagged("post_install", "-at_install")
class TestApprovalRequestName(TestApprovalMaintenanceSetup):
    def test_preventive_request_name_contains_equipment(self):
        order = self._create_order(maintenance_type="preventive")
        name = order._get_approval_request_name()
        self.assertIn("Preventivo", name)
        self.assertIn(self.equipment.name, name)

    def test_corrective_request_name_contains_type_label(self):
        order = self._create_order(maintenance_type="corrective")
        self.assertIn("Correctivo", order._get_approval_request_name())

    def test_request_name_without_lot_uses_na(self):
        order = self.env["maintenance.order"].create({"name": "No asset"})
        self.assertIn("N/A", order._get_approval_request_name())


@tagged("post_install", "-at_install")
class TestMaintenanceApprovalReasonHtml(TestApprovalMaintenanceSetup):
    def test_reason_html_is_markup(self):
        order = self._create_order()
        self.assertIsInstance(order._get_maintenance_approval_reason_html(), Markup)

    def test_reason_html_contains_equipment_name(self):
        html = self._create_order()._get_maintenance_approval_reason_html()
        self.assertIn(self.equipment.name, html)

    def test_reason_html_contains_vendor_when_set(self):
        order = self._create_order(vendor=self.vendor)
        html = order._get_maintenance_approval_reason_html()
        self.assertIn(self.vendor.name, html)

    def test_reason_html_omits_vendor_section_when_not_set(self):
        html = self._create_order()._get_maintenance_approval_reason_html()
        self.assertNotIn("Proveedor", html)

    def test_reason_html_contains_subject_when_set(self):
        order = self._create_order(name="Cambio de aceite")
        html = order._get_maintenance_approval_reason_html()
        self.assertIn("Cambio de aceite", html)


@tagged("post_install", "-at_install")
class TestConfirmEnforcement(TestApprovalMaintenanceSetup):
    def test_confirming_without_approval_opens_a_new_approval_request(self):
        order = self._create_order()
        result = order.action_confirm()
        self.assertEqual(result.get("res_model"), "approval.request")
        self.assertEqual(order.state, "draft")
        self.assertEqual(order.approval_state, "new")

    def test_confirming_raises_while_the_approval_is_pending(self):
        order = self._create_order()
        order.write(
            {"approval_request_id": self._prepare_approval("pending", order).id}
        )
        with self.assertRaises(UserError):
            order.action_confirm()
        self.assertEqual(order.state, "draft")

    def test_confirming_raises_when_the_approval_was_refused(self):
        order = self._create_order()
        order.write(
            {"approval_request_id": self._prepare_approval("refused", order).id}
        )
        with self.assertRaises(UserError):
            order.action_confirm()

    def test_granting_the_approval_confirms_the_order(self):
        order = self._create_order()
        request = self._prepare_approval("pending", order)
        order.write({"approval_request_id": request.id})
        request.with_user(self.approver_user).action_approve()
        self.assertEqual(order.state, "confirmed")


@tagged("post_install", "-at_install")
class TestApprovalMaintenancePlan(TestApprovalMaintenanceSetup):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        (
            cls.env.ref("approval_maintenance.approval_category_maintenance_preventive")
            | cls.env.ref(
                "approval_maintenance.approval_category_maintenance_corrective"
            )
        ).active = False

    def _create_plan(self):
        return self.env["maintenance.plan"].create(
            {
                "name": "Monthly check",
                "resource_ids": self.equipment.asset_id.resource_id.ids,
                "repeat_interval": 1,
                "repeat_unit": "month",
            }
        )

    def test_a_plan_opens_its_order_as_a_draft_awaiting_approval(self):
        order = self._create_plan()._get_open_order()
        self.assertEqual(order.state, "draft")
        self.assertEqual(order.approval_state, "new")
        self.assertEqual(
            order.approval_request_id.category_id, self.category_preventive
        )

    def test_approving_a_plan_order_confirms_it(self):
        order = self._create_plan()._get_open_order()
        request = order.approval_request_id
        request.action_confirm()
        request.with_user(self.approver_user).action_approve()
        self.assertEqual(order.state, "confirmed")

    def test_a_plan_order_no_category_applies_to_is_confirmed_directly(self):
        self.env["approval.category"].sudo().search(
            [("approval_type", "=", "maintenance_preventive")],
        ).write({"active": False})
        order = self._create_plan()._get_open_order()
        self.assertEqual(order.state, "confirmed")
        self.assertFalse(order.approval_request_id)
