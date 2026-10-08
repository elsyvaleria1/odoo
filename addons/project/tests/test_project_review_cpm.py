from odoo import Command
from odoo.tests import freeze_time, tagged
from odoo.tests.common import BaseCase

from .test_project_base import TestProjectCommon
from odoo.addons.project.models import project_project as cpm


@tagged("post_install", "-at_install")
class TestProjectReviewCpmFunctions(BaseCase):
    def _graph(self, edges):
        deps_on = {tid: [] for tid in (1, 2, 3, 4)}
        successors_of = {tid: [] for tid in (1, 2, 3, 4)}
        for tid, pred, dtype, lag in edges:
            deps_on[tid].append((pred, dtype, lag))
            successors_of[pred].append(tid)
        return deps_on, successors_of

    def test_topological_order_leaves_out_a_cycle(self) -> None:
        deps_on, successors_of = self._graph(
            [(2, 1, "fs", 0.0), (3, 2, "fs", 0.0), (2, 3, "fs", 0.0)]
        )
        order = cpm.get_cpm_topological_order({1, 2, 3, 4}, deps_on, successors_of)
        self.assertEqual(sorted(order), [1, 4])

    def test_topological_order_covers_a_dag(self) -> None:
        deps_on, successors_of = self._graph([(2, 1, "fs", 0.0), (3, 2, "ss", 1.0)])
        order = cpm.get_cpm_topological_order({1, 2, 3, 4}, deps_on, successors_of)
        self.assertEqual(len(order), 4)
        self.assertLess(order.index(1), order.index(2))
        self.assertLess(order.index(2), order.index(3))

    def test_release_delays_a_task_and_its_successors(self) -> None:
        deps_on, successors_of = self._graph([(2, 1, "fs", 0.0)])
        duration = {1: 4.0, 2: 2.0, 3: 1.0, 4: 1.0}
        es, ef, ls = cpm.solve_cpm(
            {1, 2, 3, 4}, deps_on, successors_of, duration, release={1: 3.0}
        )
        self.assertEqual((es[1], ef[1]), (3.0, 7.0))
        self.assertEqual((es[2], ef[2]), (7.0, 9.0))
        self.assertEqual(ls[3], 8.0)

    def test_solve_refuses_a_cycle(self) -> None:
        deps_on, successors_of = self._graph([(1, 2, "fs", 0.0), (2, 1, "fs", 0.0)])
        duration = dict.fromkeys((1, 2, 3, 4), 1.0)
        self.assertIsNone(cpm.solve_cpm({1, 2, 3, 4}, deps_on, successors_of, duration))


@freeze_time("2026-08-10 05:00:00")
@tagged("post_install", "-at_install")
class TestProjectReviewLevelling(TestProjectCommon):
    def _project(self, name):
        project = self.env["project.project"].create({"name": name})
        project.company_id = self.env.company
        project.allow_dependencies = True
        return project

    def _user(self, login):
        return self.env["res.users"].create(
            {"name": login, "login": login, "email": f"{login}@example.com"}
        )

    def test_a_shifted_task_pushes_its_successor(self) -> None:
        project = self._project("Levelling successor")
        user = self._user("leveller_succ")
        Task = self.env["project.task"]
        first = Task.create(
            {
                "name": "First",
                "project_id": project.id,
                "planned_hours": 8.0,
                "user_ids": [Command.link(user.id)],
            }
        )
        Task.create(
            {
                "name": "Chained",
                "project_id": project.id,
                "planned_hours": 16.0,
                "predecessor_ids": [Command.link(first.id)],
            }
        )
        movable = Task.create(
            {
                "name": "Movable",
                "project_id": project.id,
                "planned_hours": 1.0,
                "user_ids": [Command.link(user.id)],
            }
        )
        follower = Task.create(
            {
                "name": "Follower",
                "project_id": project.id,
                "planned_hours": 1.0,
                "predecessor_ids": [Command.link(movable.id)],
            }
        )
        project.action_compute_critical_path()
        self.env.flush_all()
        start_before = movable.cpm_date_start

        project.action_level_resources()
        self.env.flush_all()
        (movable | follower).invalidate_recordset()

        self.assertGreater(movable.cpm_date_start, start_before)
        self.assertGreaterEqual(follower.cpm_date_start, movable.cpm_date_end)
        self.assertAlmostEqual(movable.total_float, follower.total_float, places=2)

    def test_a_task_with_two_assignees_shifts_once_past_both(self) -> None:
        project = self._project("Levelling two assignees")
        user_a = self._user("leveller_two_a")
        user_b = self._user("leveller_two_b")
        Task = self.env["project.task"]
        busy_a = Task.create(
            {
                "name": "Busy A",
                "project_id": project.id,
                "planned_hours": 8.0,
                "user_ids": [Command.link(user_a.id)],
            }
        )
        busy_b = Task.create(
            {
                "name": "Busy B",
                "project_id": project.id,
                "planned_hours": 16.0,
                "user_ids": [Command.link(user_b.id)],
            }
        )
        Task.create(
            {
                "name": "Tail",
                "project_id": project.id,
                "planned_hours": 40.0,
                "predecessor_ids": [Command.link(busy_a.id)],
            }
        )
        pair = Task.create(
            {
                "name": "Pair",
                "project_id": project.id,
                "planned_hours": 2.0,
                "user_ids": [Command.link(user_a.id), Command.link(user_b.id)],
            }
        )
        project.action_compute_critical_path()
        self.env.flush_all()
        tasks = Task.search([("project_id", "=", project.id)])
        end_before = max(tasks.mapped("cpm_date_end"))

        project.action_level_resources()
        self.env.flush_all()
        tasks.invalidate_recordset()

        self.assertGreaterEqual(pair.cpm_date_start, busy_b.cpm_date_end)
        self.assertEqual(max(tasks.mapped("cpm_date_end")), end_before)
        self.assertGreaterEqual(pair.total_float, 0.0)
