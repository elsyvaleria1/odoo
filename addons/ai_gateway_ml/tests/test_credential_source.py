from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "ai_gateway_ml")
class TestLlmCredentialSource(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.credential_model = cls.env["credential.credential"]
        cls.category = cls.env.ref("credential.credential_category_custom")
        cls.openai_service = cls.env["integration.service"].search(
            [("code", "=", "openai")], limit=1
        )
        cls.env["credential.credential"]._set_system_secret("ai.openai_key", "")

    def _vault_key(self, key, company=None):
        return self.credential_model.create(
            {
                "name": "OpenAI test key",
                "endpoint_id": self.openai_service.id,
                "company_id": (company or self.env.company).id,
                "category_id": self.category.id,
                "environment": self.openai_service.environment,
                "api_key": key,
            }
        )

    def test_vault_key_is_preferred(self):
        self.env["credential.credential"]._set_system_secret(
            "ai.openai_key", "from_icp"
        )
        self._vault_key("from_vault")

        token = self.env["ai.llm.credential"]._get_api_token("openai")

        self.assertEqual(token, "from_vault")

    def test_falls_back_to_system_parameter(self):
        self.env["credential.credential"]._set_system_secret(
            "ai.openai_key", "from_icp"
        )

        token = self.env["ai.llm.credential"]._get_api_token("openai")

        self.assertEqual(token, "from_icp")

    def test_credential_is_company_scoped(self):
        other = self.env["res.company"].create({"name": "Other Co"})
        self._vault_key("other_company_key", company=other)

        with self.assertRaises(UserError):
            self.env["ai.llm.credential"]._get_api_token("openai")

    def test_google_maps_to_the_gemini_service(self):
        gemini = self.env["integration.service"].search(
            [("code", "=", "gemini")], limit=1
        )
        self.assertTrue(
            gemini, "integration_machine_learning should ship a 'gemini' service"
        )
        self.credential_model.create(
            {
                "name": "Gemini test key",
                "endpoint_id": gemini.id,
                "company_id": self.env.company.id,
                "category_id": self.category.id,
                "environment": gemini.environment,
                "api_key": "gemini_from_vault",
            }
        )

        token = self.env["ai.llm.credential"]._get_api_token("google")

        self.assertEqual(token, "gemini_from_vault")

    def test_unknown_provider_still_raises(self):
        with self.assertRaises(UserError):
            self.env["ai.llm.credential"]._get_api_token("no_such_provider")


@tagged("post_install", "-at_install", "ai_gateway_ml")
class TestLlmTransportRouting(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.transport = cls.env["ai.llm.transport"]
        cls.openai_service = cls.env["integration.service"].search(
            [("code", "=", "openai")], limit=1
        )

    def _add_credential(self):
        return self.env["credential.credential"].create(
            {
                "name": "OpenAI transport key",
                "endpoint_id": self.openai_service.id,
                "company_id": self.env.company.id,
                "category_id": self.env.ref("credential.credential_category_custom").id,
                "environment": self.openai_service.environment,
                "api_key": "sk-test",
            }
        )

    def test_service_without_credential_is_not_routed(self):
        self.assertTrue(
            self.openai_service,
            "integration_machine_learning should ship an 'openai' service",
        )
        self.assertFalse(self.transport._get_transport_service("openai"))

    def test_service_with_credential_is_routed(self):
        self._add_credential()
        self.assertEqual(
            self.transport._get_transport_service("openai"), self.openai_service
        )

    def test_unknown_provider_is_not_routed(self):
        self.assertFalse(self.transport._get_transport_service("no_such_provider"))

    def test_endpoint_is_made_relative_to_the_service_base(self):
        base = self.openai_service.endpoint_url.rstrip("/")
        self.assertEqual(
            self.transport._endpoint_for(
                f"{base}/chat/completions", self.openai_service
            ),
            "/chat/completions",
        )

    def test_foreign_url_is_passed_through_unchanged(self):
        self.assertEqual(
            self.transport._endpoint_for(
                "https://elsewhere.invalid/v1/x", self.openai_service
            ),
            "https://elsewhere.invalid/v1/x",
        )


@tagged("post_install", "-at_install", "ai_gateway_ml")
class TestClaudeRagEmbeddingProvider(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.agent = cls.env["ai.agent"].create(
            {
                "name": "Claude RAG Agent",
                "llm_model": "claude-sonnet-5",
                "response_style": "balanced",
            }
        )

    def test_override_is_installed(self):
        self.assertTrue(
            hasattr(self.env["ai.agent"], "_get_embedding_provider"),
            "ai does not define the seam",
        )
        self.assertTrue(
            hasattr(self.env["ai.agent"], "_has_usable_credentials"),
            "this module's override did not load — check models/__init__.py",
        )

    def test_claude_borrows_a_configured_provider(self):
        self.env["credential.credential"]._set_system_secret("ai.openai_key", "sk-icp")
        self.assertEqual(self.agent._get_embedding_provider(), "openai")

    def test_claude_without_any_embedding_key_explains_itself(self):
        self.env["credential.credential"]._set_system_secret("ai.openai_key", "")
        self.env["credential.credential"]._set_system_secret("ai.google_key", "")

        with self.assertRaises(UserError) as cm:
            self.agent._get_embedding_provider()

        self.assertIn("OpenAI or Google", str(cm.exception))

    def test_non_claude_agent_is_untouched(self):
        other = self.env["ai.agent"].create(
            {"name": "GPT Agent", "llm_model": "gpt-4o", "response_style": "balanced"}
        )
        self.assertEqual(other._get_embedding_provider(), "openai")

    def test_the_candidate_list_is_derived_from_the_registry(self):
        self.assertEqual(
            self.agent._embedding_capable_providers(), ["openai", "google"]
        )

    def test_a_provider_that_loses_embeddings_leaves_the_list(self):
        openai = self.env["integration.ml.provider"].search(
            [("endpoint_id.code", "=", "openai")], limit=1
        )
        self.assertTrue(
            openai, "integration_machine_learning did not seed the openai provider"
        )
        openai.has_embeddings = False
        self.assertEqual(self.agent._embedding_capable_providers(), ["google"])

    def test_claude_is_never_a_candidate_for_its_own_fallback(self):
        claude = self.env["integration.ml.provider"].search(
            [("endpoint_id.code", "=", "claude")], limit=1
        )
        self.assertTrue(
            claude, "integration_machine_learning did not seed the claude provider"
        )
        self.assertFalse(claude.has_embeddings)
        self.assertNotIn("anthropic", self.agent._embedding_capable_providers())


@tagged("post_install", "-at_install", "ai_gateway_ml")
class TestLlmKeyIsUsedNotRevealed(TransactionCase):
    def test_every_ai_call_reads_the_key_past_the_decrypt_allowance(self):
        service = self.env["integration.service"].search(
            [("code", "=", "openai")], limit=1
        )
        credential = self.env["credential.credential"].create(
            {
                "name": "OpenAI key under allowance",
                "endpoint_id": service.id,
                "company_id": self.env.company.id,
                "category_id": self.env.ref("credential.credential_category_custom").id,
                "environment": service.environment,
                "api_key": "from_vault",
            }
        )
        credential.write(
            {"decrypt_rate_limit_enabled": True, "decrypt_rate_limit_max": 1}
        )

        for _ in range(3):
            self.env.invalidate_all()
            self.assertEqual(
                self.env["ai.llm.credential"]._get_api_token("openai"), "from_vault"
            )
