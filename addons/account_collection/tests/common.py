from odoo import Command, fields
from odoo.tests.common import new_test_user

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


class CollectionCommon(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.company_data["company"]
        cls.custody_account = cls.env["account.account"].create(
            {
                "name": "Collections in custody",
                "code": "101999",
                "account_type": "asset_current",
                "reconcile": True,
            }
        )
        cls.custody_journal = cls.env["account.journal"].create(
            {
                "name": "Field Collections",
                "code": "FCOL",
                "type": "cash",
                "company_id": company.id,
                "default_account_id": cls.custody_account.id,
            }
        )
        cls.custody_journal.inbound_payment_channel_ids.payment_account_id = (
            cls.custody_account
        )
        cls.custody_journal.is_collection_custody = True
        cls.till_journal = cls.company_data["default_journal_cash"]
        cls.bank_journal = cls.company_data["default_journal_bank"]
        config = company.account_config_id
        cls.shortage_account = cls.env["account.account"].create(
            {
                "name": "Collector shortages",
                "code": "107999",
                "account_type": "asset_current",
                "reconcile": True,
            }
        )
        cls.overage_account = cls.env["account.account"].create(
            {
                "name": "Collector overages",
                "code": "499999",
                "account_type": "income_other",
            }
        )
        config.collection_shortage_account_id = cls.shortage_account
        config.collection_overage_account_id = cls.overage_account
        cls.collector = new_test_user(
            cls.env,
            login="field_collector",
            groups="base.group_user,account_collection.group_collection_collector",
            company_id=company.id,
            company_ids=[Command.set(company.ids)],
        )
        cls.other_collector = new_test_user(
            cls.env,
            login="field_collector_2",
            groups="base.group_user,account_collection.group_collection_collector",
            company_id=company.id,
            company_ids=[Command.set(company.ids)],
        )
        cls.treasurer = new_test_user(
            cls.env,
            login="field_treasurer",
            groups="base.group_user,account.group_account_invoice",
            company_id=company.id,
            company_ids=[Command.set(company.ids)],
        )
        cls.today = fields.Date.today()

    @classmethod
    def _post_invoice(cls, amount=1000.0, partner=None):
        return cls.init_invoice(
            "out_invoice",
            partner=partner,
            amounts=[amount],
            taxes=[],
            post=True,
        )

    @classmethod
    def _collect(
        cls, invoices, amount, collector=None, date=None, method="cash", check_date=None
    ):
        collector = collector or cls.collector
        return (
            invoices.with_user(collector)
            .with_privilege(
                "account_collection.privilege_register_collection",
                reason="the collector records what the customer paid them",
            )
            ._create_collection_payment(
                amount,
                date or cls.today,
                method,
                collector,
                cls.custody_journal,
                check_date=check_date,
            )
        )
