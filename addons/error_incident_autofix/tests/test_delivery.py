from datetime import timedelta
from unittest.mock import MagicMock, patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, new_test_user, tagged

from odoo.addons.agent_runner.tests.common import RunnerFixtures
from odoo.addons.error_incident.models.error_incident import capture_payload
from odoo.addons.error_incident_autofix.models import (
    error_incident_delivery as delivery,
)

DIFF = "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-broken\n+fixed\n"
REPOSITORY = "Agro-Marin/odoo"
HEAD = "a" * 40
MERGED = "b" * 40


def _defect():
    raise ValueError("delivery probe")


def _payload(user_id):
    try:
        _defect()
    except ValueError as exc:
        return capture_payload(exc, "request", user_id=user_id)
    raise AssertionError


@tagged("post_install", "-at_install")
class TestDelivery(RunnerFixtures, TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.ref("error_incident_autofix.policy_default").write(
            {"mode": "live", "min_occurrences": 2}
        )
        cls.employee = new_test_user(
            cls.env, "delivery.employee", groups="base.group_user"
        )
        cls.admin = new_test_user(cls.env, "delivery.admin", groups="base.group_system")
        cls.approver = new_test_user(
            cls.env,
            "delivery.approver",
            groups="base.group_user,error_incident_autofix.group_autofix_approver",
        )
        cls.sandbox = cls._runner("sandbox")
        cls.deployer = cls._runner("deployer", capabilities=("deploy",))

    def _occur(self):
        return self.env["error.incident"].browse(
            self.env["error.incident"]._capture(_payload(self.employee.id))
        )

    def _finish(self, runner, result, kind):
        run, token = self._claim_as_runner(runner)
        self.assertEqual(run.kind, kind)
        run._complete(
            token, result, {"input_tokens": 0, "output_tokens": 0, "cost": 0.0}
        )
        return run

    def _pushed(self, checks="none"):
        self._occur()
        incident = self._occur()
        self._finish(
            self.sandbox, {"verdict": "defect", "slug": "x"}, "error_incident.diagnose"
        )
        branch = incident.fix_branch
        self._finish(
            self.sandbox,
            {"verdict": "fixed", "diff": DIFF, "pushed": True, "branch": branch},
            "error_incident.fix",
        )
        self.assertEqual(incident.fix_state, "pushed")
        pull = self.env["integration.github.pull"]._upsert_from_github(
            REPOSITORY,
            {
                "number": 7,
                "title": "Fix x",
                "state": "open",
                "head": {
                    "ref": branch,
                    "sha": HEAD,
                    "repo": {"full_name": REPOSITORY},
                },
                "base": {"ref": "19.0-marin"},
            },
        )
        self.assertEqual(pull.incident_id, incident)
        if checks != "none":
            self._check(checks)
        return incident, pull

    def _check(self, conclusion):
        completed = conclusion != "pending"
        self.env["integration.github.check"]._record(
            REPOSITORY,
            "check_run:1",
            {
                "name": "ci",
                "head_sha": HEAD,
                "source": "check_run",
                "check_status": "completed" if completed else "in_progress",
                "conclusion": conclusion if completed else False,
            },
        )
        self.env["integration.github.pull"]._checks_moved(REPOSITORY, HEAD)

    def test_the_pull_requests_checks_drive_the_incident(self):
        incident, _pull = self._pushed()
        self.assertEqual(incident.fix_state, "testing")
        self._check("failure")
        self.assertEqual(incident.fix_state, "test_failed")
        self._check("success")
        self.assertEqual(incident.fix_state, "test_passed")

    def test_only_a_passing_fix_is_merged_or_hotfixed(self):
        incident, _pull = self._pushed(checks="failure")
        for action in ("action_autofix_merge", "action_autofix_hotfix"):
            with self.assertRaises(UserError):
                getattr(incident.with_user(self.admin), action)()
        self.assertFalse(incident.approval_request_id)

    def _merge_client(self):
        client = MagicMock()
        client.merge_pull_request.return_value = {"merged": True, "sha": MERGED}
        return patch.object(delivery, "get_github_client", return_value=client), client

    def test_a_merge_waits_for_its_approval_then_merges_that_commit(self):
        incident, _pull = self._pushed(checks="success")
        patcher, client = self._merge_client()
        with patcher:
            incident.with_user(self.admin).action_autofix_merge()
            request = incident.approval_request_id
            self.assertEqual(
                (request.operation, incident.fix_state), ("merge", "test_passed")
            )
            client.merge_pull_request.assert_not_called()
            request.with_user(self.approver).action_approve()
        client.merge_pull_request.assert_called_once_with(
            "Agro-Marin", "odoo", 7, merge_method="squash", sha=HEAD
        )
        self.assertEqual((incident.fix_state, incident.fix_commit), ("merged", MERGED))

    def test_an_approval_covers_the_commit_it_was_asked_for(self):
        incident, pull = self._pushed(checks="success")
        patcher, client = self._merge_client()
        with patcher:
            incident.with_user(self.admin).action_autofix_merge()
            pull.head_sha = "c" * 40
            incident.approval_request_id.with_user(self.approver).action_approve()
        client.merge_pull_request.assert_not_called()
        self.assertEqual(incident.fix_state, "test_passed")

    def test_a_merged_fix_is_resolved_once_production_runs_it(self):
        incident, _pull = self._pushed(checks="success")
        self._pull_merged()
        self.assertEqual((incident.fix_state, incident.fix_commit), ("merged", MERGED))
        Incident = self.env["error.incident"]
        Incident._cron_autofix_check_production()
        Incident._cron_autofix_check_production()
        run, token = self._claim_as_runner(self.deployer)
        self.assertEqual(run.kind, "error_incident.revision")
        self.assertEqual(run.payload, {"checkouts": {"odoo": [MERGED]}})
        self.assertFalse(self._claim_as_runner(self.deployer), "asked once")
        run._complete(
            token,
            {"revisions": {"odoo": "d" * 40}, "contained": []},
            {"input_tokens": 0, "output_tokens": 0, "cost": 0.0},
        )
        self.assertEqual(incident.fix_state, "merged", "not running yet")
        Incident._cron_autofix_check_production()
        self._finish(
            self.deployer,
            {"revisions": {"odoo": MERGED}, "contained": [MERGED]},
            "error_incident.revision",
        )
        self.assertEqual(
            (incident.fix_state, incident.incident_state), ("deployed", "resolved")
        )

    def _pull_merged(self):
        self.env["integration.github.pull"]._upsert_from_github(
            REPOSITORY,
            {
                "number": 7,
                "title": "Fix x",
                "state": "closed",
                "merged": True,
                "merge_commit_sha": MERGED,
                "head": {
                    "ref": self.env["error.incident"].search([], limit=1).fix_branch,
                    "sha": HEAD,
                    "repo": {"full_name": REPOSITORY},
                },
                "base": {"ref": "19.0-marin"},
            },
        )

    def test_an_approved_hotfix_reaches_production_and_resolves_the_incident(self):
        incident, pull = self._pushed(checks="success")
        incident.with_user(self.admin).action_autofix_hotfix()
        incident.approval_request_id.with_user(self.approver).action_approve()
        self.assertEqual((incident.fix_state, incident.fix_commit), ("hotfixing", HEAD))
        run, token = self._claim_as_runner(self.deployer)
        self.assertEqual(run.kind, "error_incident.hotfix")
        self.assertEqual(
            run.payload,
            {
                "checkout": "odoo",
                "repository": REPOSITORY,
                "branch": pull.head_ref,
                "base_branch": "19.0-marin",
                "commit": HEAD,
            },
        )
        self.assertEqual(
            run._github_permissions(), {"contents": "read", "metadata": "read"}
        )
        self.assertFalse(self._claim_as_runner(self.sandbox), "a sandbox never deploys")
        run._complete(
            token,
            {"revision": "e" * 40, "contained": [HEAD]},
            {"input_tokens": 0, "output_tokens": 0, "cost": 0.0},
        )
        self.assertEqual(
            (incident.fix_state, incident.incident_state), ("deployed", "resolved")
        )

    def test_a_reverted_hotfix_returns_the_fix_to_review(self):
        incident, _pull = self._pushed(checks="success")
        incident.with_user(self.admin).action_autofix_hotfix()
        incident.approval_request_id.with_user(self.approver).action_approve()
        run, token = self._claim_as_runner(self.deployer)
        run._fail(
            token, "reverted: the server did not come back healthy", retryable=False
        )
        self.assertEqual(incident.fix_state, "test_passed")
        self.assertTrue(
            any(
                "reverted" in (body or "")
                for body in incident.message_ids.mapped("body")
            )
        )

    def test_a_recurrence_after_the_fix_reopens_the_incident_with_its_history(self):
        incident, _pull = self._pushed(checks="success")
        self._pull_merged()
        self.env["error.incident"]._autofix_contained([MERGED])
        self.assertEqual(incident.incident_state, "resolved")
        self._occur()
        self.assertEqual(incident.incident_state, "regressed")
        self.assertEqual(incident.fix_state, "diagnosing")
        diagnosis = incident.fix_run_ids.filtered(
            lambda run: run.kind == "error_incident.diagnose"
        ).sorted("id")[-1]
        [previous] = diagnosis.payload["incident"]["previous_fixes"]
        self.assertEqual(previous["branch"], incident.fix_branch)

    def test_an_approval_is_spent_once_its_operation_ran(self):
        incident, _pull = self._pushed(checks="success")
        incident.with_user(self.admin).action_autofix_hotfix()
        incident.approval_request_id.with_user(self.approver).action_approve()
        run, token = self._claim_as_runner(self.deployer)
        run._fail(token, "reverted: unhealthy", retryable=False)
        self.assertEqual(incident.fix_state, "test_passed")
        self.assertFalse(incident.approval_request_id, "the approval is spent")
        incident.with_user(self.admin).action_autofix_hotfix()
        self.assertEqual(incident.fix_state, "test_passed", "a new decision")
        self.assertTrue(incident.approval_request_id)
        self.assertFalse(self._claim_as_runner(self.deployer))

    def test_an_earlier_fixs_pull_request_speaks_for_that_fix_only(self):
        incident, old = self._pushed(checks="failure")
        self.assertEqual(incident.fix_state, "test_failed")
        incident.with_user(self.admin).action_autofix_dispatch()
        self.assertEqual(incident.fix_state, "diagnosing")
        self.env["integration.github.pull"]._upsert_from_github(
            REPOSITORY,
            {
                "number": 7,
                "title": "Fix x",
                "state": "closed",
                "merged": True,
                "merge_commit_sha": MERGED,
                "head": {
                    "ref": old.head_ref,
                    "sha": HEAD,
                    "repo": {"full_name": REPOSITORY},
                },
                "base": {"ref": "19.0-marin"},
            },
        )
        self.assertEqual(incident.fix_state, "diagnosing")
        self.assertNotEqual(incident.fix_commit, MERGED)

    def test_a_pull_request_without_checks_passes_only_when_the_policy_says(self):
        incident, pull = self._pushed()
        self.assertEqual(incident.fix_state, "testing")
        self.env.ref(
            "error_incident_autofix.repository_odoo"
        ).pass_without_checks = True
        incident._autofix_pull_changed(pull)
        self.assertEqual(incident.fix_state, "test_passed")

    def test_an_approver_reads_only_the_incidents_put_to_them(self):
        decided, _pull = self._pushed(checks="success")
        other = self.env["error.incident"].create(
            {
                "name": "unrelated",
                "fingerprint": "unrelated-fp",
                "fix_analysis": "a@b.c",
            }
        )
        decided.with_user(self.admin).action_autofix_merge()
        Incident = self.env["error.incident"].with_user(self.approver)
        self.assertEqual(
            Incident.search([("id", "in", (decided | other).ids)]), decided
        )

    def test_production_is_asked_about_a_merged_fix_for_a_while_not_forever(self):
        incident, _pull = self._pushed(checks="success")
        self._pull_merged()
        self.assertTrue(incident.date_fix_merged)
        Incident = self.env["error.incident"]
        incident.date_fix_merged = fields.Datetime.now() - timedelta(days=31)
        Incident._cron_autofix_check_production()
        self.assertEqual(incident.fix_state, "not_deployed")
        self.assertIn("no longer asked", incident.message_ids[0].body)
        self.assertFalse(
            self.env["agent.run"].search([("kind", "=", "error_incident.revision")])
        )

    def test_an_approval_of_a_head_that_moved_is_asked_again(self):
        incident, pull = self._pushed(checks="success")
        patcher, client = self._merge_client()
        with patcher:
            incident.with_user(self.admin).action_autofix_merge()
            first = incident.approval_request_id
            pull.head_sha = "c" * 40
            first.with_user(self.approver).action_approve()
        client.merge_pull_request.assert_not_called()
        again = incident.approval_request_id
        self.assertNotEqual(again, first, "the moved head is asked about afresh")
        self.assertEqual(again.state, "pending")
        self.assertEqual(again.operation_snapshot["head"], "c" * 40)

    def test_a_push_while_asked_refuses_the_pending_approval(self):
        incident, pull = self._pushed(checks="success")
        incident.with_user(self.admin).action_autofix_merge()
        request = incident.approval_request_id
        self.env["integration.github.pull"]._upsert_from_github(
            REPOSITORY,
            {
                "number": 7,
                "title": "Fix x",
                "state": "open",
                "head": {
                    "ref": pull.head_ref,
                    "sha": "c" * 40,
                    "repo": {"full_name": REPOSITORY},
                },
                "base": {"ref": "19.0-marin"},
            },
        )
        self.assertFalse(incident.approval_request_id)
        self.assertEqual(request.state, "refused")

    def test_a_regression_while_a_hotfix_runs_leaves_the_hotfix_its_answer(self):
        incident, _pull = self._pushed(checks="success")
        incident.with_user(self.admin).action_autofix_hotfix()
        incident.approval_request_id.with_user(self.approver).action_approve()
        self.assertEqual(incident.fix_state, "hotfixing")
        incident.action_resolve()
        self._occur()
        self.assertEqual(incident.fix_state, "hotfixing", "a hotfix at work is live")

    def test_a_merge_while_a_hotfix_ran_is_followed_when_the_hotfix_fails(self):
        incident, _pull = self._pushed(checks="success")
        incident.with_user(self.admin).action_autofix_hotfix()
        incident.approval_request_id.with_user(self.approver).action_approve()
        self._pull_merged()
        self.assertEqual(incident.fix_state, "hotfixing", "the hotfix answers first")
        run, token = self._claim_as_runner(self.deployer)
        run._fail(token, "the fix does not apply", retryable=False)
        self.assertEqual((incident.fix_state, incident.fix_commit), ("merged", MERGED))
        self.assertTrue(incident.date_fix_merged)

    def test_a_recurrence_before_the_fix_ships_leaves_it_on_its_way(self):
        incident, _pull = self._pushed(checks="success")
        incident.with_user(self.admin).action_autofix_merge()
        request = incident.approval_request_id
        runs = len(incident.fix_run_ids)
        incident.action_resolve()
        self._occur()
        self.assertEqual(incident.incident_state, "regressed")
        self.assertEqual(incident.fix_state, "test_passed")
        self.assertEqual(
            (incident.approval_request_id, request.state), (request, "pending")
        )
        self.assertEqual(len(incident.fix_run_ids), runs, "nothing dispatched again")

    def test_a_push_after_its_approval_was_reset_cancels_the_draft(self):
        incident, pull = self._pushed(checks="success")
        incident.with_user(self.admin).action_autofix_merge()
        request = incident.approval_request_id
        request._force_draft()
        self.env["integration.github.pull"]._upsert_from_github(
            REPOSITORY,
            {
                "number": 7,
                "title": "Fix x",
                "state": "open",
                "head": {
                    "ref": pull.head_ref,
                    "sha": "c" * 40,
                    "repo": {"full_name": REPOSITORY},
                },
                "base": {"ref": "19.0-marin"},
            },
        )
        self.assertFalse(incident.approval_request_id)
        self.assertEqual(request.state, "cancelled", "not left in draft, unlinked")

    def test_a_pull_request_closed_on_github_refuses_its_pending_approval(self):
        incident, pull = self._pushed(checks="success")
        incident.with_user(self.admin).action_autofix_merge()
        request = incident.approval_request_id
        self.env["integration.github.pull"]._upsert_from_github(
            REPOSITORY,
            {
                "number": 7,
                "title": "Fix x",
                "state": "closed",
                "head": {
                    "ref": pull.head_ref,
                    "sha": HEAD,
                    "repo": {"full_name": REPOSITORY},
                },
                "base": {"ref": "19.0-marin"},
            },
        )
        self.assertEqual(incident.fix_state, "closed")
        self.assertFalse(incident.approval_request_id)
        self.assertEqual(request.state, "refused")
        self.assertIn("merged or closed on GitHub", request.refusal_note)
        self.assertNotIn(
            "cancelled", " ".join(incident.message_ids.mapped("body")).lower()
        )
