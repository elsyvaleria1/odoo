from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user, tagged

from .common import TrainingNeutralityCase


@tagged("post_install", "-at_install")
class TestTrainingSimulator(TrainingNeutralityCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.simulator = cls.env["training.simulator"].create(
            {"name": "Test game", "code": "test_game", "play_route": "/test/game"}
        )
        cls.player = new_test_user(
            cls.env,
            "trainee",
            groups="base.group_user,training_simulator.group_training_player",
        )
        cls.other = new_test_user(
            cls.env,
            "trainee2",
            groups="base.group_user,training_simulator.group_training_player",
        )

    def test_session_finish_and_neutrality(self):
        Session = self.env["training.simulator.session"].with_user(self.player)
        with self.assertNoOperationalWrites():
            session = Session.create({"simulator_id": self.simulator.id})
            session._training_finish(
                {"scenario": "1", "passed": True, "error_count": 2, "summary": "ok"}
            )
        self.assertEqual(session.state, "done")
        self.assertTrue(session.passed)
        self.assertEqual(session.error_count, 2)
        with self.assertRaises(UserError):
            session._training_finish({})

    def test_dashboard_counts_practised_scenarios(self):
        self.simulator.scenario_count = 3
        Session = self.env["training.simulator.session"].with_user(self.player)
        for scenario in ("1", "2", "2"):
            Session.create({"simulator_id": self.simulator.id})._training_finish(
                {"scenario": scenario, "passed": scenario == "1"}
            )
        card = next(
            c
            for c in self.env["training.simulator"]
            .with_user(self.player)
            .get_training_dashboard()["simulators"]
            if c["id"] == self.simulator.id
        )
        # Practised counts every finished scenario once, passed or not.
        self.assertEqual((card["best"], card["scenario_count"]), (2, 3))

    def test_player_sees_only_own_sessions(self):
        mine = (
            self.env["training.simulator.session"]
            .with_user(self.player)
            .create({"simulator_id": self.simulator.id})
        )
        with self.assertRaises(AccessError):
            mine.with_user(self.other).read(["state"])
        self.assertFalse(
            self.env["training.simulator.session"]
            .with_user(self.other)
            .search([("id", "=", mine.id)])
        )
