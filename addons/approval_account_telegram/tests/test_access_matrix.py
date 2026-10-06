from odoo import Command
from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona

START = (
    "the approver who gives the last approval starts the run only through "
    "approval_account_telegram.privilege_start_approved_workflow, which no user "
    "holds"
)
SETTLE = (
    "the approver of a payment names its partner on the statement line it "
    "claims only through approval_account_telegram."
    "privilege_start_approved_workflow, which no user holds"
)


@tagged("post_install", "-at_install", "access_matrix")
class TestApprovalAccountTelegramAccessMatrix(AccessMatrixCase):
    personas = {
        "requester_a": Persona(),
        "approver_a": Persona("approval.group_approval_approver"),
        "admin_a": Persona("base.group_system"),
        "approver_b": Persona("approval.group_approval_approver", company="b"),
        "accountant_a": Persona("account.group_account_readonly"),
        "public": Persona(public=True),
    }
    cells = (
        Cell(
            "telegram.payment.report.log",
            "log",
            note="the bot logs the request it filed for its sender only through "
            "approval_account_telegram.privilege_log_payment_request",
            admin_a="rwcd",
        ),
        Cell(
            "automation.runtime",
            "runtime_a",
            note=START,
            requester_a="r",
            approver_a="r",
            accountant_a="r",
            admin_a="rwcd",
        ),
        Cell(
            "automation.runtime.line",
            "runtime_line_a",
            note=START,
            requester_a="r",
            approver_a="r",
            accountant_a="r",
            admin_a="rwcd",
        ),
        Cell(
            "automation.runtime.edge",
            "runtime_edge_a",
            note=START,
            requester_a="r",
            approver_a="r",
            accountant_a="r",
            admin_a="rwcd",
        ),
        Cell(
            "automation.rule",
            "rule",
            note=START,
            admin_a="rwcd",
        ),
        Cell(
            "ir.actions.server",
            "step",
            note=START,
            admin_a="rwcd",
        ),
        Cell(
            "account.bank.statement.line",
            "st_line_a",
            note=SETTLE,
            accountant_a="r",
        ),
        Cell(
            "account.move",
            "st_move_a",
            note=SETTLE,
            accountant_a="r",
        ),
        Cell(
            "account.move.line",
            "st_move_line_a",
            note=SETTLE,
            accountant_a="r",
        ),
    )

    @classmethod
    def build(cls):
        env = cls.env
        a = cls.companies["a"]
        model = env["ir.model"]._get("res.partner")
        rule = env["automation.rule"].create(
            {"name": "matrix workflow", "model_id": model.id, "trigger": "on_hand"}
        )

        def step(name):
            return env["ir.actions.server"].create(
                {
                    "name": name,
                    "model_id": model.id,
                    "state": "code",
                    "code": "pass",
                    "automation_rule_id": rule.id,
                    "usage": "automation",
                }
            )

        first, second = step("matrix first"), step("matrix second")
        env["workflow.edge"].create(
            {
                "source_node_id": first.id,
                "target_node_id": second.id,
                "condition": "on_success",
            }
        )
        partner = env["res.partner"].create({"name": "matrix payee"})
        runtime = env["automation.runtime"].create(
            {
                "automation_id": rule.id,
                "res_model": "res.partner",
                "res_id": partner.id,
                "company_ids": [Command.set(a.ids)],
            }
        )
        runtime.action_start()
        journal = env["account.journal"].create(
            {
                "name": "Matrix Bank",
                "code": "MXBNK",
                "type": "bank",
                "company_id": a.id,
            }
        )
        st_line = env["account.bank.statement.line"].create(
            {
                "journal_id": journal.id,
                "amount": -10.0,
                "payment_ref": "matrix payment",
                "company_id": a.id,
            }
        )
        return {
            "log": env["telegram.payment.report.log"].create(
                {"partner_id": partner.id, "amount": 10.0}
            ),
            "runtime_a": runtime,
            "runtime_line_a": runtime.line_ids[:1],
            "runtime_edge_a": runtime.edge_ids[:1],
            "rule": rule,
            "step": first,
            "st_line_a": st_line,
            "st_move_a": st_line.move_id,
            "st_move_line_a": st_line.move_id.line_ids[:1],
        }
