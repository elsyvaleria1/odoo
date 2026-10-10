from odoo.tests import tagged
from odoo.tools import formataddr

from odoo.addons.mail.models.base import _MAIL_REPLY_TO_LENGTH_LIMIT
from odoo.addons.mail.tests.common import MailCommon


@tagged("mail_notification")
class TestReplyToLengthBoundary(MailCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.record = cls.env["res.partner"].create({"name": "Reply-To Boundary"})
        cls.author = cls.env["res.partner"].create({"name": "The Author"})

    def _name_of_exact_length(self, address, length):
        for size in range(1, length):
            name = "A" * size
            if len(formataddr((name, address))) == length:
                return name
        raise ValueError(f"no name gives a {length}-character reply-to for {address}")

    def test_reply_to_at_the_limit_keeps_the_author(self):
        address = "catchall.test@test.mycompany.com"
        self.author.name = self._name_of_exact_length(
            address, _MAIL_REPLY_TO_LENGTH_LIMIT
        )
        formatted = self.record._notify_get_reply_to_formatted_email(
            address, author_id=self.author.id
        )
        self.assertEqual(len(formatted), _MAIL_REPLY_TO_LENGTH_LIMIT)
        self.assertEqual(formatted, formataddr((self.author.name, address)))

    def test_reply_to_over_the_limit_drops_the_name(self):
        address = "catchall.test@test.mycompany.com"
        self.author.name = self._name_of_exact_length(
            address, _MAIL_REPLY_TO_LENGTH_LIMIT + 1
        )
        formatted = self.record._notify_get_reply_to_formatted_email(
            address, author_id=self.author.id
        )
        self.assertLessEqual(len(formatted), _MAIL_REPLY_TO_LENGTH_LIMIT)
        self.assertNotIn(
            self.author.name, formatted, "the over-long author name must not survive"
        )
