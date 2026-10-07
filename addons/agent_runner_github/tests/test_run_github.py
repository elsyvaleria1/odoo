from unittest.mock import patch

from odoo.libs.json import dumps as json_dumps
from odoo.tests import TransactionCase, tagged

from odoo.addons.agent_runner.tests.common import RunnerFixtures
from odoo.addons.agent_runner_github.models import agent_run as github_run
from odoo.addons.integration_github.tools import InstallationToken

REPOSITORY = "Agro-Marin/agromarin"
BRANCH = "19.0-marin-change"


@tagged("post_install", "-at_install")
class TestRunCredentials(RunnerFixtures, TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.runner = cls._runner("github runner")

    def _app(self):
        return self.env["credential.credential"].create(
            {
                "name": "GitHub App",
                "category_id": self.env.ref(
                    "integration_github.credential_category_github_app"
                ).id,
                "credential_data": json_dumps(
                    {"app_id": "1", "private_key": "pem", "installation_id": "9"}
                ),
            }
        )

    def test_a_run_is_handed_a_token_for_its_repository_alone(self):
        app = self._app()
        self._run(github_repository=REPOSITORY)
        minted = InstallationToken("ghs_run", "2026-10-07T00:00:00Z", (REPOSITORY,))
        with patch.object(
            github_run, "mint_installation_token", return_value=minted
        ) as mint:
            run, token = self.env["agent.run"]._claim(self.runner)
            answer = run._lease_answer(token)
        mint.assert_called_once_with(
            self.env, app, ["agromarin"], github_run.RUN_PERMISSIONS
        )
        self.assertEqual(
            answer["credentials"]["github"],
            {
                "token": "ghs_run",
                "expires_at": "2026-10-07T00:00:00Z",
                "repository": REPOSITORY,
            },
        )

    def test_a_run_naming_no_repository_gets_no_token(self):
        self._app()
        self._run()
        with patch.object(github_run, "mint_installation_token") as mint:
            run, token = self.env["agent.run"]._claim(self.runner)
            self.assertNotIn("github", run._lease_answer(token)["credentials"])
        mint.assert_not_called()

    def test_without_an_app_the_run_is_told_it_has_no_token(self):
        self._run(github_repository=REPOSITORY)
        run, token = self.env["agent.run"]._claim(self.runner)
        self.assertNotIn("github", run._lease_answer(token)["credentials"])
        self.assertIn("No GitHub App", " ".join(run.event_ids.mapped("message")))


@tagged("post_install", "-at_install")
class TestRunPullLink(RunnerFixtures, TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.runner = cls._runner("linker")

    def _complete(self, branch=BRANCH):
        run = self._run(github_repository=REPOSITORY)
        claimed, token = self.env["agent.run"]._claim(self.runner)
        claimed._complete(
            token,
            {"branch": branch},
            {"input_tokens": 0, "output_tokens": 0, "cost": 0.0},
        )
        return run

    def _pull(self, branch=BRANCH):
        return self.env["integration.github.pull"]._upsert_from_github(
            REPOSITORY,
            {
                "number": 4,
                "title": "x",
                "state": "open",
                "head": {"ref": branch, "sha": "a" * 40},
            },
        )

    def test_a_run_reported_first_meets_its_pull_request(self):
        run = self._complete()
        pull = self._pull()
        self.assertEqual((run.github_pull_id, pull.agent_run_id), (pull, run))

    def test_a_pull_request_seen_first_meets_its_run(self):
        pull = self._pull()
        run = self._complete()
        self.assertEqual((run.github_pull_id, pull.agent_run_id), (pull, run))

    def test_another_branch_is_another_pull_request(self):
        run = self._complete()
        self._pull(branch="unrelated")
        self.assertFalse(run.github_pull_id)
