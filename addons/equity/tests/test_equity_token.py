from datetime import timedelta

from odoo import fields
from odoo.tests import HttpCase, new_test_user, tagged
from odoo.tools import mute_logger

from odoo.addons.base.models.access_link import hash_token
from odoo.addons.equity.tests.common import TestEquityCommon


@tagged("post_install", "-at_install")
class TestEquityToken(TestEquityCommon, HttpCase):
    def _links(self, partner):
        return (
            self.env["access.link"]
            .sudo()
            .search([("res_model", "=", "res.partner"), ("res_id", "=", partner.id)])
        )

    def test_an_equity_manager_mails_a_link_in_the_partner_s_name(self):
        manager = new_test_user(
            self.env, login="equity_token_manager", groups="equity.group_equity_manager"
        )
        partner = self.contact_1.with_user(manager)

        token = partner._equity_get_or_create_token()

        partner_id, _separator, secret = token.partition("$")
        link = self._links(self.contact_1)
        self.assertEqual(partner_id, str(self.contact_1.id))
        self.assertEqual(
            (len(link), link.partner_id, link.role, link.token_hash),
            (1, self.contact_1, "comment", hash_token(secret)),
        )
        self.assertEqual(partner._equity_get_or_create_token(), token)

    def test_each_mail_carries_the_link_a_year_further(self):
        token = self.contact_1._equity_get_or_create_token()
        link = self._links(self.contact_1)
        link.write({"date_to": fields.Datetime.now() + timedelta(days=5)})

        self.assertEqual(self.contact_1._equity_get_or_create_token(), token)
        self.assertGreater(link.date_to, fields.Datetime.now() + timedelta(days=364))

    @mute_logger("odoo.http")
    def test_only_a_live_link_of_that_partner_opens_its_equity(self):
        token = self.contact_1._equity_get_or_create_token()
        other = self.contact_2._equity_get_or_create_token()
        secret = token.partition("$")[2]

        self.assertEqual(
            self.url_open(f"/my/equity?access_token={token}").status_code, 200
        )
        for refused in (
            f"{self.contact_1.id}${'x' * 32}",
            f"{self.contact_1.id}${other.partition('$')[2]}",
            f"abc${secret}",
            "no-separator",
        ):
            with self.subTest(token=refused):
                self.assertEqual(
                    self.url_open(f"/my/equity?access_token={refused}").status_code,
                    404,
                )
        self._links(self.contact_1).action_revoke("a test")
        self.assertEqual(
            self.url_open(f"/my/equity?access_token={token}").status_code, 404
        )
