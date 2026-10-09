from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user

from odoo.addons.approval.tests.common import pool_step
from odoo.addons.approval_product.tests.common import create_test_product


class TestStockPickingApproval(TransactionCase):
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
                "name": "Test Destination",
                "usage": "internal",
                "company_id": cls.company.id,
            },
        )

        cls.product = create_test_product(
            cls.env,
            name="Test Stock Product",
            type="consu",
            is_storable=True,
        )

        cls.stock_category = cls.env["approval.category"].create(
            {
                "name": "Stock Transfer Approval (picking tests)",
                "approval_type": "stock",
                "company_id": cls.company.id,
            },
        )

    def _create_picking(self, **kwargs):
        vals = {
            "picking_type_id": self.picking_type.id,
            "location_id": self.location_src.id,
            "location_dest_id": self.location_dest.id,
            "company_id": self.company.id,
        }
        vals.update(kwargs)
        return self.env["stock.picking"].create(vals)

    def test_create_picking_basic(self):
        picking = self._create_picking()

        self.assertEqual(picking.picking_type_id, self.picking_type)
        self.assertEqual(picking.location_id, self.location_src)
        self.assertEqual(picking.location_dest_id, self.location_dest)

    def test_get_approval_required_fields(self):
        picking = self._create_picking()
        required_fields = picking._get_fields_approval_required()

        self.assertIn("picking_type_id", required_fields)
        self.assertIn("location_id", required_fields)
        self.assertIn("location_dest_id", required_fields)
        self.assertIn("move_ids", required_fields)

    def test_get_domain_approval_category(self):
        picking = self._create_picking()
        domain = picking._get_domain_approval_category()

        self.assertIn(("approval_type", "=", "stock"), domain)
        self.assertIn(("target_model", "=", False), domain)

    def test_get_approval_reason_html(self):
        picking = self._create_picking()
        picking.move_ids = [
            Command.create(
                {
                    "product_id": self.product.id,
                    "product_uom_qty": 5.0,
                    "product_uom_id": self.product.uom_id.id,
                    "location_id": self.location_src.id,
                    "location_dest_id": self.location_dest.id,
                },
            ),
        ]

        reason = picking._get_approval_reason_html()

        self.assertIn("Stock Transfer", reason)
        self.assertIn(self.picking_type.name, reason)
        self.assertIn(self.product.name, reason)

    def test_prepare_approval_request_values(self):
        picking = self._create_picking()
        picking.origin = "TEST-001"

        vals = picking._prepare_approval_request_values(self.stock_category)

        self.assertNotIn("name", vals)
        self.assertEqual(vals["reference"], "TEST-001")


class TestStockPickingApprovalRequired(TransactionCase):
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
                "name": "Normal Dest",
                "usage": "internal",
                "company_id": cls.company.id,
            },
        )

        cls.restricted_location = cls.env["stock.location"].create(
            {
                "name": "Restricted Location",
                "usage": "internal",
                "stock_approval_required": True,
                "company_id": cls.company.id,
            },
        )

        cls.restricted_categ = cls.env["product.category"].create(
            {
                "name": "Controlled Substances",
                "stock_approval_required": True,
            },
        )
        cls.restricted_product = create_test_product(
            cls.env,
            name="Controlled Product",
            type="consu",
            is_storable=True,
            categ_id=cls.restricted_categ.id,
        )

        cls.catch_all = cls.env["approval.category"].create(
            {
                "name": "Flagged Transfer Catch-all",
                "approval_type": "stock",
                "company_id": cls.company.id,
                "approval_minimum": 1,
                "step_ids": pool_step(
                    [(cls.env.ref("base.user_admin").id, False, 10)], minimum=1
                ),
            },
        )

    def _create_picking(self, **kwargs):
        vals = {
            "picking_type_id": self.picking_type.id,
            "location_id": self.location_src.id,
            "location_dest_id": self.location_dest.id,
            "company_id": self.company.id,
        }
        vals.update(kwargs)
        return self.env["stock.picking"].create(vals)

    def test_a_flag_with_no_usable_catch_all_does_not_brick_the_transfer(self):
        self.catch_all.step_ids.unlink()
        picking = self._create_picking(location_id=self.restricted_location.id)

        picking.invalidate_recordset()

        self.assertFalse(
            self.catch_all.step_ids,
            "the premise: a category with no step to ask anyone",
        )
        self.assertFalse(
            picking.approval_required,
            "a category that cannot approve anything is not a fallback; the "
            "trigger alone must not raise approval_required, or the transfer "
            "can neither be validated nor sent for approval",
        )

    def test_an_unstaffed_catch_all_gives_way_to_a_staffed_one(self):
        unstaffed = self.env["approval.category"].create(
            {
                "name": "Nobody Asked",
                "approval_type": "stock",
                "company_id": self.company.id,
                "sequence": self.catch_all.sequence - 1,
                "step_ids": pool_step(minimum=1),
            },
        )
        picking = self._create_picking(location_id=self.restricted_location.id)

        self.assertFalse(unstaffed._can_be_met_for(picking))
        self.assertEqual(
            picking._get_approval_category(),
            self.catch_all,
            "a catch-all whose step no one can staff could never approve the "
            "transfer, so the next one serves it",
        )

    def test_a_step_that_does_not_apply_does_not_disqualify_the_catch_all(self):
        elsewhere = self.env["res.company"].create({"name": "Elsewhere"})
        stranger = new_test_user(
            self.env,
            login="stock_catch_all_stranger",
            company_id=elsewhere.id,
            company_ids=[Command.set(elsewhere.ids)],
        )
        self.env["approval.category.step"].create(
            {
                "category_id": self.catch_all.id,
                "name": "Only for other operations",
                "sequence": 20,
                "minimum": 1,
                "member_ids": [Command.create({"user_id": stranger.id})],
                "subject_model_id": self.env["ir.model"]._get_id("stock.picking"),
                "subject_domain": repr([("picking_type_id", "=", 0)]),
            }
        )
        picking = self._create_picking(location_id=self.restricted_location.id)

        self.assertTrue(self.catch_all._can_be_met_for(picking))
        self.assertEqual(picking._get_approval_category(), self.catch_all)

    def test_a_flag_with_no_category_at_all_does_not_brick_the_transfer(self):
        self.env["approval.category"].search(
            [("approval_type", "=", "stock"), ("target_model", "=", False)],
        ).write({"active": False})
        picking = self._create_picking(
            location_id=self.restricted_location.id,
            move_ids=[
                Command.create(
                    {
                        "product_id": self.restricted_product.id,
                        "product_uom_qty": 1.0,
                        "location_id": self.restricted_location.id,
                        "location_dest_id": self.location_dest.id,
                    },
                ),
            ],
        )

        picking.invalidate_recordset()

        self.assertFalse(picking.approval_required)
        picking.button_validate()

        self.assertEqual(
            picking.state,
            "done",
            "with nothing able to approve it, the transfer has to keep moving",
        )

    def test_approval_required_source_location_flagged(self):
        picking = self._create_picking(location_id=self.restricted_location.id)

        picking._compute_approval_required()

        self.assertTrue(picking.approval_required)

    def test_approval_required_dest_location_flagged(self):
        picking = self._create_picking(location_dest_id=self.restricted_location.id)

        picking._compute_approval_required()

        self.assertTrue(picking.approval_required)

    def test_approval_required_product_category_flagged(self):
        picking = self._create_picking()
        picking.move_ids = [
            Command.create(
                {
                    "product_id": self.restricted_product.id,
                    "product_uom_qty": 1.0,
                    "product_uom_id": self.restricted_product.uom_id.id,
                    "location_id": self.location_src.id,
                    "location_dest_id": self.location_dest.id,
                },
            ),
        ]

        picking._compute_approval_required()

        self.assertTrue(picking.approval_required)


class TestStockPickingApprovalWorkflow(TransactionCase):
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
                "name": "Workflow Dest",
                "usage": "internal",
                "company_id": cls.company.id,
            },
        )

        cls.stock_category = cls.env["approval.category"].create(
            {
                "name": "Stock Approval",
                "approval_type": "stock",
                "company_id": cls.company.id,
            },
        )

        cls.user = cls.env.ref("base.user_admin")
        cls.product = create_test_product(
            cls.env,
            name="Workflow Test Product",
            type="consu",
            is_storable=True,
        )

        cls.creation_category = cls.env["approval.category"].create(
            {
                "name": "Stock Creation",
                "allow_self_approval": True,
                "approval_type": "stock",
                "target_model": "stock.picking",
                "has_product": "required",
                "company_id": cls.company.id,
                "step_ids": pool_step([(cls.user.id, False, 10)], minimum=1),
            },
        )

    def test_picking_linked_to_creation_approval_not_required(self):
        request = self.env["approval.request"].create(
            {
                "name": "Stock Creation Request",
                "category_id": self.creation_category.id,
                "request_owner_id": self.user.id,
                "company_id": self.company.id,
                "line_ids": [Command.create({"product_id": self.product.id})],
            },
        )
        request.action_confirm()
        approver = request.approver_ids.filtered(lambda a: a.user_id == self.user)
        request.action_approve(approver)

        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": self.picking_type.id,
                "location_id": self.location_src.id,
                "location_dest_id": self.location_dest.id,
            },
        )
        request._link_produced_documents(picking)

        picking._compute_approval_required()

        self.assertFalse(picking.approval_required)


@tagged("post_install", "-at_install")
class TestStockPickingBatchValidate(TransactionCase):
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
        cls.picking_type.create_backorder = "ask"

        cls.location_flagged = cls.env["stock.location"].create(
            {
                "name": "Batch Flagged Source",
                "usage": "internal",
                "location_id": cls.warehouse.view_location_id.id,
                "company_id": cls.company.id,
                "stock_approval_required": True,
            },
        )
        cls.location_plain = cls.env["stock.location"].create(
            {
                "name": "Batch Plain Source",
                "usage": "internal",
                "location_id": cls.warehouse.view_location_id.id,
                "company_id": cls.company.id,
            },
        )
        cls.location_dest = cls.env["stock.location"].create(
            {
                "name": "Batch Dest",
                "usage": "internal",
                "location_id": cls.warehouse.view_location_id.id,
                "company_id": cls.company.id,
            },
        )
        cls.product = create_test_product(
            cls.env,
            name="Batch Validate Product",
            type="consu",
            is_storable=True,
        )
        cls.category = cls.env["approval.category"].create(
            {
                "name": "Batch Stock Approval",
                "approval_type": "stock",
                "company_id": cls.company.id,
                "stock_approval_mode": "location",
                "location_ids": [Command.link(cls.location_flagged.id)],
                "step_ids": pool_step(
                    [(cls.env.ref("base.user_admin").id, False, 10)], minimum=1
                ),
            },
        )

    def _picking(self, source):
        return self.env["stock.picking"].create(
            {
                "picking_type_id": self.picking_type.id,
                "location_id": source.id,
                "location_dest_id": self.location_dest.id,
                "company_id": self.company.id,
                "move_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": 10.0,
                            "location_id": source.id,
                            "location_dest_id": self.location_dest.id,
                        },
                    ),
                ],
            },
        )

    def test_batch_does_not_claim_a_transfer_the_wizard_stopped(self):
        needs_approval = self._picking(self.location_flagged)
        partial = self._picking(self.location_plain)
        partial.action_confirm()
        partial.move_ids.quantity = 4.0
        partial.move_ids.picked = True

        result = (needs_approval | partial).button_validate()

        self.assertEqual(result["tag"], "display_notification")
        self.assertNotEqual(
            partial.state,
            "done",
            "the backorder wizard stops this transfer; the batch must not "
            "report it as validated",
        )
        self.assertIn(
            "0 validated",
            result["params"]["message"],
            "the count has to come from what reached done, not from the size "
            "of the ready subset",
        )
        self.assertEqual(
            result["params"]["next"]["res_model"],
            "wizard.stock.picking.validate.partial",
            "the action the ready subset returned must reach the client, or "
            "those transfers silently never validate",
        )

    def test_batch_reports_what_it_really_validated(self):
        needs_approval = self._picking(self.location_flagged)
        full = self._picking(self.location_plain)
        full.action_confirm()
        full.move_ids.quantity = 10.0
        full.move_ids.picked = True

        result = (needs_approval | full).button_validate()

        self.assertEqual(full.state, "done")
        self.assertIn("1 validated", result["params"]["message"])
        self.assertNotIn("next", result["params"])


@tagged("post_install", "-at_install")
class TestStockPickingPendingWriteGuard(TransactionCase):
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
                "name": "Guard Flagged Source",
                "usage": "internal",
                "location_id": cls.warehouse.view_location_id.id,
                "company_id": cls.company.id,
                "stock_approval_required": True,
            },
        )
        cls.location_dest = cls.env["stock.location"].create(
            {
                "name": "Guard Dest",
                "usage": "internal",
                "location_id": cls.warehouse.view_location_id.id,
                "company_id": cls.company.id,
            },
        )
        cls.product = create_test_product(
            cls.env,
            name="Guard Product",
            type="consu",
            is_storable=True,
        )
        cls.category = cls.env["approval.category"].create(
            {
                "name": "Guard Stock Approval",
                "approval_type": "stock",
                "company_id": cls.company.id,
                "stock_approval_mode": "location",
                "location_ids": [Command.link(cls.location_src.id)],
                "step_ids": pool_step(
                    [(cls.env.ref("base.user_admin").id, False, 10)], minimum=1
                ),
            },
        )
        cls.requester = new_test_user(
            cls.env,
            login="approval_stock_requester",
            groups="base.group_user,stock.group_stock_user",
        )

    def _pending_picking(self):
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
                            "product_uom_qty": 10.0,
                            "location_id": self.location_src.id,
                            "location_dest_id": self.location_dest.id,
                        },
                    ),
                ],
            },
        )
        picking.action_create_approval_request()
        self.assertEqual(picking.approval_state, "pending")
        return picking.with_user(self.requester)

    def test_the_hook_names_what_the_approvers_are_deciding_on(self):
        protected = self.env["stock.picking"]._get_fields_approval_protected()

        self.assertEqual(
            set(protected),
            {
                "move_ids",
                "location_id",
                "location_dest_id",
                "picking_type_id",
                "partner_id",
            },
        )

    def test_quantities_are_frozen_while_approval_is_pending(self):
        picking = self._pending_picking()

        with self.assertRaises(UserError):
            picking.write(
                {
                    "move_ids": [
                        Command.update(
                            picking.move_ids.id,
                            {"product_uom_qty": 500.0},
                        ),
                    ],
                },
            )

    def test_the_destination_is_frozen_while_approval_is_pending(self):
        picking = self._pending_picking()

        with self.assertRaises(UserError):
            picking.write({"location_dest_id": self.location_src.id})

    def test_an_unprotected_field_still_writes(self):
        picking = self._pending_picking()

        picking.write({"origin": "still editable"})

        self.assertEqual(picking.origin, "still editable")


@tagged("post_install", "-at_install")
class TestStockApprovalWithdrawGuard(TransactionCase):
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
                "name": "Withdraw Guard Dest",
                "usage": "internal",
                "company_id": cls.company.id,
            },
        )
        cls.env["approval.category"].search(
            [("approval_type", "=", "stock"), ("active", "=", True)],
        ).write({"active": False})
        cls.category = cls.env["approval.category"].create(
            {
                "name": "Stock Withdraw Guard",
                "company_id": cls.company.id,
                "approval_type": "stock",
                "approval_minimum": 1,
                "allow_self_approval": True,
                "target_model": "stock.picking",
                "has_product": "required",
                "step_ids": pool_step([(cls.env.user.id, True, 10)], minimum=1),
            }
        )
        cls.product = create_test_product(
            cls.env,
            name="Withdraw Guard Product",
            type="consu",
            is_storable=True,
        )

    def _approved_request(self):
        request = self.env["approval.request"].create(
            {
                "name": "Stock Withdraw Test",
                "category_id": self.category.id,
                "company_id": self.company.id,
                "request_owner_id": self.env.user.id,
                "line_ids": [
                    Command.create({"product_id": self.product.id, "quantity": 1.0})
                ],
            }
        )
        request.action_confirm()
        request.approver_ids[0].with_context(skip_wizard=True).action_approve()
        self.assertEqual(request.state, "approved")
        return request

    def _link_picking(self, request):
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": self.picking_type.id,
                "location_id": self.location_src.id,
                "location_dest_id": self.location_dest.id,
                "company_id": self.company.id,
            }
        )
        request._link_produced_documents(picking)
        return picking

    def test_withdraw_allowed_without_descendant(self):
        request = self._approved_request()
        request._check_withdraw_allowed()

    def test_withdraw_blocked_with_active_picking(self):
        request = self._approved_request()
        self._link_picking(request)
        with self.assertRaises(UserError):
            request._check_withdraw_allowed()

    def test_withdraw_unblocks_when_picking_cancelled(self):
        request = self._approved_request()
        picking = self._link_picking(request)
        picking.action_cancel()
        self.assertEqual(picking.state, "cancel")
        request._check_withdraw_allowed()

    def test_withdraw_stays_blocked_once_the_goods_have_moved(self):
        request = self._approved_request()
        picking = self._link_picking(request)
        picking.move_ids = [
            Command.create(
                {
                    "product_id": self.product.id,
                    "product_uom_qty": 1.0,
                    "location_id": self.location_src.id,
                    "location_dest_id": self.location_dest.id,
                },
            ),
        ]
        picking.action_confirm()
        picking.move_ids.quantity = 1.0
        picking.move_ids.picked = True
        picking.button_validate(skip_backorder=True)
        self.assertEqual(picking.state, "done")

        with self.assertRaises(UserError):
            request._check_withdraw_allowed()


@tagged("post_install", "-at_install")
class TestStockApprovalCoversPerProduct(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")
        cls.company.stock_auto_validate_on_approval = False
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.company.id)],
            limit=1,
        )
        cls.location_src = cls.warehouse.lot_stock_id
        cls.location_dest = cls.env["stock.location"].create(
            {
                "name": "Covers Flagged Dest",
                "usage": "internal",
                "location_id": cls.location_src.location_id.id,
                "stock_approval_required": True,
            },
        )
        cls.location_dest_sub = cls.env["stock.location"].create(
            {
                "name": "Covers Dest Sub",
                "usage": "internal",
                "location_id": cls.location_dest.id,
            },
        )
        cls.user = cls.env.ref("base.user_admin")
        cls.category = cls.env["approval.category"].create(
            {
                "name": "Covers Catch All",
                "approval_type": "stock",
                "stock_approval_mode": "combined",
                "has_partner": "no",
                "allow_self_approval": True,
                "company_id": cls.company.id,
                "step_ids": pool_step([(cls.user.id, False, 10)], minimum=1),
            },
        )
        cls.product = create_test_product(
            cls.env,
            name="Covers Product",
            type="consu",
            is_storable=True,
        )
        cls.env["stock.quant"]._update_available_quantity(
            cls.product,
            cls.location_src,
            100,
        )

    def _approved_two_move_picking(self):
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": self.warehouse.int_type_id.id,
                "location_id": self.location_src.id,
                "location_dest_id": self.location_dest.id,
                "move_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": 5,
                            "location_id": self.location_src.id,
                            "location_dest_id": self.location_dest.id,
                        },
                    ),
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": 10,
                            "location_id": self.location_src.id,
                            "location_dest_id": self.location_dest_sub.id,
                        },
                    ),
                ],
            },
        )
        picking.action_confirm()
        picking.button_validate()
        request = picking.approval_request_id
        request.with_user(self.user).action_approve()
        self.assertEqual(request.state, "approved")
        self.assertEqual(len(picking.move_ids), 2, "the moves must not merge")
        return picking

    def test_a_product_split_over_two_moves_cannot_exceed_its_grant(self):
        picking = self._approved_two_move_picking()

        for move in picking.move_ids:
            move.quantity = 10
            move.picked = True

        with self.assertRaises(UserError, msg="20 picked against 15 approved"):
            picking.button_validate()

    def test_a_move_counted_in_another_unit_is_not_what_was_approved(self):
        picking = self._approved_two_move_picking()
        move = picking.move_ids[0]

        move.product_uom_id = self.env.ref("uom.product_uom_dozen")

        with self.assertRaises(UserError, msg="5 dozen against 5 units approved"):
            picking.button_validate()
        self.assertNotEqual(picking.state, "done")

    def test_the_grant_still_covers_the_approved_total(self):
        picking = self._approved_two_move_picking()

        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True

        picking.button_validate()

        self.assertEqual(picking.state, "done")
