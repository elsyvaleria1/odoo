from odoo import Command
from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona


@tagged("post_install", "-at_install", "access_matrix")
class TestApprovalAccessMatrix(AccessMatrixCase):
    personas = {
        "requester_a": Persona(),
        "approver_a": Persona("approval.group_approval_approver"),
        "colleague_a": Persona(),
        "manager_a": Persona("approval.group_approval_manager"),
        "requester_b": Persona(company="b"),
        "portal_c": Persona(portal="customer_c"),
        "manager_ab": Persona("approval.group_approval_manager", companies=("a", "b")),
    }
    cells = (
        Cell(
            "approval.category",
            "category_employees",
            requester_a="r",
            approver_a="r",
            colleague_a="r",
            manager_a="rwcd",
            manager_ab="rwcd",
        ),
        Cell(
            "approval.category",
            "category_private",
            requester_a="r",
            approver_a="r",
            colleague_a="r",
            manager_a="rwcd",
            manager_ab="rwcd",
        ),
        Cell(
            "approval.category",
            "category_b",
            requester_b="r",
            manager_ab="rwcd",
        ),
        Cell(
            "approval.category.step",
            "step",
            requester_a="r",
            approver_a="r",
            colleague_a="r",
            manager_a="rwcd",
            manager_ab="rwcd",
        ),
        Cell(
            "approval.category.step.member",
            "step_member",
            requester_a="r",
            approver_a="r",
            colleague_a="r",
            manager_a="rwcd",
            manager_ab="rwcd",
        ),
        Cell(
            "approval.request",
            "request_own",
            requester_a="rwc cancel confirm reset resubmit",
            approver_a="rw approve confirm refuse request_change resubmit",
            colleague_a="r",
            manager_a="rwc cancel confirm reset resubmit",
            manager_ab="rwc cancel confirm reset resubmit",
        ),
        Cell(
            "approval.request",
            "request_draft",
            requester_a="rwcd cancel confirm reset resubmit",
            approver_a="rw approve confirm refuse request_change resubmit",
            colleague_a="r",
            manager_a="rwcd cancel confirm reset resubmit",
            manager_ab="rwcd cancel confirm reset resubmit",
        ),
        Cell(
            "approval.request",
            "request_private",
            requester_a="rwc cancel confirm reset resubmit",
            approver_a="rw approve confirm refuse request_change resubmit",
            manager_a="rwc cancel confirm reset resubmit",
            manager_ab="rwc cancel confirm reset resubmit",
        ),
        Cell(
            "approval.request",
            "request_b",
            requester_b="rwc cancel confirm reset resubmit",
            manager_ab="rwc approve cancel confirm refuse request_change reset resubmit",
        ),
        Cell(
            "approval.approver",
            "approver_row",
            requester_a="r",
            approver_a="rw",
            colleague_a="r",
            manager_a="rwcd",
            manager_ab="rwcd",
        ),
        Cell(
            "approval.approver",
            "approver_row_private",
            requester_a="r",
            approver_a="rw",
            manager_a="rwcd",
            manager_ab="rwcd",
        ),
        Cell(
            "approval.request",
            "request_decided",
            requester_a="rwc cancel confirm resubmit",
            approver_a="rw approve confirm refuse request_change resubmit",
            colleague_a="r",
            manager_a="rwc cancel confirm reset resubmit",
            manager_ab="rwc cancel confirm reset resubmit",
        ),
        Cell(
            "approval.decision.log",
            "decision_log",
            requester_a="r",
            approver_a="r",
            colleague_a="r",
            manager_a="r",
            manager_ab="r",
        ),
        Cell(
            "approval.decision.log",
            "decision_log_private",
            requester_a="r",
            approver_a="r",
            manager_a="r",
            manager_ab="r",
        ),
        Cell(
            "approval.refusal.reason",
            "refusal_reason",
            requester_a="r",
            approver_a="r",
            colleague_a="r",
            manager_a="rwcd",
            manager_ab="rwcd",
        ),
        Cell(
            "approval.rule",
            "rule",
            requester_a="r",
            approver_a="r",
            colleague_a="r",
            manager_a="rwcd",
            manager_ab="rwcd",
        ),
        Cell(
            "approval.authority.limit",
            "authority_limit",
            needs="a verb with an amount (sale, purchase or account installed)",
            approver_a="r",
            manager_a="rwcd",
            manager_ab="rwcd",
        ),
        Cell(
            "approval.binding",
            "binding",
            requester_a="r",
            approver_a="r",
            colleague_a="r",
            manager_a="rwcd",
            requester_b="r",
            manager_ab="rwcd",
        ),
        Cell(
            "approval.observation",
            "observation",
            manager_a="r",
            manager_ab="r",
        ),
        Cell(
            "res.users.grant",
            "decider_grant",
            approver_a="r",
            manager_a="r",
            manager_ab="r",
        ),
    )

    @classmethod
    def build(cls):
        env = cls.env
        a, b = cls.companies["a"], cls.companies["b"]
        users = cls.users

        def category(name, privacy, company, approver="approver_a", **values):
            return env["approval.category"].create(
                {
                    "name": name,
                    "sequence_code": name.upper().replace(" ", "")[:10],
                    "approval_minimum": 1,
                    "privacy_visibility": privacy,
                    "company_id": company.id,
                    "step_ids": [
                        Command.create(
                            {
                                "name": "Approvers",
                                "sequence": 10,
                                "minimum": 1,
                                "counts_added_approvers": True,
                                "member_ids": [
                                    Command.create(
                                        {
                                            "user_id": users[approver].id,
                                            "required": True,
                                            "sequence": 10,
                                        }
                                    )
                                ],
                            }
                        )
                    ],
                    **values,
                }
            )

        category_employees = category("matrix employees", "employees", a)
        category_private = category(
            "matrix private",
            "restricted_users",
            a,
            allowed_user_ids=[Command.set(users["requester_a"].ids)],
        )
        category_b = category("matrix b", "employees", b, approver="manager_ab")

        def request(category_record, owner, confirm=True):
            record = (
                env["approval.request"]
                .with_company(category_record.company_id)
                .create(
                    {
                        "category_id": category_record.id,
                        "request_owner_id": owner.id,
                        "reason": "<p>matrix</p>",
                    }
                )
            )
            if confirm:
                record.action_confirm()
            return record

        request_own = request(category_employees, users["requester_a"])
        request_draft = request(category_employees, users["requester_a"], False)
        request_private = request(category_private, users["requester_a"])
        request_b = request(category_b, users["requester_b"])
        request_decided = request(category_employees, users["requester_a"])
        request_decided.approver_ids[:1].sudo()._record_decision("approved")
        private_decided = request(category_private, users["requester_a"])
        private_decided.approver_ids[:1].sudo()._record_decision("approved")
        # a limit qualifies a verb with an amount, which only modules approval
        # does not depend on declare (sale, purchase, account)
        limited = next(
            (
                (model, name)
                for model, verbs in sorted(env.registry.model_verbs.items())
                for name, verb in verbs.items()
                if verb.amount
            ),
            None,
        )
        grant = env["res.users.grant"].create(
            {
                "user_id": users["approver_a"].id,
                "group_id": env.ref("approval.group_approval_approver").id,
            }
        )
        authority_limit = None
        if limited:
            authority_limit = env["approval.authority.limit"].create(
                {
                    "grant_id": grant.id,
                    "model_id": env["ir.model"]._get_id(limited[0]),
                    "verb": limited[1],
                    "amount_max": 100.0,
                    "currency_id": a.currency_id.id,
                }
            )
        return {
            "category_employees": category_employees,
            "category_private": category_private,
            "category_b": category_b,
            "step": category_employees.step_ids[:1],
            "step_member": category_employees.step_ids.member_ids[:1],
            "request_own": request_own,
            "request_draft": request_draft,
            "request_private": request_private,
            "request_b": request_b,
            "approver_row": request_own.approver_ids[:1],
            "approver_row_private": request_private.approver_ids[:1],
            "request_decided": request_decided,
            "decision_log": env["approval.decision.log"].search(
                [("request_id", "=", request_decided.id)], limit=1
            ),
            "decision_log_private": env["approval.decision.log"].search(
                [("request_id", "=", private_decided.id)], limit=1
            ),
            "refusal_reason": env["approval.refusal.reason"].create(
                {"name": "matrix reason", "company_id": a.id}
            ),
            "rule": env["approval.rule"].create(
                {
                    "category_id": category_employees.id,
                    "action_type": "condition",
                    "name": "matrix rule",
                    "condition_field": "amount",
                    "operator": "gt",
                    "threshold": 100,
                }
            ),
            "authority_limit": authority_limit,
            "binding": env["approval.binding"].search([], limit=1),
            "observation": env["approval.observation"].create(
                {
                    "model_name": "approval.request",
                    "operation": "approve",
                    "elevation": "none",
                }
            ),
            "decider_grant": env["res.users.grant"].search(
                [("user_id", "=", users["approver_a"].id)], limit=1
            ),
        }
