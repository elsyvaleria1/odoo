from unittest.mock import patch

import psycopg

from odoo.exceptions import AccessError, UserError
from odoo.tools import mute_logger

from .test_queued_dispatch import QueuedCase
from .test_run_completion import RunCompletionCase
from .test_workflow_dag import link

LINE_LOGGER = "odoo.addons.automation.models.automation_runtime_line"
FAILING = "raise ValueError('boom')"


class TestFailedRun(RunCompletionCase):
    def _chain(self):
        first = self._action("first", sequence=1)
        failing = self._action("failing", FAILING, sequence=2)
        last = self._action("last", "record.write({'ref': 'last ran'})", sequence=3)
        link(self.env, first, failing)
        link(self.env, failing, last)
        return first, failing, last

    @mute_logger(LINE_LOGGER)
    def test_only_the_step_that_failed_is_failed(self):
        first, failing, last = self._chain()

        runtime = self._run()

        self.assertEqual(runtime.state, "error")
        self.assertEqual(self._line(runtime, first).state, "done")
        self.assertEqual(self._line(runtime, failing).state, "error")
        self.assertIn("boom", self._line(runtime, failing).error_message)
        self.assertEqual(self._line(runtime, last).state, "waiting")
        self.assertFalse(self._line(runtime, last).error_message)

    @mute_logger(LINE_LOGGER)
    def test_the_failure_is_kept_in_the_chatter(self):
        self._chain()

        runtime = self._run()

        failure = runtime.message_ids.filtered(
            lambda message: message.subject == "Workflow Failed",
        )
        self.assertIn("failing", failure.body)
        self.assertIn("boom", failure.body)

    @mute_logger(LINE_LOGGER)
    def test_a_retry_runs_the_failed_step_again_and_no_other(self):
        _first, failing, last = self._chain()
        runtime = self._run()
        failing.code = "record.write({'function': 'retried'})"

        runtime.action_retry()

        self.assertEqual(self._line(runtime, failing).state, "done")
        self.assertFalse(self._line(runtime, failing).error_message)
        self.assertEqual(self._line(runtime, last).state, "ready")
        self.assertEqual(runtime.state, "in_progress")
        self.assertEqual(self.partner.function, "retried")
        self.assertFalse(self.partner.ref, "the step after it waits for its own turn")

    @mute_logger(LINE_LOGGER)
    def test_a_retried_run_finishes_like_any_other(self):
        _first, failing, last = self._chain()
        runtime = self._run()
        failing.code = "pass"
        runtime.action_retry()

        runtime.action_next_step()

        self.assertEqual(self._line(runtime, last).state, "done")
        self.assertEqual(runtime.state, "done")
        self.assertEqual(self.partner.ref, "last ran")

    @mute_logger(LINE_LOGGER)
    def test_a_retry_that_fails_again_fails_the_run_again(self):
        _first, failing, last = self._chain()
        runtime = self._run()
        failing.code = "raise ValueError('still broken')"

        runtime.action_retry()

        self.assertEqual(runtime.state, "error")
        self.assertEqual(self._line(runtime, failing).state, "error")
        self.assertIn("still broken", self._line(runtime, failing).error_message)
        self.assertEqual(self._line(runtime, last).state, "waiting")

    @mute_logger(LINE_LOGGER)
    def test_a_step_that_cannot_be_settled_leaves_nothing_behind(self):
        only = self._action("only", "record.write({'ref': 'written'})")
        runtime = self.env["automation.runtime"].create(
            {
                "automation_id": self.automation.id,
                "res_model": "res.partner",
                "res_id": self.partner.id,
            }
        )
        runtime.action_start()

        with patch.object(
            type(runtime),
            "action_done",
            autospec=True,
            side_effect=ValueError("closing the run failed"),
        ):
            runtime.action_next_step()

        self.assertEqual(self._line(runtime, only).state, "error")
        self.assertIn("closing the run", self._line(runtime, only).error_message)
        self.assertEqual(runtime.state, "error")
        self.assertFalse(
            self.partner.ref,
            "a step shown as failed must not have left its effect, or a retry "
            "does it twice",
        )

        runtime.action_retry()

        self.assertEqual(runtime.state, "done")
        self.assertEqual(self.partner.ref, "written")

    def test_a_run_that_did_not_fail_cannot_be_retried(self):
        self._action("only")
        runtime = self._run()

        with self.assertRaises(UserError):
            runtime.action_retry()

    @mute_logger(LINE_LOGGER)
    def test_a_handled_failure_is_not_run_again(self):
        handled = self._action("handled", FAILING, sequence=1)
        handler = self._action("handler", sequence=2)
        failing = self._action("failing", FAILING, sequence=3)
        link(self.env, handled, handler, condition="on_error")
        link(self.env, handler, failing)
        runtime = self._run()
        self.assertEqual(runtime.state, "error")
        failing.code = "pass"

        runtime.action_retry()

        self.assertEqual(
            self._line(runtime, handled).state,
            "error",
            "its failure was the path the workflow took, not one to repair",
        )
        self.assertEqual(self._line(runtime, failing).state, "done")
        self.assertEqual(runtime.state, "done")

    @mute_logger(LINE_LOGGER)
    def test_a_retry_releases_steps_an_older_version_failed_wholesale(self):
        _first, failing, last = self._chain()
        runtime = self._run()
        self._line(runtime, last).write(
            {
                "state": "error",
                "date_settled": self.env.cr.now(),
                "error_message": "Step never ran: the workflow already failed.",
            }
        )
        failing.code = "pass"

        runtime.action_retry()

        self.assertEqual(self._line(runtime, failing).state, "done")
        self.assertEqual(self._line(runtime, last).state, "ready")
        self.assertFalse(self._line(runtime, last).error_message)

    @mute_logger(LINE_LOGGER)
    def test_a_failed_run_can_be_cancelled(self):
        _first, failing, last = self._chain()
        runtime = self._run()

        runtime.action_cancel()

        self.assertEqual(runtime.state, "cancel")
        self.assertEqual(self._line(runtime, last).state, "cancel")
        self.assertEqual(
            self._line(runtime, failing).state,
            "error",
            "what failed stays on record",
        )

    @mute_logger(LINE_LOGGER)
    def test_a_sub_workflow_is_retried_through_its_parent(self):
        child_rule = self.automation.copy({"name": "Child"})
        self.Action.create(
            {
                "name": "child fails",
                "model_id": self.model_partner.id,
                "state": "code",
                "code": FAILING,
                "automation_rule_id": child_rule.id,
                "usage": "automation",
            }
        )
        gate = self._action(
            "call child",
            node_type="subflow",
            subflow_automation_id=child_rule.id,
        )
        runtime = self._run()
        child = self._line(runtime, gate).created_record_ref
        self.assertEqual(child.state, "error")
        self.assertEqual(runtime.state, "error")

        with self.assertRaises(UserError):
            child.action_retry()

        child_rule.action_server_ids.code = "pass"
        runtime.action_retry()

        self.assertEqual(self._line(runtime, gate).state, "done")
        self.assertEqual(runtime.state, "done")

    def test_a_step_by_step_run_waits_when_it_reaches_a_pause(self):
        first = self._action("first", sequence=1)
        pause = self._action("pause", node_type="wait", wait_delay=1, sequence=2)
        link(self.env, first, pause)
        runtime = self.env["automation.runtime"].create(
            {
                "automation_id": self.automation.id,
                "res_model": "res.partner",
                "res_id": self.partner.id,
            }
        )
        runtime.action_start()
        runtime.action_next_step()

        runtime.action_next_step()

        self.assertEqual(self._line(runtime, pause).state, "paused")
        self.assertEqual(
            runtime.state,
            "waiting_resume",
            "left in progress, the resume cron would never find the run",
        )


class TestLostTransaction(RunCompletionCase):
    def _ready_line(self):
        step = self._action("step", "record.write({'ref': 'ran'})")
        runtime = self.env["automation.runtime"].create(
            {
                "automation_id": self.automation.id,
                "res_model": "res.partner",
                "res_id": self.partner.id,
            }
        )
        runtime.action_start()
        line = self._line(runtime, step)
        self.assertEqual(line.state, "ready")
        return line

    def _execute_losing(self, line, target, attribute):
        raised = None
        lost = psycopg.errors.SerializationFailure("concurrent update")
        with patch.object(target, attribute, side_effect=lost):
            try:
                line.action_execute()
            except psycopg.errors.SerializationFailure as error:
                raised = error
        self.assertIsNotNone(raised, "the lost transaction reaches the caller")

    def _assert_not_failed(self, line):
        self.assertNotEqual(line.state, "error")
        self.assertFalse(line.error_message)
        self.assertNotEqual(line.runtime_id.state, "error")

    def test_a_step_losing_its_transaction_raises_instead_of_failing(self):
        line = self._ready_line()

        self._execute_losing(line, type(self.env["ir.actions.server"]), "run")

        self._assert_not_failed(line)

    def test_a_savepoint_refused_by_a_concurrent_update_raises_too(self):
        line = self._ready_line()

        self._execute_losing(line, self.env.cr, "savepoint")

        self._assert_not_failed(line)


class TestFailedQueuedRun(QueuedCase):
    def test_a_ready_step_of_a_failed_run_is_not_dispatched(self):
        failing = self._action("failing", FAILING, sequence=1)
        other = self._action("other", "record.write({'ref': 'other ran'})", sequence=2)
        (runtime,) = self._launch(self.partner)

        with mute_logger(LINE_LOGGER):
            self._dispatch()

        self.assertEqual(runtime.state, "error")
        self.assertEqual(self._line(runtime, failing).state, "error")
        self.assertEqual(self._line(runtime, other).state, "ready")
        self.assertFalse(self.partner.ref)

    def test_a_retried_queued_run_goes_back_to_the_dispatcher(self):
        failing = self._action("failing", FAILING, sequence=1)
        other = self._action("other", "record.write({'ref': 'other ran'})", sequence=2)
        (runtime,) = self._launch(self.partner)
        with mute_logger(LINE_LOGGER):
            self._dispatch()
        failing.code = "pass"

        runtime.action_retry()

        self.assertEqual(runtime.state, "in_progress")
        self.assertEqual(
            self._line(runtime, failing).state,
            "ready",
            "a queued run is executed by the dispatcher, never inline",
        )

        self._dispatch()

        self.assertEqual(runtime.state, "done")
        self.assertEqual(self._line(runtime, other).state, "done")
        self.assertEqual(self.partner.ref, "other ran")


class TestRunGraph(RunCompletionCase):
    @mute_logger(LINE_LOGGER)
    def test_the_run_graph_draws_each_step_where_it_stands(self):
        first = self._action("first", sequence=1)
        failing = self._action("failing", FAILING, sequence=2)
        last = self._action("last", sequence=3)
        link(self.env, first, failing)
        link(self.env, failing, last, condition="always")
        runtime = self.env["automation.runtime"].create(
            {
                "automation_id": self.automation.id,
                "res_model": "res.partner",
                "res_id": self.partner.id,
            }
        )
        runtime.action_start()
        runtime.action_next_step()
        runtime.action_next_step()

        graph = runtime.get_workflow_graph()

        self.assertEqual(graph["runtime_id"], runtime.id)
        self.assertTrue(graph["readonly"])
        self.assertEqual(graph["automation_id"], self.automation.id)
        nodes = {node["id"]: node for node in graph["nodes"]}
        self.assertEqual(set(nodes), {first.id, failing.id, last.id})
        self.assertEqual(nodes[first.id]["runtime_state"], "done")
        self.assertEqual(nodes[failing.id]["runtime_state"], "error")
        self.assertIn("boom", nodes[failing.id]["error_message"])
        self.assertEqual(nodes[failing.id]["line_id"], self._line(runtime, failing).id)
        self.assertFalse(any(node["deletable"] for node in graph["nodes"]))
        self.assertEqual(
            {
                (edge["source"], edge["target"], edge["condition"])
                for edge in graph["edges"]
            },
            {
                (first.id, failing.id, "on_success"),
                (failing.id, last.id, "always"),
            },
        )

    def test_the_run_graph_is_the_run_s_own_not_the_definition_s(self):
        first = self._action("first", sequence=1)
        second = self._action("second", sequence=2)
        edge = link(self.env, first, second)
        runtime = self.env["automation.runtime"].create(
            {
                "automation_id": self.automation.id,
                "res_model": "res.partner",
                "res_id": self.partner.id,
            }
        )
        runtime.action_start()
        added = self._action("added later", sequence=3)
        link(self.env, second, added)
        edge.condition = "always"
        runtime.action_run_all()

        graph = runtime.get_workflow_graph()

        self.assertNotIn(added.id, {node["id"] for node in graph["nodes"]})
        self.assertEqual(
            [edge["condition"] for edge in graph["edges"]],
            ["on_success"],
            "the run routes on the condition it started with",
        )

    def test_whoever_reads_a_run_can_see_it_drawn(self):
        only = self._action("only")
        runtime = self._run()
        reader = self.env["res.users"].create(
            {
                "name": "Run Reader",
                "login": "run_reader_wf",
                "group_ids": [(6, 0, [self.env.ref("base.group_user").id])],
            }
        )

        with self.assertRaises(AccessError):
            only.with_user(reader).read(["name"])

        graph = runtime.with_user(reader).get_workflow_graph()

        self.assertEqual([node["id"] for node in graph["nodes"]], [only.id])
        self.assertEqual(graph["nodes"][0]["runtime_state"], "done")

    def test_the_run_graph_names_the_record_a_step_created(self):
        self._action(
            "only",
            "runtime_line.write({'created_record_ref': 'automation.runtime,%s' % runtime.id})",
        )
        runtime = self._run()

        graph = runtime.get_workflow_graph()

        self.assertEqual(graph["nodes"][0]["created_record"], runtime.display_name)
