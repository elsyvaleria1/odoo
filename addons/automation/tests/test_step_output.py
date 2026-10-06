from .test_run_completion import RunCompletionCase
from .test_workflow_dag import link

REPORT_THREE = "runtime_line._set_output({'count': 3}, 'Counted three')"


class TestStepOutput(RunCompletionCase):
    def test_a_step_reports_what_it_did(self):
        count = self._action("count", REPORT_THREE)

        runtime = self._run()

        line = self._line(runtime, count)
        self.assertEqual(line.output, {"count": 3})
        self.assertEqual(line.output_summary, "Counted three")

    def test_a_step_that_reports_nothing_has_no_output(self):
        quiet = self._action("quiet")

        runtime = self._run()

        self.assertFalse(self._line(runtime, quiet).output)
        self.assertFalse(self._line(runtime, quiet).output_summary)

    def test_an_edge_branches_on_what_its_source_reported(self):
        count = self._action("count", REPORT_THREE)
        many = self._action("many")
        few = self._action("few")
        link(
            self.env,
            count,
            many,
            condition="expression",
            condition_expr="output['count'] > 2",
        )
        link(
            self.env,
            count,
            few,
            condition="expression",
            condition_expr="output['count'] <= 2",
        )

        runtime = self._run()

        self.assertEqual(self._line(runtime, many).state, "done")
        self.assertEqual(self._line(runtime, few).state, "skipped")
        self.assertEqual(runtime.state, "done")

    def test_an_edge_reads_an_empty_output_when_its_source_reported_none(self):
        quiet = self._action("quiet")
        after = self._action("after")
        link(
            self.env,
            quiet,
            after,
            condition="expression",
            condition_expr="not output",
        )

        runtime = self._run()

        self.assertEqual(self._line(runtime, after).state, "done")

    def test_the_run_diagram_shows_what_each_step_reported(self):
        count = self._action("count", REPORT_THREE)
        runtime = self._run()

        nodes = runtime.get_workflow_graph()["nodes"]

        node = next(node for node in nodes if node["id"] == count.id)
        self.assertEqual(node["output_summary"], "Counted three")
