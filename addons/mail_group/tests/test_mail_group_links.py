import re
from urllib.parse import urlsplit

from odoo.tests import HttpCase, tagged

from odoo.addons.mail_group.tests.common import TestMailListCommon


@tagged("post_install", "-at_install")
class TestMailGroupConfirmationLinks(TestMailListCommon, HttpCase):

    def _link(self, email, action):
        url = urlsplit(self.test_group._generate_action_url(email, action))
        return f"{url.path}?{url.query}"

    def _confirm(self, link, opened):
        csrf_token = re.search(
            r'name="csrf_token"\s+value="([^"]+)"', opened.text
        ).group(1)
        return self.url_open(link, data={"csrf_token": csrf_token})

    def _members(self, email):
        return self.env["mail.group.member"].search(
            [
                ("mail_group_id", "=", self.test_group.id),
                ("email_normalized", "=", email),
            ]
        )

    def test_opening_a_subscription_link_joins_nobody_and_its_page_does(self):
        link = self._link("joining@test.example.com", "subscribe")

        opened = self.url_open(link)
        self.assertEqual(opened.status_code, 200)
        self.assertIn("o_mail_group_confirm", opened.text)
        self.assertFalse(
            self._members("joining@test.example.com"), "opening the link joined"
        )

        confirmed = self._confirm(link, opened)
        self.assertEqual(confirmed.status_code, 200)
        self.assertTrue(self._members("joining@test.example.com"))

    def test_opening_an_unsubscription_link_removes_nobody_and_its_page_does(self):
        link = self._link("member_2@test.com", "unsubscribe")

        opened = self.url_open(link)
        self.assertEqual(opened.status_code, 200)
        self.assertIn("o_mail_group_confirm", opened.text)
        self.assertTrue(self._members("member_2@test.com"), "opening the link left")

        self._confirm(link, opened)
        self.assertFalse(self._members("member_2@test.com"))

    def test_a_forged_link_neither_asks_nor_acts(self):
        link = self._link("member_2@test.com", "unsubscribe").replace(
            "token=", "token=x"
        )
        for method in ("GET", "POST"):
            with self.subTest(method=method):
                response = self.url_open(link, method=method)
                self.assertNotIn("o_mail_group_confirm", response.text)
        self.assertTrue(self._members("member_2@test.com"))
