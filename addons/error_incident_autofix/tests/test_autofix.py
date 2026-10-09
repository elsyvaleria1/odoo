from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, new_test_user, tagged

from odoo.addons.agent_runner.tests.common import RunnerFixtures
from odoo.addons.error_incident.models.error_incident import capture_payload
from odoo.addons.error_incident_autofix.models import (
    error_incident_autofix_repository as repository,
)

DIFF = "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-broken\n+fixed\n"


def _defect():
    raise ValueError("autofix probe")


def _payload(user_id=None, **overrides):
    try:
        _defect()
    except ValueError as exc:
        payload = capture_payload(exc, "request", user_id=user_id)
    return payload | overrides


@tagged("post_install", "-at_install")
class TestAutofix(RunnerFixtures, TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.policy = cls.env.ref("error_incident_autofix.policy_default")
        cls.policy.write({"mode": "shadow", "min_occurrences": 2})
        cls.employee = new_test_user(
            cls.env, "autofix.employee", groups="base.group_user"
        )
        cls.runner = cls._runner("autofix runner")
        cls.Incident = cls.env["error.incident"]

    def _occur(self, times=1, **overrides):
        incident_id = None
        for _ in range(times):
            incident_id = self.Incident._capture(
                _payload(user_id=self.employee.id, **overrides)
            )
        return self.Incident.browse(incident_id)

    def _runs(self, incident, kind=None):
        runs = incident.fix_run_ids
        return runs.filtered(lambda run: run.kind == kind) if kind else runs

    def _finish(self, incident, result, kind):
        run, token = self._claim_as_runner(self.runner)
        self.assertEqual((run.kind, run.res_id), (kind, incident.id))
        run._complete(
            token, result, {"input_tokens": 1, "output_tokens": 1, "cost": 0.1}
        )
        return run

    def test_an_incident_meeting_the_policy_is_diagnosed(self):
        incident = self._occur(2)
        self.assertEqual(incident.fix_state, "diagnosing")
        [run] = self._runs(incident)
        self.assertEqual(run.kind, "error_incident.diagnose")
        self.assertEqual(run.github_repository, "Agro-Marin/odoo")
        payload = run.payload
        self.assertEqual(payload["prompt_version"], 1)
        self.assertEqual(payload["base_branch"], "19.0-marin")
        self.assertEqual(payload["incident"]["origin"]["function"], "_defect")
        self.assertIn("autofix probe", payload["incident"]["traceback"])
        self._occur()
        self.assertEqual(len(self._runs(incident)), 1, "one run at a time")

    def test_nothing_is_dispatched_below_the_policy(self):
        self.assertEqual(self._occur(1).fix_state, "none")

    def test_nothing_is_dispatched_with_the_autofix_off(self):
        self.policy.mode = "off"
        self.assertFalse(self._runs(self._occur(3)))

    def test_what_a_person_must_decide_is_not_dispatched(self):
        self.policy.excluded_exception_types = "ValueError"
        self.assertEqual(self._occur(3).fix_state, "none")

    def test_an_error_no_internal_user_hit_waits_for_a_person(self):
        incident_id = None
        for _ in range(3):
            incident_id = self.Incident._capture(_payload())
        self.assertEqual(self.Incident.browse(incident_id).fix_state, "none")

    def test_a_real_defect_is_handed_to_a_fix_run_that_proposes_in_shadow(self):
        incident = self._occur(2)
        self._finish(
            incident,
            {"verdict": "defect", "root_cause": "x is None", "slug": "none-guard"},
            "error_incident.diagnose",
        )
        self.assertEqual(incident.fix_state, "fixing")
        [fix] = self._runs(incident, "error_incident.fix")
        self.assertEqual(
            fix.payload["branch"], f"19.0-marin-fix-none-guard-i{incident.id}-a1"
        )
        self.assertFalse(fix.payload["push"], "shadow pushes nothing")
        self.assertEqual(fix.payload["diagnosis"]["root_cause"], "x is None")
        self._finish(
            incident,
            {"verdict": "fixed", "note": "guarded", "diff": DIFF},
            "error_incident.fix",
        )
        self.assertEqual(incident.fix_state, "proposed")
        self.assertEqual(incident.fix_diff, DIFF)
        self.assertIn("x is None", incident.fix_analysis)
        self.assertIn("guarded", incident.fix_analysis)
        self.assertAlmostEqual(incident.fix_cost, 0.2)

    def test_a_run_s_end_is_recorded_by_the_runner_s_principal(self):
        principal = self.env.ref("agent_runner.user_agent_runner")
        incident = self._occur(2)
        diagnosis = self._finish(
            incident,
            {"verdict": "defect", "root_cause": "x is None", "slug": "none-guard"},
            "error_incident.diagnose",
        )

        [fix] = self._runs(incident, "error_incident.fix")
        self.assertEqual(fix.create_uid, principal)
        self.assertEqual(
            (incident.fix_state, incident.write_uid), ("fixing", principal)
        )
        note = incident.message_ids.filtered(
            lambda message: diagnosis.name in (message.body or "")
        )
        self.assertEqual(note.author_id, principal.partner_id)
        audited = self.env["ir.access.log"].search(
            [
                ("event", "=", "privilege_used"),
                ("subject_user_id", "=", principal.id),
                ("model_name", "=", "error.incident"),
                ("operation", "=", "write"),
            ]
        )
        self.assertIn(
            self.env.ref("error_incident_autofix.privilege_report_agent_run"),
            audited.group_id,
        )

    def test_live_mode_pushes(self):
        self.policy.mode = "live"
        incident = self._occur(2)
        self._finish(
            incident, {"verdict": "defect", "slug": "x"}, "error_incident.diagnose"
        )
        self.assertTrue(self._runs(incident, "error_incident.fix").payload["push"])
        self._finish(
            incident,
            {"verdict": "fixed", "diff": DIFF, "pushed": True},
            "error_incident.fix",
        )
        self.assertEqual(incident.fix_state, "pushed")

    def test_each_verdict_rests_where_it_belongs(self):
        cases = (
            ({"verdict": "not_a_defect", "root_cause": "bad data"}, "not_a_defect"),
            ({"verdict": "maybe"}, "unclear"),
        )
        for result, state in cases:
            with self.subTest(state=state):
                incident = self._occur(2, fingerprint=state)
                self._finish(incident, result, "error_incident.diagnose")
                self.assertEqual(incident.fix_state, state)
                self.assertFalse(self._runs(incident, "error_incident.fix"))

    def test_a_fix_without_a_change_is_no_fix(self):
        incident = self._occur(2)
        self._finish(incident, {"verdict": "defect"}, "error_incident.diagnose")
        self._finish(incident, {"verdict": "fixed", "diff": "  "}, "error_incident.fix")
        self.assertEqual(incident.fix_state, "unchanged")

    def test_a_failed_run_says_so(self):
        incident = self._occur(2)
        run, token = self._claim_as_runner(self.runner)
        run._fail(token, "agent crashed", retryable=False)
        self.assertEqual(incident.fix_state, "failed")

    def test_a_data_policy_that_keeps_incidents_from_the_model_fails_the_run(self):
        self.env["integration.ml.policy"].create(
            {
                "purpose_id": self.env.ref(
                    "error_incident_autofix.purpose_error_incident_autofix"
                ).id,
                "provider_ids": [],
            }
        )
        incident = self._occur(2)
        self.assertEqual(self._runs(incident).ml_purpose, "error_incident.autofix")
        self.assertIsNone(self._lease_as_runner(self.runner))
        self.assertEqual(incident.fix_state, "failed")

    def test_the_daily_cap_holds(self):
        self.policy.daily_run_cap = 1
        first = self._occur(2, fingerprint="cap-a")
        second = self._occur(2, fingerprint="cap-b")
        self.assertEqual((first.fix_state, second.fix_state), ("diagnosing", "none"))

    def test_a_regression_is_diagnosed_again_with_the_fix_that_did_not_hold(self):
        incident = self._occur(2)
        self._finish(
            incident, {"verdict": "defect", "slug": "x"}, "error_incident.diagnose"
        )
        self._finish(
            incident,
            {"verdict": "fixed", "diff": DIFF, "note": "first try"},
            "error_incident.fix",
        )
        incident.action_resolve()
        self._occur()
        self.assertEqual(incident.incident_state, "regressed")
        self.assertEqual(
            (incident.fix_state, incident.count_fix_attempt), ("diagnosing", 0)
        )
        diagnosis = self._runs(incident, "error_incident.diagnose").sorted("id")[-1]
        [previous] = diagnosis.payload["incident"]["previous_fixes"]
        self.assertEqual(previous["analysis"], "first try")

    def test_fix_attempts_run_out(self):
        self.policy.max_attempts = 1
        incident = self._occur(2)
        self._finish(incident, {"verdict": "defect"}, "error_incident.diagnose")
        self._finish(incident, {"verdict": "unchanged"}, "error_incident.fix")
        with self.assertRaises(UserError):
            incident.action_autofix_dispatch()

    def test_a_person_dispatches_below_the_thresholds(self):
        incident = self._occur(1)
        incident.action_autofix_dispatch()
        self.assertEqual(incident.fix_state, "diagnosing")
        self.policy.mode = "off"
        with self.assertRaises(UserError):
            self._occur(1, fingerprint="off").action_autofix_dispatch()

    def test_a_diagnosis_reads_and_a_fix_writes(self):
        incident = self._occur(2)
        diagnosis = self._runs(incident)
        self.assertEqual(
            diagnosis._github_permissions(), {"contents": "read", "metadata": "read"}
        )
        self._finish(incident, {"verdict": "defect"}, "error_incident.diagnose")
        fix = self._runs(incident, "error_incident.fix")
        self.assertEqual(fix._github_permissions()["contents"], "write")

    def test_the_payload_carries_what_the_runner_reads(self):
        # tooling/agent_runner/incident.py: what each executor reads of
        # lease["payload"]; a key missing here fails the run on the runner.
        incident = self._occur(2)
        diagnosis = self._runs(incident).payload
        common = {"prompt", "model", "timeout", "repository", "base_branch", "incident"}
        self.assertLessEqual(common, diagnosis.keys())
        self.assertEqual(diagnosis["repository"], "Agro-Marin/odoo")
        self._finish(incident, {"verdict": "defect"}, "error_incident.diagnose")
        fix = self._runs(incident, "error_incident.fix").payload
        self.assertLessEqual(
            common | {"branch", "diagnosis", "push", "commit_author"}, fix.keys()
        )
        self.assertIn("id", fix["incident"])

    def _fixed_and_regressed(self):
        incident = self._occur(2)
        self._finish(
            incident, {"verdict": "defect", "slug": "x"}, "error_incident.diagnose"
        )
        self._finish(
            incident,
            {"verdict": "fixed", "diff": DIFF, "note": "first try"},
            "error_incident.fix",
        )
        incident.action_resolve()
        self._occur()
        return incident

    def test_a_regression_dispatches_once_not_at_every_occurrence(self):
        incident = self._fixed_and_regressed()
        self.assertEqual(len(self._runs(incident, "error_incident.diagnose")), 2)
        for _ in range(4):
            self._occur()
        self.assertEqual(len(self._runs(incident, "error_incident.diagnose")), 2)
        self.assertEqual(incident.fix_state, "diagnosing")

    def test_a_fix_after_a_regression_gets_a_branch_of_its_own(self):
        incident = self._fixed_and_regressed()
        first = self._runs(incident, "error_incident.fix").payload["branch"]
        self._finish(
            incident, {"verdict": "defect", "slug": "x"}, "error_incident.diagnose"
        )
        second = self._runs(incident, "error_incident.fix").sorted("id")[-1]
        self.assertNotEqual(second.payload["branch"], first)
        self.assertTrue(second.payload["branch"].endswith("-a2"))

    def test_an_overtaken_run_changes_nothing(self):
        incident = self._occur(2)
        stale, token = self._claim_as_runner(self.runner)
        incident.write({"fix_state": "none"})
        incident.action_autofix_dispatch()
        stale._complete(
            token,
            {"verdict": "not_a_defect"},
            {"input_tokens": 0, "output_tokens": 0, "cost": 0.0},
        )
        self.assertEqual(incident.fix_state, "diagnosing")

    def test_an_occurrence_refused_on_policy_does_not_ask_git(self):
        with patch.object(
            repository, "origin_url", wraps=repository.origin_url
        ) as origin_url:
            for fingerprint in ("rare-a", "rare-b", "rare-c"):
                self._occur(1, fingerprint=fingerprint)
        origin_url.assert_not_called()
