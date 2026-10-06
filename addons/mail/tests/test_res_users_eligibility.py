from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestActivationNotice(TransactionCase):
    def test_an_activation_is_told_to_the_access_administrators(self):
        administrator = new_test_user(
            self.env, login="access_admin", groups="base.group_erp_manager"
        )
        person = new_test_user(self.env, login="eligible", groups="base.group_user")
        eligibility = self.env["res.users.eligibility"].create(
            {
                "user_id": person.id,
                "group_id": self.env.ref("base.group_partner_manager").id,
            }
        )
        eligibility.with_user(person).action_activate(1, "merge two partners")
        notices = self.env["mail.message"].search(
            [("partner_ids", "in", administrator.partner_id.ids)]
        )
        self.assertTrue(notices)
        self.assertIn("merge two partners", notices[0].body)
        self.assertNotIn(
            person.partner_id,
            notices.partner_ids,
            "the person activating is not told of their own activation",
        )
