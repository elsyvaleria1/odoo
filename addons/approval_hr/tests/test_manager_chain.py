from odoo.tests.common import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestManagerChain(TransactionCase):
    def _employee(self, login, parent=None):
        user = new_test_user(self.env, login=login, groups="base.group_user")
        return self.env["hr.employee"].create(
            {
                "name": login,
                "user_id": user.id,
                "parent_id": parent.id if parent else False,
                "company_id": self.env.company.id,
            }
        )

    def test_the_chain_is_the_managers_above_nearest_first(self):
        top = self._employee("chain_top")
        mid = self._employee("chain_mid", parent=top)
        asker = self._employee("chain_asker", parent=mid)
        request = self.env["approval.request"].new({"company_id": self.env.company.id})
        self.assertTrue(request._supplies_manager_chain())
        chain = request.with_user(asker.user_id)._get_manager_chain(asker.user_id)
        self.assertEqual(chain.ids, (mid.user_id | top.user_id).ids)
        self.assertFalse(request._get_manager_chain(top.user_id))
