from odoo.exceptions import UserError
from odoo.tests.common import HttpCase, TransactionCase, tagged


def _raise(exc):
    raise exc


@tagged("post_install", "-at_install")
class TestScheduledActionFailure(TransactionCase):
    def _cron(self, code):
        return self.env["ir.cron"].create(
            {
                "name": "Incident Probe",
                "model_id": self.env.ref("base.model_res_partner").id,
                "state": "code",
                "code": code,
            }
        )

    def test_a_failing_scheduled_action_is_an_incident(self):
        cron = self._cron("1 / 0")
        cron.method_direct_trigger()
        incident = self.env["error.incident"].search([("source", "=", "cron")])
        self.assertEqual(len(incident), 1)
        self.assertEqual(incident.exception_type, "ZeroDivisionError")
        self.assertEqual(incident.occurrence_ids.location, "Incident Probe")

    def test_a_refusal_raised_for_the_user_is_not(self):
        cron = self._cron("raise UserError('not allowed')")
        cron.method_direct_trigger()
        self.assertFalse(self.env["error.incident"].search([("source", "=", "cron")]))


@tagged("post_install", "-at_install")
class TestBackgroundJobFailure(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = cls.env["res.users"].create(
            {"name": "Job Owner", "login": "job.owner@example.com"}
        )

    def _job(self):
        return {
            "id": 0,
            "model_name": "res.partner",
            "method_name": "_x",
            "user_id": self.user.id,
        }

    def _exception(self, exc):
        try:
            _raise(exc)
        except Exception as caught:
            return caught
        raise AssertionError

    def test_a_job_that_fails_for_good_is_an_incident(self):
        IrJob = type(self.env["ir.job"])
        IrJob._notify_failed(self.env.cr, self._job(), self._exception(KeyError("k")))
        incident = self.env["error.incident"].search([("source", "=", "job")])
        self.assertEqual(incident.exception_type, "KeyError")
        self.assertEqual(incident.occurrence_ids.location, "res.partner._x")
        self.assertEqual(incident.user_ids, self.user)

    def test_a_terminal_refusal_is_not(self):
        IrJob = type(self.env["ir.job"])
        IrJob._notify_failed(self.env.cr, self._job(), self._exception(UserError("u")))
        self.assertFalse(self.env["error.incident"].search([("source", "=", "job")]))


@tagged("post_install", "-at_install")
class TestRequestFailure(HttpCase):
    def _call(self, route, params):
        return self.url_open(route, json=self.prepare_rpc_payload(params)).json()

    def test_the_error_names_its_incident_and_the_incident_is_recorded(self):
        self.authenticate("admin", "admin")
        answer = self._call(
            "/web/dataset/call_kw/res.partner/search",
            {
                "model": "res.partner",
                "method": "search",
                "args": [[["no_such_field", "=", 1]]],
                "kwargs": {},
            },
        )
        data = answer["error"]["data"]
        self.assertEqual(data["name"], "builtins.ValueError")
        named = data["context"]["error_incident"]
        incident = self.env["error.incident"].search(
            [("fingerprint", "=", named["fingerprint"])]
        )
        self.assertEqual(len(incident), 1)
        self.assertEqual(incident.source, "request")
        occurrence = incident.occurrence_ids
        self.assertEqual(occurrence.occurrence_ref, named["occurrence"])
        self.assertIn("/web/dataset/call_kw/res.partner/search", occurrence.location)
        self.assertEqual(occurrence.user_id, self.env.ref("base.user_admin"))
        self.assertTrue(occurrence.request_ref)

    def test_an_error_raised_for_the_user_carries_no_incident(self):
        self.env["res.users"].create(
            {
                "name": "Plain",
                "login": "plain.incident",
                "password": "plain.incident",
                "group_ids": [(6, 0, [self.env.ref("base.group_user").id])],
            }
        )
        self.authenticate("plain.incident", "plain.incident")
        answer = self._call(
            "/web/dataset/call_kw/ir.config_parameter/search_read",
            {
                "model": "ir.config_parameter",
                "method": "search_read",
                "args": [[]],
                "kwargs": {},
            },
        )
        self.assertEqual(answer["error"]["data"]["name"], "odoo.exceptions.AccessError")
        self.assertNotIn("error_incident", answer["error"]["data"].get("context") or {})
