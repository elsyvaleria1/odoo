from odoo.tests.common import tagged

from .common import AutomationAccountCommon


@tagged("post_install", "-at_install")
class TestDAGResolution(AutomationAccountCommon):
    DONE = "action.mark_action_done_and_continue(record)"

    def _line_of(self, runtime, step):
        return runtime.line_ids.filtered(lambda line: line.action_id == step)

    def test_sequential_dag_resolution(self):
        first, second, third = self._make_chain([self.DONE] * 3)
        runtime = self._make_runtime()

        line_a = self._line_of(runtime, first)
        line_b = self._line_of(runtime, second)
        line_c = self._line_of(runtime, third)

        self.assertEqual(line_a.state, "ready")
        self.assertEqual(line_b.state, "waiting")
        self.assertEqual(line_c.state, "waiting")

        runtime.action_next_step()
        self.assertEqual(line_a.state, "done")
        self.assertEqual(line_b.state, "ready")
        self.assertEqual(line_c.state, "waiting")

        runtime.action_next_step()
        self.assertEqual(line_b.state, "done")
        self.assertEqual(line_c.state, "ready")

        runtime.action_next_step()
        self.assertEqual(line_c.state, "done")
        self.assertEqual(runtime.state, "done")

    def test_parallel_fork_dag(self):
        root = self._make_step(self.DONE, name="Root")
        left = self._make_step(self.DONE, name="Left", predecessors=root)
        right = self._make_step(self.DONE, name="Right", predecessors=root)

        runtime = self._make_runtime()

        self.assertEqual(self._line_of(runtime, root).state, "ready")
        self.assertEqual(self._line_of(runtime, left).state, "waiting")
        self.assertEqual(self._line_of(runtime, right).state, "waiting")

        runtime.action_next_step()

        self.assertEqual(self._line_of(runtime, root).state, "done")
        self.assertEqual(self._line_of(runtime, left).state, "ready")
        self.assertEqual(self._line_of(runtime, right).state, "ready")

    def test_join_pattern_dag(self):
        left = self._make_step(self.DONE, name="Left")
        right = self._make_step(self.DONE, name="Right")
        join = self._make_step(self.DONE, name="Join", predecessors=left | right)

        runtime = self._make_runtime()
        line_join = self._line_of(runtime, join)

        self.assertEqual(line_join.state, "waiting")

        self._line_of(runtime, left).action_execute()
        self.assertEqual(line_join.state, "waiting")

        self._line_of(runtime, right).action_execute()
        self.assertEqual(line_join.state, "ready")

    def test_diamond_pattern_dag(self):
        root = self._make_step(self.DONE, name="Root")
        left = self._make_step(self.DONE, name="Left", predecessors=root)
        right = self._make_step(self.DONE, name="Right", predecessors=root)
        sink = self._make_step(self.DONE, name="Sink", predecessors=left | right)

        runtime = self._make_runtime()
        runtime.action_run_all()

        self.assertEqual(runtime.state, "done")
        self.assertEqual(
            set(runtime.line_ids.mapped("state")),
            {"done"},
        )
        self.assertEqual(len(self._line_of(runtime, sink)), 1)
        self.assertEqual(len(runtime.line_ids), 4)

    def test_predecessor_computation(self):
        first, second, third = self._make_chain([self.DONE] * 3)
        runtime = self._make_runtime()

        line_a = self._line_of(runtime, first)
        line_b = self._line_of(runtime, second)
        line_c = self._line_of(runtime, third)

        self.assertFalse(line_a._get_predecessors())
        self.assertEqual(line_b._get_predecessors(), line_a)
        self.assertEqual(line_c._get_predecessors(), line_b)
        self.assertEqual(line_a._get_successors(), line_b)

    def test_a_whole_chain_runs_to_done(self):
        self._make_chain(["pass", "pass", "pass"])
        runtime = self._make_runtime()

        runtime.action_run_all()

        self.assertEqual(runtime.state, "done")
        self.assertEqual(set(runtime.line_ids.mapped("state")), {"done"})
