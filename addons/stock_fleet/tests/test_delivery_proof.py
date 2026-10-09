import base64
import io
from ast import literal_eval
from datetime import timedelta

from PIL import Image

from odoo import Command, fields
from odoo.exceptions import AccessError, RedirectWarning
from odoo.tests import TransactionCase, tagged


def _photo(color="white"):
    buffer = io.BytesIO()
    Image.new("RGB", (40, 30), color).save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue())


@tagged("post_install", "-at_install")
class TestDeliveryProof(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock_location = cls.warehouse.lot_stock_id
        cls.customer_location = cls.env.ref("stock.stock_location_customers")
        cls.out_type = cls.warehouse.out_type_id
        cls.out_type.delivery_proof_required = True

        def user(login, *groups):
            return cls.env["res.users"].create(
                {
                    "name": login,
                    "login": login,
                    "group_ids": [Command.set([cls.env.ref(g).id for g in groups])],
                }
            )

        cls.clerk = user("proof_clerk", "stock.group_stock_user")
        cls.office = user("proof_office", "stock.group_stock_manager")
        cls.reviewer = user(
            "proof_reviewer", "stock_fleet.group_delivery_proof_reviewer"
        )
        cls.driver_user = user("proof_driver", "stock_fleet.group_trip_driver")
        cls.driver = cls.env["hr.employee"].create(
            {"name": "Driver", "user_id": cls.driver_user.id}
        )
        cls.model = cls.env["product.product"].create(
            {
                "name": "Test Van",
                "type": "consu",
                "asset_kind_id": cls.env.ref("base.kind_vehicle").id,
            }
        )
        cls.vehicle = cls.env["resource.resource"].create(
            {
                "name": "Van",
                "kind_id": cls.env.ref("base.kind_vehicle").id,
                "product_id": cls.model.id,
            }
        )
        cls.product = cls.env["product.product"].create(
            {"name": "Freight", "is_storable": True}
        )
        cls.env["stock.quant"]._update_available_quantity(
            cls.product, cls.stock_location, 1000
        )

    def _picking(self):
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": self.out_type.id,
                "partner_id": self.env["res.partner"].create({"name": "Customer"}).id,
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "move_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": 1,
                            "location_id": self.stock_location.id,
                            "location_dest_id": self.customer_location.id,
                        }
                    )
                ],
            }
        )
        picking.action_confirm()
        picking.action_assign()
        picking.move_ids.picked = True
        return picking

    def _delivered(self, uploader=None):
        picking = self._picking()
        picking.with_user(uploader or self.clerk).delivery_proof = _photo()
        picking.button_validate()
        self.assertEqual(picking.state, "done")
        return picking

    def _confirm_photo(self, action, user):
        context = {
            key.removeprefix("default_"): value
            for key, value in action["context"].items()
        }
        wizard = (
            self.env[action["res_model"]]
            .with_user(user)
            .create({**context, "delivery_proof": _photo()})
        )
        return wizard.action_confirm()

    def test_a_type_that_does_not_require_it_validates_without_the_photo(self):
        self.out_type.delivery_proof_required = False
        picking = self._picking()
        picking.button_validate()
        self.assertEqual(picking.state, "done")

    def test_the_office_does_not_validate_without_the_photo_either(self):
        picking = self._picking()
        with self.assertRaisesRegex(RedirectWarning, picking.name) as refusal:
            picking.with_user(self.office).button_validate()
        action = refusal.exception.args[1]
        self.assertEqual(action["res_model"], "wizard.stock.picking.delivery.proof")
        self.assertEqual(
            action["views"],
            [(False, "form")],
            "The client reads the views of an action a RedirectWarning carries.",
        )
        self.assertFalse(action["context"]["default_resume"])
        self.assertEqual(picking.state, "assigned")

    def test_the_dialog_keeps_the_photo_and_validate_is_repeated(self):
        picking = self._picking()
        with self.assertRaises(RedirectWarning) as refusal:
            picking.with_user(self.office).button_validate()
        self._confirm_photo(refusal.exception.args[1], self.office)
        self.assertEqual(picking.state, "assigned")
        self.assertTrue(picking.delivery_proof)
        self.assertTrue(picking.delivery_proof_ok)
        self.assertEqual(picking.delivery_proof_uid, self.office)
        self.assertTrue(picking.delivery_proof_date)
        picking.with_user(self.office).button_validate()
        self.assertEqual(picking.state, "done")

    def test_a_batch_names_every_transfer_missing_its_photo(self):
        first, second = self._picking(), self._picking()
        batch = self.env["stock.picking.batch"].create(
            {"picking_ids": [Command.set((first | second).ids)]}
        )
        batch.action_confirm()
        with self.assertRaises(RedirectWarning) as refusal:
            batch.action_done()
        message, action = refusal.exception.args[:2]
        self.assertIn(first.name, message)
        self.assertIn(second.name, message)
        self.assertFalse(action["context"]["default_resume"])
        self.assertEqual((first | second).mapped("state"), ["assigned", "assigned"])

    def test_delivered_asks_for_the_photo_and_delivers(self):
        picking = self._picking()
        trip = self.env["stock.picking.batch"].create(
            {
                "picking_type_id": self.out_type.id,
                "picking_ids": [Command.set(picking.ids)],
                "vehicle_id": self.vehicle.id,
                "operator_id": self.driver.id,
                "supervisor_id": self.office.id,
                "odometer_departure": 1000.0,
            }
        )
        trip.action_depart()
        with self.assertRaises(RedirectWarning) as refusal:
            picking.with_user(self.driver_user).action_deliver()
        action = refusal.exception.args[1]
        self.assertEqual(action["context"]["default_resume"], "deliver")
        self._confirm_photo(action, self.driver_user)
        self.assertEqual(picking.state, "done")
        self.assertEqual(picking.delivery_proof_uid, self.driver_user)

    def test_only_a_reviewer_rejects_the_photo(self):
        picking = self._delivered()
        self.assertTrue(picking.delivery_proof_ok)
        with self.assertRaises(AccessError):
            picking.with_user(self.clerk).delivery_proof_ok = False
        with self.assertRaises(AccessError):
            picking.with_user(self.office).delivery_proof_ok = False
        picking.with_user(self.reviewer).delivery_proof_ok = False
        self.assertFalse(picking.delivery_proof_ok)
        activity = picking.activity_ids.filtered(
            lambda activity: activity.user_id == self.clerk
        )
        self.assertEqual(len(activity), 1, "Whoever uploaded it is asked again.")

    def test_the_uploader_does_not_vouch_for_a_rejected_photo_but_replaces_it(self):
        picking = self._delivered()
        picking.with_user(self.reviewer).delivery_proof_ok = False
        with self.assertRaises(AccessError):
            picking.with_user(self.clerk).delivery_proof_ok = True
        picking.with_user(self.clerk).delivery_proof = _photo("black")
        self.assertTrue(picking.delivery_proof_ok)

    def test_the_customer_signature_counts_as_evidence(self):
        picking = self._picking()
        picking.with_user(self.clerk).signature = _photo("black")
        self.assertTrue(picking.delivery_proof_ok)
        self.assertEqual(picking.delivery_proof_uid, self.clerk)
        self.assertTrue(picking.delivery_proof_date)

    def test_a_reviewer_rejects_a_signature(self):
        picking = self._picking()
        picking.with_user(self.clerk).signature = _photo("black")
        with self.assertRaises(AccessError):
            picking.with_user(self.clerk).delivery_proof_ok = False
        picking.with_user(self.reviewer).delivery_proof_ok = False
        self.assertFalse(picking.delivery_proof_ok)
        activity = picking.activity_ids.filtered(
            lambda activity: activity.user_id == self.clerk
        )
        self.assertEqual(len(activity), 1, "Whoever captured it is asked again.")

    def test_the_photo_keeps_who_captured_the_signature(self):
        picking = self._picking()
        picking.with_user(self.clerk).signature = _photo("black")
        picking.with_user(self.office).delivery_proof = False
        self.assertEqual(picking.delivery_proof_uid, self.clerk)
        picking.with_user(self.office).signature = False
        self.assertFalse(picking.delivery_proof_uid)
        self.assertFalse(picking.delivery_proof_ok)

    def _kept(self, picking):
        return picking.message_ids.attachment_ids.filtered(
            lambda attachment: attachment.name.startswith(f"{picking.name} - ")
        )

    def test_a_delivered_slip_is_rewritten_only_by_a_reviewer(self):
        picking = self._delivered()
        accepted = picking.delivery_proof
        for vals in (
            {"delivery_proof": _photo("black")},
            {"delivery_proof": False},
            {"signature": _photo("black")},
        ):
            with self.subTest(vals=list(vals)), self.assertRaises(AccessError):
                picking.with_user(self.clerk).write(vals)
        self.assertTrue(picking.delivery_proof_ok)
        self.assertEqual(picking.delivery_proof, accepted)
        self.assertFalse(picking.signature)

        picking.with_user(self.reviewer).delivery_proof = _photo("black")
        self.assertNotEqual(picking.delivery_proof, accepted)
        kept = self._kept(picking)
        self.assertEqual(len(kept), 1, "The replaced photo stays on the chatter.")
        self.assertEqual(kept.raw, base64.b64decode(accepted))

    def test_whoever_delivered_adds_the_photo_it_lacks(self):
        picking = self._delivered()
        picking.with_user(self.reviewer).delivery_proof = False
        self.assertFalse(picking.delivery_proof_ok)
        self.assertFalse(picking.delivery_proof_uid)
        picking.with_user(self.clerk).delivery_proof = _photo("black")
        self.assertTrue(picking.delivery_proof_ok)
        self.assertEqual(picking.delivery_proof_uid, self.clerk)

    def test_the_rejected_photo_stays_on_the_chatter(self):
        picking = self._delivered()
        rejected = picking.delivery_proof
        picking.with_user(self.reviewer).delivery_proof_ok = False
        picking.with_user(self.clerk).delivery_proof = _photo("black")
        self.assertTrue(picking.delivery_proof_ok)
        self.assertEqual(self._kept(picking).raw, base64.b64decode(rejected))

    def test_a_rejection_lifted_by_new_evidence_is_said(self):
        picking = self._delivered()
        picking.with_user(self.reviewer).delivery_proof_ok = False
        picking.with_user(self.reviewer).signature = _photo("black")
        self.assertTrue(picking.delivery_proof_ok)
        said = picking.message_ids.filtered(
            lambda message: "had rejected" in (message.body or "")
        )
        self.assertEqual(len(said), 1)

    def test_an_undelivered_transfer_takes_any_evidence(self):
        picking = self._picking()
        picking.with_user(self.clerk).delivery_proof = _photo()
        picking.with_user(self.clerk).delivery_proof = _photo("black")
        picking.with_user(self.clerk).signature = _photo("black")
        picking.with_user(self.clerk).delivery_proof = False
        self.assertTrue(picking.delivery_proof_ok)
        self.assertFalse(self._kept(picking))

    def test_only_a_reviewer_receives_the_paper(self):
        picking = self._delivered()
        with self.assertRaises(AccessError):
            picking.with_user(self.clerk).action_receive_delivery_paper()
        picking.with_user(self.reviewer).action_receive_delivery_paper()
        self.assertTrue(picking.delivery_paper_received)
        self.assertEqual(picking.delivery_paper_received_uid, self.reviewer)
        self.assertTrue(picking.delivery_paper_received_date)
        with self.assertRaises(AccessError):
            picking.with_user(self.clerk).delivery_paper_received = False
        picking.with_user(self.reviewer).delivery_paper_received = False
        self.assertFalse(picking.delivery_paper_received_uid)
        self.assertFalse(picking.delivery_paper_received_date)

    def test_a_transfer_not_yet_delivered_is_not_received_on_paper(self):
        picking = self._picking()
        picking.with_user(self.reviewer).action_receive_delivery_paper()
        self.assertFalse(picking.delivery_paper_received)

    def test_switching_the_requirement_on_dates_it(self):
        picking_type = self.env["stock.picking.type"].create(
            {
                "name": "Deliveries on proof",
                "code": "outgoing",
                "sequence_code": "PROOF",
                "warehouse_id": self.warehouse.id,
            }
        )
        self.assertFalse(picking_type.delivery_proof_since)
        picking_type.delivery_proof_required = True
        started = picking_type.delivery_proof_since
        self.assertTrue(started)
        picking_type.delivery_proof_required = False
        picking_type.delivery_proof_required = True
        self.assertEqual(
            picking_type.delivery_proof_since, started, "a date already set is kept"
        )
        given = fields.Datetime.now() - timedelta(days=3)
        dated = self.env["stock.picking.type"].create(
            {
                "name": "Deliveries on proof, dated",
                "code": "outgoing",
                "sequence_code": "PROOFD",
                "warehouse_id": self.warehouse.id,
                "delivery_proof_required": True,
                "delivery_proof_since": given,
            }
        )
        self.assertEqual(dated.delivery_proof_since, given, "a given date is kept")

    def test_the_reviewers_list_starts_when_the_requirement_does(self):
        earlier = self._delivered()
        earlier.date_done = fields.Datetime.now() - timedelta(days=2)
        self.out_type.delivery_proof_since = fields.Datetime.now() - timedelta(days=1)
        since = self._delivered()
        action = self.env.ref("stock_fleet.action_picking_delivery_proof")
        listed = (
            self.env["stock.picking"]
            .with_user(self.reviewer)
            .search(literal_eval(action.domain))
        )
        self.assertIn(since, listed)
        self.assertNotIn(earlier, listed)
        self.assertTrue(since.delivery_proof_due)
        self.assertFalse(earlier.delivery_proof_due)

        self.out_type.delivery_proof_required = False
        self.assertFalse(
            self.env["stock.picking"].search([("delivery_proof_due", "=", True)]),
            "a type that no longer asks for it has no deliveries to review",
        )

    def _overdue(self):
        self.out_type.delivery_proof_since = fields.Datetime.now() - timedelta(days=60)
        self.out_type.delivery_paper_days = 3
        picking = self._delivered()
        picking.date_done = fields.Datetime.now() - timedelta(days=30)
        return picking

    def test_whoever_holds_the_paper_is_reminded_once(self):
        picking = self._overdue()
        Picking = self.env["stock.picking"]
        Picking._cron_remind_delivery_paper()
        reminder = picking.activity_ids.filtered(
            lambda activity: activity.user_id == self.clerk
        )
        self.assertEqual(len(reminder), 1, "whoever filed the slip holds the paper")
        self.assertTrue(picking.delivery_paper_reminded)
        reminder.action_feedback()
        Picking._cron_remind_delivery_paper()
        self.assertFalse(
            picking.activity_ids,
            "a reminder marked done without the paper is not sent again",
        )

    def test_the_reviewers_get_the_overdue_list_every_day(self):
        overdue = self._overdue()
        on_time = self._delivered()
        Message = self.env["mail.message"]
        for _day in range(2):
            last = Message.search([], order="id desc", limit=1).id
            self.env["stock.picking"]._cron_remind_delivery_paper()
            listed = Message.search(
                [
                    ("id", ">", last),
                    ("model", "=", "stock.picking.type"),
                    ("res_id", "=", self.out_type.id),
                    ("partner_ids", "in", self.reviewer.partner_id.ids),
                ]
            )
            self.assertEqual(len(listed), 1)
            self.assertIn(overdue.name, listed.body)
            self.assertNotIn(on_time.name, listed.body)
            self.assertNotIn(self.clerk.partner_id, listed.partner_ids)

    def test_no_list_when_nothing_is_overdue(self):
        self._delivered()
        last = self.env["mail.message"].search([], order="id desc", limit=1).id
        self.env["stock.picking"]._cron_remind_delivery_paper()
        self.assertFalse(
            self.env["mail.message"].search(
                [("id", ">", last), ("model", "=", "stock.picking.type")]
            )
        )
