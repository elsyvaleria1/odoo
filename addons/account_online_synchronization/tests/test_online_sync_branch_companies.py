from odoo.tests import tagged

from odoo.addons.account_online_synchronization.tests.common import (
    AccountOnlineSynchronizationCommon,
)


@tagged("post_install", "-at_install")
class TestSynchInBranches(AccountOnlineSynchronizationCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.mother_company = cls.env["res.company"].create(
            {"name": "Mother company 2000"}
        )
        cls.branch_company = cls.env["res.company"].create(
            {"name": "Branch company", "parent_id": cls.mother_company.id}
        )

        cls.mother_bank_journal = cls.env["account.journal"].create(
            {
                "name": "Mother Bank Journal",
                "type": "bank",
                "code": "MBJ",
                "company_id": cls.mother_company.id,
            }
        )
        cls.mother_account_online_link = cls.env["account.online.link"].create(
            {
                "name": "Test Bank",
                "client_id": "client_id_1",
                "refresh_token": "refresh_token",
                "access_token": "access_token",
                "company_id": cls.mother_company.id,
            }
        )

    def test_show_sync_actions(self):
        self.assertTrue(
            self.mother_account_online_link.with_context(
                allowed_company_ids=(self.mother_company)._ids
            )
            .with_company(self.mother_company)
            .show_sync_actions
        )

        self.assertTrue(
            self.mother_account_online_link.with_context(
                allowed_company_ids=(self.branch_company + self.mother_company)._ids
            )
            .with_company(self.mother_company)
            .show_sync_actions
        )

        self.assertTrue(
            self.mother_account_online_link.with_context(
                allowed_company_ids=(self.branch_company + self.mother_company)._ids
            )
            .with_company(self.branch_company)
            .show_sync_actions
        )

        self.assertFalse(
            self.mother_account_online_link.with_context(
                allowed_company_ids=(self.branch_company)._ids
            )
            .with_company(self.branch_company)
            .show_sync_actions
        )

    def test_show_bank_connect(self):
        dashboard_data = (
            self.mother_bank_journal.with_context(
                allowed_company_ids=(self.mother_company)._ids
            )
            .with_company(self.mother_company)
            ._get_journal_dashboard_data_batched()
        )
        self.assertTrue(
            dashboard_data[self.mother_bank_journal.id].get(
                "display_connect_bank_in_dashboard"
            )
        )

        dashboard_data = (
            self.mother_bank_journal.with_context(
                allowed_company_ids=(self.branch_company + self.mother_company)._ids
            )
            .with_company(self.branch_company)
            ._get_journal_dashboard_data_batched()
        )
        self.assertFalse(
            dashboard_data[self.mother_bank_journal.id].get(
                "display_connect_bank_in_dashboard"
            )
        )
