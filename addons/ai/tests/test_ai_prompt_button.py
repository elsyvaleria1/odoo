from odoo.tests import TransactionCase, tagged

from odoo.addons.ai.models.ai_prompt_button import PROMPT_MODULE_MAP


@tagged("post_install", "-at_install")
class TestAIPromptButton(TransactionCase):
    def test_every_prompt_module_names_a_module(self):
        known = set(
            self.env["ir.module.module"]
            .search([("name", "in", list(PROMPT_MODULE_MAP))])
            .mapped("name")
        )
        self.assertEqual(sorted(set(PROMPT_MODULE_MAP) - known), [])

    def test_the_prompt_of_an_installed_module_is_listed(self):
        installed = self.env["ir.module.module"].search(
            [("name", "=", "account"), ("state", "=", "installed")]
        )
        if not installed:
            self.skipTest("account is not installed")
        prompt = self.env.ref("ai.ai_prompt_cash_flow_status")
        self.assertIn(prompt, self.env["ai.prompt.button"].search([]))
