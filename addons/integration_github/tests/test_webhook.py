import uuid
from unittest.mock import patch

from odoo.tests import HttpCase, tagged

from .common import WebhookDelivery, fixture

REPOSITORY = "Codertocat/Hello-World"
HEAD = "ec26c3e57ca3a959ca5aad62de7213c562f8c821"


@tagged("post_install", "-at_install", "integration_github", "github")
class TestWebhook(WebhookDelivery, HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._create_hook()

    def _pull(self):
        return self.env["integration.github.pull"].search(
            [("repository", "=", REPOSITORY), ("number", "=", 2)]
        )

    def test_a_pull_request_and_its_checks_are_followed_to_the_merge(self):
        response = self._deliver("pull_request", fixture("pull_request__opened"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(), {"event": "pull_request", "outcome": "pull_request"}
        )
        pull = self._pull()
        self.assertEqual(
            (pull.pull_state, pull.head_ref, pull.head_sha, pull.base_ref),
            ("open", "changes", HEAD, "master"),
        )
        self.assertEqual(pull.checks_state, "none")

        self._deliver("check_run", fixture("check_run__created"))
        self.assertEqual(pull.checks_state, "pending")

        failed = fixture("check_run__completed_failure")
        self._deliver("check_run", failed)
        self.assertEqual(pull.checks_state, "failure")

        rerun = fixture("check_run__completed_success")
        rerun["check_run"]["id"] = failed["check_run"]["id"]
        self._deliver("check_run", rerun)
        created = fixture("check_run__created")
        created["check_run"].update(status="completed", conclusion="success")
        self._deliver("check_run", created)
        self.assertEqual(pull.checks_state, "success")

        closed = fixture("pull_request__closed")
        closed["pull_request"].update(
            merged=True,
            merged_at="2019-05-15T15:20:41Z",
            merge_commit_sha="c4295bd74fb0f4fda03689c3df3f2803b658fd85",
        )
        self._deliver("pull_request", closed)
        self.assertEqual(pull.pull_state, "merged")
        self.assertEqual(
            pull.merge_commit_sha, "c4295bd74fb0f4fda03689c3df3f2803b658fd85"
        )
        self.assertEqual(len(self._pull()), 1, "the same pull request, not another")

    def test_a_workflow_run_and_a_status_are_checks_of_the_head(self):
        self._deliver("pull_request", fixture("pull_request__opened"))
        run = fixture("workflow_run__completed")
        run["repository"]["full_name"] = REPOSITORY
        run["workflow_run"]["head_sha"] = HEAD
        self._deliver("workflow_run", run)
        pull = self._pull()
        self.assertEqual(pull.checks_state, "success")
        status = fixture("status")
        status.update(repository={"full_name": REPOSITORY}, sha=HEAD, state="pending")
        self._deliver("status", status)
        self.assertEqual(pull.checks_state, "pending")
        status["state"] = "error"
        self._deliver("status", status)
        self.assertEqual(pull.checks_state, "failure")
        self.assertEqual(
            sorted(pull.check_ids.mapped("source")), ["status", "workflow_run"]
        )

    def test_a_new_head_starts_its_checks_afresh(self):
        self._deliver("pull_request", fixture("pull_request__opened"))
        self._deliver("check_run", fixture("check_run__completed_failure"))
        pushed = fixture("pull_request__synchronize")
        pushed["pull_request"]["head"]["sha"] = "1" * 40
        self._deliver("pull_request", pushed)
        pull = self._pull()
        self.assertEqual((pull.head_sha, pull.checks_state), ("1" * 40, "none"))

    def test_followers_hear_of_each_change(self):
        Pull = type(self.env["integration.github.pull"])
        with patch.object(Pull, "_github_updated", autospec=True) as updated:
            self._deliver("pull_request", fixture("pull_request__opened"))
            self._deliver("check_run", fixture("check_run__created"))
            self._deliver("check_run", fixture("check_run__created"))
        self.assertEqual(
            updated.call_count, 2, "a check that changes nothing is no news"
        )

    def test_a_redelivery_is_refused_as_a_duplicate(self):
        delivery = str(uuid.uuid4())
        self.assertEqual(
            self._deliver("ping", {"zen": "x"}, delivery=delivery).status_code, 200
        )
        self.assertEqual(
            self._deliver("ping", {"zen": "x"}, delivery=delivery).status_code, 409
        )

    def test_a_delivery_signed_with_another_secret_is_refused(self):
        response = self._deliver(
            "pull_request", fixture("pull_request__opened"), secret="not-it"
        )
        self.assertGreaterEqual(response.status_code, 400)
        self.assertFalse(self._pull())

    def test_an_unknown_hook_answers_not_found(self):
        stray = self.env["integration.github.webhook"].new({"hook_uuid": "0" * 32})
        self.assertEqual(self._deliver("ping", {}, hook=stray).status_code, 404)

    def test_events_nobody_follows_are_acknowledged_and_ignored(self):
        for event in ("star", "check_suite", "../etc"):
            response = self._deliver(event, fixture("check_suite__completed"))
            self.assertEqual(
                (response.status_code, response.json()["outcome"]), (200, "ignored")
            )
        self.assertEqual(self._deliver("ping", {"zen": "x"}).json()["outcome"], "pong")
