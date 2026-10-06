from odoo import fields
from odoo.tests.common import tagged
from odoo.tools import mute_logger

from .common import AutomationAccountCommon


@tagged("post_install", "-at_install")
class TestWorkflowExecution(AutomationAccountCommon):
    CREATE_AND_CONTINUE = """
move = action.create_move_from_template(record, template)
record.write({'created_record_ref': 'account.move,%s' % move.id})
action.mark_action_done_and_continue(record)
"""

    def setUp(self):
        super().setUp()
        self.create_step_code = (
            "template = env['account.move.template'].search("
            "[('name', '=', %r)], limit=1)\n" % self.template_invoice.name
        ) + self.CREATE_AND_CONTINUE

    def test_workflow_creation_and_start(self):
        self._make_chain(["pass", "pass", "pass"])

        runtime = self.env["automation.runtime"].create(
            {
                "automation_id": self.automation.id,
                "partner_id": self.partner.id,
                "amount": 1500.0,
                "date": fields.Date.to_date("2026-08-27"),
                "reference": "TEST-WORKFLOW-001",
            },
        )

        self.assertEqual(runtime.state, "draft")
        self.assertFalse(runtime.line_ids)

        runtime.action_start()

        self.assertEqual(runtime.state, "in_progress")
        self.assertEqual(len(runtime.line_ids), 3)

        lines = runtime.line_ids.sorted("sequence")
        self.assertEqual(lines[0].state, "ready")
        for line in lines[1:]:
            self.assertEqual(line.state, "waiting")

    def test_sequential_workflow_execution(self):
        self._make_chain(["pass", "pass", "pass"])
        runtime = self._make_runtime(reference="TEST-SEQ-001")

        total = len(runtime.line_ids)
        for _step in range(total):
            ready = runtime.line_ids.filtered(lambda line: line.state == "ready")
            self.assertEqual(len(ready), 1)
            runtime.action_next_step()
            self.assertEqual(ready.state, "done")

        self.assertEqual(runtime.state, "done")
        self.assertEqual(runtime.progress, 100)
        self.assertEqual(set(runtime.line_ids.mapped("state")), {"done"})

    def test_a_step_body_creates_and_records_a_move(self):
        self._make_chain([self.create_step_code, "pass"])
        runtime = self._make_runtime(reference="TEST-DOCS-001")

        runtime.action_next_step()

        first = runtime.line_ids.sorted("sequence")[0]
        self.assertEqual(first.state, "done")
        self.assertFalse(first.error_message)
        self.assertEqual(first.created_record_ref._name, "account.move")
        self.assertEqual(first.created_record_ref.partner_id, self.partner)

    def test_workflow_context_propagation(self):
        st_line = self.env["account.bank.statement.line"].create(
            {
                "journal_id": self.journal_bank.id,
                "payment_ref": "TEST-CTX-001",
                "partner_id": self.partner.id,
                "amount": 500.0,
                "date": fields.Date.to_date("2026-08-21"),
            },
        )
        self._make_chain(["pass"])
        runtime = self._make_runtime(
            st_line_id=st_line.id,
            third_party_id=self.third_party.id,
        )

        context = runtime._prepare_execution_context()

        self.assertEqual(context["st_line_id"], st_line.id)
        self.assertEqual(context["third_party_id"], self.third_party.id)

    @mute_logger("odoo.addons.automation.models.automation_runtime_line")
    def test_workflow_error_handling(self):
        self._make_chain(["raise UserError('step blew up')", "pass"])
        runtime = self._make_runtime()

        first = runtime.line_ids.sorted("sequence")[0]
        result = first.action_execute()

        self.assertFalse(result)
        self.assertEqual(first.state, "error")
        self.assertIn("step blew up", first.error_message)
        self.assertEqual(runtime.state, "error")

    @mute_logger("odoo.addons.automation.models.automation_runtime_line")
    def test_workflow_run_all_stops_on_a_failing_step(self):
        self._make_chain(["raise UserError('stop here')", "pass"])
        runtime = self._make_runtime()

        runtime.action_run_all()

        lines = runtime.line_ids.sorted("sequence")
        self.assertEqual(lines[0].state, "error")
        self.assertEqual(lines[1].state, "waiting")
        self.assertFalse(lines[1].error_message)
        self.assertEqual(runtime.state, "error")

    def test_workflow_cancel(self):
        self._make_chain(["pass", "pass"])
        runtime = self._make_runtime()

        runtime.action_cancel()

        self.assertEqual(runtime.state, "cancel")
        self.assertEqual(set(runtime.line_ids.mapped("state")), {"cancel"})

    def test_multiple_workflows_run_independently(self):
        self._make_chain(["pass", "pass"])
        first = self._make_runtime(reference="TEST-PAR-001")
        second = self._make_runtime(reference="TEST-PAR-002")

        first.action_run_all()

        self.assertEqual(first.state, "done")
        self.assertEqual(second.state, "in_progress")

    def test_starting_a_started_runtime_is_a_no_op(self):
        self._make_chain(["pass"])
        runtime = self._make_runtime()

        runtime.action_start()

        self.assertEqual(runtime.state, "in_progress")
        self.assertEqual(len(runtime.line_ids), 1)
