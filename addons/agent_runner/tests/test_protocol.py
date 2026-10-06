from odoo.tests.common import TransactionCase, tagged

from .common import RunnerFixtures
from odoo.addons.agent_runner.models.agent_run import LeaseLost


@tagged("post_install", "-at_install")
class TestProtocol(RunnerFixtures, TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Run = cls.env["agent.run"]
        cls.first = cls._runner("first")
        cls.second = cls._runner("second")

    def _usage(self, cost=0.0):
        return {"input_tokens": 10, "output_tokens": 5, "cost": cost}

    def test_the_most_urgent_run_of_its_capability_is_leased(self):
        self._run("low", priority=1)
        urgent = self._run("urgent", priority=50)
        self._run("deploy", capability="deploy", priority=99)
        run, token = self.Run._claim(self.first)
        self.assertEqual(run, urgent)
        self.assertEqual(run.run_state, "leased")
        self.assertEqual(run.runner_id, self.first)
        self.assertEqual(run.count_attempt, 1)
        self.assertTrue(run._holds(token))
        self.assertFalse(run._holds("another"))

    def test_a_runner_holds_no_more_than_its_concurrency(self):
        self._run("a")
        second_run = self._run("b")
        self.assertTrue(self.Run._claim(self.first))
        self.assertIsNone(self.Run._claim(self.first))
        run, _token = self.Run._claim(self.second)
        self.assertEqual(run, second_run)

    def test_nothing_is_leased_twice(self):
        self._run("only")
        self.assertTrue(self.Run._claim(self.first))
        self.assertIsNone(self.Run._claim(self.second))

    def test_a_company_over_its_budget_is_handed_no_work(self):
        self._run("costly")
        self.env.company.ml_config_id.ml_monthly_budget = 5
        self._spend(self.first, 5)
        self.assertIsNone(self.Run._claim(self.first))
        self.env.company.ml_config_id.ml_monthly_budget = 10
        self.assertTrue(self.Run._claim(self.first))

    def test_a_heartbeat_starts_the_run_and_extends_its_lease(self):
        self._run()
        run, token = self.Run._claim(self.first)
        leased_until = run.date_lease_until
        self._expire(run)
        self.assertEqual(
            run._heartbeat(token),
            {"cancel": False, "lease_seconds": run._lease_seconds()},
        )
        self.assertEqual(run.run_state, "running")
        self.assertTrue(run.date_started)
        self.assertGreaterEqual(run.date_lease_until, leased_until)
        with self.assertRaises(LeaseLost):
            run._heartbeat("not the lease")

    def test_completion_is_idempotent(self):
        self._run()
        run, token = self.Run._claim(self.first)
        self.assertTrue(run._complete(token, {"answer": 42}, self._usage(0.25)))
        self.assertEqual(run.run_state, "succeeded")
        self.assertEqual(run.result, {"answer": 42})
        self.assertEqual(run.cost, 0.25)
        self.assertFalse(run._complete(token, {"answer": 0}, self._usage(9)))
        self.assertEqual(run.result, {"answer": 42}, "a replay changes nothing")
        self.assertEqual(run.cost, 0.25)

    def test_a_lost_lease_cannot_finish_the_run(self):
        self._run(max_attempts=2)
        run, stale = self.Run._claim(self.first)
        self._expire(run)
        self.Run._reap_expired_leases()
        run, fresh = self.Run._claim(self.second)
        with self.assertRaises(LeaseLost):
            run._complete(stale, {}, self._usage())
        self.assertTrue(run._complete(fresh, {}, self._usage()))
        self.assertEqual(run.runner_id, self.second)

    def test_a_cancelled_run_tells_its_runner_to_stop(self):
        self._run()
        run, token = self.Run._claim(self.first)
        run.action_cancel()
        self.assertEqual(run._heartbeat(token), {"cancel": True})
        with self.assertRaises(LeaseLost):
            run._complete(token, {}, self._usage())

    def test_a_retryable_failure_is_queued_again_until_its_attempts_run_out(self):
        self._run(max_attempts=2)
        run, token = self.Run._claim(self.first)
        self.assertEqual(run._fail(token, "flaky", retryable=True), "queued")
        self.assertEqual(run._fail(token, "flaky", retryable=True), "queued", "replay")
        run, token = self.Run._claim(self.first)
        self.assertEqual(run._fail(token, "flaky again", retryable=True), "failed")
        self.assertEqual(run.error, "flaky again")
        self.assertTrue(run.date_finished)

    def test_a_final_failure_is_not_retried(self):
        self._run()
        run, token = self.Run._claim(self.first)
        self.assertEqual(run._fail(token, "broken", retryable=False), "failed")

    def test_an_expired_lease_is_handed_out_again_then_failed(self):
        run = self._run(max_attempts=2)
        for _attempt in (1, 2):
            claimed, _token = self.Run._claim(self.first)
            self.assertEqual(claimed, run)
            self._expire(run)
            self.assertEqual(self.Run._reap_expired_leases(), 1)
        self.assertEqual(run.run_state, "failed")
        self.assertEqual(run.count_attempt, 2)
        self.assertIn("expired", " ".join(run.event_ids.mapped("message")))
        self.assertEqual(self.Run._reap_expired_leases(), 0)

    def test_a_live_lease_is_not_reaped(self):
        self._run()
        self.Run._claim(self.first)
        self.assertEqual(self.Run._reap_expired_leases(), 0)

    def test_events_are_appended_masked_and_typed(self):
        self._run()
        run, token = self.Run._claim(self.first)
        accepted = run._append_events(
            token,
            [
                {"type": "progress", "message": "half way", "data": {"done": 5}},
                {"type": "nonsense", "message": "password=hunter2"},
                "not an event",
            ],
        )
        self.assertEqual(accepted, 2)
        progress, other = run.event_ids.filtered(lambda e: e.event_type != "system")
        self.assertEqual(
            (progress.event_type, progress.data), ("progress", {"done": 5})
        )
        self.assertEqual(other.event_type, "info")
        self.assertNotIn("hunter2", other.message)

    def test_the_record_it_works_for_hears_how_it_ended(self):
        partner = self.env["res.partner"].create({"name": "Owner"})
        self._run("for the partner", res_model="res.partner", res_id=partner.id)
        run, token = self.Run._claim(self.first)
        run._complete(token, {}, self._usage())
        self.assertIn("for the partner: Succeeded.", partner.message_ids[0].body)

    def test_retry_queues_an_ended_run_afresh(self):
        self._run(max_attempts=1)
        run, token = self.Run._claim(self.first)
        run._fail(token, "broken", retryable=True)
        self.assertEqual(run.run_state, "failed")
        run.action_retry()
        self.assertEqual((run.run_state, run.count_attempt), ("queued", 0))
