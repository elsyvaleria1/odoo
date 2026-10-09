from odoo import Command
from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona

ANSWER = (
    "a message reaches it only through "
    "automation_telegram.privilege_answer_question, which no user holds"
)


@tagged("post_install", "-at_install", "access_matrix")
class TestAutomationTelegramAccessMatrix(AccessMatrixCase):
    personas = {
        "employee_a": Persona(),
        "employee_b": Persona(company="b"),
        "admin_a": Persona("base.group_system"),
        "public": Persona(public=True),
    }
    cells = (
        Cell(
            "automation.telegram.wait",
            "wait",
            note=ANSWER,
            employee_a="r",
            admin_a="rwcd",
        ),
        Cell(
            "automation.runtime",
            "runtime",
            note=ANSWER,
            employee_a="r",
            admin_a="rwcd",
        ),
        Cell(
            "automation.runtime.line",
            "line",
            note=ANSWER,
            employee_a="r",
            admin_a="rwcd",
        ),
        Cell(
            "automation.runtime.edge",
            "edge",
            note=ANSWER,
            employee_a="r",
            admin_a="rwcd",
        ),
    )

    @classmethod
    def build(cls):
        env = cls.env
        partner_model = env["ir.model"]._get("res.partner")
        rule = env["automation.rule"].create(
            {
                "name": "matrix question",
                "model_id": partner_model.id,
                "trigger": "on_hand",
                "create_runtime_instance": True,
            }
        )
        ask, answered = (
            env["ir.actions.server"].create(
                {
                    "name": name,
                    "model_id": partner_model.id,
                    "state": "code",
                    "code": "pass",
                    "automation_rule_id": rule.id,
                    "usage": "automation",
                }
            )
            for name in ("ask", "answered")
        )
        runtime = env["automation.runtime"].create(
            {
                "automation_id": rule.id,
                "res_model": "res.partner",
                "res_id": env.user.partner_id.id,
                "company_ids": [Command.set(cls.companies["a"].ids)],
            }
        )
        line, next_line = env["automation.runtime.line"].create(
            [
                {"runtime_id": runtime.id, "action_id": ask.id, "name": "ask"},
                {
                    "runtime_id": runtime.id,
                    "action_id": answered.id,
                    "name": "answered",
                },
            ]
        )
        edge = env["automation.runtime.edge"].create(
            {
                "runtime_id": runtime.id,
                "source_line_id": line.id,
                "target_line_id": next_line.id,
                "condition": "event",
                "event_code": "answer",
            }
        )
        credential = env["credential.credential"].create(
            {
                "name": "matrix telegram credential",
                "category_id": env.ref(
                    "credential.credential_category_bearer_token"
                ).id,
                "endpoint_id": env.ref("telegram.service_telegram").id,
            }
        )
        bot = env["telegram.bot"].create(
            {"name": "matrix bot", "credential_id": credential.id}
        )
        chat = env["telegram.chat"].create(
            {"chat_id": "4242", "chat_type": "private", "bot_id": bot.id}
        )
        wait = env["automation.telegram.wait"].create(
            {
                "line_id": line.id,
                "event_code": "answer",
                "chat_id": chat.id,
                "accepted_kinds": "text",
            }
        )
        return {"wait": wait, "runtime": runtime, "line": line, "edge": edge}
