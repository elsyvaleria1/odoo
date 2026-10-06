from odoo.exceptions import AccessError, UserError
from odoo.fields import Command
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestSimulate(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = new_test_user(
            cls.env, login="access_admin", groups="base.group_erp_manager"
        )
        cls.person = new_test_user(cls.env, login="person", groups="base.group_user")
        cls.blinded = cls.env["res.groups"].create({"name": "Probe: blinded"})
        cls.admin.group_ids = [Command.link(cls.blinded.id)]
        cls.env["ir.access"].create(
            {
                "name": "Probe: the blinded read no secret",
                "model_id": cls.env["ir.model"]._get_id("res.partner.industry"),
                "group_id": cls.blinded.id,
                "kind": "guard",
                "guard_scope": "members",
                "operation": "r",
                "domain": "[('name', 'not like', 'secret')]",
            }
        )
        Industry = cls.env["res.partner.industry"]
        cls.common = Industry.create({"name": "probe common"})
        cls.secret = Industry.create({"name": "probe secret"})

    def simulate(self):
        wizard = (
            self.env["wizard.res.users.simulate.access"]
            .with_user(self.admin)
            .create(
                {
                    "user_id": self.person.id,
                    "model_name": "res.partner.industry",
                    "domain": "[('name', 'like', 'probe')]",
                }
            )
        )
        wizard.action_simulate()
        return wizard

    def test_the_counts_are_the_principals_and_only_both_readable_ids_show(self):
        wizard = self.simulate()
        theirs = (
            self.env["res.partner.industry"]
            .with_user(self.person)
            .search([("name", "like", "probe")])
        )
        self.assertIn(self.secret, theirs)
        self.assertEqual(wizard.reached_count, len(theirs))
        self.assertEqual(wizard.hidden_count, 1)
        self.assertIn(self.common.id, wizard.shared_ids)
        self.assertNotIn(
            self.secret.id, (wizard.shared_ids or []) + (wizard.extra_ids or [])
        )
        opened = wizard.action_open_shared()
        self.assertEqual(opened["domain"], [("id", "in", wizard.shared_ids)])
        log = self.env["ir.access.log"].search(
            [("event", "=", "simulated"), ("actor_id", "=", self.admin.id)]
        )
        self.assertEqual(log.subject_user_id, self.person)
        self.assertEqual(log.count, len(theirs))

    def test_simulate_is_for_the_access_administrators_about_someone_else(self):
        with self.assertRaises(AccessError):
            self.env["wizard.res.users.simulate.access"].with_user(self.person).create(
                {"user_id": self.admin.id, "model_name": "res.partner.industry"}
            )
        own = (
            self.env["wizard.res.users.simulate.access"]
            .with_user(self.admin)
            .create({"user_id": self.admin.id, "model_name": "res.partner.industry"})
        )
        with self.assertRaises(UserError):
            own.action_simulate()
