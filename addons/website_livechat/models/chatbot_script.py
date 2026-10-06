from odoo import models


class ChatbotScript(models.Model):
    _inherit = "chatbot.script"

    def action_test_script(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_url",
            "url": "/chatbot/%s/test" % self.id,
            "target": "self",
        }
