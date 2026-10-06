from unittest.mock import patch

from odoo.exceptions import AccessError
from odoo.service.model import call_kw
from odoo.tests import new_test_user, tagged

from .common import AccountOnlineSynchronizationCommon


@tagged("post_install", "-at_install")
class TestOnlineLinkRpcElevation(AccountOnlineSynchronizationCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.auditor = new_test_user(
            cls.env,
            login="online_link_auditor",
            groups="base.group_user,account.group_account_readonly",
            company_id=cls.env.company.id,
        )
        cls.links_as_auditor = cls.env["account.online.link"].with_user(cls.auditor)

    def test_a_reader_rewrites_no_token_of_the_link(self):
        link = self.account_online_link
        self.assertTrue(link.with_user(self.auditor).has_access("read"))
        before = link.sudo().read(["client_id", "refresh_token"])[0]
        proxy = {"client_id": "stolen", "refresh_token": "stolen"}
        with (
            patch.object(type(link), "_get_odoo_fin", return_value=proxy) as odoo_fin,
            self.assertRaises(AccessError),
        ):
            call_kw(self.links_as_auditor, "exchange_token", [[link.id], "x"], {})
        odoo_fin.assert_not_called()
        link.invalidate_recordset()
        self.assertEqual(link.sudo().read(["client_id", "refresh_token"])[0], before)

    def test_a_reader_creates_no_bank_journal(self):
        journals = self.env["account.journal"].search_count([])
        with self.assertRaises(AccessError):
            call_kw(
                self.links_as_auditor,
                "create_new_bank_account_action",
                [
                    [self.account_online_link.id],
                    {"account_number": "BE71096123456769", "name": "Rogue Bank"},
                ],
                {},
            )
        self.assertEqual(self.env["account.journal"].search_count([]), journals)
        self.assertFalse(self.env["res.bank"].search([("name", "=", "Rogue Bank")]))
