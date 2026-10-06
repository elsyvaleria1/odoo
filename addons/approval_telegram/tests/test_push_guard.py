from unittest.mock import patch

from odoo.tests import tagged

from .test_approval_request import ApprovalRequestTestBase
from odoo.addons.telegram.tools.telegram_client import TelegramClient


@tagged("post_install", "-at_install")
class TestTelegramCannotFailAnApproval(ApprovalRequestTestBase):
    def test_pushes_are_queued_and_telegram_is_not_called(self):
        """A push used to call Telegram inside the approval's transaction and
        swallow what went wrong -- retryable database errors included -- or
        let it abort the approval. Queued, Telegram is reached after commit."""
        self.test_bot.notify_approvals = True
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
            self.approver._create_activity()
        self.assertTrue(
            self.env["telegram.message"].search_count(
                [("chat_id", "=", self.test_chat.id), ("state", "=", "outgoing")]
            )
        )
