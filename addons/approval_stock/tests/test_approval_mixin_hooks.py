from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.approval.tests.common import pool_step


@tagged("post_install", "-at_install")
class TestApprovalMixinHooks(TransactionCase):
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

        cls.product = cls.env["product.product"].create(
            {
                "name": "Mixin Hook Probe Product",
                "type": "consu",
                "is_storable": True,
            },
        )
        cls.approver = cls.env["res.users"].create(
            {
                "name": "Mixin Hook Approver",
                "login": "mixin_hook_approver",
                "company_id": cls.company.id,
                "company_ids": [Command.set([cls.company.id])],
            },
        )
        cls.category = cls.env["approval.category"].create(
            {
                "name": "Mixin Hook Stock Category",
                "approval_type": "stock",
                "company_id": cls.company.id,
                "approval_minimum": 1,
                "picking_type_ids": [Command.set([cls.picking_type.id])],
                "step_ids": pool_step([(cls.approver.id, True, 10)], minimum=1),
            },
        )

    def _create_picking(self):
        location = self.warehouse.lot_stock_id
        return self.env["stock.picking"].create(
            {
                "picking_type_id": self.picking_type.id,
                "location_id": location.id,
                "location_dest_id": location.id,
                "company_id": self.company.id,
                "move_ids": [
                    Command.create(
                        {
                            "description_picking": self.product.name,
                            "product_id": self.product.id,
                            "product_uom_qty": 1.0,
                            "product_uom_id": self.product.uom_id.id,
                            "location_id": location.id,
                            "location_dest_id": location.id,
                        },
                    ),
                ],
            },
        )

    def _approval_messages(self, picking):
        messages = self.env["mail.message"].search(
            [("model", "=", "stock.picking"), ("res_id", "=", picking.id)],
        )
        markers = (
            "Approval granted",
            "Approval refused",
            "Stock Transfer Approved",
            "Stock Transfer Rejected",
        )
        return [m for m in messages if any(k in (m.body or "") for k in markers)]

    def test_approved_posts_exactly_one_message(self):
        picking = self._create_picking()
        picking.action_create_approval_request()
        request = picking.approval_request_id
        self.assertTrue(request, "the mixin should have created and linked a request")

        request.with_user(self.approver).action_approve()
        self.env.flush_all()
        picking.invalidate_recordset()

        bodies = self._approval_messages(picking)
        self.assertEqual(
            len(bodies),
            1,
            "expected exactly one approval message, got:\n"
            + "\n".join(m.body or "" for m in bodies),
        )
        self.assertIn(
            "Stock Transfer Approved",
            bodies[0].body,
            "the satellite's rich message should be the one kept",
        )
        self.assertNotIn(
            "Approval granted",
            bodies[0].body,
            "the base's generic note must be replaced, not appended",
        )

    def test_mixin_sets_source_document_backlink(self):
        picking = self._create_picking()
        picking.action_create_approval_request()
        request = picking.approval_request_id

        self.assertEqual(request.res_model, "stock.picking")
        self.assertEqual(request.res_id, picking.id)
        self.assertTrue(
            request.res_name,
            "res_name is computed from the back-link and must resolve",
        )

    def test_request_name_uses_category_sequence(self):
        picking = self._create_picking()
        picking.action_create_approval_request()

        name = picking.approval_request_id.name
        self.assertTrue(name, "the request should have been numbered on confirm")
        self.assertNotIn(
            picking.name,
            name,
            "the document label must not leak into the sequence-assigned name",
        )

    def test_criteria_less_category_is_fail_closed(self):
        catch_all = self.env["approval.category"].create(
            {
                "name": "Mixin Hook Criteria-less Category",
                "approval_type": "stock",
                "company_id": self.company.id,
            },
        )
        picking = self._create_picking()
        self.assertFalse(
            catch_all._is_applicable_for(picking),
            "a category with no picking criteria must not match every transfer",
        )

    def test_is_applicable_for_ignores_foreign_documents(self):
        request = self.env["approval.request"].create(
            {"category_id": self.category.id},
        )
        self.assertTrue(
            self.category._is_applicable_for(request),
            "the base predicate is permissive; stock must fall through to it",
        )

    def test_failed_auto_validate_does_not_kill_the_approval(self):
        self.company.stock_auto_validate_on_approval = True
        self.addCleanup(
            lambda: self.company.write({"stock_auto_validate_on_approval": False}),
        )

        picking = self._create_picking()
        picking.action_create_approval_request()
        request = picking.approval_request_id

        picking_model = type(self.env["stock.picking"])
        original = picking_model.button_validate

        def failing_validate(records, *args, **kwargs):
            records.write({"origin": "auto-validate probe"})
            raise UserError("simulated validation failure")

        picking_model.button_validate = failing_validate
        self.addCleanup(setattr, picking_model, "button_validate", original)

        request.with_user(self.approver).action_approve()
        self.env.flush_all()
        request.invalidate_recordset()
        picking.invalidate_recordset()

        self.assertEqual(
            request.state,
            "approved",
            "the approval must survive a failed auto-validate",
        )
        warnings = (
            self.env["mail.message"]
            .search(
                [("model", "=", "stock.picking"), ("res_id", "=", picking.id)],
            )
            .filtered(lambda m: "Could not auto-validate" in (m.body or ""))
        )
        self.assertTrue(
            warnings,
            "the failure should be reported on the transfer, not swallowed",
        )
        self.assertIn(
            "simulated validation failure",
            warnings[0].body,
            "the helper must substitute %(error)s, not post the literal "
            "placeholder — the note is translated before it is formatted",
        )
        self.assertNotEqual(
            picking.origin,
            "auto-validate probe",
            "the savepoint must roll back the partial write button_validate made",
        )
