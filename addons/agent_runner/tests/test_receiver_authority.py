import importlib.util
from pathlib import Path
from unittest.mock import patch

from odoo import Command
from odoo.http import request
from odoo.libs.json import dumps as json_dumps
from odoo.tests.common import HttpCase, TransactionCase, new_test_user, tagged

from . import test_credentials
from .common import RunnerFixtures


@tagged("post_install", "-at_install")
class TestRunnerAuthority(RunnerFixtures, HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.principal = cls.env.ref("agent_runner.user_agent_runner")
        cls.runner = cls._runner("authority runner")
        cls.token = cls._token(cls.runner)

    def _post(self, verb, body=None):
        self.env.flush_all()
        response = self.url_open(
            f"/agent_runner/v1/{verb}",
            data=json_dumps(body or {}),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.token}",
            },
        )
        return response.status_code, response.json()

    def _lease_token(self, run):
        status, answer = self._post("claim")
        self.assertEqual((status, answer["run"]["id"]), (200, run.id))
        return answer["run"]["lease_token"]

    def _declared(self):
        return frozenset(
            self.env.ref(name).id
            for name in self.env["agent.runner"]._inbound_receiver_privileges()
        )

    def test_every_route_runs_as_the_principal_without_su(self):
        seen = []
        Runner = type(self.env["agent.runner"])
        touch = Runner._touch

        def spy(runner):
            seen.append(
                (
                    request.env.uid,
                    request.env.su,
                    runner.env.su,
                    request.env.privileges,
                    request.env.context.get("allowed_company_ids"),
                )
            )
            return touch(runner)

        done = self._run("done", priority=2)
        failed = self._run("failed", priority=1)
        with patch.object(Runner, "_touch", spy):
            token = self._lease_token(done)
            for verb, extra in (
                ("heartbeat", {}),
                ("events", {"events": [{"type": "progress", "message": "half"}]}),
                ("complete", {"result": {"answer": 42}}),
            ):
                status, _answer = self._post(
                    verb, {"run": done.id, "lease_token": token, **extra}
                )
                self.assertEqual(status, 200, verb)
            token = self._lease_token(failed)
            status, answer = self._post(
                "fail", {"run": failed.id, "lease_token": token, "error": "broken"}
            )
            self.assertEqual((status, answer), (200, {"state": "failed"}))

        self.assertEqual((done.run_state, failed.run_state), ("succeeded", "failed"))
        self.assertLessEqual(
            {
                self.env.ref("agent_runner.privilege_run_agent").id,
                self.env.ref("integration.privilege_keep_inbound_exchange").id,
            },
            self._declared(),
        )
        held = (
            self.principal.id,
            False,
            False,
            self._declared(),
            self.runner.company_id.ids,
        )
        self.assertEqual(seen, [held] * 6)

    def test_what_a_runner_reports_is_recorded_as_its_principal(self):
        run = self._run()
        token = self._lease_token(run)
        self._post(
            "events",
            {"run": run.id, "lease_token": token, "events": [{"message": "seen"}]},
        )
        self._post("complete", {"run": run.id, "lease_token": token})

        self.assertEqual((run.run_state, run.write_uid), ("succeeded", self.principal))
        self.assertIn("seen", run.event_ids.mapped("message"))
        self.assertEqual(
            run.message_ids.sorted("id")[-1].author_id, self.principal.partner_id
        )

    def test_a_run_ends_even_when_its_owner_cannot_be_told(self):
        # no module grants the runner anything on a contact
        owner = self.env["res.partner"].create({"name": "Hand-made run's owner"})
        run = self._run(res_model="res.partner", res_id=owner.id)
        token = self._lease_token(run)

        status, _body = self._post("complete", {"run": run.id, "lease_token": token})

        self.assertEqual(status, 200)
        self.assertEqual(run.run_state, "succeeded")
        self.assertIn(
            f"res.partner,{owner.id} was not told how this run ended",
            " ".join(run.event_ids.mapped("message")),
        )

    def test_an_archived_principal_is_refused(self):
        run = self._run()
        self.principal.active = False

        status, answer = self._post("claim")

        self.assertEqual((status, answer.get("error")), (403, "principal_unfit"))
        self.assertEqual(run.run_state, "queued")

    def test_a_principal_outside_the_runner_s_company_is_refused(self):
        other = self.env["res.company"].create({"name": "Unplaced runner company"})
        self.env.cr.execute(
            "UPDATE agent_runner SET company_id = %s WHERE id = %s",
            (other.id, self.runner.id),
        )
        self.runner.invalidate_recordset()
        self.assertNotIn(other, self.principal.company_ids)

        status, answer = self._post("claim")

        self.assertEqual((status, answer.get("error")), (403, "principal_unfit"))


@tagged("post_install", "-at_install")
class TestModelCredentialsAsRunner(test_credentials.TestModelCredentials):
    # every credentials case, leased in the environment a runner's call runs in
    allow_inherited_tests_method = True

    def setUp(self):
        super().setUp()
        self.Run = self._as_runner(self.runner).env["agent.run"]


@tagged("post_install", "-at_install")
class TestRunnerPlacement(RunnerFixtures, TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.principal = cls.env.ref("agent_runner.user_agent_runner")
        cls.other_company = cls.env["res.company"].create({"name": "Runner tenant"})

    def test_a_runner_of_another_company_puts_its_principal_there(self):
        administrator = new_test_user(
            self.env,
            login="tenant_runner_admin",
            groups="base.group_system",
            company_id=self.other_company.id,
            company_ids=[Command.set(self.other_company.ids)],
        )
        self.assertNotIn(self.other_company, self.principal.company_ids)

        self.env["agent.runner"].with_user(administrator).create(
            {"name": "tenant runner", "company_id": self.other_company.id}
        )

        self.assertIn(self.other_company, self.principal.company_ids)

    def test_the_upgrade_activates_the_principal_and_places_it(self):
        runner = self._runner("tenant runner")
        runner.company_id = self.other_company
        self.principal.write(
            {"active": False, "company_ids": [Command.unlink(self.other_company.id)]}
        )
        migration = (
            Path(__file__).parents[1] / "migrations" / "1.1.0" / "post-migrate.py"
        )
        spec = importlib.util.spec_from_file_location("agent_runner_1_1_0", migration)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        module.migrate(self.env.cr, "1.0.0")

        self.assertTrue(self.principal.active)
        self.assertIn(self.other_company, self.principal.company_ids)
