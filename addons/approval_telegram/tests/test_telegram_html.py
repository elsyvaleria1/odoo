from unittest.mock import patch

from odoo.exceptions import UserError

from .test_approval_request import ApprovalRequestTestBase
from odoo.addons.approval_telegram.services.approval_notifier import (
    TelegramApprovalNotifier,
)
from odoo.addons.telegram.models.telegram_bot import TelegramBot


class TestApprovalReplyEscaping(ApprovalRequestTestBase):
    def _approve(self, **approve_patch):
        handler = self.env["telegram.handler.approval"]
        with (
            patch.object(TelegramApprovalNotifier, "_approve", **approve_patch),
            patch.object(TelegramBot, "send_message") as mock_send,
        ):
            handler._approve_request(self.test_bot, self.test_chat, {}, self.approver)
        return mock_send.call_args

    def test_an_approval_error_arrives_as_literal_text(self):
        call = self._approve(side_effect=UserError("Step <x> & co_*"))

        self.assertIn("Step &lt;x&gt; &amp; co_*", call.args[1])
        self.assertNotIn("<x>", call.args[1])
        self.assertNotIn("parse_mode", call.kwargs)

    def test_the_approved_request_name_arrives_as_literal_text(self):
        self.approval_request.name = "REQ<1>&_"

        call = self._approve(return_value=True)

        self.assertIn("REQ&lt;1&gt;&amp;_", call.args[1])
