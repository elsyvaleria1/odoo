from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from odoo.addons.ai.utils.llm_api_service import LLMApiService

TRANSPORT = "odoo.addons.ai.models.ai_llm_transport.AiLlmTransport._request"


@tagged("post_install", "-at_install", "ai_gateway_ml")
class TestPurposePolicy(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Policy = cls.env["integration.ml.policy"]
        cls.Purpose = cls.env["integration.ml.purpose"]
        cls.openai = cls.env["ai.llm.transport"]._get_gateway_provider("openai")
        cls.Policy.search([("company_id", "=", cls.env.company.id)]).unlink()

    def _send(self, purpose):
        service = LLMApiService(self.env, "openai", purpose=purpose)
        with (
            patch(TRANSPORT, return_value={"ok": True}) as wire,
            patch.object(
                type(self.env["ai.llm.transport"]),
                "_get_transport_service",
                return_value=self.env["integration.service"],
            ),
        ):
            result = service._request("post", "/chat", {}, {"x": 1})
        return result, wire

    def test_the_vendor_is_known_to_the_gateway(self):
        self.assertTrue(self.openai)

    def test_a_purpose_no_policy_names_is_allowed_unless_sensitive(self):
        result, wire = self._send("ai.agent")
        self.assertEqual(result, {"ok": True})
        self.assertEqual(wire.call_args.kwargs["purpose"], "ai.agent")
        self.Purpose._get_or_create_by_key("ai.agent").sensitive = True
        with self.assertRaises(UserError):
            self._send("ai.agent")

    def test_a_policy_naming_another_vendor_refuses_before_sending(self):
        other = self.env["integration.ml.provider"].search(
            [("id", "!=", self.openai.id)], limit=1
        )
        self.Policy.create(
            {
                "company_id": self.env.company.id,
                "purpose_id": self.Purpose._get_or_create_by_key("ai.action").id,
                "provider_ids": [(6, 0, other.ids)],
            }
        )
        with self.assertRaises(UserError) as caught:
            self._send("ai.action")
        self.assertIn("ai.action", str(caught.exception))
        _result, wire = self._send("ai.agent")
        self.assertTrue(wire.called, "another purpose is not governed by it")

    def test_a_parent_purpose_governs_its_children(self):
        self.Policy.create(
            {
                "company_id": self.env.company.id,
                "purpose_id": self.Purpose._get_or_create_by_key("ai").id,
                "provider_ids": [(6, 0, self.openai.ids)],
            }
        )
        _result, wire = self._send("ai.fields")
        self.assertTrue(wire.called)
