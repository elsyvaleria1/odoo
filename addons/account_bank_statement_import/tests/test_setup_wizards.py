from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestSetupBankManualConfigWizard(AccountTestInvoicingCommon):
    """Unit tests for wizard.res.partner.bank.account.create's action_finish_bank_setup() override,
    which defaults bank_statements_source on the linked journal."""

    def _neutralize_other_bank_journal_candidates(self):
        """Give every journal that currently matches the wizard's
        "unlinked bank journal" domain a bank account, so it stops matching
        and a journal set up by the test becomes the sole candidate."""
        wiz_new = self.env["wizard.res.partner.bank.account.create"].new({})
        domain = wiz_new._get_domain_unlinked_journal("bank")
        others = self.env["account.journal"].search(domain)
        if others:
            dummy_bank = self.env["res.partner.bank.account"].create(
                {
                    "acc_number": "BE71096123456769",
                    "partner_id": self.env.company.partner_id.id,
                }
            )
            others.bank_account_id = dummy_bank.id

    def test_validate_does_not_clobber_already_configured_source(self):
        """A journal already connected to Online Synchronization, but with
        no bank_account_id yet, must keep its bank_statements_source when
        this wizard is completed -- num_journals_without_account_bank == 0
        must not force it back to 'file_import'."""
        self._neutralize_other_bank_journal_candidates()
        journal = self.env["account.journal"].create(
            {
                "name": "Online Sync Journal",
                "code": "OSYNC",
                "type": "bank",
                "company_id": self.env.company.id,
                "bank_statements_source": "online_sync",
            }
        )
        wiz = self.env["wizard.res.partner.bank.account.create"].create(
            {"acc_number": "BE15001559627230"}
        )
        self.assertEqual(wiz.linked_journal_id, journal)
        self.assertEqual(wiz.num_journals_without_account_bank, 0)

        wiz.action_finish_bank_setup()

        self.assertEqual(journal.bank_statements_source, "online_sync")

    def test_validate_still_defaults_undefined_source(self):
        """The wizard's actual purpose -- defaulting a brand-new bank
        journal's source to 'file_import' -- must keep working."""
        self._neutralize_other_bank_journal_candidates()
        journal = self.env["account.journal"].create(
            {
                "name": "New Bank Journal",
                "code": "NEWBK",
                "type": "bank",
                "company_id": self.env.company.id,
            }
        )
        self.assertEqual(journal.bank_statements_source, "undefined")
        wiz = self.env["wizard.res.partner.bank.account.create"].create(
            {"acc_number": "BE68539007547034"}
        )
        self.assertEqual(wiz.linked_journal_id, journal)

        wiz.action_finish_bank_setup()

        self.assertEqual(journal.bank_statements_source, "file_import")
