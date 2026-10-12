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

    def test_a_domain_cannot_probe_what_only_they_read(self):
        counts = []
        for probe in ("[('name', '=', 'probe secret')]", "[('name', '=', 'nothing')]"):
            wizard = (
                self.env["wizard.res.users.simulate.access"]
                .with_user(self.admin)
                .create(
                    {
                        "user_id": self.person.id,
                        "model_name": "res.partner.industry",
                        "domain": probe,
                    }
                )
            )
            wizard.action_simulate()
            counts.append((wizard.hidden_count, wizard.reached_count))
        self.assertEqual(counts[0], counts[1])

    def test_a_domain_through_a_relation_cannot_probe_what_only_they_read(self):
        Tag = self.env["res.partner.tag"]
        self.env["ir.access"].create(
            {
                "name": "Probe: the blinded read no secret tag",
                "model_id": self.env["ir.model"]._get_id("res.partner.tag"),
                "group_id": self.blinded.id,
                "kind": "guard",
                "guard_scope": "members",
                "operation": "r",
                "domain": "[('name', 'not like', 'secret')]",
            }
        )
        secret = Tag.create({"name": "probe secret"})
        partner = self.env["res.partner"].create(
            {"name": "Probe tagged", "tag_ids": [Command.link(secret.id)]}
        )
        counts = []
        for guess in ("probe secret", "probe other"):
            wizard = (
                self.env["wizard.res.users.simulate.access"]
                .with_user(self.admin)
                .create(
                    {
                        "user_id": self.person.id,
                        "model_name": "res.partner",
                        "domain": f"[('id', '=', {partner.id}), ('tag_ids', "
                        f"'not any', [('name', '=', '{guess}')])]",
                    }
                )
            )
            wizard.action_simulate()
            counts.append((wizard.shared_count, wizard.extra_count))
        self.assertEqual(counts, [(1, 0), (1, 0)])

    def test_archived_records_the_domain_selects_are_simulated_too(self):
        self.common.active = False
        wizard = (
            self.env["wizard.res.users.simulate.access"]
            .with_user(self.admin)
            .create(
                {
                    "user_id": self.person.id,
                    "model_name": "res.partner.industry",
                    "domain": "[('name', '=', 'probe common'), "
                    "('active', 'in', [True, False])]",
                }
            )
        )
        wizard.action_simulate()
        self.assertEqual(wizard.shared_ids, [self.common.id])

    def test_both_reaches_span_every_company_each_works_in(self):
        elsewhere = self.env["res.company"].create({"name": "Simulate elsewhere"})
        (self.admin | self.person).company_ids = [Command.link(elsewhere.id)]
        partner = self.env["res.partner"].create(
            {"name": "Simulate in elsewhere", "company_id": elsewhere.id}
        )
        wizard = (
            self.env["wizard.res.users.simulate.access"]
            .with_user(self.admin)
            .with_context(allowed_company_ids=self.env.company.ids)
            .create(
                {
                    "user_id": self.person.id,
                    "model_name": "res.partner",
                    "domain": f"[('id', '=', {partner.id})]",
                }
            )
        )
        wizard.action_simulate()
        self.assertEqual(wizard.shared_ids, partner.ids)
        self.assertEqual(wizard.hidden_count, 0)
