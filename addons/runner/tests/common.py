from datetime import timedelta

from odoo import fields


class RunnerFixtures:
    @classmethod
    def _runner(cls, name, capabilities=("sandbox",), concurrency=1):
        return cls.env["runner.machine"].create(
            {
                "name": name,
                "concurrency": concurrency,
                "capability_ids": [
                    (
                        6,
                        0,
                        [
                            cls.env.ref(f"runner.capability_{c}").id
                            for c in capabilities
                        ],
                    )
                ],
            }
        )

    @classmethod
    def _token(cls, runner):
        action = runner.action_issue_token()
        return action["params"]["message"].split("\n", 1)[0]

    @classmethod
    def _run(cls, name="probe", capability="sandbox", **vals):
        return cls.env["runner.job"].create(
            {
                "name": name,
                "kind": "probe",
                "capability_id": cls.env.ref(f"runner.capability_{capability}").id,
                **vals,
            }
        )

    @classmethod
    def _as_runner(cls, runner):
        env = runner._inbound_principal_env(cls.env, runner._inbound_service_user())
        return runner.with_env(env)

    def _claim_as_runner(self, runner):
        runner = self._as_runner(runner)
        return runner.env["runner.job"]._claim(runner)

    def _lease_as_runner(self, runner):
        runner = self._as_runner(runner)
        return runner.env["runner.job"]._lease(runner)

    def _expire(self, run):
        run.date_lease_until = fields.Datetime.now() - timedelta(seconds=1)

    def _spend(self, runner, cost, company=None):
        self.env["integration.exchange"].create(
            {
                "direction": "inbound",
                "channel_id": f"runner.machine,{runner.id}",
                "company_id": (company or self.env.company).id,
                "ml_cost": cost,
            }
        )
