from unittest.mock import patch

import requests

from odoo.exceptions import RetryableJobError, TerminalJobError, UserError
from odoo.libs.netguard import UnresolvableDestination
from odoo.tests import TransactionCase, tagged

from odoo.addons.base.models.ir_job import IrJob


@tagged("post_install", "-at_install")
class TestWebhookDelivery(TransactionCase):
    def setUp(self):
        super().setUp()
        self.env["ir.config_parameter"].set_param(
            "base.egress_allowed_networks", "127.0.0.1/32"
        )
        self.partner = self.env["res.partner"].create({"name": "Original payload"})
        self.action = self.env["ir.actions.server"].create(
            {
                "name": "Durable webhook",
                "model_id": self.env["ir.model"]._get_id("res.partner"),
                "state": "webhook",
                "webhook_url": "http://127.0.0.1:9/original",
                "webhook_delivery": "queued",
                "webhook_field_ids": [
                    (6, 0, self.env["ir.model.fields"]._get("res.partner", "name").ids)
                ],
            }
        )

    def _enqueue(self):
        self.action.with_context(
            active_model="res.partner",
            active_id=self.partner.id,
            active_ids=self.partner.ids,
        ).run()
        return self.env["ir.job"].search(
            [
                ("method_name", "=", "_deliver_webhook_job"),
            ],
            order="id desc",
            limit=1,
        )

    def _claim(self):
        return IrJob._claim_next(self.cr, "webhook-test", channels=["base.webhook"])

    def _response(self, status):
        response = requests.Response()
        response.status_code = status
        return response

    def test_enqueue_persists_intent_without_sending(self):
        with patch.object(requests.Session, "post") as post:
            job = self._enqueue()
            post.assert_not_called()
        self.assertEqual(job.state, "pending")
        self.assertEqual(job.channel, "base.webhook")
        self.assertEqual(job.max_retries, 5)
        self.assertTrue(job.args[3])
        self.assertEqual(job.user_id, self.env.user)
        self.assertEqual(self.env.ref("base.job_channel_webhook").capacity, 2)

    def test_rollback_discards_the_intent(self):
        with self.assertRaises(RuntimeError), self.cr.savepoint():
            job = self._enqueue()
            job_id = job.id
            raise RuntimeError("roll back enqueue")
        self.assertFalse(self.env["ir.job"].browse(job_id).exists())

    def test_delivery_uses_frozen_payload_url_and_key(self):
        job = self._enqueue()
        original = list(job.args)
        self.partner.name = "Changed after enqueue"
        self.action.webhook_url = "http://127.0.0.1:9/changed"
        with patch.object(
            requests.Session, "post", return_value=self._response(204)
        ) as post:
            IrJob._run_claimed(self.cr, self._claim())
        args, kwargs = post.call_args
        self.assertEqual(args[0], original[0])
        self.assertEqual(kwargs["data"], original[2])
        self.assertIn("Original payload", kwargs["data"])
        self.assertEqual(kwargs["headers"]["Idempotency-Key"], original[3])
        self.assertFalse(kwargs["allow_redirects"])
        job.invalidate_recordset()
        self.assertEqual(job.state, "done")

    def test_retry_after_delivery_rollback_preserves_identity_and_payload(self):
        job = self._enqueue()
        claimed = self._claim()
        with patch.object(
            requests.Session, "post", return_value=self._response(200)
        ) as post:
            with self.assertRaises(RuntimeError), self.cr.savepoint():
                IrJob._run_claimed(self.cr, claimed)
                raise RuntimeError("crash before commit")
            IrJob._run_claimed(self.cr, claimed)
        self.assertEqual(post.call_count, 2)
        self.assertEqual(post.call_args_list[0], post.call_args_list[1])
        job.invalidate_recordset()
        self.assertEqual(job.state, "done")

    def test_transient_statuses_retry_and_rejections_fail_terminally(self):
        job = self._enqueue()
        for status, exception in [
            (408, RetryableJobError),
            (425, RetryableJobError),
            (429, RetryableJobError),
            (503, RetryableJobError),
            (302, TerminalJobError),
            (400, TerminalJobError),
            (401, TerminalJobError),
            (404, TerminalJobError),
        ]:
            with (
                self.subTest(status=status),
                patch.object(
                    requests.Session, "post", return_value=self._response(status)
                ),
                self.assertRaises(exception),
            ):
                self.action._deliver_webhook_job(*job.args)

    def test_network_failure_is_retried_without_exposing_the_url(self):
        job = self._enqueue()
        with patch.object(
            requests.Session, "post", side_effect=requests.ReadTimeout("secret-url")
        ):
            with self.assertRaises(RetryableJobError) as caught:
                self.action._deliver_webhook_job(*job.args)
        self.assertNotIn("secret-url", str(caught.exception))

    def test_delivery_rechecks_current_egress_policy(self):
        job = self._enqueue()
        self.env["ir.config_parameter"].set_param("base.egress_allowed_networks", "")
        with (
            patch.object(requests.Session, "post") as post,
            self.assertRaises(TerminalJobError),
        ):
            self.action._deliver_webhook_job(*job.args)
        post.assert_not_called()

    def test_distinct_action_executions_have_distinct_delivery_keys(self):
        first = self._enqueue()
        second = self._enqueue()
        self.assertNotEqual(first.args[3], second.args[3])

    def test_default_delivery_remains_once_after_commit(self):
        self.assertEqual(
            self.env["ir.actions.server"].default_get(["webhook_delivery"]),
            {"webhook_delivery": "once"},
        )

    def test_dns_outage_at_enqueue_retains_delivery_intent(self):
        with patch.object(
            type(self.env["ir.egress"]),
            "check_url",
            side_effect=UnresolvableDestination("Temporary DNS outage"),
        ):
            job = self._enqueue()
            self.assertEqual(job.state, "pending")
            with self.assertRaises(RetryableJobError):
                self.action._deliver_webhook_job(*job.args)
        with patch.object(requests.Session, "post", return_value=self._response(204)):
            IrJob._run_claimed(self.cr, self._claim())
        job.invalidate_recordset()
        self.assertEqual(job.state, "done")

    def test_once_delivery_still_rejects_dns_outage_at_enqueue(self):
        self.action.webhook_delivery = "once"
        with (
            patch.object(
                type(self.env["ir.egress"]),
                "check_url",
                side_effect=UnresolvableDestination("Temporary DNS outage"),
            ),
            self.assertRaises(UserError),
        ):
            self._enqueue()

    def test_queued_delivery_checks_policy_before_sending(self):
        self.env["ir.config_parameter"].set_param("base.egress_allowed_networks", "")
        with patch.object(requests.Session, "post") as post:
            job = self._enqueue()
            with self.assertRaises(TerminalJobError):
                self.action._deliver_webhook_job(*job.args)
        post.assert_not_called()

    def test_queued_delivery_rejects_invalid_url_before_enqueue(self):
        with self.assertRaises(UserError):
            self.action.webhook_url = "ftp://example.com/webhook"
            self._enqueue()
