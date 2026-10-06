from odoo.exceptions import AccessError
from odoo.tests import new_test_user, tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestCategoryScope(TransactionCase):
    def test_an_accounting_manager_writes_only_accounting_categories(self):
        manager = new_test_user(
            self.env,
            login="scope_account_manager",
            groups="account.group_account_manager",
        )
        general, payment = self.env["approval.category"].create(
            [
                {"name": "Scope General", "approval_type": "general"},
                {"name": "Scope Payment", "approval_type": "payment"},
            ]
        )
        with self.assertRaises(AccessError):
            general.with_user(manager).write({"allow_self_approval": True})
        payment.with_user(manager).write({"allow_self_approval": True})
        self.assertTrue(payment.allow_self_approval)
