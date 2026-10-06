from odoo.exceptions import AccessError, UserError
from odoo.service.model import calling
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestChangesetApproval(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.author = new_test_user(
            cls.env, login="author", groups="base.group_erp_manager"
        )
        cls.approver = new_test_user(
            cls.env, login="approver", groups="base.group_erp_manager"
        )
        cls.readers = cls.env["res.groups"].create({"name": "Probe: readers"})
        cls.guard = cls.env["ir.access"].create(
            {
                "name": "Probe: readers read the a-industries",
                "model_id": cls.env["ir.model"]._get_id("res.partner.industry"),
                "group_id": cls.readers.id,
                "kind": "guard",
                "guard_scope": "members",
                "operation": "r",
                "domain": "[('name', '=like', 'a%')]",
            }
        )

    def test_a_change_set_is_activated_once_another_administrator_approves(self):
        with calling("ir.access"):
            self.guard.with_user(self.author).write(
                {"domain": "[('name', '=like', 'b%')]"}
            )
        changeset = self.env["ir.access.changeset"].search(
            [("author_id", "=", self.author.id), ("state", "=", "draft")]
        )
        changeset.with_user(self.author).action_activate()
        self.assertEqual(changeset.state, "draft", "the call asks, it does not run")
        self.assertEqual(self.guard.domain, "[('name', '=like', 'a%')]")
        request = self.env["approval.request"].search(
            [("res_model", "=", changeset._name), ("res_id", "=", changeset.id)]
        )
        self.assertEqual(request.state, "pending")
        with self.assertRaises((AccessError, UserError)):
            request.with_user(self.author).action_approve()
        request.with_user(self.approver).action_approve()
        self.assertEqual(changeset.state, "active")
        self.assertEqual(changeset.activated_by_id, self.author)
        self.assertEqual(self.guard.domain, "[('name', '=like', 'b%')]")

    def stage_and_ask(self, author):
        with calling("ir.access"):
            self.guard.with_user(author).write({"domain": "[('name', '=like', 'b%')]"})
        changeset = self.env["ir.access.changeset"].search(
            [("author_id", "=", author.id), ("state", "=", "draft")]
        )
        changeset.with_user(author).action_activate()
        request = self.env["approval.request"].search(
            [("res_model", "=", changeset._name), ("res_id", "=", changeset.id)]
        )
        return changeset, request

    def test_an_approver_decides_without_administration_and_it_applies(self):
        approver = new_test_user(
            self.env, login="decider", groups="base.group_access_change_approver"
        )
        author = new_test_user(self.env, login="stager", groups="base.group_user")
        eligibility = self.env["res.users.eligibility"].create(
            {
                "user_id": author.id,
                "group_id": self.env.ref("base.group_erp_manager").id,
            }
        )
        eligibility.with_user(author).action_activate(1, "stage a change")
        changeset, request = self.stage_and_ask(author)
        self.assertIn(approver, request.approver_ids.user_id)
        eligibility.with_user(author).action_stop()
        self.assertFalse(author.has_group("base.group_erp_manager"))
        request.with_user(approver).action_approve()
        self.assertEqual(changeset.state, "active")
        self.assertEqual(self.guard.domain, "[('name', '=like', 'b%')]")

    def test_the_author_never_approves_their_own_even_elevated(self):
        author = new_test_user(self.env, login="elevated", groups="base.group_user")
        eligibility = self.env["res.users.eligibility"].create(
            {
                "user_id": author.id,
                "group_id": self.env.ref("base.group_erp_manager").id,
            }
        )
        eligibility.with_user(author).action_activate(2, "stage a change")
        changeset, request = self.stage_and_ask(author)
        with self.assertRaises((AccessError, UserError)):
            request.with_user(author).action_approve()
        self.assertEqual(changeset.state, "draft")

    def test_nobody_activates_an_unapproved_or_refused_change_set(self):
        changeset, request = self.stage_and_ask(self.author)
        changeset.with_user(self.author).action_activate()
        changeset.with_user(self.approver).action_activate()
        self.assertEqual(changeset.state, "draft", "unapproved, for anyone")
        self.assertEqual(self.guard.domain, "[('name', '=like', 'a%')]")
        request.with_user(self.approver).with_context(skip_wizard=True).action_refuse()
        self.assertEqual(request.state, "refused")
        changeset.with_user(self.author).action_activate()
        changeset.with_user(self.approver).action_activate()
        self.assertEqual(changeset.state, "draft", "refused, for anyone")
        self.assertEqual(self.guard.domain, "[('name', '=like', 'a%')]")

    def test_a_stale_change_set_is_not_applied_even_approved(self):
        changeset, request = self.stage_and_ask(self.author)
        self.guard.write({"domain": "[('name', '=like', 'c%')]"})
        request.with_user(self.approver).action_approve()
        self.assertEqual(request.state, "approved")
        self.assertEqual(changeset.state, "draft", "approved, but stale: not run")
        with self.assertRaises(UserError):
            changeset.with_user(self.author).action_activate()
        self.assertEqual(self.guard.domain, "[('name', '=like', 'c%')]")

    def test_a_withdrawn_approval_no_longer_opens_the_change_set(self):
        binding = self.env.ref(
            "approval_access_changeset.obligation_access_changeset_activate"
        )
        binding.run_on_approval = False
        changeset, request = self.stage_and_ask(self.author)
        request.with_user(self.approver).action_approve()
        self.assertEqual(request.state, "approved")
        self.assertEqual(changeset.state, "draft", "approval only clears the gate")
        request.with_user(self.approver).action_withdraw()
        self.assertNotEqual(request.state, "approved")
        changeset.with_user(self.author).action_activate()
        self.assertEqual(changeset.state, "draft")
        self.assertEqual(self.guard.domain, "[('name', '=like', 'a%')]")
