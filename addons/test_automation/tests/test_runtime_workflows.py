
import logging

from odoo.exceptions import UserError
from odoo.tests import common, tagged

_logger = logging.getLogger(__name__)


@tagged("post_install", "-at_install")
class TestRuntimeWorkflows(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.Runtime = cls.env["automation.runtime"]
        cls.RuntimeLine = cls.env["automation.runtime.line"]
        cls.Automation = cls.env["automation.rule"]
        cls.Action = cls.env["ir.actions.server"]
        cls.Partner = cls.env["res.partner"]

        cls.model_automation = cls.env["ir.model"]._get("automation.rule")

        cls.test_partner = cls.Partner.create(
            {
                "name": "Test Partner for Runtime",
                "email": "test@runtime.com",
            }
        )

        cls.automation = cls.Automation.create(
            {
                "name": "Test Runtime Workflow",
                "model_id": cls.model_automation.id,
                "trigger": "on_hand",
            }
        )

    def _create_runtime_action(self, name, code="pass", predecessors=None):
        vals = {
            "name": name,
            "model_id": self.model_automation.id,
            "state": "code",
            "code": code,
            "automation_rule_id": self.automation.id,
            "usage": "automation",
        }

        action = self.Action.create(vals)
        for predecessor in predecessors or []:
            self.env["workflow.edge"].create(
                {
                    "source_node_id": predecessor.id,
                    "target_node_id": action.id,
                }
            )
        return action

    def test_runtime_creation(self):
        _logger.info("Testing runtime creation")

        runtime = self.Runtime.create(
            {
                "automation_id": self.automation.id,
                "partner_id": self.test_partner.id,
                "amount": 1500.00,
                "date": "2025-10-20",
                "reference": "TEST-001",
            }
        )

        self.assertEqual(runtime.state, "draft")
        self.assertEqual(runtime.partner_id, self.test_partner)
        self.assertEqual(runtime.amount, 1500.00)
        self.assertNotEqual(runtime.name, "New")
        self.assertEqual(runtime.progress, 0)

    def test_runtime_start_creates_lines(self):
        _logger.info("Testing runtime start creates lines")

        action_a = self._create_runtime_action("Action A")
        action_b = self._create_runtime_action("Action B", predecessors=[action_a])
        action_c = self._create_runtime_action("Action C", predecessors=[action_b])

        runtime = self.Runtime.create(
            {
                "automation_id": self.automation.id,
                "partner_id": self.test_partner.id,
                "amount": 1000.00,
                "date": "2025-10-20",
            }
        )

        runtime.action_start()

        self.assertEqual(runtime.state, "in_progress")

        self.assertEqual(len(runtime.line_ids), 3)

        line_a = runtime.line_ids.filtered(lambda l: l.action_id == action_a)
        line_b = runtime.line_ids.filtered(lambda l: l.action_id == action_b)
        line_c = runtime.line_ids.filtered(lambda l: l.action_id == action_c)

        self.assertEqual(line_a.state, "ready")
        self.assertEqual(line_b.state, "waiting")
        self.assertEqual(line_c.state, "waiting")

        self.assertFalse(line_a.edge_in_ids)
        self.assertEqual(line_b._get_predecessors(), line_a)
        self.assertEqual(line_c._get_predecessors(), line_b)

    def test_runtime_without_partner_fails(self):
        _logger.info("Testing runtime partner requirement")

        runtime = self.Runtime.create(
            {
                "automation_id": self.automation.id,
                "partner_id": False,
                "amount": 1000.00,
                "date": "2025-10-20",
            }
        )

        with self.assertRaises(UserError, msg="Should require partner"):
            runtime.action_start()

    def test_runtime_without_actions_fails(self):
        _logger.info("Testing runtime actions requirement")

        empty_automation = self.Automation.create(
            {
                "name": "Empty Workflow",
                "model_id": self.model_automation.id,
                "trigger": "on_hand",
            }
        )

        runtime = self.Runtime.create(
            {
                "automation_id": empty_automation.id,
                "partner_id": self.test_partner.id,
                "amount": 1000.00,
                "date": "2025-10-20",
            }
        )

        with self.assertRaises(UserError, msg="Should require at least one action"):
            runtime.action_start()

    def test_runtime_auto_completes(self):
        _logger.info("Testing runtime auto-completion")

        self._create_runtime_action("Single Action")

        runtime = self.Runtime.create(
            {
                "automation_id": self.automation.id,
                "partner_id": self.test_partner.id,
                "amount": 1000.00,
                "date": "2025-10-20",
            }
        )

        runtime.action_start()

        runtime.line_ids.action_mark_done()

        self.assertEqual(runtime.state, "done")

    def test_progress_calculation(self):
        _logger.info("Testing progress calculation")

        action_a = self._create_runtime_action("A")
        action_b = self._create_runtime_action("B", predecessors=[action_a])
        action_c = self._create_runtime_action("C", predecessors=[action_b])

        runtime = self.Runtime.create(
            {
                "automation_id": self.automation.id,
                "partner_id": self.test_partner.id,
                "amount": 1000.00,
                "date": "2025-10-20",
            }
        )

        runtime.action_start()

        self.assertEqual(runtime.progress, 0)
        self.assertEqual(runtime.progress_display, "0/3 steps")

        line_a = runtime.line_ids.filtered(lambda l: l.action_id == action_a)
        line_a.action_mark_done()

        self.assertEqual(runtime.progress, 33)
        self.assertEqual(runtime.progress_display, "1/3 steps")

        line_b = runtime.line_ids.filtered(lambda l: l.action_id == action_b)
        line_b.action_mark_done()

        self.assertEqual(runtime.progress, 67)
        self.assertEqual(runtime.progress_display, "2/3 steps")

        line_c = runtime.line_ids.filtered(lambda l: l.action_id == action_c)
        line_c.action_mark_done()

        self.assertEqual(runtime.progress, 100)
        self.assertEqual(runtime.progress_display, "3/3 steps")
        self.assertEqual(runtime.state, "done")

    def test_runtime_next_step_execution(self):
        _logger.info("Testing runtime next step execution")

        self._create_runtime_action(
            "Log Action",
            code=(
                "env['ir.config_parameter'].sudo().set_param("
                "'test_automation.next_step', 'executed')"
            ),
        )

        runtime = self.Runtime.create(
            {
                "automation_id": self.automation.id,
                "partner_id": self.test_partner.id,
                "amount": 1000.00,
                "date": "2025-10-20",
            }
        )

        runtime.action_start()

        runtime.action_next_step()

        self.assertEqual(
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "test_automation.next_step",
            ),
            "executed",
        )
        self.assertEqual(runtime.line_ids.state, "done")
        self.assertEqual(runtime.state, "done")

    def test_runtime_next_step_with_no_ready_actions(self):
        _logger.info("Testing next_step with no ready actions")

        action_a = self._create_runtime_action("A")
        self._create_runtime_action("B", predecessors=[action_a])

        runtime = self.Runtime.create(
            {
                "automation_id": self.automation.id,
                "partner_id": self.test_partner.id,
                "amount": 1000.00,
                "date": "2025-10-20",
            }
        )

        runtime.action_start()

        runtime.line_ids[0].write({"state": "waiting"})

        with self.assertRaises(UserError, msg="Should fail when no actions ready"):
            runtime.action_next_step()

    def test_runtime_not_in_progress_fails(self):
        _logger.info("Testing next_step state requirement")

        self._create_runtime_action("Action")

        runtime = self.Runtime.create(
            {
                "automation_id": self.automation.id,
                "partner_id": self.test_partner.id,
                "amount": 1000.00,
                "date": "2025-10-20",
            }
        )

        with self.assertRaises(UserError, msg="Should require in_progress state"):
            runtime.action_next_step()

    def test_runtime_cancel(self):
        _logger.info("Testing runtime cancellation")

        action_a = self._create_runtime_action("A")
        self._create_runtime_action("B", predecessors=[action_a])

        runtime = self.Runtime.create(
            {
                "automation_id": self.automation.id,
                "partner_id": self.test_partner.id,
                "amount": 1000.00,
                "date": "2025-10-20",
            }
        )

        runtime.action_start()

        runtime.action_cancel()

        self.assertEqual(runtime.state, "cancel")

        with self.assertRaises(UserError):
            runtime.action_next_step()

    def test_runtime_cancel_idempotent(self):
        _logger.info("Testing cancel idempotency")

        self._create_runtime_action("Action")

        runtime = self.Runtime.create(
            {
                "automation_id": self.automation.id,
                "partner_id": self.test_partner.id,
                "amount": 1000.00,
                "date": "2025-10-20",
            }
        )

        runtime.action_start()

        runtime.action_cancel()
        runtime.action_cancel()

        self.assertEqual(runtime.state, "cancel")

    def test_execution_context_passed_to_actions(self):
        _logger.info("Testing context propagation")

        self._create_runtime_action(
            "Context Action",
            code="""
env['ir.config_parameter'].sudo().set_param(
    'test_automation.ctx',
    '%s|%s|%s' % (runtime.partner_id.name, runtime.amount,
                  runtime.reference or 'No reference'),
)
""",
        )

        runtime = self.Runtime.create(
            {
                "automation_id": self.automation.id,
                "partner_id": self.test_partner.id,
                "amount": 2500.00,
                "date": "2025-10-20",
                "reference": "CTX-TEST",
            }
        )

        runtime.action_start()
        runtime.action_next_step()

        self.assertEqual(runtime.line_ids.state, "done")
        self.assertEqual(runtime.state, "done")
        self.assertEqual(
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "test_automation.ctx",
            ),
            f"{self.test_partner.name}|2500.0|CTX-TEST",
            "the step must be able to read its own runtime's context",
        )

    def test_multicompany_context(self):
        _logger.info("Testing multi-company context")

        self._create_runtime_action(
            "Company Action",
            code="""
env['ir.config_parameter'].sudo().set_param(
    'test_automation.company', runtime.company_ids.name,
)
""",
        )

        runtime = self.Runtime.create(
            {
                "automation_id": self.automation.id,
                "partner_id": self.test_partner.id,
                "amount": 1000.00,
                "date": "2025-10-20",
            }
        )

        runtime.action_start()
        runtime.action_next_step()

        self.assertEqual(runtime.state, "done")
        self.assertEqual(
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "test_automation.company",
            ),
            runtime.company_ids.name,
        )

    def test_runtime_line_dag_resolution(self):
        _logger.info("Testing DAG dependency resolution")

        action_a = self._create_runtime_action("A")
        action_b = self._create_runtime_action("B", predecessors=[action_a])
        action_c = self._create_runtime_action("C", predecessors=[action_a])
        action_d = self._create_runtime_action("D", predecessors=[action_b, action_c])

        runtime = self.Runtime.create(
            {
                "automation_id": self.automation.id,
                "partner_id": self.test_partner.id,
                "amount": 1000.00,
                "date": "2025-10-20",
            }
        )

        runtime.action_start()

        line_a = runtime.line_ids.filtered(lambda l: l.action_id == action_a)
        line_b = runtime.line_ids.filtered(lambda l: l.action_id == action_b)
        line_c = runtime.line_ids.filtered(lambda l: l.action_id == action_c)
        line_d = runtime.line_ids.filtered(lambda l: l.action_id == action_d)

        self.assertEqual(line_a.state, "ready")
        self.assertEqual(line_b.state, "waiting")
        self.assertEqual(line_c.state, "waiting")
        self.assertEqual(line_d.state, "waiting")

        line_a.action_mark_done()
        self.assertEqual(line_b.state, "ready")
        self.assertEqual(line_c.state, "ready")
        self.assertEqual(line_d.state, "waiting")

        line_b.action_mark_done()
        self.assertEqual(line_d.state, "waiting")

        line_c.action_mark_done()
        self.assertEqual(line_d.state, "ready")

    def test_runtime_line_error_handling(self):
        _logger.info("Testing error handling")

        self._create_runtime_action(
            "Failing Action",
            code="raise Exception('Test error')",
        )

        runtime = self.Runtime.create(
            {
                "automation_id": self.automation.id,
                "partner_id": self.test_partner.id,
                "amount": 1000.00,
                "date": "2025-10-20",
            }
        )

        runtime.action_start()

        runtime.action_next_step()

        self.assertEqual(runtime.line_ids.state, "error")
        self.assertIn("Test error", runtime.line_ids.error_message)
        self.assertEqual(runtime.state, "error")

    def test_multiple_concurrent_runtimes(self):
        _logger.info("Testing concurrent runtimes")

        self._create_runtime_action("Action")

        runtime1 = self.Runtime.create(
            {
                "automation_id": self.automation.id,
                "partner_id": self.test_partner.id,
                "amount": 1000.00,
                "date": "2025-10-20",
                "reference": "RT-001",
            }
        )

        runtime2 = self.Runtime.create(
            {
                "automation_id": self.automation.id,
                "partner_id": self.test_partner.id,
                "amount": 2000.00,
                "date": "2025-10-21",
                "reference": "RT-002",
            }
        )

        runtime1.action_start()
        runtime2.action_start()

        self.assertEqual(runtime1.state, "in_progress")
        self.assertEqual(runtime2.state, "in_progress")

        runtime1.action_next_step()
        self.assertEqual(runtime1.state, "done")

        self.assertEqual(runtime2.state, "in_progress")

        runtime2.action_next_step()
        self.assertEqual(runtime2.state, "done")

    def test_runtime_with_single_action(self):
        _logger.info("Testing single action runtime")

        self._create_runtime_action("Only Action")

        runtime = self.Runtime.create(
            {
                "automation_id": self.automation.id,
                "partner_id": self.test_partner.id,
                "amount": 1000.00,
                "date": "2025-10-20",
            }
        )

        runtime.action_start()

        self.assertEqual(len(runtime.line_ids), 1)
        self.assertEqual(runtime.line_ids.state, "ready")

        runtime.action_next_step()

        self.assertEqual(runtime.state, "done")
        self.assertEqual(runtime.progress, 100)

    def test_runtime_sequence_generation(self):
        _logger.info("Testing sequence generation")

        self._create_runtime_action("Action")

        runtime1 = self.Runtime.create(
            {
                "automation_id": self.automation.id,
                "partner_id": self.test_partner.id,
                "amount": 1000.00,
                "date": "2025-10-20",
            }
        )

        runtime2 = self.Runtime.create(
            {
                "automation_id": self.automation.id,
                "partner_id": self.test_partner.id,
                "amount": 2000.00,
                "date": "2025-10-20",
            }
        )

        self.assertNotEqual(runtime1.name, runtime2.name)
        self.assertNotEqual(runtime1.name, "New")
        self.assertNotEqual(runtime2.name, "New")
