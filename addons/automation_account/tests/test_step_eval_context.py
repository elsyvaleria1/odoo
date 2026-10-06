from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestStepEvalContext(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.model_line = cls.env.ref("automation.model_automation_runtime_line")
        cls.partner = cls.env["res.partner"].create({"name": "Step Eval Partner"})
        cls.automation = cls.env["automation.rule"].create(
            {
                "name": "TEST - Step Eval Context",
                "model_id": cls.model_line.id,
                "trigger": "on_hand",
            },
        )

    def _make_step(self, code, name="Step", predecessors=None):
        step = self.env["ir.actions.server"].create(
            {
                "name": name,
                "automation_rule_id": self.automation.id,
                "model_id": self.model_line.id,
                "state": "code",
                "code": code,
            },
        )
        for predecessor in predecessors or self.env["ir.actions.server"]:
            self.env["workflow.edge"].create(
                {"source_node_id": predecessor.id, "target_node_id": step.id},
            )
        return step

    def _make_runtime(self):
        runtime = self.env["automation.runtime"].create(
            {
                "automation_id": self.automation.id,
                "name": "TEST - Step Eval Run",
                "partner_id": self.partner.id,
            },
        )
        runtime.action_start()
        return runtime

    def test_step_body_reaches_the_helper_as_action(self):
        self._make_step("action.mark_action_done_and_continue(record)")

        runtime = self._make_runtime()
        line = runtime.line_ids
        self.assertEqual(len(line), 1)

        line.action_execute()

        self.assertEqual(line.state, "done")
        self.assertFalse(line.error_message)
        self.assertEqual(runtime.state, "done")

    def test_step_body_reaches_the_helper_as_server_action(self):
        self._make_step("server_action.mark_action_done_and_continue(record)")

        runtime = self._make_runtime()
        line = runtime.line_ids

        line.action_execute()

        self.assertEqual(line.state, "done")
        self.assertFalse(line.error_message)

    def test_action_is_not_bound_outside_the_runtime_path(self):
        partner_action = self.env["ir.actions.server"].create(
            {
                "name": "TEST - Plain code action",
                "model_id": self.env.ref("base.model_res_partner").id,
                "state": "code",
                "code": "record.write({'comment': 'step eval probe'})",
            },
        )

        result = partner_action.with_context(
            active_model="res.partner",
            active_id=self.partner.id,
            active_ids=self.partner.ids,
        ).run()

        self.assertFalse(result)
        self.assertEqual(self.partner.comment, "<p>step eval probe</p>")

    def test_the_override_does_not_touch_unrelated_actions(self):
        partner_action = self.env["ir.actions.server"].create(
            {
                "name": "TEST - Foreign model action",
                "model_id": self.env.ref("base.model_res_users").id,
                "state": "code",
                "code": "raise UserError('record=%s' % bool(record))",
            },
        )

        with self.assertRaises(UserError) as caught:
            partner_action.with_context(
                active_model="res.partner",
                active_id=self.partner.id,
                active_ids=self.partner.ids,
            ).run()

        self.assertEqual(caught.exception.args[0], "record=False")
