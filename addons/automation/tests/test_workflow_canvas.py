from psycopg.errors import IntegrityError

from odoo.exceptions import ValidationError
from odoo.fields import Command
from odoo.tests.common import TransactionCase, new_test_user
from odoo.tools import mute_logger


class TestWorkflowCanvasState(TransactionCase):
    def setUp(self):
        super().setUp()
        self.model_partner = self.env["ir.model"]._get("res.partner")
        self.automation = self.env["automation.rule"].create(
            {
                "name": "Canvas State",
                "model_id": self.model_partner.id,
                "trigger": "on_hand",
            }
        )
        self.first, self.second, self.third = self.env["ir.actions.server"].create(
            [
                {
                    "name": name,
                    "model_id": self.model_partner.id,
                    "state": "code",
                    "code": "pass",
                    "automation_rule_id": self.automation.id,
                    "usage": "automation",
                }
                for name in ("first", "second", "third")
            ]
        )

    def _link(self, source, target, condition="on_success"):
        return self.env["workflow.edge"].create(
            {
                "source_node_id": source.id,
                "target_node_id": target.id,
                "condition": condition,
            }
        )


class TestNodeSize(TestWorkflowCanvasState):
    def test_zero_is_the_unset_size(self):
        self.first.write({"pos_width": 0, "pos_height": 0})
        self.assertFalse(self.first.pos_width or self.first.pos_height)

    def test_a_size_inside_the_bounds_is_stored(self):
        self.first.write({"pos_width": 300, "pos_height": 150})
        self.assertEqual((self.first.pos_width, self.first.pos_height), (300, 150))

    def test_a_width_under_the_minimum_is_refused(self):
        with self.assertRaises(ValidationError):
            self.first.pos_width = 40

    def test_a_width_over_the_maximum_is_refused(self):
        with self.assertRaises(ValidationError):
            self.first.pos_width = 5000

    def test_a_height_under_the_minimum_is_refused(self):
        with self.assertRaises(ValidationError):
            self.first.pos_height = 10

    def test_a_height_over_the_maximum_is_refused(self):
        with self.assertRaises(ValidationError):
            self.first.pos_height = 900

    def test_the_payload_carries_the_bounds_and_resolves_the_default(self):
        self.first.write({"pos_width": 320, "pos_height": 200})

        payload = self.automation.get_workflow_graph()
        sizes = {
            node["id"]: (node["width"], node["height"]) for node in payload["nodes"]
        }
        bounds = payload["node_size"]

        self.assertEqual(sizes[self.first.id], (320, 200))
        self.assertEqual(
            sizes[self.second.id],
            (bounds["default"]["width"], bounds["default"]["height"]),
        )
        self.assertLess(bounds["min"]["width"], bounds["default"]["width"])
        self.assertGreater(bounds["max"]["width"], bounds["default"]["width"])
        self.assertGreater(bounds["header_height"], 0)

    def test_every_bound_the_payload_states_is_the_one_enforced(self):
        bounds = self.automation.get_workflow_graph()["node_size"]

        for axis, field in (("width", "pos_width"), ("height", "pos_height")):
            self.first.write({field: bounds["min"][axis]})
            self.first.write({field: bounds["max"][axis]})
            with self.assertRaises(ValidationError):
                self.first.write({field: bounds["min"][axis] - 1})
            with self.assertRaises(ValidationError):
                self.first.write({field: bounds["max"][axis] + 1})


class TestStepRemoval(TestWorkflowCanvasState):
    def _record_a_run_over(self, action):
        runtime = self.env["automation.runtime"].create(
            {
                "automation_id": self.automation.id,
                "res_model": "res.partner",
                "res_id": self.env.user.partner_id.id,
            }
        )
        return self.env["automation.runtime.line"].create(
            {
                "runtime_id": runtime.id,
                "action_id": action.id,
                "name": action.name,
            }
        )

    def test_a_step_no_run_reached_is_offered_for_removal(self):
        deletable = {
            node["id"]: node["deletable"]
            for node in self.automation.get_workflow_graph()["nodes"]
        }

        self.assertEqual(
            deletable,
            {self.first.id: True, self.second.id: True, self.third.id: True},
        )

    def test_a_step_a_run_reached_is_withheld(self):
        self._record_a_run_over(self.second)

        deletable = {
            node["id"]: node["deletable"]
            for node in self.automation.get_workflow_graph()["nodes"]
        }

        self.assertEqual(
            deletable,
            {self.first.id: True, self.second.id: False, self.third.id: True},
        )

    def test_the_withheld_step_is_the_one_that_cannot_be_unlinked(self):
        self._record_a_run_over(self.second)

        with self.assertRaises(IntegrityError), mute_logger("odoo.db.cursor"):
            with self.env.cr.savepoint():
                self.second.unlink()

    def test_removing_a_step_takes_the_edges_that_touch_it(self):
        self._link(self.first, self.second)
        self._link(self.second, self.third)
        edge_ids = self.automation.edge_ids.ids

        self.first.unlink()

        self.assertEqual(len(self.automation.edge_ids), 1)
        self.assertTrue(self.env["workflow.edge"].browse(edge_ids[1]).exists())

    def test_a_run_of_another_company_still_withholds_the_step(self):
        elsewhere = self.env["res.company"].create({"name": "Elsewhere Co"})
        runtime = self.env["automation.runtime"].create(
            {
                "automation_id": self.automation.id,
                "company_ids": [Command.set(elsewhere.ids)],
                "res_model": "res.partner",
                "res_id": self.env.user.partner_id.id,
            }
        )
        self.env["automation.runtime.line"].create(
            {
                "runtime_id": runtime.id,
                "action_id": self.second.id,
                "name": self.second.name,
            }
        )
        reader = new_test_user(
            self.env, login="canvas_outsider", groups="base.group_system"
        )
        self.assertNotIn(elsewhere, reader.company_ids)
        self.assertFalse(
            self.env["automation.runtime.line"]
            .with_user(reader)
            .search([("action_id", "=", self.second.id)]),
            "the premise: the reader cannot see the line that holds the step",
        )

        deletable = {
            node["id"]: node["deletable"]
            for node in self.automation.with_user(reader).get_workflow_graph()["nodes"]
        }

        self.assertFalse(deletable[self.second.id])
        self.assertTrue(deletable[self.first.id])
        self.assertEqual(
            self.env["automation.runtime.line"]._fields["action_id"].ondelete,
            "restrict",
        )

    def test_the_payload_says_nothing_about_another_automations_runs(self):
        other = self.env["automation.rule"].create(
            {
                "name": "Elsewhere",
                "model_id": self.model_partner.id,
                "trigger": "on_hand",
            }
        )
        elsewhere = self.env["ir.actions.server"].create(
            {
                "name": "elsewhere",
                "model_id": self.model_partner.id,
                "state": "code",
                "code": "pass",
                "automation_rule_id": other.id,
                "usage": "automation",
            }
        )
        runtime = self.env["automation.runtime"].create(
            {
                "automation_id": other.id,
                "res_model": "res.partner",
                "res_id": self.env.user.partner_id.id,
            }
        )
        self.env["automation.runtime.line"].create(
            {
                "runtime_id": runtime.id,
                "action_id": elsewhere.id,
                "name": elsewhere.name,
            }
        )

        deletable = {
            node["id"]: node["deletable"]
            for node in self.automation.get_workflow_graph()["nodes"]
        }

        self.assertTrue(all(deletable.values()))
        self.assertNotIn(elsewhere.id, deletable)


class TestStepDetail(TestWorkflowCanvasState):
    def _nodes(self):
        return {
            node["id"]: node for node in self.automation.get_workflow_graph()["nodes"]
        }

    def test_a_wait_step_carries_its_duration(self):
        self.first.write({"node_type": "wait", "wait_delay": 36, "wait_unit": "hour"})

        node = self._nodes()[self.first.id]

        self.assertEqual((node["wait_delay"], node["wait_unit"]), (36, "hour"))

    def test_an_approval_step_carries_its_approvers(self):
        approver = new_test_user(self.env, login="canvas_approver")
        self.first.write(
            {
                "node_type": "approval",
                "approval_user_ids": [(6, 0, approver.ids)],
                "approval_note": "Sign it",
            }
        )

        self.assertEqual(
            self._nodes()[self.first.id]["approver_names"],
            approver.display_name,
        )

    def test_a_subflow_step_names_the_automation_it_runs(self):
        target = self.env["automation.rule"].create(
            {
                "name": "Nightly sweep",
                "model_id": self.model_partner.id,
                "trigger": "on_hand",
            }
        )
        self.first.write({"node_type": "subflow", "subflow_automation_id": target.id})

        self.assertEqual(self._nodes()[self.first.id]["subflow_name"], "Nightly sweep")

    def test_a_plain_action_step_names_no_approver_and_no_subflow(self):
        node = self._nodes()[self.second.id]

        self.assertEqual(node["approver_names"], "")
        self.assertEqual(node["subflow_name"], "")


class TestFullScreen(TestWorkflowCanvasState):
    def test_the_rule_opens_its_workflow_on_a_page_of_its_own(self):
        action = self.automation.action_view_workflow()

        self.assertEqual(action["res_model"], "automation.rule")
        self.assertEqual(action["res_id"], self.automation.id)
        self.assertEqual(
            action["views"],
            [
                (
                    self.env.ref("automation.view_automation_form_workflow_full").id,
                    "form",
                )
            ],
        )

    def test_a_run_opens_its_diagram_on_a_page_of_its_own(self):
        runtime = self.env["automation.runtime"].create(
            {
                "automation_id": self.automation.id,
                "res_model": "res.partner",
                "res_id": self.env.user.partner_id.id,
            }
        )

        action = runtime.action_view_workflow()

        self.assertEqual(action["res_model"], "automation.runtime")
        self.assertEqual(action["res_id"], runtime.id)
        self.assertEqual(
            action["views"],
            [
                (
                    self.env.ref(
                        "automation.view_automation_runtime_form_workflow_full"
                    ).id,
                    "form",
                )
            ],
        )

    def test_the_graph_carries_no_viewport_to_restore(self):
        graph = self.automation.get_workflow_graph()

        self.assertNotIn("viewport", graph)


class TestWorkflowCounts(TestWorkflowCanvasState):
    def test_the_counts_follow_the_graph(self):
        self.assertEqual(self.automation.step_count, 3)
        self.assertEqual(self.automation.edge_count, 0)

        self._link(self.first, self.second)
        self._link(self.second, self.third)
        self.assertEqual(self.automation.edge_count, 2)

        self.third.unlink()
        self.assertEqual(self.automation.step_count, 2)
        self.assertEqual(self.automation.edge_count, 1)

    def test_the_counts_are_stored_and_searchable(self):
        self._link(self.first, self.second)
        self.automation.flush_recordset()

        self.assertIn(
            self.automation,
            self.env["automation.rule"].search([("step_count", "=", 3)]),
        )
        self.assertIn(
            self.automation,
            self.env["automation.rule"].search([("edge_count", "=", 1)]),
        )

    def test_an_unsaved_automation_counts_the_steps_in_the_form(self):
        draft = self.env["automation.rule"].new(
            {
                "name": "Draft",
                "model_id": self.model_partner.id,
                "trigger": "on_hand",
                "action_server_ids": [
                    (0, 0, {"name": "one", "state": "code", "code": "pass"}),
                    (0, 0, {"name": "two", "state": "code", "code": "pass"}),
                ],
            }
        )

        self.assertEqual(draft.step_count, 2)
        self.assertEqual(draft.edge_count, 0)
