from unittest.mock import patch

from odoo.exceptions import RetryableJobError, TerminalJobError, ValidationError
from odoo.libs import netguard
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger

from odoo.addons.integration.models.ir_actions_server import _EndpointDelivery
from odoo.addons.integration.tests.common import revealed

_MODULE = "odoo.addons.integration.models.ir_actions_server"


@tagged("post_install", "-at_install")
class TestWebhookActionEndpoint(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.model = cls.env["ir.model"]._get("res.partner")
        cls.partner = cls.env["res.partner"].create({"name": "webhook target"})
        cls.endpoint = cls.env["integration.service"].create(
            {
                "name": "receiver",
                "code": "wh_receiver",
                "endpoint_url": "https://example.com",
                "auth_type": "bearer",
                "retry_enabled": False,
            }
        )
        cls.env["credential.credential"].create(
            {
                "name": "receiver token",
                "endpoint_id": cls.endpoint.id,
                "category_id": cls.env.ref("credential.credential_category_custom").id,
                "bearer_token": "SECRETTOKEN",
            }
        )

    def _action(self, **vals):
        return self.env["ir.actions.server"].create(
            {
                "name": "notify",
                "model_id": self.model.id,
                "state": "webhook",
                "webhook_url": "https://example.com/hook",
                **vals,
            }
        )

    def test_without_an_endpoint_base_still_posts_directly(self):
        action = self._action()
        deliver = action._prepare_webhook_delivery(
            "https://example.com/hook", 1, "n(#1)", "x"
        )
        self.assertNotIsInstance(deliver, _EndpointDelivery)

    def test_the_delivery_holds_no_recordset(self):
        action = self._action(webhook_endpoint_id=self.endpoint.id)
        deliver = action._prepare_webhook_delivery(
            "https://example.com/hook", 5, "n(#1)", "x"
        )

        self.assertIsInstance(deliver, _EndpointDelivery)
        for name, value in vars(deliver).items():
            with self.subTest(attribute=name):
                self.assertIsInstance(
                    value,
                    (str, int, type(None), netguard.Policy),
                    f"{name} is a {type(value).__name__}; only plain values may "
                    f"cross into the postcommit hook",
                )

    def test_it_captures_what_the_client_will_need(self):
        action = self._action(webhook_endpoint_id=self.endpoint.id)
        deliver = action._prepare_webhook_delivery(
            "https://example.com/hook", 7, "n(#1)", "x"
        )

        self.assertEqual(deliver.endpoint_code, "wh_receiver")
        self.assertEqual(deliver.dbname, self.env.cr.dbname)
        self.assertEqual(deliver.company_id, self.env.company.id)
        self.assertEqual(deliver.uid, self.env.uid)
        self.assertEqual(deliver.timeout, 7)

    @mute_logger(_MODULE)
    def test_the_delivery_opens_its_own_cursor(self):
        action = self._action(webhook_endpoint_id=self.endpoint.id)
        deliver = action._prepare_webhook_delivery(
            "https://example.com/hook", 5, "n(#1)", "x"
        )

        with patch(f"{_MODULE}.Registry") as registry:
            deliver('{"a": 1}')

        registry.assert_called_once_with(self.env.cr.dbname)
        registry.return_value.cursor.assert_called_once()

    def test_the_request_carries_the_endpoint_credential(self):
        action = self._action(webhook_endpoint_id=self.endpoint.id)
        deliver = action._prepare_webhook_delivery(
            "https://example.com/hook", 5, "n(#1)", "x"
        )

        sent = {}

        def fake_request(method, url, headers=None, **kwargs):
            sent.update(method=method, url=url, headers=headers or {}, kwargs=kwargs)
            raise RuntimeError("stop before the network")

        with (
            patch(f"{_MODULE}.Registry") as registry,
            patch("requests.Session.request", side_effect=fake_request),
            mute_logger(_MODULE),
        ):
            registry.return_value.cursor.return_value.__enter__.return_value = (
                self.env.cr
            )
            deliver('{"a": 1}')

        self.assertEqual(sent["method"], "POST")
        self.assertEqual(
            sent["url"],
            "https://example.com/hook",
            "the action still owns where it points; the endpoint only supplies auth",
        )
        self.assertEqual(
            revealed(sent["headers"].get("Authorization")), "Bearer SECRETTOKEN"
        )
        self.assertEqual(sent["headers"].get("Content-Type"), "application/json")

    def test_an_endpoint_that_retries_is_refused(self):
        retrying = self.env["integration.service"].create(
            {
                "name": "retries",
                "code": "wh_retries",
                "endpoint_url": "https://example.com",
                "auth_type": "none",
                "retry_enabled": True,
            }
        )
        with self.assertRaises(ValidationError) as caught:
            self._action(webhook_endpoint_id=retrying.id)
        self.assertIn("retry", str(caught.exception).lower())

    def test_a_non_webhook_action_cannot_carry_an_endpoint(self):
        with self.assertRaises(ValidationError):
            self.env["ir.actions.server"].create(
                {
                    "name": "code action",
                    "model_id": self.model.id,
                    "state": "code",
                    "code": "pass",
                    "webhook_endpoint_id": self.endpoint.id,
                }
            )

    @mute_logger(_MODULE)
    def test_the_guard_runs_again_at_delivery(self):
        action = self._action(webhook_endpoint_id=self.endpoint.id)
        deliver = action._prepare_webhook_delivery(
            "https://example.com/hook", 5, "n(#1)", "x"
        )

        with (
            patch(f"{_MODULE}.Registry") as registry,
            patch(
                "socket.getaddrinfo",
                return_value=[(2, 1, 6, "", ("127.0.0.1", 443))],
            ),
            mute_logger(_MODULE),
        ):
            deliver('{"a": 1}')

        registry.assert_not_called()

    def test_a_failed_delivery_does_not_escape_the_hook(self):
        action = self._action(webhook_endpoint_id=self.endpoint.id)
        deliver = action._prepare_webhook_delivery(
            "https://example.com/hook", 5, "n(#1)", "x"
        )

        with patch(f"{_MODULE}.Registry", side_effect=RuntimeError("no database")):
            deliver('{"a": 1}')

    def test_a_scheme_no_http_session_carries_is_refused_at_delivery(self):
        action = self._action(webhook_endpoint_id=self.endpoint.id)
        deliver = action._prepare_webhook_delivery(
            "ws://93.184.216.34/hook", 5, "n(#1)", "x"
        )
        with (
            patch(f"{_MODULE}.Registry") as registry,
            self.assertLogs(_MODULE, "ERROR") as logs,
        ):
            deliver('{"a": 1}')
        registry.assert_not_called()
        self.assertIn("was NOT sent", logs.output[0])
        self.assertIn("correct the action's URL", logs.output[0])
        self.assertNotIn("resolves elsewhere", logs.output[0])

    def test_queued_delivery_keeps_the_selected_endpoint(self):
        action = self._action(
            webhook_endpoint_id=self.endpoint.id, webhook_delivery="queued"
        )
        options = action._get_webhook_job_options()
        action.webhook_endpoint_id = False
        with patch(f"{_MODULE}.get_api_client") as factory:
            client = factory.return_value
            client.post.return_value.status_code = 202
            status = action._send_webhook_request(
                "https://example.com/hook", 3, '{"a": 1}', "stable-key", options
            )
        self.assertEqual(status, 202)
        self.assertEqual(factory.call_args.args[1], self.endpoint.code)
        self.assertEqual(factory.call_args.kwargs["egress_policy"], "public")
        self.assertEqual(
            client.post.call_args.kwargs["headers"]["Idempotency-Key"], "stable-key"
        )
        self.assertFalse(client.post.call_args.kwargs["allow_redirects"])
        self.assertFalse(client.post.call_args.kwargs["raise_for_status"])
        self.assertTrue(client.post.call_args.kwargs["raw"])

    def test_queued_endpoint_status_is_classified_by_the_job(self):
        action = self._action(
            webhook_endpoint_id=self.endpoint.id, webhook_delivery="queued"
        )
        options = action._get_webhook_job_options()
        for status, exception in [
            (503, RetryableJobError),
            (429, RetryableJobError),
            (403, TerminalJobError),
        ]:
            with (
                self.subTest(status=status),
                patch(f"{_MODULE}.get_api_client") as factory,
            ):
                factory.return_value.post.return_value.status_code = status
                with self.assertRaises(exception):
                    action._deliver_webhook_job(
                        "https://example.com/hook", 3, "{}", "stable-key", options
                    )

    def test_queued_delivery_rejects_a_disabled_endpoint(self):
        action = self._action(
            webhook_endpoint_id=self.endpoint.id, webhook_delivery="queued"
        )
        options = action._get_webhook_job_options()
        self.endpoint.active = False
        with (
            patch(f"{_MODULE}.get_api_client") as factory,
            self.assertRaises(TerminalJobError),
        ):
            action._send_webhook_request(
                "https://example.com/hook", 3, "{}", "stable-key", options
            )
        factory.assert_not_called()

    def test_queued_delivery_refuses_in_request_retries_enabled_later(self):
        action = self._action(
            webhook_endpoint_id=self.endpoint.id, webhook_delivery="queued"
        )
        options = action._get_webhook_job_options()
        self.endpoint.retry_enabled = True
        with (
            patch(f"{_MODULE}.get_api_client") as factory,
            self.assertRaises(TerminalJobError),
        ):
            action._send_webhook_request(
                "https://example.com/hook", 3, "{}", "stable-key", options
            )
        factory.assert_not_called()
