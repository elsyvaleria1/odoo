from unittest.mock import patch

from odoo.libs.json import dumps as json_dumps
from odoo.tests import HttpCase, TransactionCase, tagged

from odoo.addons.agent_runner.tests.common import RunnerFixtures
from odoo.addons.error_incident.models.error_incident import capture_payload
from odoo.addons.error_incident_github.models import agent_run as github_run
from odoo.addons.integration_github.tests.common import WebhookDelivery, fixture
from odoo.addons.integration_github.tools import InstallationToken

REPOSITORY = "Agro-Marin/agromarin"
BRANCH = "19.0-marin-fix-incident"


def _incident(env):
    try:
        raise ValueError("github link")
    except ValueError as exc:
        payload = capture_payload(exc, "request")
    return env["error.incident"].browse(env["error.incident"]._capture(payload))


def _usage():
    return {"input_tokens": 0, "output_tokens": 0, "cost": 0.0}


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
class TestPullLinking(RunnerFixtures, WebhookDelivery, HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._create_hook()
        cls.runner = cls._runner("fixer")
        cls.incident = _incident(cls.env)

    def _fixing_run(self):
        return self._run(
            "fix",
            github_repository=REPOSITORY,
            res_model="error.incident",
            res_id=self.incident.id,
        )

    def _complete(self, run, branch=BRANCH):
        claimed, token = self.env["agent.run"]._claim(self.runner)
        self.assertEqual(claimed, run)
        run._complete(token, {"branch": branch}, _usage())

    def _pull_request(self, action, branch=BRANCH, **pull):
        payload = fixture(f"pull_request__{action}")
        payload["repository"]["full_name"] = REPOSITORY
        payload["pull_request"]["head"]["ref"] = branch
        payload["pull_request"].update(pull)
        return payload

    def _notes(self):
        return self.incident.message_ids.mapped("body")

    def test_the_pull_request_of_the_runs_branch_reaches_its_incident(self):
        run = self._fixing_run()
        self._complete(run)
        self.assertEqual(run.github_branch, BRANCH)
        self._deliver("pull_request", self._pull_request("opened"))
        pull = run.github_pull_id
        self.assertTrue(pull)
        self.assertEqual((pull.agent_run_id, pull.incident_id), (run, self.incident))
        self.assertEqual(self.incident.pull_ids, pull)
        self.assertTrue(any("is open" in note for note in self._notes()))

    def test_a_pull_request_seen_first_is_linked_when_the_run_reports(self):
        self._deliver("pull_request", self._pull_request("opened"))
        run = self._fixing_run()
        self._complete(run)
        self.assertEqual(run.github_pull_id.incident_id, self.incident)

    def test_the_incident_hears_each_change_once(self):
        run = self._fixing_run()
        self._complete(run)
        self._deliver("pull_request", self._pull_request("opened"))
        failure = fixture("check_run__completed_failure")
        failure["repository"]["full_name"] = REPOSITORY
        failure["check_run"]["head_sha"] = run.github_pull_id.head_sha
        self._deliver("check_run", failure)
        self._deliver("check_run", failure)
        self._deliver(
            "pull_request",
            self._pull_request("closed", merged=True, merged_at="2026-10-06T22:00:00Z"),
        )
        notes = self._notes()
        self.assertEqual(sum("fail" in note for note in notes), 1)
        self.assertEqual(sum("was merged" in note for note in notes), 1)

    def test_a_pull_request_of_another_branch_is_not_the_incidents(self):
        run = self._fixing_run()
        self._complete(run)
        self._deliver("pull_request", self._pull_request("opened", branch="unrelated"))
        self.assertFalse(run.github_pull_id)
        self.assertFalse(self.incident.pull_ids)
