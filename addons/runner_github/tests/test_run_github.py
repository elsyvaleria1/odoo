from unittest.mock import patch

from odoo.libs.json import dumps as json_dumps
from odoo.tests import TransactionCase, tagged

from odoo.addons.integration_github.tools import InstallationToken
from odoo.addons.runner.tests.common import RunnerFixtures
from odoo.addons.runner_github.models import runner_job as github_run

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
            run, token = self._claim_as_runner(self.runner)
            answer = run._lease_answer(token)
        mint.assert_called_once()
        self.assertEqual(
            mint.call_args.args[1:], (app, ["agromarin"], github_run.RUN_PERMISSIONS)
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
            run, token = self._claim_as_runner(self.runner)
            self.assertNotIn("github", run._lease_answer(token)["credentials"])
        mint.assert_not_called()

    def test_a_token_that_does_not_reach_the_repository_is_refused(self):
        self._app()
        run = self._run(github_repository="other-owner/agromarin")
        minted = InstallationToken(
            "ghs_run", "2026-10-07T00:00:00Z", ("Agro-Marin/agromarin",)
        )
        with patch.object(github_run, "mint_installation_token", return_value=minted):
            self.assertIsNone(self._lease_as_runner(self.runner))
        self.assertEqual(run.job_state, "failed")
        self.assertIn("not installed on other-owner/agromarin", run.error)

    def test_without_an_app_the_run_is_told_it_has_no_token(self):
        self._run(github_repository=REPOSITORY)
        run, token = self._claim_as_runner(self.runner)
        self.assertNotIn("github", run._lease_answer(token)["credentials"])
        self.assertIn(
            "No GitHub App",
            " ".join(run.with_env(self.env).event_ids.mapped("message")),
        )


@tagged("post_install", "-at_install")
class TestRunPullLink(RunnerFixtures, TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.runner = cls._runner("linker")

    def _complete(self, branch=BRANCH, repository=REPOSITORY):
        run = self._run(github_repository=repository)
        claimed, token = self._claim_as_runner(self.runner)
        claimed._complete(
            token,
            {"branch": branch},
            {"input_tokens": 0, "output_tokens": 0, "cost": 0.0},
        )
        return run

    def _pull(self, branch=BRANCH, number=4, head_repository=REPOSITORY, **pr):
        return self.env["integration.github.pull"]._upsert_from_github(
            REPOSITORY,
            {
                "number": number,
                "title": "x",
                "state": "open",
                "head": {
                    "ref": branch,
                    "sha": "a" * 40,
                    "repo": {"full_name": head_repository},
                },
                **pr,
            },
        )

    def test_a_run_reported_first_meets_its_pull_request(self):
        run = self._complete()
        pull = self._pull()
        self.assertEqual((run.github_pull_id, pull.runner_job_id), (pull, run))

    def test_a_pull_request_seen_first_meets_its_run(self):
        pull = self._pull()
        run = self._complete()
        self.assertEqual((run.github_pull_id, pull.runner_job_id), (pull, run))

    def test_another_branch_is_another_pull_request(self):
        run = self._complete()
        self._pull(branch="unrelated")
        self.assertFalse(run.github_pull_id)

    def test_a_pull_request_from_a_fork_is_no_runs(self):
        run = self._complete()
        pull = self._pull(head_repository="stranger/agromarin")
        self.assertFalse(run.github_pull_id)
        self.assertFalse(pull.runner_job_id)
        self._complete(branch="other")
        self.assertFalse(pull.runner_job_id)

    def test_a_repository_is_one_whatever_its_case(self):
        run = self._complete(repository=REPOSITORY.lower())
        pull = self._pull()
        self.assertEqual(pull.runner_job_id, run)

    def test_a_later_run_on_the_same_branch_leaves_the_earlier_pull_alone(self):
        first = self._complete()
        earlier = self._pull(state="closed", merged=True)
        self.assertEqual(earlier.runner_job_id, first)
        second = self._complete()
        self.assertEqual(earlier.runner_job_id, first)
        self.assertFalse(second.github_pull_id)
        newer = self._pull(number=5)
        self.assertEqual((newer.runner_job_id, second.github_pull_id), (second, newer))
