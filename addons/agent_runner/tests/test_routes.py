from unittest.mock import patch

from odoo.libs.json import dumps as json_dumps
from odoo.tests.common import HttpCase, tagged

from .common import RunnerFixtures


@tagged("post_install", "-at_install")
class TestRoutes(RunnerFixtures, HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.runner = cls._runner("route runner")
        cls.token = cls._token(cls.runner)

    def _post(self, verb, body=None, token=None):
        self.env.flush_all()
        response = self.url_open(
            f"/agent_runner/v1/{verb}",
            data=json_dumps(body or {}),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token or self.token}",
            },
        )
        return response.status_code, response.json()

    def _exchanges(self, event_type):
        return self.env["integration.exchange"].search(
            [
                ("channel_id", "=", f"agent.runner,{self.runner.id}"),
                ("event_type", "=", event_type),
            ]
        )

    def _claim(self):
        status, answer = self._post("claim")
        self.assertEqual(status, 200)
        return answer["run"]

    def test_a_runner_claims_works_and_completes_a_run(self):
        run = self._run("routed", payload={"question": 6})
        lease = self._claim()
        self.assertEqual(lease["id"], run.id)
        self.assertEqual(lease["payload"], {"question": 6})
        self.assertEqual((lease["kind"], lease["capability"]), ("probe", "sandbox"))
        token = lease["lease_token"]
        status, beat = self._post("heartbeat", {"run": run.id, "lease_token": token})
        self.assertEqual((status, beat["cancel"]), (200, False))
        status, _ = self._post(
            "events",
            {"run": run.id, "lease_token": token, "events": [{"message": "thinking"}]},
        )
        self.assertEqual(status, 200)
        status, done = self._post(
            "complete",
            {
                "run": run.id,
                "lease_token": token,
                "result": {"answer": 42},
                "usage": {"input_tokens": 100, "output_tokens": 20, "cost": 0.5},
            },
        )
        self.assertEqual(
            (status, done), (200, {"state": "succeeded", "replayed": False})
        )
        self.assertEqual(run.run_state, "succeeded")
        self.assertTrue(self.runner.date_last_seen)

    def test_reported_spend_counts_once_against_the_runs_company(self):
        run = self._run()
        token = self._claim()["lease_token"]
        body = {"run": run.id, "lease_token": token, "usage": {"cost": 1.25}}
        before = self.env.company._ml_spend_this_month()
        self.assertEqual(self._post("complete", body)[1]["replayed"], False)
        self.assertEqual(self._post("complete", body)[1]["replayed"], True)
        self.assertAlmostEqual(self.env.company._ml_spend_this_month() - before, 1.25)
        [row, _replay] = self._exchanges("agent_complete").sorted("id")
        self.assertEqual(row.ml_cost, 1.25)
        self.assertEqual(row.user_id, self.env.ref("agent_runner.user_agent_runner"))

    def test_polling_leaves_no_rows(self):
        self._claim()
        self.assertFalse(self._exchanges("agent_claim"))

    def test_an_empty_queue_answers_no_run(self):
        self.assertIsNone(self._claim())

    def test_a_stale_lease_is_refused(self):
        run = self._run()
        self._claim()
        status, answer = self._post("complete", {"run": run.id, "lease_token": "stale"})
        self.assertEqual((status, answer), (409, {"error": "lease_lost"}))
        self.assertEqual(run.run_state, "leased")

    def test_a_run_this_runner_does_not_hold_answers_as_a_lost_lease(self):
        other = self._runner("other runner")
        held = self._run()
        self.env["agent.run"]._claim(other)
        for run_id in (held.id, 0, held.id + 1000):
            status, answer = self._post(
                "heartbeat", {"run": run_id, "lease_token": "x"}
            )
            self.assertEqual((status, answer), (409, {"error": "lease_lost"}))

    def test_a_failed_attempts_spend_counts_once(self):
        run = self._run(max_attempts=2)
        token = self._claim()["lease_token"]
        body = {
            "run": run.id,
            "lease_token": token,
            "error": "the agent gave no verdict",
            "retryable": True,
            "usage": {"input_tokens": 10, "cost": 0.75},
        }
        before = self.env.company._ml_spend_this_month()
        self.assertEqual(self._post("fail", body), (200, {"state": "queued"}))
        # queued again, the run is no longer this runner's: the replay is refused
        self.assertEqual(self._post("fail", body), (409, {"error": "lease_lost"}))
        self.assertAlmostEqual(self.env.company._ml_spend_this_month() - before, 0.75)
        self.assertEqual((run.cost, run.count_input_token), (0.75, 10))

    def test_credentials_that_cannot_be_prepared_do_not_wedge_the_runner(self):
        stuck = self._run("stuck", priority=50)
        waiting = self._run("waiting")
        Run = type(self.env["agent.run"])
        original = Run._prepare_credentials

        def unreachable(run):
            if run == stuck:
                raise ConnectionError("github is unreachable")
            return original(run)

        with patch.object(Run, "_prepare_credentials", unreachable):
            self.assertEqual(self._claim()["id"], waiting.id)
        self.assertEqual((stuck.run_state, stuck.count_attempt), ("queued", 0))
        self.assertIn("unreachable", stuck.error)

    def test_a_wrong_token_reaches_nothing(self):
        run = self._run()
        status, _answer = self._post("claim", token="not-a-runner")
        self.assertEqual(status, 404)
        self.assertEqual(run.run_state, "queued")

    def test_an_archived_runner_reaches_nothing(self):
        self._run()
        self.runner.active = False
        status, _answer = self._post("claim")
        self.assertEqual(status, 404)
