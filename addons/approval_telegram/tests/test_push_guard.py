from unittest.mock import patch

from odoo.tests import tagged

from .test_approval_request import ApprovalRequestTestBase
from odoo.addons.telegram.tools.telegram_client import TelegramClient


@tagged("post_install", "-at_install")
class TestTelegramCannotFailAnApproval(ApprovalRequestTestBase):
    def test_pushes_are_queued_and_telegram_is_not_called(self):
        self.test_bot.notify_approvals = True
        request = self.env["approval.request"].create(
            {
                "category_id": self.category.id,
                "request_owner_id": self.env.ref("base.user_admin").id,
            }
        )
        with (
            patch.object(
                TelegramClient,
                "call",
                side_effect=AssertionError("called in-transaction"),
            ),
            patch.object(
                TelegramClient, "send_message", side_effect=AssertionError("called")
            ),
        ):
            request.action_confirm()
        self.assertTrue(
            self.env["telegram.message"].search_count(
                [("chat_id", "=", self.test_chat.id), ("state", "=", "outgoing")]
            )
        )
