from odoo.tests import tagged

from .test_approvals import TestStudioApprovalsCommon


@tagged("mail_activity_mixin", "-at_install", "post_install")
class TestApprovalsActivity(TestStudioApprovalsCommon):
    def test_approve_via_activity(self):
        for name in ("Rule 1", "Rule 2"):
            self._step(
                "action_confirm",
                name,
                group=self.group_user,
                approvers=[self.admin_user],
                notify=[self.admin_user],
                exclusive=True,
            )
        record = self.env[self.MODEL].create({"name": "test"})

        self._click("demo", record, "action_confirm")
        self.assertFalse(record.confirmed)
        request = self._request(record, "action_confirm")
        activity = request.activity_ids
        self.assertEqual(
            activity.activity_type_id,
            self.env.ref("approval.mail_activity_data_approval"),
        )
        self.assertEqual(activity.user_id, self.admin_user)
        self.assertEqual(
            self._decided(record, "action_confirm"),
            {"Rule 1": {"demo"}, "Rule 2": set()},
        )

        activity.with_user(self.admin_user).action_feedback("Losing my religion")
        self.assertEqual(
            self._decided(record, "action_confirm"),
            {"Rule 1": {"demo"}, "Rule 2": {"admin"}},
        )
        self.assertEqual(request.state, "approved")
        self.assertFalse(request.activity_ids)
        feedback = request.message_ids.filtered(
            lambda message: "Losing my religion" in message.body
        )
        self.assertEqual(len(feedback), 1)
