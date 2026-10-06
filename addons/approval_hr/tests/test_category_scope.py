from odoo.exceptions import AccessError
from odoo.tests import new_test_user, tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestCategoryScope(TransactionCase):
    def test_an_hr_manager_writes_only_hr_categories(self):
        manager = new_test_user(
            self.env, login="scope_hr_manager", groups="hr.group_hr_manager"
        )
        general, hr = self.env["approval.category"].create(
            [
                {"name": "Scope General", "approval_type": "general"},
                {"name": "Scope HR", "approval_type": "hr"},
            ]
        )
        with self.assertRaises(AccessError):
            general.with_user(manager).action_archive()
        hr.with_user(manager).action_archive()
        self.assertFalse(hr.active)
