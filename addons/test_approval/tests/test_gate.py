from unittest.mock import patch

from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from odoo.addons.approval.tests.common import ApprovalCommon


@tagged("post_install", "-at_install")
class TestApprovalGate(ApprovalCommon):
    def setUp(self):
        super().setUp()
        self.category = self._make_category(
            name=f"Gate Cat {self.id()}",
            approvers=[self.approver_1],
        )

    def _document(self, name="Gated", amount=100.0, **values):
        return self.env["approval.test.gated"].create(
            {
                "name": name,
                "partner_id": self.partner.id,
                "amount_total": amount,
                "test_category_id": self.category.id,
                **values,
            }
        )

    def _approve(self, document):
        document.approval_request_id.with_user(self.approver_1).action_approve()

    def _obligation(self, verb):
        return self.env.ref(f"test_approval.obligation_gated_{verb}")

    def _enforce(self, verb):
        obligation = self._obligation(verb)
        obligation.mode = "request"
        return obligation

    def _watch(self, verb):
        obligation = self._obligation(verb)
        obligation.mode = "advise"
        return obligation

    def test_the_operation_asks_instead_of_running(self):
        document = self._document()
        document.action_ship()
        self.assertEqual(document.ship_count, 0)
        self.assertEqual(document.approval_state, "pending")
        self.assertEqual(document.approval_request_id.operation, "ship")
        with self.assertRaises(UserError):
            document.action_ship()

    def test_a_call_the_transaction_admitted_passes_the_door_without_asking(self):
        document = self._document()
        with self.env.transaction.admitting(document._name, "ship", document.ids):
            document.action_ship()
        self.assertEqual(document.ship_count, 1)
        self.assertFalse(document.approval_request_id)

        document.action_ship()
        self.assertEqual(document.ship_count, 1, "the admission ended with its block")
        self.assertEqual(document.approval_state, "pending")

    def test_held_names_what_the_checkpoint_would_refuse(self):
        Obligation = self.env["ir.access.obligation"]
        waiting, granted = self._document(), self._document(name="Granted")
        granted.action_ship()
        self._approve(granted)

        self.assertEqual(Obligation._get_held(waiting | granted, "ship"), waiting)
        with self.env.transaction.admitting(waiting._name, "ship", waiting.ids):
            self.assertFalse(Obligation._get_held(waiting, "ship"))
        self._watch("ship")
        self.assertFalse(
            Obligation._get_held(waiting, "ship"), "a watching obligation holds none"
        )

    def test_the_grant_runs_the_operation_once(self):
        document = self._document()
        document.action_ship()
        self._approve(document)
        self.assertEqual(document.ship_count, 1)
        self.assertEqual(document.state, "shipped")
        self.assertTrue(document.approval_request_id.date_operation_run)
        with self.assertRaisesRegex(UserError, "already went through"):
            document.approval_request_id.with_user(self.approver_1).action_withdraw()
        document.action_ship()
        self.assertEqual(document.ship_count, 2, "a covered call runs; nothing replays")

    def _asked_by_owner(self, **values):
        access = self.env["ir.access"].create(
            {
                "name": "approval.test.gated requester",
                "model_id": self.env["ir.model"]._get("approval.test.gated").id,
                "group_id": self.env.ref("base.group_user").id,
                "kind": "permission",
                "operation": "ru",
            }
        )
        document = self._document(**values)
        document.with_user(self.owner_user).action_ship()
        self.assertEqual(document.approval_request_id.request_owner_id, self.owner_user)
        return document, access

    def test_the_grant_runs_the_operation_as_its_requester(self):
        document, _access = self._asked_by_owner()
        Gated = self.registry["approval.test.gated"]
        ship = Gated._ship
        ran_as = []

        def spy(records, shipped):
            ran_as.append((shipped.env.uid, shipped.env.su))
            return ship(records, shipped)

        with patch.object(Gated, "_ship", spy):
            self._approve(document)
        self.assertEqual(ran_as, [(self.owner_user.id, False)])
        self.assertEqual(document.ship_count, 1)

    def test_a_requester_who_lost_the_right_is_not_run_as_superuser(self):
        document, access = self._asked_by_owner()
        access.unlink()
        self._approve(document)
        self.assertEqual(document.approval_state, "approved")
        self.assertEqual(document.ship_count, 0, "nobody may ship it any more")
        self.assertTrue(
            any(
                "could not go through" in body
                for body in document.message_ids.mapped("body")
            )
        )

    def test_a_grant_that_does_not_run_leaves_the_operation_to_its_caller(self):
        document = self._document(runs_on_approval=False)
        document.action_ship()
        self._approve(document)
        self.assertEqual(document.ship_count, 0)
        document.action_ship()
        self.assertEqual(document.ship_count, 1)

    def test_a_grant_clears_the_operation_it_was_asked_for_and_no_other(self):
        document = self._document(runs_on_approval=False)
        document.action_ship()
        self._approve(document)
        with self.assertRaises(UserError):
            document.action_bill()
        self.assertEqual(document.bill_count, 0)

    def test_a_document_changed_after_its_grant_asks_again(self):
        document, _access = self._asked_by_owner(runs_on_approval=False)
        request = document.approval_request_id
        self._approve(document)
        document.sudo().amount_total = 400.0
        document.with_user(self.owner_user).action_ship()
        self.assertEqual(document.ship_count, 0)
        self.assertEqual(document.approval_request_id, request, "its own request")
        self.assertEqual(request.state, "pending")
        self.assertEqual(request.amount, 400.0, "submitted for what is there now")
        self._approve(document)
        document.with_user(self.owner_user).action_ship()
        self.assertEqual(document.ship_count, 1)

    def test_a_grant_running_on_what_it_does_not_cover_is_left_as_decided(self):
        document = self._document()
        document.action_ship()
        request = document.approval_request_id
        document.sudo().amount_total = 400.0
        self._approve(document)
        self.assertEqual(request.state, "approved", "not undone in its own cascade")
        self.assertEqual(document.ship_count, 0)
        self.assertTrue(
            any(
                "could not go through" in body
                for body in document.message_ids.mapped("body")
            )
        )
        document.action_ship()
        self.assertEqual(request.state, "pending")
        self.assertEqual(request.amount, 400.0)

    def test_a_path_that_cannot_ask_refuses_a_grant_the_document_outgrew(self):
        document = self._document(runs_on_approval=False)
        document.action_ship()
        self._approve(document)
        document.sudo().amount_total = 400.0
        with self.assertRaises(UserError):
            document.action_ship_from_elsewhere()
        self.assertEqual(document.ship_count, 0)
        self.assertEqual(document.approval_state, "approved")

    def test_a_request_reset_to_draft_asks_again_from_the_operation(self):
        document, _access = self._asked_by_owner(runs_on_approval=False)
        request = document.approval_request_id
        self._approve(document)
        request._force_draft()
        document.with_user(self.owner_user).action_ship()
        self.assertEqual(request.state, "pending")
        self.assertEqual(document.ship_count, 0)

    def test_a_new_cycle_of_a_spent_grant_runs_again(self):
        document = self._document()
        document.action_ship()
        self._approve(document)
        request = document.approval_request_id
        self.assertTrue(request.date_operation_run)
        request._force_draft()
        self.assertFalse(request.date_operation_run)
        request.action_confirm()
        self._approve(document)
        self.assertEqual(document.ship_count, 2)

    def test_what_needs_no_approval_goes_through_beside_what_does(self):
        gated = self._document("Gated one")
        plain = self._document("Plain one", test_category_id=False)
        (gated | plain).action_ship()
        self.assertEqual(plain.ship_count, 1)
        self.assertEqual(gated.ship_count, 0)
        self.assertEqual(gated.approval_state, "pending")

    def test_every_path_is_watched_while_the_obligation_watches(self):
        obligation = self._watch("ship")
        document = self._document()
        document.action_ship()
        self.assertEqual(document.ship_count, 1, "a watching obligation asks nothing")
        self.assertFalse(document.approval_request_id)
        document.action_ship_from_elsewhere()
        self.assertEqual(document.ship_count, 2)
        self.assertRecordValues(
            obligation.observation_ids.sorted("id"),
            [
                {
                    "model_name": "approval.test.gated",
                    "operation": "ship",
                    "res_id": document.id,
                    "would_block": True,
                }
            ]
            * 2,
        )

    def test_another_path_is_refused(self):
        document = self._document()
        document.action_ship()
        with self.assertRaises(UserError):
            document.action_ship_from_elsewhere()
        self.assertEqual(document.ship_count, 0)

    def test_a_forged_admission_in_the_context_admits_nothing(self):
        self._enforce("ship")
        document = self._document()
        forged = document.with_context(
            approval_binding_admitted=[["approval.test.gated", "ship", [document.id]]]
        )
        with self.assertRaises(UserError):
            forged.action_ship_from_elsewhere()
        self.assertEqual(document.ship_count, 0)
        self.assertFalse(document.approval_request_id)

    def test_the_gate_admits_what_it_let_through(self):
        self._enforce("ship")
        document = self._document(test_category_id=False)
        document.action_ship()
        self.assertEqual(document.ship_count, 1)

    def test_every_verb_ships_its_obligation_and_it_enforces(self):
        obligations = self.env["approval.binding"].search(
            [("model_name", "=", "approval.test.gated")]
        )
        self.assertEqual(set(obligations.mapped("verb")), {"ship", "bill"})
        self.assertEqual(set(obligations.mapped("origin")), {"module"})
        self.assertEqual(
            set(obligations.mapped("mode")),
            {"request"},
            "an obligation enforces from its creation: a door the code declares is "
            "closed before anyone has to remember to close it",
        )

    def test_enforcing_one_verb_leaves_the_other_watching(self):
        ship = self._enforce("ship")
        bill = self._watch("bill")
        self.assertTrue(ship._enforces())
        self.assertFalse(
            bill._enforces(),
            "an obligation is switched per verb, so a cheap one need not wait for an "
            "expensive one",
        )
        document = self._document()
        document.action_ship()
        with self.assertRaises(UserError):
            document.action_ship_from_elsewhere()

    def test_the_count_beside_an_obligation_is_its_own(self):
        ship = self._watch("ship")
        document = self._document()
        document.action_ship_from_elsewhere()
        self.assertEqual(ship.observation_count, 1)

        self.env["approval.observation"].sudo().create(
            {
                "model_name": "approval.test.gated",
                "operation": "elsewhere",
                "res_id": document.id,
                "elevation": "none",
                "would_block": True,
            }
        )
        ship.invalidate_recordset(["observation_count"])
        self.assertEqual(
            ship.observation_count,
            1,
            "an obligation counts what reached its own verb, not its neighbour's",
        )

    def test_the_document_obligation_takes_no_condition_of_its_own(self):
        with self.assertRaises(ValidationError):
            self._obligation("ship").subject_domain = "[('amount_total', '>', 0)]"

    def test_a_method_that_is_a_verb_door_is_bound_through_its_verb(self):
        with self.assertRaises(ValidationError):
            self.env["approval.binding"].create(
                {
                    "model_id": self.env["ir.model"]._get_id("approval.test.gated"),
                    "method": "action_ship",
                    "mode": "block",
                    "category_id": self.category.id,
                }
            )
