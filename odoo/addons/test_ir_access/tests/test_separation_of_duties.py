from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError
from odoo.fields import Command
from odoo.tests import TransactionCase, new_test_user, tagged
from odoo.tools import mute_logger


@tagged("post_install", "-at_install")
class TestSeparationOfDuties(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Groups = cls.env["res.groups"]
        cls.payers = Groups.create({"name": "SoD Payers"})
        cls.approvers = Groups.create({"name": "SoD Approvers"})
        Function = cls.env["ir.access.sod.function"]
        cls.pay = Function.create(
            {"name": "pay suppliers", "group_ids": [Command.link(cls.payers.id)]}
        )
        cls.approve = Function.create(
            {
                "name": "approve payments",
                "group_ids": [Command.link(cls.approvers.id)],
                "verb_ids": [
                    Command.create(
                        {
                            "model_id": cls.env["ir.model"]._get_id(
                                "test_ir_access.document"
                            ),
                            "verb": "post",
                        }
                    )
                ],
            }
        )
        cls.rule = cls.env["ir.access.sod.rule"].create(
            {
                "name": "pay and approve",
                "function_a_id": cls.pay.id,
                "function_b_id": cls.approve.id,
                "action": "block",
            }
        )
        cls.clerk = new_test_user(cls.env, login="sod_clerk", groups="base.group_user")
        cls.Grant = cls.env["res.users.grant"]

    def _grant(self, group):
        return self.Grant._grant(self.clerk, group, cause="manual")

    def _logged(self, event):
        return self.env["ir.access.log"].search(
            [
                ("event", "=", event),
                ("subject_user_id", "=", self.clerk.id),
                ("cause_model", "=", "ir.access.sod.rule"),
            ]
        )

    def test_a_grant_that_joins_two_duties_is_refused(self):
        self._grant(self.payers)
        with (
            mute_logger("odoo.addons.base.models.ir_access_sod"),
            self.assertRaises(AccessError),
        ):
            self._grant(self.approvers)

    def test_a_grant_scheduled_to_join_two_duties_is_refused(self):
        self._grant(self.payers)
        with (
            mute_logger("odoo.addons.base.models.ir_access_sod"),
            self.assertRaises(AccessError),
        ):
            self.Grant.create(
                {
                    "user_id": self.clerk.id,
                    "group_id": self.approvers.id,
                    "date_from": fields.Datetime.now() + timedelta(days=1),
                }
            )

    def test_an_implication_that_joins_two_duties_is_refused(self):
        self._grant(self.payers)
        with (
            mute_logger("odoo.addons.base.models.ir_access_sod"),
            self.assertRaises(AccessError),
        ):
            self.payers.write({"implied_ids": [Command.link(self.approvers.id)]})

    def test_a_verb_is_a_duty_as_much_as_a_group(self):
        self._grant(self.payers)
        with (
            mute_logger("odoo.addons.base.models.ir_access_sod"),
            self.assertRaises(AccessError),
        ):
            self._grant(self.env.ref("base.group_system"))

    def test_an_exception_lets_one_person_hold_both_and_counts_the_use(self):
        self._grant(self.payers)
        exception = self.env["ir.access.exception"].create(
            {
                "user_id": self.clerk.id,
                "kind": "sod",
                "res_model": self.rule._name,
                "res_id": self.rule.id,
                "reason": "two-person company",
                "date_to": fields.Datetime.now() + timedelta(days=30),
            }
        )
        self._grant(self.approvers)
        self.assertEqual(exception.use_count, 1)

    def test_a_warning_rule_logs_the_conflict_and_lets_it_through(self):
        self.rule.action = "warn"
        self._grant(self.payers)
        self.assertFalse(self._logged("sod_conflict"))
        self._grant(self.approvers)
        self.assertEqual(len(self._logged("sod_conflict")), 1)

    def test_a_holder_of_an_excluded_group_does_not_hold_the_duty(self):
        managers = self.env["res.groups"].create({"name": "SoD Pay Managers"})
        self.pay.excluded_group_ids = managers
        self._grant(self.payers | managers)
        self._grant(self.approvers)
        self.assertFalse(self.rule._get_conflicting_user_ids(self.clerk))

    def test_the_report_lists_who_holds_both(self):
        self.rule.action = "warn"
        self._grant(self.payers | self.approvers)
        action = self.env["ir.access.sod.rule"].action_view_conflicts()
        conflicts = self.env["ir.access.sod.conflict"].search(action["domain"])
        self.assertIn(
            (self.rule, self.clerk),
            [(conflict.rule_id, conflict.user_id) for conflict in conflicts],
        )

    def _conflicts(self, cause):
        return self._logged("sod_conflict").filtered(lambda log: log.cause == cause)

    def test_a_duty_widened_onto_its_holders_logs_their_conflict_once(self):
        auditors = self.env["res.groups"].create({"name": "SoD Auditors"})
        self._grant(self.payers | auditors)

        self.approve.group_ids = [Command.link(auditors.id)]
        self.assertEqual(len(self._conflicts("duty_changed")), 1)
        self.approve.excluded_group_ids = self.env["res.groups"].create(
            {"name": "SoD Nobody"}
        )
        self.assertEqual(len(self._conflicts("duty_changed")), 1)
        with (
            mute_logger("odoo.addons.base.models.ir_access_sod"),
            self.assertRaises(AccessError),
        ):
            self._grant(self.approvers)

    def test_a_rule_turned_on_over_holders_logs_them(self):
        self.rule.active = False
        self._grant(self.payers | self.approvers)
        self.assertFalse(self._logged("sod_conflict"))

        self.rule.active = True
        self.assertEqual(len(self._conflicts("rule_changed")), 1)
        self.env["ir.access.sod.rule"].create(
            {
                "name": "approve and pay",
                "function_a_id": self.approve.id,
                "function_b_id": self.pay.id,
            }
        )
        self.assertEqual(len(self._conflicts("rule_changed")), 2)

    def test_a_row_giving_a_duty_s_verb_logs_its_holders(self):
        posters = self.env["res.groups"].create(
            {
                "name": "SoD Posters",
                "implied_ids": [Command.link(self.env.ref("base.group_user").id)],
            }
        )
        self._grant(self.payers | posters)

        self.env["ir.access"].create(
            {
                "name": "SoD posters post",
                "model_id": self.env["ir.model"]._get_id("test_ir_access.document"),
                "group_id": posters.id,
                "kind": "permission",
                "verbs": "post",
            }
        )
        self.assertEqual(len(self._conflicts("access_changed")), 1)

    def test_a_conflict_under_an_exception_is_not_logged(self):
        auditors = self.env["res.groups"].create({"name": "SoD Auditors"})
        self._grant(self.payers | auditors)
        self.env["ir.access.exception"].create(
            {
                "user_id": self.clerk.id,
                "kind": "sod",
                "res_model": self.rule._name,
                "res_id": self.rule.id,
                "reason": "two-person company",
                "date_to": fields.Datetime.now() + timedelta(days=30),
            }
        )
        self.approve.group_ids = [Command.link(auditors.id)]
        self.assertFalse(self._conflicts("duty_changed"))

    def test_a_refused_change_of_a_duty_s_rows_is_refused_as_a_change(self):
        Log = type(self.env["ir.access.log"])
        calls = []
        original = Log._record_denial

        def spy(log, model_name, operation, ids, refusing):
            calls.append((model_name, operation))
            return original(log, model_name, operation, ids, refusing)

        row = self.env.ref("test_ir_access.access_document_post")
        with patch.object(Log, "_record_denial", spy), self.assertRaises(AccessError):
            row.with_user(self.clerk).write({"name": "mine now"})
        self.assertEqual(calls, [("ir.access", "write")])

    def test_a_verb_completed_by_another_group_is_a_duty_held(self):
        posters = self.env["res.groups"].create({"name": "SoD Posters, verb only"})
        self.env["ir.access"].create(
            {
                "name": "SoD posters post",
                "model_id": self.env["ir.model"]._get_id("test_ir_access.document"),
                "group_id": posters.id,
                "kind": "permission",
                "verbs": "post",
            }
        )
        self._grant(self.payers)
        with (
            mute_logger("odoo.addons.base.models.ir_access_sod"),
            self.assertRaises(AccessError),
        ):
            self._grant(posters)
