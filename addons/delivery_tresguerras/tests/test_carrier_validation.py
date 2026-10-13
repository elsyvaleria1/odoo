import base64
import io
from datetime import timedelta
from unittest.mock import patch

from PIL import Image

from odoo import Command, fields
from odoo.tests.common import TransactionCase, tagged
from odoo.tools import SQL

from .test_tresguerras_tracking import (
    AT_OCURRE,
    DELIVERED_HOME,
    IN_TRANSIT,
    FakeResponse,
)
from odoo.addons.delivery_tracking.models.stock_picking_validation import (
    VALIDATION_ACTIVITY,
)


@tagged("post_install", "-at_install")
class TestCarrierValidation(TransactionCase):
    """Exercise real stock validation from carrier tracking snapshots."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.out_type = cls.env.ref("stock.picking_type_out")
        cls.location = cls.out_type.default_location_src_id
        cls.customer = cls.env.ref("stock.stock_location_customers")
        cls.partner = cls.env["res.partner"].create({"name": "Tracking customer"})
        cls.product = cls.env["product.product"].create(
            {"name": "Tracked shipment product", "is_storable": True}
        )
        cls.env["stock.quant"]._update_available_quantity(
            cls.product, cls.location, 1000
        )
        cls.carrier = cls.env["delivery.carrier"].create(
            {
                "name": "Tracked carrier",
                "product_id": cls.env["product.product"]
                .create({"name": "Tracking freight", "type": "service"})
                .id,
                "tracking_provider": "tresguerras",
                "tracking_notify_user_id": cls.env.user.id,
            }
        )
        cls.out_type.auto_validation_carrier_ids = cls.carrier
        if "dispatch_mode" in cls.carrier._fields:
            cls.carrier.dispatch_mode = "third_party"
        if "delivery_proof_required" in cls.out_type._fields:
            cls.out_type.delivery_proof_required = False

    def _picking(
        self, reference="TOL01583026", *, ready=True, picking_type=None, product=None
    ):
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": (picking_type or self.out_type).id,
                "partner_id": self.partner.id,
                "location_id": self.location.id,
                "location_dest_id": self.customer.id,
                "carrier_id": self.carrier.id,
                "carrier_tracking_ref": reference,
                "move_ids": [
                    Command.create(
                        {
                            "product_id": (product or self.product).id,
                            "product_uom_qty": 5,
                            "location_id": self.location.id,
                            "location_dest_id": self.customer.id,
                        }
                    )
                ],
            }
        )
        if ready:
            picking.action_confirm()
            picking.action_assign()
            self.assertEqual(picking.state, "assigned")
        return picking

    def _answering(self, *responses):
        return patch.object(
            type(self.env["ir.egress"]),
            "request",
            side_effect=[
                response
                if isinstance(response, FakeResponse)
                else FakeResponse(response)
                for response in responses
            ],
        )

    def _delivered_snapshot(self, picking):
        for transfer in picking:
            transfer.write(
                {
                    "carrier_tracking_state": "delivered",
                    "carrier_status_code": "07",
                    "carrier_tracking_details": {
                        reference: {"state": "delivered"}
                        for reference in transfer._get_carrier_tracking_references()
                    },
                },
            )

    def test_delivered_closes_stock_once(self):
        """Confirmed delivery completes the real moves without duplicate posting."""
        picking = self._picking()
        with self._answering(DELIVERED_HOME, DELIVERED_HOME):
            picking.action_fetch_carrier_tracking()
            self.assertEqual(picking.state, "done")
            self.assertEqual(picking.move_ids.quantity, 5)
            self.assertEqual(picking.move_ids.state, "done")
            self.assertEqual(
                picking.carrier_tracking_details["TOL01583026"]["state"], "delivered"
            )
            self.assertFalse(picking.carrier_tracking_error)
            self.assertFalse(picking.activity_ids)
            messages, date_done = len(picking.message_ids), picking.date_done
            picking.action_fetch_carrier_tracking()
        self.env["stock.picking"]._cron_fetch_carrier_tracking()
        self.assertEqual(len(picking.message_ids), messages)
        self.assertEqual(picking.date_done, date_done)
        self.assertFalse(picking.backorder_ids)

    def test_ocurre_and_transit_remain_open(self):
        """A branch notification and transit are not delivery confirmations."""
        for status, state in [
            (AT_OCURRE, "at_destination"),
            (IN_TRANSIT, "in_transit"),
        ]:
            with self.subTest(state=state):
                picking = self._picking()
                with self._answering(status):
                    picking.action_fetch_carrier_tracking()
                self.assertEqual(picking.state, "assigned")
                self.assertEqual(picking.carrier_tracking_state, state)
                self.assertFalse(picking.activity_ids)

    def test_shared_number_closes_each_transfer_with_one_request(self):
        """One carrier response can validate three independent transfers."""
        pickings = self._picking() | self._picking() | self._picking()
        with self._answering(DELIVERED_HOME) as request:
            pickings.action_fetch_carrier_tracking()
        self.assertEqual(request.call_count, 1)
        self.assertEqual(set(pickings.mapped("state")), {"done"})

    def test_eleven_outs_close_ten_and_keep_ocurre_open(self):
        """The CDG scenario completes ten OUTs with nine distinct guide reads."""
        references = [
            "TOL01583036",
            "TOL01583041",
            "TOL01583031",
            "TOL01583040",
            "TOL01583030",
            "TOL01583030",
            "TOL01583030",
            "TOL01583026",
            "TOL01584640",
            "TOL01584639",
            "TOL01584642",
        ]
        pickings = self.env["stock.picking"]
        for reference in references:
            pickings |= self._picking(reference)

        def carrier_response(method, url, **kwargs):
            status = (
                AT_OCURRE
                if kwargs["params"]["rastreo"] == "TOL01584640"
                else DELIVERED_HOME
            )
            return FakeResponse(status)

        with patch.object(
            type(self.env["ir.egress"]), "request", side_effect=carrier_response
        ) as request:
            self.env["stock.picking"]._cron_fetch_carrier_tracking()
        self.assertEqual(request.call_count, 9)
        self.assertEqual(
            len(pickings.filtered(lambda picking: picking.state == "done")), 10
        )
        pending = pickings.filtered(lambda picking: picking.state != "done")
        self.assertEqual(pending.carrier_tracking_ref, "TOL01584640")
        self.assertEqual(pending.carrier_status_text, "CLIENTE DE OCURRE AVISADO")
        self.assertEqual(pending.state, "assigned")

    def test_all_numbers_must_be_delivered(self):
        """A missing or pending second number blocks completion."""
        picking = self._picking("TOL01583026, TOL01583030")
        with self._answering(DELIVERED_HOME, FakeResponse({}, 500)):
            picking.action_fetch_carrier_tracking()
        self.assertEqual(picking.state, "assigned")
        with self._answering(DELIVERED_HOME, AT_OCURRE):
            picking.action_fetch_carrier_tracking()
        self.assertEqual(picking.state, "assigned")
        with self._answering(DELIVERED_HOME, DELIVERED_HOME):
            picking.action_fetch_carrier_tracking()
        self.assertEqual(picking.state, "done")

    def test_disabled_or_different_carrier_remains_manual(self):
        """Opt-in applies to the selected carrier on the selected operation type."""
        for carriers in [self.env["delivery.carrier"], self.carrier.copy()]:
            with self.subTest(carrier_ids=carriers.ids):
                self.out_type.auto_validation_carrier_ids = carriers
                picking = self._picking()
                with self._answering(DELIVERED_HOME):
                    picking.action_fetch_carrier_tracking()
                self.assertEqual(picking.state, "assigned")
                self.assertEqual(len(picking.activity_ids), 1)
                self.assertFalse(picking.carrier_validation_error)

    def test_other_operation_type_is_not_enabled(self):
        """A different outgoing type retains its own configuration."""
        other_type = self.out_type.copy(
            {"auto_validation_carrier_ids": [Command.clear()]}
        )
        picking = self._picking(picking_type=other_type)
        with self._answering(DELIVERED_HOME):
            picking.action_fetch_carrier_tracking()
        self.assertEqual(picking.state, "assigned")

    def test_non_outgoing_is_not_validated(self):
        """Incoming and internal transfers are excluded even if configured."""
        for code in ["incoming", "internal"]:
            with self.subTest(code=code):
                self.out_type.code = code
                picking = self._picking()
                self._delivered_snapshot(picking)
                picking._complete_carrier_deliveries()
                self.assertEqual(picking.state, "assigned")

    def test_draft_and_cancelled_are_not_validated(self):
        """Delivery status does not confirm drafts or resurrect cancellations."""
        draft = self._picking(ready=False)
        cancelled = self._picking()
        cancelled.action_cancel()
        self._delivered_snapshot(draft | cancelled)
        (draft | cancelled)._complete_carrier_deliveries()
        self.assertEqual(draft.state, "draft")
        self.assertEqual(cancelled.state, "cancel")

    def test_old_delivered_backlog_and_incomplete_snapshot(self):
        """The cron recovers old deliveries and reads incomplete snapshots."""
        complete = self._picking()
        incomplete = self._picking("TOL01583030")
        self._delivered_snapshot(complete | incomplete)
        incomplete.carrier_tracking_details = False
        self.env.flush_all()
        self.env.cr.execute(
            SQL(
                "UPDATE stock_picking SET create_date = %s WHERE id IN %s",
                fields.Datetime.now() - timedelta(days=60),
                tuple((complete | incomplete).ids),
            )
        )
        (complete | incomplete).invalidate_recordset(["create_date"])
        with self._answering(DELIVERED_HOME) as request:
            self.env["stock.picking"]._cron_fetch_carrier_tracking()
        self.assertEqual(request.call_count, 1)
        self.assertEqual(complete.state, "done")
        self.assertEqual(incomplete.state, "done")

    def test_failed_refresh_prevents_cached_delivery_then_cron_retries(self):
        """An HTTP failure preserves delivery without validating stale data."""
        picking = self._picking()
        self._delivered_snapshot(picking)
        with self._answering(FakeResponse({}, 500)):
            picking.action_fetch_carrier_tracking()
        self.assertEqual(picking.state, "assigned")
        self.assertEqual(picking.carrier_tracking_state, "delivered")
        self.assertIn("HTTP 500", picking.carrier_tracking_error)
        with self._answering(DELIVERED_HOME):
            self.env["stock.picking"]._cron_fetch_carrier_tracking()
        self.assertEqual(picking.state, "done")
        self.assertFalse(picking.carrier_tracking_error)

    def test_quantities_are_not_repaired_or_partially_validated(self):
        """Zero, short and excess quantities block every backorder policy."""
        for policy in ["ask", "always", "never"]:
            for quantity in [0, 3, 7]:
                with self.subTest(policy=policy, quantity=quantity):
                    self.out_type.create_backorder = policy
                    picking = self._picking()
                    picking.move_ids.quantity = quantity
                    # Zero reservations can demote the picking; both cases stay open.
                    self._delivered_snapshot(picking)
                    picking._complete_carrier_deliveries()
                    self.assertNotEqual(picking.state, "done")
                    self.assertEqual(picking.move_ids.quantity, quantity)
                    self.assertFalse(picking.move_ids.picked)
                    self.assertFalse(picking.backorder_ids)

    def test_picked_subset_is_not_silently_backordered(self):
        """Mixed picked and unpicked moves cannot create a partial delivery."""
        picking = self._picking()
        other_move = picking.move_ids.copy({"picking_id": picking.id})
        other_move._action_confirm(merge=False)
        other_move._action_assign()
        picking.move_ids[0].picked = True
        self._delivered_snapshot(picking)
        picking._complete_carrier_deliveries()
        self.assertEqual(picking.state, "assigned")
        self.assertTrue(picking.carrier_validation_error)
        self.assertFalse(picking.backorder_ids)

    def test_picked_subset_within_a_move_is_not_partially_validated(self):
        """Full reserved quantity does not excuse an incomplete picked subset."""
        picking = self._picking()
        line = picking.move_line_ids
        line.quantity = 2
        line.copy({"quantity": 3, "picked": False})
        line.picked = True
        self.assertTrue(picking.move_ids.picked)
        self.assertEqual(picking.move_ids.quantity, 5)
        self._delivered_snapshot(picking)
        picking._complete_carrier_deliveries()
        self.assertEqual(picking.state, "assigned")
        self.assertTrue(picking.carrier_validation_error)
        self.assertEqual(picking.move_ids.quantity, 5)
        self.assertFalse(picking.backorder_ids)

    def test_wizard_rolls_back_picked_lines_and_retry_clears_only_own_activity(self):
        """A wizard rolls back stock changes and creates only one retry activity."""
        picking = self._picking()
        unrelated = picking.activity_schedule(
            "mail.mail_activity_data_todo", summary="Other work"
        )
        self._delivered_snapshot(picking)

        def wizard(records, **kwargs):
            records.move_ids.picked = True
            return {
                "type": "ir.actions.act_window",
                "res_model": "stock.backorder.confirmation",
            }

        with patch.object(type(picking), "button_validate", wizard):
            picking._complete_carrier_deliveries()
            picking._complete_carrier_deliveries()
        self.assertEqual(picking.state, "assigned")
        self.assertFalse(picking.move_ids.picked)
        self.assertTrue(picking.carrier_validation_error)
        self.assertEqual(len(picking.activity_search([VALIDATION_ACTIVITY])), 1)
        self.assertEqual(picking.carrier_tracking_state, "delivered")
        self.env["stock.picking"]._cron_fetch_carrier_tracking()
        self.assertEqual(picking.state, "done")
        self.assertFalse(picking.carrier_validation_error)
        self.assertFalse(picking.activity_search([VALIDATION_ACTIVITY]))
        self.assertTrue(unrelated.exists())

    def test_manual_completion_or_cancellation_resolves_only_own_failure(self):
        """Manual resolution also clears the automatic failure and activity."""
        for operation in ["button_validate", "action_cancel"]:
            with self.subTest(operation=operation):
                picking = self._picking()
                picking.move_ids.quantity = 7
                self._delivered_snapshot(picking)
                picking._complete_carrier_deliveries()
                self.assertTrue(picking.carrier_validation_error)
                unrelated = picking.activity_schedule(
                    "mail.mail_activity_data_todo", summary="Other work"
                )
                picking.move_ids.quantity = 5
                getattr(picking, operation)()
                self.assertFalse(picking.carrier_validation_error)
                self.assertFalse(picking.activity_search([VALIDATION_ACTIVITY]))
                self.assertTrue(unrelated.exists())

    def test_missing_lot_keeps_delivery_and_does_not_block_another_out(self):
        """Normal lot checks survive automatic validation and isolate failures."""
        lot_product = self.product.copy({"tracking": "lot"})
        self.env["stock.quant"]._update_available_quantity(
            lot_product, self.location, 10
        )
        missing_lot = self._picking(product=lot_product)
        good = self._picking("TOL01583030")
        with self._answering(DELIVERED_HOME, DELIVERED_HOME):
            (missing_lot | good).action_fetch_carrier_tracking()
        self.assertNotEqual(missing_lot.state, "done")
        self.assertTrue(missing_lot.carrier_validation_error)
        self.assertEqual(missing_lot.carrier_tracking_state, "delivered")
        self.assertEqual(good.state, "done")

    def test_missing_photo_keeps_delivery_and_retries(self):
        """The installed fleet proof requirement remains mandatory."""
        if "delivery_proof_required" not in self.out_type._fields:
            self.skipTest("Install stock_fleet_delivery to exercise the photo gate")
        self.out_type.delivery_proof_required = True
        picking = self._picking()
        with self._answering(DELIVERED_HOME):
            picking.action_fetch_carrier_tracking()
        self.assertEqual(picking.state, "assigned")
        self.assertIn("photo", picking.carrier_validation_error)
        self.assertEqual(picking.carrier_tracking_state, "delivered")
        self.assertFalse(picking.move_ids.picked)
        self.assertEqual(len(picking.activity_search([VALIDATION_ACTIVITY])), 1)

        photo = io.BytesIO()
        Image.new("RGB", (40, 30), "white").save(photo, format="PNG")
        picking.delivery_proof = base64.b64encode(photo.getvalue())
        self.env["stock.picking"]._cron_fetch_carrier_tracking()
        self.assertEqual(picking.state, "done")
        self.assertFalse(picking.carrier_validation_error)
        self.assertFalse(picking.activity_search([VALIDATION_ACTIVITY]))

    def test_changed_guide_or_carrier_clears_old_failure_and_snapshot(self):
        """A replacement shipment cannot inherit delivery or its old activity."""
        for change in [
            {"carrier_tracking_ref": "TOL01584640"},
            {"carrier_id": self.carrier.copy().id},
        ]:
            with self.subTest(change=change):
                picking = self._picking()
                picking.move_ids.quantity = 7
                self._delivered_snapshot(picking)
                picking._complete_carrier_deliveries()
                self.assertTrue(picking.carrier_validation_error)
                picking.write(change)
                self.assertFalse(picking.carrier_validation_error)
                self.assertFalse(picking.carrier_tracking_details)
                self.assertFalse(picking.carrier_tracking_state)
                self.assertFalse(picking.activity_search([VALIDATION_ACTIVITY]))

    def test_locked_transfer_waits_for_a_later_run(self):
        """A transfer locked by another transaction is left for the next run."""
        picking = self._picking()
        self._delivered_snapshot(picking)
        with patch.object(
            type(picking), "try_lock_for_update", return_value=self.env["stock.picking"]
        ):
            picking._complete_carrier_deliveries()
        self.assertEqual(picking.state, "assigned")
        picking._complete_carrier_deliveries()
        self.assertEqual(picking.state, "done")

    def test_print_action_after_completion_is_success(self):
        """A report returned after real stock completion is not a blocking wizard."""
        picking = self._picking()
        self._delivered_snapshot(picking)
        original = type(picking).button_validate

        def validate_and_print(records, **kwargs):
            original(records, **kwargs)
            return {"type": "ir.actions.report"}

        with patch.object(type(picking), "button_validate", validate_and_print):
            picking._complete_carrier_deliveries()
        self.assertEqual(picking.state, "done")
        self.assertFalse(picking.carrier_validation_error)
