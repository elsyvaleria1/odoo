from unittest.mock import patch

from odoo.tests.common import TransactionCase, tagged

from .common import RunnerFixtures

PURPOSE = "agent_runner.test"


@tagged("post_install", "-at_install")
class TestModelCredentials(RunnerFixtures, TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Run = cls.env["agent.run"]
        cls.runner = cls._runner("credentials")
        cls.provider = cls.env.ref("integration_machine_learning.ai_provider_anthropic")

    def _key(self, value="sk-run"):
        return self.env["credential.credential"].create(
            {
                "name": "Runner model key",
                "category_id": self.env.ref(
                    "credential.credential_category_api_key"
                ).id,
                "endpoint_id": self.provider.endpoint_id.id,
                "company_id": self.env.company.id,
                "api_key": value,
            }
        )

    def _refuse(self):
        self.env["integration.ml.policy"].create(
            {
                "purpose_id": self.env["integration.ml.purpose"]
                ._get_or_create_by_key(PURPOSE)
                .id,
                "provider_ids": [],
            }
        )

    def test_a_run_calling_no_model_is_handed_no_key(self):
        self._key()
        self._run()
        self.assertEqual(self.Run._lease(self.runner)["credentials"], {})

    def test_a_run_is_handed_its_companys_model_key(self):
        self._key("sk-run")
        self._run(ml_purpose=PURPOSE)
        answer = self.Run._lease(self.runner)
        self.assertEqual(answer["credentials"], {"anthropic": {"api_key": "sk-run"}})

    def test_without_a_key_the_run_is_told_so(self):
        run = self._run(ml_purpose=PURPOSE)
        self.assertEqual(self.Run._lease(self.runner)["credentials"], {})
        self.assertTrue(
            any("No Anthropic credential" in m for m in run.event_ids.mapped("message"))
        )

    def test_a_run_its_policy_refuses_fails_and_the_next_one_is_leased(self):
        self._key()
        self._refuse()
        refused = self._run("refused", ml_purpose=PURPOSE, priority=20)
        allowed = self._run("allowed")
        answer = self.Run._lease(self.runner)
        self.assertEqual(answer["id"], allowed.id)
        self.assertEqual(refused.run_state, "failed")
        self.assertIn("data policy", refused.error)

    def test_a_refused_run_is_not_retried(self):
        self._key()
        self._refuse()
        refused = self._run(ml_purpose=PURPOSE, max_attempts=3)
        self.assertIsNone(self.Run._lease(self.runner))
        self.assertEqual((refused.run_state, refused.count_attempt), ("failed", 1))

    def test_credentials_that_cannot_be_prepared_requeue_the_run(self):
        run = self._run(ml_purpose=PURPOSE, max_attempts=2)
        Run = type(self.Run)
        with patch.object(
            Run, "_prepare_credentials", side_effect=ConnectionError("timed out")
        ):
            self.assertIsNone(self.Run._lease(self.runner))
            self.assertEqual((run.run_state, run.count_attempt), ("queued", 1))
            self.assertTrue(
                any("timed out" in m for m in run.event_ids.mapped("message"))
            )
            self.assertIsNone(self.Run._lease(self.runner))
        self.assertEqual((run.run_state, run.count_attempt), ("failed", 2))
