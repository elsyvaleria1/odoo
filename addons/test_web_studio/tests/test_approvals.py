from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests.common import HttpCase, TransactionCase, tagged

from odoo.addons.web_studio.tests.test_ui import setup_view_editor_data


class TestStudioApprovalsCommon(TransactionCase):
    MODEL = "test.studio.model_action"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin_user = cls.env.ref("base.user_admin")
        cls.admin_user.write({"email": "mitchell.admin@example.com"})
        cls.demo_user = cls.env["res.users"].search([("login", "=", "demo")], limit=1)
        if not cls.demo_user:
            cls.demo_user = cls.env["res.users"].create(
                {
                    "login": "demo",
                    "name": "demo",
                    "email": "demo@demo",
                    "group_ids": [Command.link(cls.env.ref("base.group_user").id)],
                }
            )
        cls.other_user = cls.env["res.users"].create(
            {
                "name": "test",
                "login": "test",
                "email": "test@test.test",
                "group_ids": [Command.link(cls.env.ref("base.group_user").id)],
            }
        )
        cls.test_user_2 = cls.env["res.users"].create(
            {
                "name": "test_2",
                "login": "test_2",
                "email": "test_2@test_2.test_2",
                "group_ids": [Command.link(cls.env.ref("base.group_user").id)],
            }
        )
        cls.group_user = cls.env.ref("base.group_user")
        cls.Binding = cls.env["approval.binding"]

    def setUp(self):
        super().setUp()
        self.addCleanup(self.Binding._unregister_hook)

    def _step(
        self,
        method,
        name,
        *,
        model=MODEL,
        group=None,
        approvers=(),
        notify=(),
        exclusive=False,
        sequence=1,
        domain=False,
    ):
        step = self.env["approval.category.step"].browse(
            self.Binding.create_step_for_button(model, method, False)
        )
        step.write(
            {
                "name": name,
                "group_id": group.id if group else False,
                "user_ids": [Command.set([user.id for user in approvers])],
                "notify_user_ids": [Command.set([user.id for user in notify])],
                "exclusive": exclusive,
                "sequence": sequence,
                "subject_domain": domain,
            }
        )
        return step

    def _request(self, record, method):
        return self.env["approval.request"].search(
            [
                ("res_model", "=", record._name),
                ("res_id", "=", record.id),
                ("binding_id.method", "=", method),
            ],
            order="id desc",
            limit=1,
        )

    def _spec(self, record, method):
        return self.Binding.get_button_approvals(
            [
                {
                    "model": record._name,
                    "res_id": record.id,
                    "method": method,
                    "action_id": False,
                }
            ]
        )[0]

    def _decided(self, record, method):
        users = self.env["res.users"]
        return {
            step["name"]: set(
                users.browse(
                    [
                        decision["user_id"]
                        for decision in step["decisions"]
                        if decision["state"] == "approved"
                    ]
                ).mapped("login")
            )
            for step in self._spec(record, method)["steps"]
        }

    def _asked(self, record, method):
        activity_type = self.env.ref("approval.mail_activity_data_approval")
        return set(
            self._request(record, method)
            .activity_ids.filtered(lambda a: a.activity_type_id == activity_type)
            .user_id.mapped("login")
        )

    def _notes_to(self, record, method, user):
        return self._request(record, method).message_ids.filtered(
            lambda message: user.partner_id in message.partner_ids
        )

    def _click(self, login, record, method):
        with self.with_user(login):
            getattr(self.env[record._name].browse(record.id), method)()

    def _decide(self, login, record, method, step, approve=True):
        with self.with_user(login):
            self.env["approval.binding"].action_decide_approval(
                record._name, record.id, method, False, approve, step.id
            )


@tagged("-at_install", "post_install")
class TestStudioApprovals(TestStudioApprovalsCommon):
    def test_approval_method_two_models(self):
        rule_vals = {
            "group": self.group_user,
            "approvers": [self.admin_user],
            "exclusive": True,
        }
        rule_1 = self._step(
            "action_confirm", "Rule 1", notify=[self.admin_user], **rule_vals
        )
        rule_2 = self._step(
            "action_confirm", "Rule 2", notify=[self.admin_user], **rule_vals
        )
        rule_3 = self._step(
            "action_confirm",
            "Rule 3",
            notify=[self.other_user],
            sequence=2,
            **rule_vals,
        )
        self._step(
            "action_confirm",
            "Rule 4",
            model="test.studio.model_action2",
            notify=[self.admin_user],
            **rule_vals,
        )
        record = self.env[self.MODEL].create({"name": "test"})

        self._click("demo", record, "action_confirm")
        self.assertFalse(record.confirmed)
        self.assertEqual(
            self._decided(record, "action_confirm"),
            {"Rule 1": {"demo"}, "Rule 2": set(), "Rule 3": set()},
        )
        note = self._notes_to(record, "action_confirm", self.admin_user)
        self.assertEqual(len(note), 1)
        self.assertIn("Rule 1", note.body)
        self.assertEqual(note.author_id, self.demo_user.partner_id)
        self.assertEqual(self._asked(record, "action_confirm"), {"admin"})

        self._click("admin", record, "action_confirm")
        self.assertFalse(record.confirmed)
        self.assertEqual(
            self._decided(record, "action_confirm"),
            {"Rule 1": {"demo"}, "Rule 2": {"admin"}, "Rule 3": set()},
        )
        self.assertEqual(
            self._asked(record, "action_confirm"),
            set(),
            "Studio still asked the admin for Rule 3, which exclusivity bars them from",
        )

        self._click("test", record, "action_confirm")
        self.assertTrue(record.confirmed)
        self.assertEqual(
            self._decided(record, "action_confirm"),
            {"Rule 1": {"demo"}, "Rule 2": {"admin"}, "Rule 3": {"test"}},
        )
        self.assertIn(
            "Rule 3", self._notes_to(record, "action_confirm", self.other_user).body
        )
        self.assertEqual(self._asked(record, "action_confirm"), set())
        self.assertEqual(
            self._request(record, "action_confirm").approver_ids.step_ids,
            rule_1 | rule_2 | rule_3,
            "Rule 4 gates the other model only",
        )

    def test_notify_higher_notification_order(self):
        common = {"group": self.group_user, "approvers": [self.admin_user]}
        self._step(
            "action_step",
            "rule 1",
            domain="[('step', '<', 1)]",
            notify=[self.admin_user],
            **common,
        )
        rule_2 = self._step(
            "action_step",
            "rule 2",
            sequence=2,
            exclusive=True,
            notify=[self.other_user],
            **common,
        )
        self._step(
            "action_step",
            "rule 2 - bis",
            domain="[('step', '>=', 1)]",
            sequence=2,
            notify=[self.other_user],
            **common,
        )
        self._step(
            "action_step",
            "rule 3",
            model="test.studio.model_action2",
            notify=[self.admin_user],
            **common,
        )
        record = self.env[self.MODEL].create({"name": "test"})

        self._click("demo", record, "action_step")
        self.assertEqual(record.step, 0)
        self.assertEqual(
            self._decided(record, "action_step"), {"rule 1": {"demo"}, "rule 2": set()}
        )
        self.assertIn(
            "rule 1", self._notes_to(record, "action_step", self.admin_user).body
        )
        self.assertEqual(self._asked(record, "action_step"), {"admin"})

        self._decide("admin", record, "action_step", rule_2)
        self.assertEqual(record.step, 0, "deciding runs nothing")
        self.assertEqual(
            self._decided(record, "action_step"),
            {"rule 1": {"demo"}, "rule 2": {"admin"}},
        )
        note = self._notes_to(record, "action_step", self.other_user)
        self.assertIn("rule 2", note.body)
        self.assertNotIn("rule 2 - bis", note.body)
        self.assertEqual(self._asked(record, "action_step"), set())

    def test_entries_approved_by_other_read_by_regular_user(self):
        common = {"group": self.group_user, "exclusive": True}
        for name, sequence, approver in (
            ("R0", 1, self.admin_user),
            ("R1", 2, self.admin_user),
            ("R2", 2, self.admin_user),
            ("R3", 3, self.test_user_2),
        ):
            self._step(
                "action_step", name, sequence=sequence, approvers=[approver], **common
            )
        record = self.env[self.MODEL].create({"name": "test"})

        self._click("admin", record, "action_step")
        self.assertEqual(record.step, 0)
        self.assertEqual(self._decided(record, "action_step")["R0"], {"admin"})
        self.assertEqual(
            self._asked(record, "action_step"),
            set(),
            "the admin, the only one listed for R1 and R2, may not decide them now",
        )

        self._click("test", record, "action_step")
        self.assertEqual(record.step, 0)
        self.assertEqual(self._decided(record, "action_step")["R1"], {"test"})

        self._click("demo", record, "action_step")
        self.assertEqual(record.step, 0)
        self.assertEqual(self._decided(record, "action_step")["R2"], {"demo"})
        self.assertEqual(self._asked(record, "action_step"), {"test_2"})

        self._click("test_2", record, "action_step")
        self.assertEqual(record.step, 1)
        self.assertEqual(
            self._decided(record, "action_step"),
            {"R0": {"admin"}, "R1": {"test"}, "R2": {"demo"}, "R3": {"test_2"}},
        )
        self.assertEqual(self._asked(record, "action_step"), set())

    def test_no_responsible(self):
        self._step(
            "action_step",
            "R0",
            group=self.env.ref("base.group_system"),
            notify=[self.demo_user, self.other_user],
        )
        record = self.env[self.MODEL].create({"name": "test"})
        self._click("test_2", record, "action_step")
        self.assertEqual(record.step, 0)
        self.assertEqual(self._request(record, "action_step").state, "pending")
        self.assertEqual(self._asked(record, "action_step"), set())
        self.assertFalse(self._notes_to(record, "action_step", self.demo_user))

    def test_rule_notify_domain(self):
        common = {
            "group": self.group_user,
            "approvers": [self.admin_user],
            "exclusive": True,
        }
        record = self.env[self.MODEL].create({"name": "test 2"})
        self._step(
            "action_confirm",
            "ruledomain",
            domain="[('name', '=', 'test')]",
            notify=[self.admin_user],
            **common,
        )
        self._step("action_confirm", "rule 2", notify=[self.admin_user], **common)
        self._step(
            "action_confirm", "rule3", sequence=2, notify=[self.other_user], **common
        )
        self._click("demo", record, "action_confirm")
        self.assertFalse(record.confirmed)
        self.assertEqual(
            self._decided(record, "action_confirm"),
            {"rule 2": {"demo"}, "rule3": set()},
            "a rule whose condition the record fails is no step of it",
        )
        self.assertEqual(self._asked(record, "action_confirm"), {"admin"})

    def test_rule_notify_higher_order_domain(self):
        record = self.env[self.MODEL].create({"name": "test 2"})
        common = {"group": self.group_user, "notify": [self.admin_user]}
        rule_1 = self._step(
            "action_confirm", "rule 1", approvers=[self.admin_user], **common
        )
        self._step(
            "action_confirm",
            "rule 1 - bis",
            domain="[('name', '=', 'test')]",
            approvers=[self.admin_user],
            **common,
        )
        self._step(
            "action_confirm",
            "rule 2",
            domain="[('name', '=', 'test')]",
            sequence=2,
            approvers=[self.admin_user],
            **common,
        )
        self._step(
            "action_confirm",
            "rule3",
            sequence=2,
            group=self.group_user,
            approvers=[self.other_user],
            notify=[self.other_user],
        )
        self._decide("demo", record, "action_confirm", rule_1)
        self.assertFalse(record.confirmed)
        self.assertEqual(
            self._decided(record, "action_confirm"),
            {"rule 1": {"demo"}, "rule3": set()},
            "a decision under rule 1 is not also one under rule3",
        )
        self.assertIn(
            "rule 1", self._notes_to(record, "action_confirm", self.admin_user).body
        )
        self.assertEqual(self._asked(record, "action_confirm"), {"test"})

    def _three_rules(self):
        common = {
            "group": self.group_user,
            "approvers": [self.admin_user],
            "notify": [self.admin_user],
        }
        return (
            self._step("action_confirm", "rule 1", **common),
            self._step("action_confirm", "rule 1 - bis", **common),
            self._step("action_confirm", "rule 2", sequence=2, **common),
        )

    def test_notify_higher_1(self):
        record = self.env[self.MODEL].create({"name": "test 2"})
        rule_1, rule_1_bis, _rule_2 = self._three_rules()
        self._decide("demo", record, "action_confirm", rule_1)
        self.assertEqual(
            self._decided(record, "action_confirm"),
            {"rule 1": {"demo"}, "rule 1 - bis": set(), "rule 2": set()},
        )
        self.assertEqual(
            self._asked(record, "action_confirm"),
            {"admin"},
            "rule 1 - bis is still open, and the admin is listed for it",
        )
        self._decide("demo", record, "action_confirm", rule_1_bis)
        self.assertEqual(
            self._decided(record, "action_confirm"),
            {"rule 1": {"demo"}, "rule 1 - bis": {"demo"}, "rule 2": set()},
        )
        self.assertEqual(self._asked(record, "action_confirm"), {"admin"})

    def test_notify_higher_2(self):
        record = self.env[self.MODEL].create({"name": "test 2"})
        rule_1, rule_1_bis, _rule_2 = self._three_rules()
        self._decide("demo", record, "action_confirm", rule_1, approve=False)
        self.assertEqual(self._request(record, "action_confirm").state, "refused")
        self.assertEqual(self._asked(record, "action_confirm"), set())
        with self.assertRaises(UserError, msg="a refusal stands until it is reopened"):
            self._decide("demo", record, "action_confirm", rule_1_bis)
        self.assertEqual(self._asked(record, "action_confirm"), set())

    def test_notify_higher_3(self):
        record = self.env[self.MODEL].create({"name": "test 2"})
        rule_1, rule_1_bis, _rule_2 = self._three_rules()
        self._decide("demo", record, "action_confirm", rule_1)
        self._decide("demo", record, "action_confirm", rule_1_bis, approve=False)
        request = self._request(record, "action_confirm")
        self.assertEqual(request.state, "refused")
        row = request.approver_ids.filtered(lambda a: a.user_id == self.demo_user)
        self.assertEqual(row.decided_step_ids, rule_1_bis)
        self.assertEqual(self._asked(record, "action_confirm"), set())

    def test_can_revoke_approval_with_inferior_order(self):
        rule_0 = self._step("action_step", "R0", approvers=[self.other_user])
        self._step("action_step", "R1", approvers=[self.demo_user])
        self._step("action_step", "R2", sequence=2, approvers=[self.test_user_2])
        record = self.env[self.MODEL].create({"name": "test"})
        self._decide("test", record, "action_step", rule_0)
        [decision] = self._spec(record, "action_step")["steps"][0]["decisions"]

        def withdraw(user):
            return self.Binding.with_user(user).action_withdraw_decision(
                self.MODEL,
                record.id,
                "action_step",
                False,
                decision["approver_id"],
                rule_0.id,
            )

        with self.assertRaises(AccessError, msg="a member of the same order may not"):
            withdraw(self.demo_user)
        withdraw(self.test_user_2)
        self.assertEqual(self._decided(record, "action_step")["R0"], set())

    def test_create_automation(self):
        rule_1 = self._step("action_step", "rule 1", approvers=[self.admin_user])
        self._step("action_step", "rule 1 - bis", approvers=[self.admin_user])
        binding = self.Binding.search([("category_id", "=", rule_1.category_id.id)])
        binding.reset_domain = "[('confirmed', '=', False)]"
        automation = binding.reset_automation_id
        self.assertTrue(automation)
        self._step("action_step", "rule recreate", approvers=[self.admin_user])
        self.assertEqual(
            binding.reset_automation_id, automation, "a new step reuses the rule"
        )

        record = self.env[self.MODEL].create({"name": "test 2"})
        self._decide("admin", record, "action_step", rule_1)
        self.assertEqual(self._decided(record, "action_step")["rule 1"], {"admin"})

        record.action_confirm()
        self.assertEqual(self._decided(record, "action_step")["rule 1"], {"admin"})

        record.confirmed = False
        self.assertEqual(self._request(record, "action_step").state, "new")
        self.assertEqual(self._decided(record, "action_step")["rule 1"], set())


@tagged("-at_install", "post_install")
class TestStudioApprovalsUIUnit(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        setup_view_editor_data(cls)
        cls.testAction.res_model = "test.studio.model_action"
        cls.testView.model = "test.studio.model_action"
        cls.testView.arch = """
            <form>
                <button name="action_confirm" type="object" class="mybutton"/>
            </form>
        """
        cls.admin_user = cls.env.ref("base.user_admin")

    def _step(self):
        Binding = self.env["approval.binding"]
        self.addCleanup(Binding._unregister_hook)
        step = self.env["approval.category.step"].browse(
            Binding.create_step_for_button(
                "test.studio.model_action", "action_confirm", False
            )
        )
        step.write(
            {
                "group_id": self.env.ref("base.group_user").id,
                "user_ids": [Command.set(self.admin_user.ids)],
                "notify_user_ids": [Command.set(self.admin_user.ids)],
            }
        )
        return step

    def _url(self):
        return (
            f"/odoo/action-{self.testAction.id}/studio?mode=editor&_view_type=form"
            f"&_tab=views&menu_id={self.testMenu.id}"
        )

    def test_disable_approvals(self):
        step = self._step()
        self.start_tour(
            self._url(), "test_web_studio.test_disable_approvals", login="admin"
        )
        self.assertFalse(step.active)

    def test_disable_approvals_via_kanban(self):
        step = self._step()
        self.start_tour(
            self._url(),
            "test_web_studio.test_disable_approvals_via_kanban",
            login="admin",
        )
        self.assertFalse(step.active)
