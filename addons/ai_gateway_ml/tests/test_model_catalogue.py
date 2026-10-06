from odoo.tests import TransactionCase, tagged

from odoo.addons.ai.utils.llm_providers import get_provider


@tagged("post_install", "-at_install", "ai_gateway_ml")
class TestClaudeModelCatalogue(TransactionCase):
    def _claude_rows(self):
        return self.env["integration.ml.model"].search(
            [("provider_id.endpoint_id.code", "=", "claude"), ("kind", "=", "chat")]
        )

    def test_every_claude_row_is_selectable(self):
        offered = dict(self.env["ai.agent"]._get_llm_model_selection())
        for row in self._claude_rows():
            self.assertEqual(offered.get(row.code), row.name)

    def test_dated_aliases_stay_selectable(self):
        offered = dict(self.env["ai.agent"]._get_llm_model_selection())
        for code in ("claude-sonnet-4-5-20250929", "claude-haiku-4-5-20251001"):
            self.assertIn(code, offered)

    def test_no_duplicate_identifiers(self):
        codes = [
            code for code, _label in self.env["ai.agent"]._get_llm_model_selection()
        ]
        self.assertEqual(len(codes), len(set(codes)))

    def test_every_row_reaches_the_provider_lookup(self):
        for row in self._claude_rows():
            self.assertEqual(get_provider(self.env, row.code), "claude")

    def test_a_row_added_later_is_selectable_without_a_restart(self):
        claude = self.env.ref("integration_machine_learning.ai_provider_anthropic")
        self.env["integration.ml.model"].create(
            {"provider_id": claude.id, "name": "Claude Next", "code": "claude-next"}
        )
        self.assertIn(
            "claude-next", dict(self.env["ai.agent"]._get_llm_model_selection())
        )
        self.assertEqual(get_provider(self.env, "claude-next"), "claude")

    def test_an_archived_row_is_no_longer_offered(self):
        self.env.ref(
            "integration_machine_learning.ai_model_claude_haiku_4_5"
        ).active = False
        self.assertNotIn(
            "claude-haiku-4-5", dict(self.env["ai.agent"]._get_llm_model_selection())
        )
