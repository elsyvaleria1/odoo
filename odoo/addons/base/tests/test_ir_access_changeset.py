from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.service.model import calling
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestChangeset(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = new_test_user(
            cls.env, login="access_admin", groups="base.group_erp_manager"
        )
        cls.readers = cls.env["res.groups"].create({"name": "Probe: industry readers"})
        cls.reader = new_test_user(cls.env, login="reader", groups="base.group_user")
        cls.reader.group_ids = [Command.link(cls.readers.id)]
        cls.model_id = cls.env["ir.model"]._get_id("res.partner.industry")
        cls.guard = cls.env["ir.access"].create(
            {
                "name": "Probe: readers read only the a-industries",
                "model_id": cls.model_id,
                "group_id": cls.readers.id,
                "kind": "guard",
                "guard_scope": "members",
                "operation": "r",
                "domain": "[('name', '=like', 'a%')]",
            }
        )
        if "approval.binding" in cls.env:
            cls.env["approval.binding"].sudo().search(
                [
                    (
                        "model_id",
                        "=",
                        cls.env["ir.model"]._get_id("ir.access.changeset"),
                    ),
                    ("verb", "=", "activate"),
                ]
            ).write({"active": False})
        Industry = cls.env["res.partner.industry"]
        cls.agro = Industry.create({"name": "agro probe"})
        cls.banking = Industry.create({"name": "banking probe"})

    def reads(self, record):
        return record.with_user(self.reader).has_access("read")

    def changeset(self):
        return self.env["ir.access.changeset"].search(
            [("author_id", "=", self.admin.id), ("state", "=", "draft")]
        )

    def test_a_persons_edit_waits_for_its_change_set(self):
        with calling("ir.access"):
            self.guard.with_user(self.admin).write(
                {"domain": "[('name', '=like', 'b%')]"}
            )
        self.assertEqual(self.guard.domain, "[('name', '=like', 'a%')]")
        self.assertTrue(self.reads(self.agro))
        self.assertFalse(self.reads(self.banking))
        changeset = self.changeset()
        self.assertEqual(changeset.line_ids.operation, "write")
        self.assertEqual(
            changeset.line_ids.values_before, {"domain": "[('name', '=like', 'a%')]"}
        )
        changeset.with_user(self.admin).action_propose()
        Industries = self.env["res.partner.industry"].with_context(active_test=False)
        before = Industries.search_count([("name", "=like", "a%")])
        after = Industries.search_count([("name", "=like", "b%")])
        self.assertEqual(
            changeset.impact[str(self.reader.id)]["res.partner.industry"]["read"],
            [before, after, after, before],
        )
        self.assertIn(self.reader.name, changeset.impact_summary)
        self.assertTrue(self.reads(self.agro), "the impact is a dry run")
        changeset.action_activate()
        self.assertEqual(self.guard.domain, "[('name', '=like', 'b%')]")
        self.assertFalse(self.reads(self.agro))
        self.assertTrue(self.reads(self.banking))
        self.assertTrue(
            self.env["ir.access.log"].search(
                [
                    ("event", "=", "security_changed"),
                    ("model_name", "=", "ir.access"),
                    ("res_ids", "=", str(self.guard.id)),
                    ("operation", "=", "write"),
                ]
            )
        )

    def test_a_new_row_is_inactive_and_a_deleted_one_stays_until_activation(self):
        Access = self.env["ir.access"].with_user(self.admin)
        with calling("ir.access"):
            row = Access.create(
                {
                    "name": "Probe: staged row",
                    "model_id": self.model_id,
                    "group_id": self.readers.id,
                    "kind": "guard",
                    "guard_scope": "members",
                    "operation": "r",
                    "domain": "[('name', '!=', 'agro probe')]",
                }
            )
        self.assertFalse(row.active)
        self.assertTrue(self.reads(self.agro))
        with calling("ir.access"):
            self.guard.with_user(self.admin).unlink()
        self.assertTrue(self.guard.exists())
        self.changeset().action_activate()
        self.assertTrue(row.active)
        self.assertFalse(self.guard.exists())
        self.assertFalse(self.reads(self.agro))

    def test_a_stale_change_set_is_refused(self):
        with calling("ir.access"):
            self.guard.with_user(self.admin).write(
                {"domain": "[('name', '=like', 'b%')]"}
            )
        self.guard.write({"domain": "[('name', '=like', 'c%')]"})
        with self.assertRaises(UserError):
            self.changeset().action_activate()

    def test_a_rollback_restores_what_the_change_set_changed(self):
        with calling("ir.access"):
            self.guard.with_user(self.admin).write(
                {"domain": "[('name', '=like', 'b%')]"}
            )
        changeset = self.changeset()
        changeset.action_activate()
        action = changeset.with_user(self.admin).action_rollback()
        rollback = self.env["ir.access.changeset"].browse(action["res_id"])
        self.assertEqual(rollback.rollback_of_id, changeset)
        rollback.action_activate()
        self.assertEqual(self.guard.domain, "[('name', '=like', 'a%')]")
        self.assertTrue(self.reads(self.agro))

    def test_a_group_implication_stages_and_a_feature_or_a_module_does_not(self):
        implied = self.env.ref("base.group_partner_manager")
        readers = self.readers.with_user(self.admin)
        with calling("res.groups"):
            readers.implied_ids = [Command.link(implied.id)]
        self.assertNotIn(implied, self.readers.implied_ids)
        with calling("res.partner"):
            readers.implied_ids = [Command.link(implied.id)]
        self.assertIn(implied, self.readers.implied_ids, "a feature's doing")
        self.readers.implied_ids = [Command.unlink(implied.id)]
        with calling("res.groups"):
            self.readers.with_context(install_module="probe").with_user(
                self.admin
            ).implied_ids = [Command.link(implied.id)]
        self.assertIn(implied, self.readers.implied_ids, "a module's load")

    def test_the_model_form_and_an_import_stage_as_the_access_form_does(self):
        for door in ("ir.model", "base_import.import"):
            with self.subTest(door=door), calling(door):
                self.guard.with_user(self.admin).write(
                    {"domain": "[('name', '=like', 'b%')]"}
                )
                self.assertEqual(self.guard.domain, "[('name', '=like', 'a%')]")
                self.assertTrue(self.reads(self.agro))

    def test_a_staged_eligibility_cannot_be_activated_before_its_change_set(self):
        with calling("res.users"):
            eligibility = (
                self.env["res.users.eligibility"]
                .with_user(self.admin)
                .create(
                    {
                        "user_id": self.reader.id,
                        "group_id": self.env.ref("base.group_partner_manager").id,
                    }
                )
            )
        self.assertEqual(eligibility.state, "staged")
        with self.assertRaises(UserError):
            eligibility.with_user(self.reader).action_activate(1, "too early")
        self.changeset().action_activate()
        self.assertEqual(eligibility.state, "active")
        eligibility.with_user(self.reader).action_activate(1, "now")

    def test_making_someone_eligible_is_another_persons_to_activate(self):
        with calling("res.users"):
            self.env["res.users.eligibility"].with_user(self.admin).create(
                {
                    "user_id": self.reader.id,
                    "group_id": self.env.ref("base.group_system").id,
                    "justification_required": False,
                }
            )
        changeset = self.changeset()
        with self.assertRaisesRegex(UserError, "another access administrator"):
            changeset.with_user(self.admin).action_activate()
        other = new_test_user(
            self.env, login="access_admin_2", groups="base.group_erp_manager"
        )
        changeset.with_user(other).action_activate()
        self.assertEqual(changeset.state, "active")

    def test_narrowing_an_eligibility_is_its_authors_to_activate(self):
        eligibility = self.env["res.users.eligibility"].create(
            {
                "user_id": self.reader.id,
                "group_id": self.env.ref("base.group_system").id,
                "max_hours": 8,
            }
        )
        company = self.env.company
        with calling("res.users"):
            eligibility.with_user(self.admin).write(
                {"max_hours": 2, "company_ids": [Command.set(company.ids)]}
            )
        self.changeset().with_user(self.admin).action_activate()
        self.assertEqual((eligibility.max_hours, eligibility.company_ids), (2, company))
        with calling("res.users"):
            eligibility.with_user(self.admin).write({"company_ids": [Command.clear()]})
        with self.assertRaisesRegex(UserError, "another access administrator"):
            self.changeset().with_user(self.admin).action_activate()

    def test_activation_bumps_the_policy_version(self):
        parameters = self.env["ir.config_parameter"]
        before = int(parameters.get_param("base.access_policy_version", "0"))
        with calling("ir.access"):
            self.guard.with_user(self.admin).write(
                {"domain": "[('name', '=like', 'b%')]"}
            )
        changeset = self.changeset()
        changeset.action_activate()
        self.assertEqual(changeset.policy_version, before + 1)
        self.assertEqual(
            int(parameters.get_param("base.access_policy_version")), before + 1
        )

    def stage(self, domain):
        with calling("ir.access"):
            self.guard.with_user(self.admin).write({"domain": domain})
        return self.changeset()

    def test_a_widening_is_another_persons_to_activate(self):
        changeset = self.stage("[('name', '!=', False)]")
        changeset.with_user(self.admin).action_propose()

        with self.assertRaisesRegex(UserError, "another access administrator"):
            changeset.with_user(self.admin).action_activate()
        self.assertFalse(self.reads(self.banking))

        other = new_test_user(
            self.env, login="access_admin_2", groups="base.group_erp_manager"
        )
        changeset.with_user(other).action_activate()
        self.assertTrue(self.reads(self.banking))
        self.assertEqual(changeset.state, "active")

    def test_a_narrowing_its_author_activates(self):
        changeset = self.stage("[('name', '=like', 'agro%')]")
        changeset.with_user(self.admin).action_propose()
        changeset.with_user(self.admin).action_activate()
        self.assertEqual(changeset.state, "active")

    def test_what_is_activated_is_what_was_reviewed(self):
        changeset = self.stage("[('name', '=like', 'b%')]")
        changeset.with_user(self.admin).action_propose()
        other = new_test_user(
            self.env, login="access_admin_2", groups="base.group_erp_manager"
        )
        self.reader.group_ids = [Command.unlink(self.readers.id)]

        with self.assertRaisesRegex(UserError, "propose it again"):
            changeset.with_user(other).action_activate()

        changeset.write({"state": "draft"})
        changeset.with_user(self.admin).action_propose()
        changeset.with_user(other).action_activate()
        self.assertEqual(changeset.state, "active")

    def test_an_implication_written_from_the_implied_side_stages(self):
        implied = self.env.ref("base.group_partner_manager")
        with calling("res.groups"):
            implied.with_user(self.admin).implied_by_ids = [
                Command.link(self.readers.id)
            ]
        self.assertNotIn(implied, self.readers.implied_ids)
        self.assertEqual(self.changeset().line_ids.mapped("res_id"), [self.readers.id])
        self.changeset().action_activate()
        self.assertIn(implied, self.readers.implied_ids)

    def test_who_staged_a_change_set_is_not_rewritten_by_hand(self):
        changeset = self.stage("[('name', '!=', False)]")
        other = new_test_user(
            self.env, login="access_admin_2", groups="base.group_erp_manager"
        )
        for values in (
            {"author_id": other.id},
            {"state": "active"},
            {"impact": {"": {}}},
        ):
            with self.subTest(values=values), self.assertRaises(UserError):
                changeset.with_user(self.admin).write(values)
        self.assertEqual(changeset.author_id, self.admin)

    def test_a_change_set_is_created_a_draft_of_its_author(self):
        other = new_test_user(
            self.env, login="access_admin_2", groups="base.group_erp_manager"
        )
        Changesets = self.env["ir.access.changeset"].with_user(self.admin)
        for values in (
            {"author_id": other.id},
            {"state": "active", "activated_by_id": other.id},
            {"cause": "module_update", "module": "base"},
        ):
            with self.subTest(values=values), self.assertRaises(UserError):
                Changesets.create({"name": "Probe: forged", **values})
        draft = Changesets.create(
            {"name": "Probe: by hand", "author_id": self.admin.id, "state": "draft"}
        )
        self.assertEqual((draft.author_id, draft.state), (self.admin, "draft"))

    def assertAuthorCannotActivate(self, changeset):
        changeset.with_user(self.admin).action_propose()
        with self.assertRaisesRegex(UserError, "another access administrator"):
            changeset.with_user(self.admin).action_activate()

    def test_a_widening_for_portal_users_is_another_persons_to_activate(self):
        new_test_user(self.env, login="industry_portal", groups="base.group_portal")
        row = self.env["ir.access"].create(
            {
                "name": "Probe: portal users read the a-industries",
                "model_id": self.model_id,
                "group_id": self.env.ref("base.group_portal").id,
                "kind": "permission",
                "operation": "r",
                "domain": "[('name', '=like', 'a%')]",
            }
        )
        with calling("ir.access"):
            row.with_user(self.admin).write({"domain": "[('name', '!=', False)]"})
        self.assertAuthorCannotActivate(self.changeset())

    def test_a_widening_through_a_predicate_is_another_persons_to_activate(self):
        predicate = self.env["ir.access.predicate"].create(
            {
                "name": "base.probe_industry_prefix",
                "template": "[('name', '=like', args.prefix)]",
            }
        )
        self.guard.write(
            {
                "domain": False,
                "reach": "predicate",
                "predicate_id": predicate.id,
                "predicate_args": {"prefix": "a%"},
            }
        )
        self.assertFalse(self.reads(self.banking))
        with calling("ir.access.predicate"):
            predicate.with_user(self.admin).write(
                {"template": "[('name', '!=', args.prefix)]"}
            )
        self.assertAuthorCannotActivate(self.changeset())

    def test_a_widening_through_an_implied_groups_implications_is_counted(self):
        settings_readers = self.env["res.groups"].create(
            {"name": "Probe: settings readers"}
        )
        self.env["ir.access"].create(
            {
                "name": "Probe: settings readers read the parameters",
                "model_id": self.env["ir.model"]._get_id("ir.config_parameter"),
                "group_id": settings_readers.id,
                "kind": "permission",
                "operation": "r",
            }
        )
        relay = self.env["res.groups"].create(
            {
                "name": "Probe: a group that only implies",
                "implied_ids": [Command.link(settings_readers.id)],
            }
        )
        with calling("res.groups"):
            self.readers.with_user(self.admin).implied_ids = [Command.link(relay.id)]
        self.assertAuthorCannotActivate(self.changeset())

    def test_a_guard_on_everyone_counts_who_is_outside_its_group(self):
        self.guard.guard_scope = "everyone"
        self.reader.group_ids = [Command.unlink(self.readers.id)]
        self.assertFalse(self.reads(self.banking))
        self.assertAuthorCannotActivate(self.stage("[('name', '!=', False)]"))
