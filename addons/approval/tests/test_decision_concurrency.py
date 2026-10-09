import uuid

import psycopg

from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestConcurrentDecisions(TransactionCase):
    def test_a_decision_on_rows_another_just_decided_is_retried(self):
        tag = uuid.uuid4().hex[:10]
        ids = {}
        try:
            with self.leave_registry_test_mode():
                with self.registry.cursor() as cr:
                    env = self.env(cr=cr)
                    users = env["res.users"].create(
                        [
                            {"name": f"{role} {tag}", "login": f"{role}-{tag}"}
                            for role in ("owner", "first", "second")
                        ]
                    )
                    owner, first, second = users
                    category = env["approval.category"].create(
                        {
                            "name": f"Race {tag}",
                            "approval_minimum": 2,
                            "step_ids": [
                                Command.create(
                                    {
                                        "name": "Both",
                                        "minimum": 2,
                                        "member_ids": [
                                            Command.create({"user_id": first.id}),
                                            Command.create({"user_id": second.id}),
                                        ],
                                    }
                                )
                            ],
                        }
                    )
                    request = env["approval.request"].create(
                        {"category_id": category.id, "request_owner_id": owner.id}
                    )
                    request.action_confirm()
                    ids.update(
                        users=users.ids, category=category.id, request=request.id
                    )

                with self.registry.cursor() as late_cr:
                    late = self.env(cr=late_cr, user=second.id)
                    late_request = late["approval.request"].browse(ids["request"])
                    self.assertEqual(late_request.state, "pending")
                    with self.registry.cursor() as cr:
                        self.env(cr=cr, user=first.id)["approval.request"].browse(
                            ids["request"]
                        ).action_approve()
                    with self.assertRaises(psycopg.errors.SerializationFailure):
                        late_request.action_approve()
                    late_cr.rollback()
                    late_request.invalidate_recordset()
                    late_request.action_approve()
                    self.assertEqual(late_request.state, "approved")
        finally:
            with self.leave_registry_test_mode(), self.registry.cursor() as cr:
                if ids:
                    cr.execute(
                        "DELETE FROM approval_decision_log WHERE request_id = %s",
                        [ids["request"]],
                    )
                    cr.execute(
                        "DELETE FROM approval_request WHERE id = %s", [ids["request"]]
                    )
                    env = self.env(cr=cr)
                    env["approval.category"].browse(ids["category"]).unlink()
                    env["res.users"].browse(ids["users"]).action_archive()
