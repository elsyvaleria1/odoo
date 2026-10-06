from odoo.tests import TransactionCase

from odoo.addons.mail.tests.discuss.test_discuss_channel_policy import (
    mock_channel_type_policies,
)


class TestTelegramChannelTypePolicy(TransactionCase):
    def test_the_hoot_mock_server_serves_the_python_telegram_row(self):
        policy = self.env["discuss.channel"]._channel_type_policy_map()["telegram"]
        self.assertEqual(
            mock_channel_type_policies(
                "mail_telegram/static/tests/mock_server/discuss_channel_mock_patch.js"
            ),
            {"telegram": policy._client_flags()},
        )
